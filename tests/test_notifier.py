#!/usr/bin/env python3
"""
測試 TelegramNotifier 類別
"""
import unittest
import os
from unittest.mock import patch, MagicMock
from src.notifier import TelegramNotifier


class TestTelegramNotifier(unittest.TestCase):
    def setUp(self):
        """每個測試前設置環境變數"""
        os.environ["TELEGRAM_BOT_TOKEN"] = "test_token"
        os.environ["TELEGRAM_CHAT_ID"] = "test_chat_id"

    def tearDown(self):
        """每個測試後清理環境變數"""
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)
        os.environ.pop("TELEGRAM_CHAT_ID", None)

    def test_init(self):
        """測試初始化"""
        notifier = TelegramNotifier()
        self.assertEqual(notifier.bot_token, "test_token")
        self.assertEqual(notifier.chat_id, "test_chat_id")

    def test_init_with_parameters(self):
        """測試使用參數初始化"""
        notifier = TelegramNotifier(bot_token="custom_token", chat_id="custom_chat")
        self.assertEqual(notifier.bot_token, "custom_token")
        self.assertEqual(notifier.chat_id, "custom_chat")

    @patch("src.notifier.requests.post")
    def test_notify_new_product(self, mock_post):
        """測試通知新商品"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        notifier = TelegramNotifier()
        product = {
            "id": "test123",
            "title": "測試商品",
            "price_jpy": 1000,
            "price_twd": 200,
            "image_url": "https://example.com/image.jpg",
            "product_url": "https://example.com/product",
        }

        result = notifier.notify_new_product(product)
        self.assertTrue(result)
        mock_post.assert_called_once()

    @patch("src.notifier.requests.post")
    def test_notify_price_drop(self, mock_post):
        """測試通知價格降低"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        notifier = TelegramNotifier()
        product = {
            "id": "test123",
            "title": "測試商品",
            "price_jpy": 800,  # 新價格
            "price_twd": 160,
            "image_url": "https://example.com/image.jpg",
            "product_url": "https://example.com/product",
        }

        result = notifier.notify_price_drop(product, old_price_jpy=1000)
        self.assertTrue(result)
        mock_post.assert_called_once()

        # 檢查訊息內容包含降價資訊
        call_args = mock_post.call_args
        self.assertIn("價格降低", str(call_args))

    @patch("src.notifier.requests.post")
    def test_notify_batch(self, mock_post):
        """測試批次通知"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        notifier = TelegramNotifier()
        new_products = [
            {
                "id": "new1",
                "title": "新商品1",
                "price_jpy": 1000,
                "price_twd": 200,
                "image_url": "https://example.com/image.jpg",
                "product_url": "https://example.com/product1",
            }
        ]
        price_dropped = [
            {
                "product": {
                    "id": "test123",
                    "title": "測試商品",
                    "price_jpy": 800,
                    "price_twd": 160,
                    "image_url": "https://example.com/image.jpg",
                    "product_url": "https://example.com/product",
                },
                "old_price_jpy": 1000,
            }
        ]

        success, total = notifier.notify_batch(new_products, price_dropped)
        self.assertEqual(success, 2)
        self.assertEqual(total, 2)
        self.assertEqual(mock_post.call_count, 2)


if __name__ == "__main__":
    unittest.main()

