#!/usr/bin/env python3
"""
單一來源執行腳本

支援命令列參數指定來源，用於排程系統或手動執行單一來源的爬取。
"""
import argparse
import sys
import traceback
from typing import Optional
from dotenv import load_dotenv

from core.config import load_source_config, SOURCE_TO_CONFIG_FILE
from core.scheduler import is_due_for_scraping, record_run_time, get_last_run_time, get_next_run_time
from core.storage import ProductStorage
from core.notifier import TelegramNotifier

# 載入 .env 檔案
load_dotenv()


def get_scraper_for_source(source: str, headless: bool = True):
    """
    根據來源名稱取得對應的爬蟲實例
    
    Args:
        source: 來源名稱 (amazon_us, mercari_jp)
        headless: 是否以無頭模式運行瀏覽器
    
    Returns:
        對應的爬蟲實例
    """
    if source == "amazon_us":
        from scrapers.amazon.scraper import AmazonScraper
        return AmazonScraper(headless=headless)
    elif source == "mercari_jp":
        from scrapers.mercari.scraper import MercariScraper
        return MercariScraper(headless=headless, fetch_product_names=True)
    else:
        raise ValueError(f"Unknown source: {source}")


def get_max_threshold(url_config, source: str) -> Optional[float]:
    """取得價格上限門檻"""
    if source == "amazon_us":
        return url_config.max_usd
    else:
        return url_config.max_ntd


def run_source(
    source: str,
    force: bool = False,
    headless: bool = True,
    dry_run: bool = False
) -> bool:
    """
    執行單一來源的爬取
    
    Args:
        source: 來源名稱 (amazon_us, mercari_jp)
        force: 是否強制執行（忽略排程）
        headless: 是否以無頭模式運行
        dry_run: 是否為測試模式（不發送通知）
    
    Returns:
        是否成功執行
    """
    # 載入設定
    try:
        config = load_source_config(source)
    except (ValueError, FileNotFoundError) as e:
        print(f"Error loading config for {source}: {e}")
        return False
    
    # 檢查是否有追蹤 URL
    if not config.tracking_urls:
        print(f"[{source}] No tracking URLs configured")
        return False
    
    # 檢查排程
    if not force:
        if not is_due_for_scraping(source, config.schedule_interval_hours):
            last_run = get_last_run_time(source)
            next_run = get_next_run_time(source, config.schedule_interval_hours)
            print(f"[{source}] Not due for scraping yet")
            if last_run:
                print(f"  Last run: {last_run.strftime('%Y-%m-%d %H:%M:%S')}")
            if next_run:
                print(f"  Next run: {next_run.strftime('%Y-%m-%d %H:%M:%S')}")
            return True  # 不是錯誤，只是還沒到時間
    
    print(f"\n{'='*60}")
    print(f"Running source: {source}")
    print(f"Schedule interval: {config.schedule_interval_hours} hours")
    print(f"Tracking mode: {config.price_tracking_mode}")
    print(f"Tracking URLs: {len(config.tracking_urls)}")
    if dry_run:
        print("Mode: DRY RUN (no notifications)")
    print(f"{'='*60}\n")
    
    # 初始化元件
    storage = ProductStorage()
    scraper = get_scraper_for_source(source, headless=headless)
    
    notifier = None
    if not dry_run:
        try:
            notifier = TelegramNotifier()
        except ValueError as e:
            print(f"Warning: Telegram notifier not configured: {e}")
    
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
                price_field = "price_usd" if source == "amazon_us" else "price_twd"
                
                filtered_new = [
                    p for p in new_products
                    if p.get(price_field, 0) > 0 and p.get(price_field, 0) <= max_threshold
                ]
                filtered_dropped = [
                    item for item in price_dropped
                    if item["product"].get(price_field, 0) > 0
                    and item["product"].get(price_field, 0) <= max_threshold
                ]
                
                print(f"New products (total: {len(new_products)}, within budget: {len(filtered_new)})")
                print(f"Price dropped (total: {len(price_dropped)}, within budget: {len(filtered_dropped)})")
                
                new_products = filtered_new
                price_dropped = filtered_dropped
            else:
                print(f"New products: {len(new_products)}")
                print(f"Price dropped: {len(price_dropped)}")
            
            # 收集通知
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
    
    # 發送通知
    if (all_new_products or all_price_dropped) and notifier:
        print(f"\n{'='*60}")
        print("Sending notifications...")
        print(f"{'='*60}\n")
        
        success_count = 0
        total_count = len(all_new_products) + len(all_price_dropped)
        
        for product, max_threshold in all_new_products:
            is_within_budget = False
            if max_threshold is not None:
                price_field = "price_usd" if source == "amazon_us" else "price_twd"
                price = product.get(price_field, 0)
                is_within_budget = price > 0 and price <= max_threshold
            
            if notifier.notify_new_product(product, source=source, is_within_budget=is_within_budget):
                success_count += 1
        
        for item, max_threshold in all_price_dropped:
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
        
        print(f"Notifications sent: {success_count}/{total_count}")
    elif all_new_products or all_price_dropped:
        print(f"\nFound {len(all_new_products)} new products and {len(all_price_dropped)} price drops")
        if dry_run:
            print("(Notifications skipped in dry-run mode)")
        else:
            print("(Notifications skipped - notifier not configured)")
    else:
        print("\nNo new products or price changes to notify")
    
    print("\nDone!")
    return True


def show_status(source: str):
    """顯示來源的排程狀態"""
    try:
        config = load_source_config(source)
    except (ValueError, FileNotFoundError) as e:
        print(f"Error loading config for {source}: {e}")
        return
    
    print(f"\n=== {source} Status ===")
    print(f"Schedule interval: {config.schedule_interval_hours} hours")
    print(f"Tracking mode: {config.price_tracking_mode}")
    print(f"Tracking URLs: {len(config.tracking_urls)}")
    
    last_run = get_last_run_time(source)
    if last_run:
        print(f"Last run: {last_run.strftime('%Y-%m-%d %H:%M:%S')}")
    else:
        print("Last run: Never")
    
    next_run = get_next_run_time(source, config.schedule_interval_hours)
    if next_run:
        print(f"Next run: {next_run.strftime('%Y-%m-%d %H:%M:%S')}")
    
    is_due = is_due_for_scraping(source, config.schedule_interval_hours)
    print(f"Due for scraping: {'Yes' if is_due else 'No'}")


def main():
    """主程式"""
    parser = argparse.ArgumentParser(
        description="單一來源商品追蹤執行腳本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例:
  %(prog)s amazon_us              # 執行 Amazon US 爬取（遵循排程）
  %(prog)s mercari_jp --force     # 強制執行 Mercari JP 爬取
  %(prog)s amazon_us --dry-run    # 測試模式（不發送通知）
  %(prog)s amazon_us --status     # 顯示排程狀態
  %(prog)s --list                 # 列出所有可用來源
        """
    )
    
    parser.add_argument(
        "source",
        type=str,
        nargs="?",
        choices=list(SOURCE_TO_CONFIG_FILE.keys()),
        help="要執行的來源名稱"
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
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="測試模式，不發送通知"
    )
    parser.add_argument(
        "--status", "-s",
        action="store_true",
        help="顯示來源的排程狀態"
    )
    parser.add_argument(
        "--list", "-l",
        action="store_true",
        help="列出所有可用來源"
    )
    
    args = parser.parse_args()
    
    # 列出所有來源
    if args.list:
        print("Available sources:")
        for source in SOURCE_TO_CONFIG_FILE.keys():
            print(f"  - {source}")
        return 0
    
    # 檢查是否指定來源
    if not args.source:
        parser.print_help()
        return 1
    
    # 顯示狀態
    if args.status:
        show_status(args.source)
        return 0
    
    # 執行爬取
    headless = not args.headed
    success = run_source(
        args.source,
        force=args.force,
        headless=headless,
        dry_run=args.dry_run
    )
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
