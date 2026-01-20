#!/usr/bin/env python3
"""
多來源商品追蹤系統主程式

支援多個來源（Amazon US、Mercari JP）的商品追蹤，
根據設定檔選擇對應的爬蟲，並整合排程檢查功能。
"""
import argparse
import traceback
from typing import Dict, List, Optional, Tuple
from dotenv import load_dotenv

from core.config import (
    load_source_config,
    load_all_configs,
    SourceConfig,
    get_scraper_for_source,
    get_max_threshold,
)
from core.scheduler import is_due_for_scraping, record_run_time
from core.storage import ProductStorage
from core.notifier import TelegramNotifier

# 載入 .env 檔案
load_dotenv()


def filter_products_by_threshold(
    products: List[Dict],
    max_threshold: Optional[float],
    source: str
) -> List[Dict]:
    """
    根據價格門檻過濾商品
    
    Args:
        products: 商品列表
        max_threshold: 價格上限
        source: 來源名稱
    
    Returns:
        過濾後的商品列表
    """
    if max_threshold is None:
        return products
    
    price_field = "price_usd" if source == "amazon_us" else "price_twd"
    
    return [
        p for p in products
        if p.get(price_field, 0) > 0 and p.get(price_field, 0) <= max_threshold
    ]


def filter_price_dropped_by_threshold(
    price_dropped: List[Dict],
    max_threshold: Optional[float],
    source: str
) -> List[Dict]:
    """
    根據價格門檻過濾降價商品
    
    Args:
        price_dropped: 降價商品列表
        max_threshold: 價格上限
        source: 來源名稱
    
    Returns:
        過濾後的降價商品列表
    """
    if max_threshold is None:
        return price_dropped
    
    price_field = "price_usd" if source == "amazon_us" else "price_twd"
    
    return [
        item for item in price_dropped
        if item["product"].get(price_field, 0) > 0 
        and item["product"].get(price_field, 0) <= max_threshold
    ]


def process_source(
    config: SourceConfig,
    storage: ProductStorage,
    headless: bool = True,
    force: bool = False
) -> Tuple[List[Tuple[Dict, Optional[float]]], List[Tuple[Dict, Optional[float]]]]:
    """
    處理單一來源的爬取
    
    Args:
        config: 來源設定
        storage: 儲存服務
        headless: 是否以無頭模式運行
        force: 是否強制執行（忽略排程）
    
    Returns:
        (新商品列表, 降價商品列表)，每個元素為 (商品/降價資訊, max_threshold) 元組
    """
    source = config.source
    
    # 檢查排程
    if not force and not is_due_for_scraping(source, config.schedule_interval_hours):
        print(f"[{source}] Not due for scraping yet, skipping...")
        return [], []
    
    print(f"\n{'='*60}")
    print(f"Processing source: {source}")
    print(f"Schedule interval: {config.schedule_interval_hours} hours")
    print(f"Tracking mode: {config.price_tracking_mode}")
    print(f"{'='*60}\n")
    
    # 取得爬蟲
    scraper = get_scraper_for_source(source, headless=headless)
    
    all_new_products = []
    all_price_dropped = []
    
    # 處理每個追蹤 URL
    for url_config in config.tracking_urls:
        name = url_config.name
        url = url_config.url
        max_threshold = get_max_threshold(url_config, source)
        
        if not url:
            print(f"Skipping {name}: No URL provided")
            continue
        
        print(f"\n--- {name} ---")
        print(f"URL: {url}")
        if max_threshold is not None:
            threshold_label = "max_usd" if source == "amazon_us" else "max_ntd"
            print(f"{threshold_label}: {max_threshold}")
        
        try:
            # 爬取商品
            current_products = scraper.scrape(url)
            print(f"Scraped {len(current_products)} products")
            
            # 比較並更新
            result = storage.compare_products(
                current_products, 
                source, 
                config.price_tracking_mode
            )
            new_products = result["new"]
            price_dropped = result["price_dropped"]
            
            # 過濾符合門檻的商品
            if max_threshold is not None:
                filtered_new = filter_products_by_threshold(new_products, max_threshold, source)
                filtered_dropped = filter_price_dropped_by_threshold(price_dropped, max_threshold, source)
                print(f"New products (total: {len(new_products)}, within budget: {len(filtered_new)})")
                print(f"Price dropped (total: {len(price_dropped)}, within budget: {len(filtered_dropped)})")
                new_products = filtered_new
                price_dropped = filtered_dropped
            else:
                print(f"New products: {len(new_products)}")
                print(f"Price dropped: {len(price_dropped)}")
            
            # 收集通知（包含 max_threshold 資訊）
            for product in new_products:
                all_new_products.append((product, max_threshold))
            for item in price_dropped:
                all_price_dropped.append((item, max_threshold))
                
        except Exception as e:
            print(f"Error processing {name}: {e}")
            traceback.print_exc()
            continue
    
    # 記錄執行時間
    record_run_time(source)
    
    return all_new_products, all_price_dropped


def send_notifications(
    new_products: List[Tuple[Dict, Optional[float]]],
    price_dropped: List[Tuple[Dict, Optional[float]]],
    source: str,
    notifier: TelegramNotifier
) -> Tuple[int, int]:
    """
    發送通知
    
    Args:
        new_products: 新商品列表（含 max_threshold）
        price_dropped: 降價商品列表（含 max_threshold）
        source: 來源名稱
        notifier: 通知服務
    
    Returns:
        (成功數, 總數)
    """
    success_count = 0
    total_count = len(new_products) + len(price_dropped)
    
    for product, max_threshold in new_products:
        # 檢查是否在預算內
        is_within_budget = False
        if max_threshold is not None:
            price_field = "price_usd" if source == "amazon_us" else "price_twd"
            price = product.get(price_field, 0)
            is_within_budget = price > 0 and price <= max_threshold
        
        if notifier.notify_new_product(product, source=source, is_within_budget=is_within_budget):
            success_count += 1
    
    for item, max_threshold in price_dropped:
        product = item["product"]
        
        if source == "amazon_us":
            old_price = item.get("old_price_usd", 0)
            old_price_twd = None
        else:
            old_price = item.get("old_price_jpy", 0)
            old_price_twd = item.get("old_price_twd")
        
        if notifier.notify_price_drop(
            product,
            old_price,
            source=source,
            old_price_twd=old_price_twd,
            max_threshold=max_threshold
        ):
            success_count += 1
    
    return success_count, total_count


def main():
    """主程式"""
    parser = argparse.ArgumentParser(description="多來源商品追蹤系統")
    parser.add_argument(
        "--source", "-s",
        type=str,
        choices=["amazon_us", "mercari_jp", "all"],
        default="all",
        help="指定要執行的來源（預設: all）"
    )
    parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="強制執行，忽略排程檢查"
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="以有頭模式運行瀏覽器（用於除錯）"
    )
    args = parser.parse_args()
    
    headless = not args.headed
    
    # 載入設定
    if args.source == "all":
        configs = load_all_configs()
    else:
        configs = {args.source: load_source_config(args.source)}
    
    # 初始化共用元件
    storage = ProductStorage()
    
    try:
        notifier = TelegramNotifier()
    except ValueError as e:
        print(f"Warning: Telegram notifier not configured: {e}")
        notifier = None
    
    # 收集所有來源的通知
    all_notifications: Dict[str, Tuple[List, List]] = {}
    
    # 處理每個來源
    for source, config in configs.items():
        if not config.tracking_urls:
            print(f"[{source}] No tracking URLs configured, skipping...")
            continue
        
        new_products, price_dropped = process_source(
            config, 
            storage, 
            headless=headless,
            force=args.force
        )
        
        if new_products or price_dropped:
            all_notifications[source] = (new_products, price_dropped)
    
    # 發送通知
    if all_notifications and notifier:
        print(f"\n{'='*60}")
        print("Sending notifications...")
        print(f"{'='*60}\n")
        
        total_success = 0
        total_count = 0
        
        for source, (new_products, price_dropped) in all_notifications.items():
            success, count = send_notifications(new_products, price_dropped, source, notifier)
            total_success += success
            total_count += count
            print(f"[{source}] Notifications sent: {success}/{count}")
        
        print(f"\nTotal notifications sent: {total_success}/{total_count}")
    elif not all_notifications:
        print("\nNo new products or price changes to notify")
    else:
        print("\nNotifications skipped (notifier not configured)")
    
    print("\nDone!")


if __name__ == "__main__":
    main()
