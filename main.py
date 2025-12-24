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
        if not url:
            print(f"Skipping {name}: No URL provided")
            continue

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

            print(f"New products: {len(new_products)}")
            print(f"Price dropped: {len(price_dropped)}")

            # 收集通知
            all_new_products.extend(new_products)
            all_price_dropped.extend(price_dropped)

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
        success, total = notifier.notify_batch(all_new_products, all_price_dropped)
        print(f"Notifications sent: {success}/{total}")
    else:
        print("\nNo new products or price changes to notify")

    print("\nDone!")


if __name__ == "__main__":
    main()

