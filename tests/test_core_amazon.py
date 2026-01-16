#!/usr/bin/env python3
"""
測試 core 模組的 Amazon 相關功能

測試：
- TelegramNotifier 的 USD 價格格式化
- ProductStorage 的 amazon_us 來源支援
"""
import unittest
import os
import tempfile
import shutil
from unittest.mock import patch, MagicMock

from core.notifier import TelegramNotifier, format_usd_price
from core.storage import ProductStorage


class TestNotifierAmazonFormatting(unittest.TestCase):
    """測試通知服務的 Amazon 格式化功能"""

    def setUp(self):
        """設置環境變數"""
        os.environ["TELEGRAM_BOT_TOKEN"] = "test_token"
        os.environ["TELEGRAM_CHAT_ID"] = "test_chat_id"

    def tearDown(self):
        """清理環境變數"""
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)
        os.environ.pop("TELEGRAM_CHAT_ID", None)

    def test_format_price_amazon_us(self):
        """測試 Amazon US 價格格式化"""
        notifier = TelegramNotifier()
        product = {"price_usd": 19.99}
        result = notifier._format_price(product, "amazon_us")
        self.assertEqual(result, "USD $19.99")

    def test_format_price_amazon_us_zero(self):
        """測試 Amazon US 零價格格式化"""
        notifier = TelegramNotifier()
        product = {"price_usd": 0}
        result = notifier._format_price(product, "amazon_us")
        self.assertEqual(result, "價格未標示")

    def test_format_price_amazon_us_missing(self):
        """測試 Amazon US 缺少價格格式化"""
        notifier = TelegramNotifier()
        product = {}
        result = notifier._format_price(product, "amazon_us")
        self.assertEqual(result, "價格未標示")

    def test_format_price_amazon_us_large_number(self):
        """測試 Amazon US 大數字價格格式化"""
        notifier = TelegramNotifier()
        product = {"price_usd": 1234.56}
        result = notifier._format_price(product, "amazon_us")
        self.assertEqual(result, "USD $1234.56")

    def test_format_usd_price_function(self):
        """測試獨立的 USD 價格格式化函數"""
        self.assertEqual(format_usd_price(19.99), "USD $19.99")
        self.assertEqual(format_usd_price(0), "價格未標示")
        self.assertEqual(format_usd_price(-1), "價格未標示")

    def test_get_source_display_name_amazon(self):
        """測試 Amazon 來源顯示名稱"""
        notifier = TelegramNotifier()
        self.assertEqual(notifier._get_source_display_name("amazon_us"), "Amazon US")

    @patch("core.notifier.requests.post")
    def test_notify_new_product_amazon(self, mock_post):
        """測試 Amazon 新商品通知"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        notifier = TelegramNotifier()
        product = {
            "id": "B013HLGTL2",
            "title": "Zippo Hand Warmer",
            "price_usd": 19.99,
            "image_url": "https://example.com/image.jpg",
            "product_url": "https://www.amazon.com/dp/B013HLGTL2",
            "variant_name": "Black",
        }

        result = notifier.notify_new_product(product, source="amazon_us")
        self.assertTrue(result)
        mock_post.assert_called_once()

        # 檢查訊息內容
        call_data = mock_post.call_args[1]["json"]
        message_text = call_data.get("caption") or call_data.get("text", "")
        self.assertIn("Amazon US", message_text)
        self.assertIn("USD $19.99", message_text)
        self.assertIn("Black", message_text)

    @patch("core.notifier.requests.post")
    def test_notify_price_drop_amazon(self, mock_post):
        """測試 Amazon 價格降低通知"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        notifier = TelegramNotifier()
        product = {
            "id": "B013HLGTL2",
            "title": "Zippo Hand Warmer",
            "price_usd": 15.99,
            "image_url": "https://example.com/image.jpg",
            "product_url": "https://www.amazon.com/dp/B013HLGTL2",
        }

        result = notifier.notify_price_drop(
            product, old_price=19.99, source="amazon_us"
        )
        self.assertTrue(result)
        mock_post.assert_called_once()

        # 檢查訊息內容
        call_data = mock_post.call_args[1]["json"]
        message_text = call_data.get("caption") or call_data.get("text", "")
        self.assertIn("價格降低", message_text)
        self.assertIn("Amazon US", message_text)


class TestStorageAmazonSource(unittest.TestCase):
    """測試儲存服務的 Amazon 來源支援"""

    def setUp(self):
        """創建臨時資料庫"""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_products.db")
        self.storage = ProductStorage(db_path=self.db_path)

    def tearDown(self):
        """清理臨時資料庫"""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_valid_sources(self):
        """測試有效來源列表"""
        self.assertIn("amazon_us", ProductStorage.VALID_SOURCES)
        self.assertIn("mercari_jp", ProductStorage.VALID_SOURCES)

    def test_upsert_amazon_product(self):
        """測試新增 Amazon 商品"""
        product = {
            "id": "B013HLGTL2",
            "title": "Zippo Hand Warmer",
            "price_usd": 19.99,
            "image_url": "https://example.com/image.jpg",
            "product_url": "https://www.amazon.com/dp/B013HLGTL2",
            "variant_name": "Black",
        }
        self.storage.upsert_product(product, source="amazon_us")

        # 檢查商品是否已新增
        existing = self.storage.get_existing_products({"B013HLGTL2"}, "amazon_us")
        self.assertIn("B013HLGTL2", existing)
        self.assertEqual(existing["B013HLGTL2"]["title"], "Zippo Hand Warmer")
        self.assertEqual(existing["B013HLGTL2"]["price_usd"], 19.99)
        self.assertEqual(existing["B013HLGTL2"]["source"], "amazon_us")

    def test_upsert_amazon_product_update_price(self):
        """測試更新 Amazon 商品價格"""
        # 先新增商品
        product1 = {
            "id": "B013HLGTL2",
            "title": "Zippo Hand Warmer",
            "price_usd": 19.99,
            "image_url": "https://example.com/image.jpg",
            "product_url": "https://www.amazon.com/dp/B013HLGTL2",
        }
        self.storage.upsert_product(product1, source="amazon_us")

        # 更新價格
        product2 = {
            "id": "B013HLGTL2",
            "title": "Zippo Hand Warmer",
            "price_usd": 15.99,
            "image_url": "https://example.com/image.jpg",
            "product_url": "https://www.amazon.com/dp/B013HLGTL2",
        }
        self.storage.upsert_product(product2, source="amazon_us")

        # 檢查價格已更新
        existing = self.storage.get_existing_products({"B013HLGTL2"}, "amazon_us")
        self.assertEqual(existing["B013HLGTL2"]["price_usd"], 15.99)
        # 最低價格應該是 15.99
        self.assertEqual(existing["B013HLGTL2"]["lowest_price_usd"], 15.99)

    def test_compare_products_amazon_new(self):
        """測試比較 Amazon 商品 - 新商品"""
        current_products = [
            {
                "id": "B013HLGTL2",
                "title": "Zippo Hand Warmer",
                "price_usd": 19.99,
                "image_url": "https://example.com/image.jpg",
                "product_url": "https://www.amazon.com/dp/B013HLGTL2",
            }
        ]

        result = self.storage.compare_products(current_products, source="amazon_us")
        self.assertEqual(len(result["new"]), 1)
        self.assertEqual(len(result["price_dropped"]), 0)
        self.assertEqual(result["new"][0]["id"], "B013HLGTL2")

    def test_compare_products_amazon_price_drop(self):
        """測試比較 Amazon 商品 - 價格降低"""
        # 先新增商品
        product1 = {
            "id": "B013HLGTL2",
            "title": "Zippo Hand Warmer",
            "price_usd": 19.99,
            "image_url": "https://example.com/image.jpg",
            "product_url": "https://www.amazon.com/dp/B013HLGTL2",
        }
        self.storage.upsert_product(product1, source="amazon_us")

        # 價格降低
        product2 = {
            "id": "B013HLGTL2",
            "title": "Zippo Hand Warmer",
            "price_usd": 15.99,
            "image_url": "https://example.com/image.jpg",
            "product_url": "https://www.amazon.com/dp/B013HLGTL2",
        }

        result = self.storage.compare_products([product2], source="amazon_us")
        self.assertEqual(len(result["new"]), 0)
        self.assertEqual(len(result["price_dropped"]), 1)
        self.assertEqual(result["price_dropped"][0]["old_price_usd"], 19.99)

    def test_source_isolation(self):
        """測試不同來源的商品隔離"""
        # 新增 Amazon 商品
        amazon_product = {
            "id": "TEST123",
            "title": "Amazon Product",
            "price_usd": 19.99,
            "product_url": "https://www.amazon.com/dp/TEST123",
        }
        self.storage.upsert_product(amazon_product, source="amazon_us")

        # 新增 Mercari 商品（相同 ID）
        mercari_product = {
            "id": "TEST123",
            "title": "Mercari Product",
            "price_jpy": 2000,
            "price_twd": 400,
            "product_url": "https://jp.mercari.com/item/TEST123",
        }
        self.storage.upsert_product(mercari_product, source="mercari_jp")

        # 檢查兩個商品都存在且獨立
        amazon_existing = self.storage.get_existing_products({"TEST123"}, "amazon_us")
        mercari_existing = self.storage.get_existing_products({"TEST123"}, "mercari_jp")

        self.assertEqual(amazon_existing["TEST123"]["title"], "Amazon Product")
        self.assertEqual(mercari_existing["TEST123"]["title"], "Mercari Product")

    def test_full_history_mode_amazon(self):
        """測試 Amazon 商品的 full_history 模式"""
        product = {
            "id": "B013HLGTL2",
            "title": "Zippo Hand Warmer",
            "price_usd": 19.99,
            "product_url": "https://www.amazon.com/dp/B013HLGTL2",
        }

        # 使用 full_history 模式新增
        self.storage.upsert_product(product, source="amazon_us", tracking_mode="full_history")

        # 更新價格
        product["price_usd"] = 17.99
        self.storage.upsert_product(product, source="amazon_us", tracking_mode="full_history")

        # 再次更新價格
        product["price_usd"] = 15.99
        self.storage.upsert_product(product, source="amazon_us", tracking_mode="full_history")

        # 檢查價格歷史記錄數量
        history_count = self.storage.get_price_history_count("B013HLGTL2", "amazon_us")
        self.assertEqual(history_count, 3)

    def test_invalid_source_raises_error(self):
        """測試無效來源會拋出錯誤"""
        product = {"id": "TEST", "title": "Test"}
        with self.assertRaises(ValueError):
            self.storage.upsert_product(product, source="invalid_source")


if __name__ == "__main__":
    unittest.main()
