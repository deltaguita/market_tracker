#!/usr/bin/env python3
"""
Mercari 商品追蹤系統主程式
"""
import json
from dotenv import load_dotenv

from src.scraper import MercariScraper
from src.storage import ProductStorage
from src.notifier import TelegramNotifier

# 載入 .env 檔案
load_dotenv()


def load_config(config_path: str = "config/urls.json") -> dict:
    """載入追蹤網址配置"""
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    """主程式"""
    # 載入配置
    config = load_config()
    tracking_urls = config.get("tracking_urls", [])

    if not tracking_urls:
        print("No tracking URLs configured")
        return

    # 初始化元件
    # fetch_product_names=True 會訪問商品詳情頁獲取名稱（較慢但準確）
    # fetch_product_names=False 只使用搜尋結果頁的資訊（較快但可能沒有名稱）
    scraper = MercariScraper(headless=True, fetch_product_names=True)
    storage = ProductStorage()
    notifier = TelegramNotifier()

    all_new_products = []
    all_price_dropped = []

    # 處理每個追蹤網址
    for url_config in tracking_urls:
        name = url_config.get("name", "Unknown")
        url = url_config.get("url")
        max_ntd = url_config.get("max_ntd")  # 可選的台幣價格門檻

        if not url:
            print(f"Skipping {name}: No URL provided")
            continue

        if max_ntd is not None:
            print(f"Max NTD threshold: {max_ntd}")

        print(f"\n{'='*60}")
        print(f"Processing: {name}")
        print(f"URL: {url}")
        print(f"{'='*60}\n")

        try:
            # 爬取商品
            current_products = scraper.scrape(url)
            print(f"Scraped {len(current_products)} products")

            # 比較並更新
            result = storage.compare_products(current_products)
            new_products = result["new"]
            price_dropped = result["price_dropped"]

            # 如果有設定 max_ntd，過濾符合門檻的商品
            if max_ntd is not None:
                # 過濾新商品：只保留台幣價格 <= max_ntd 的商品
                filtered_new_products = [
                    p for p in new_products
                    if p.get("price_twd", 0) > 0 and p.get("price_twd", 0) <= max_ntd
                ]
                print(f"New products (total: {len(new_products)}, within budget: {len(filtered_new_products)})")

                # 過濾降價商品：只保留台幣價格 <= max_ntd 的商品
                filtered_price_dropped = [
                    item for item in price_dropped
                    if item["product"].get("price_twd", 0) > 0
                    and item["product"].get("price_twd", 0) <= max_ntd
                ]
                print(f"Price dropped (total: {len(price_dropped)}, within budget: {len(filtered_price_dropped)})")

                new_products = filtered_new_products
                price_dropped = filtered_price_dropped
            else:
                print(f"New products: {len(new_products)}")
                print(f"Price dropped: {len(price_dropped)}")

            # 收集通知（需要保存 max_ntd 資訊以便後續通知使用）
            # 為每個商品添加 max_ntd 資訊（使用元組包裝）
            for product in new_products:
                all_new_products.append((product, max_ntd))
            for item in price_dropped:
                all_price_dropped.append((item, max_ntd))

        except Exception as e:
            print(f"Error processing {name}: {e}")
            import traceback
            traceback.print_exc()
            continue

    # 發送通知
    if all_new_products or all_price_dropped:
        print(f"\n{'='*60}")
        print("Sending notifications...")
        print(f"{'='*60}\n")

        # 由於 main.py 處理多個 URL，每個 URL 可能有不同的 max_ntd
        # 我們需要分別處理每個商品的通知
        success_count = 0
        total_count = len(all_new_products) + len(all_price_dropped)

        for product, max_ntd in all_new_products:
            is_within_budget = False
            if max_ntd is not None:
                price_twd = product.get("price_twd", 0)
                is_within_budget = price_twd > 0 and price_twd <= max_ntd
            if notifier.notify_new_product(product, is_within_budget=is_within_budget):
                success_count += 1

        for item, max_ntd in all_price_dropped:
            product = item["product"]
            old_price_jpy = item["old_price_jpy"]
            old_price_twd = item.get("old_price_twd")
            if notifier.notify_price_drop(product, old_price_jpy, old_price_twd, max_ntd):
                success_count += 1

        print(f"Notifications sent: {success_count}/{total_count}")
    else:
        print("\nNo new products or price changes to notify")

    print("\nDone!")


if __name__ == "__main__":
    main()

