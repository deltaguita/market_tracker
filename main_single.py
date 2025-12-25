#!/usr/bin/env python3
"""
處理單一 URL 的追蹤程式
用於 Matrix Strategy 並行處理
"""
import json
import os
import sys
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
    """主程式：處理單一 URL"""
    # 從環境變數獲取要處理的 URL index
    url_index = int(os.getenv("URL_INDEX", "0"))
    
    # 載入配置
    config = load_config()
    tracking_urls = config.get("tracking_urls", [])

    if not tracking_urls:
        print("No tracking URLs configured")
        return

    if url_index >= len(tracking_urls):
        print(f"URL index {url_index} out of range (total: {len(tracking_urls)})")
        return

    # 獲取要處理的 URL
    url_config = tracking_urls[url_index]
    name = url_config.get("name", "Unknown")
    url = url_config.get("url")
    
    if not url:
        print(f"Skipping {name}: No URL provided")
        return

    print(f"\n{'='*60}")
    print(f"Processing: {name} (Index: {url_index})")
    print(f"URL: {url}")
    print(f"{'='*60}\n")

    # 初始化元件
    scraper = MercariScraper(headless=True, fetch_product_names=True)
    storage = ProductStorage()
    notifier = TelegramNotifier()

    try:
        # 爬取商品
        current_products = scraper.scrape(url)
        print(f"Scraped {len(current_products)} products")

        # 比較並更新
        result = storage.compare_products(current_products)
        new_products = result["new"]
        price_dropped = result["price_dropped"]

        print(f"New products: {len(new_products)}")
        print(f"Price dropped: {len(price_dropped)}")

        # 發送通知（每個 URL 獨立發送）
        if new_products or price_dropped:
            print(f"\n{'='*60}")
            print(f"Sending notifications for {name}...")
            print(f"{'='*60}\n")
            success, total = notifier.notify_batch(new_products, price_dropped)
            print(f"Notifications sent: {success}/{total}")
        else:
            print(f"\nNo new products or price changes for {name}")

    except Exception as e:
        print(f"Error processing {name}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    print(f"\nDone processing {name}!")


if __name__ == "__main__":
    main()

