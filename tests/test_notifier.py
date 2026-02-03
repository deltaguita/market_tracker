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

    @patch("src.notifier.requests.get")
    @patch("src.notifier.requests.post")
    def test_notify_new_product(self, mock_post, mock_get):
        """測試通知新商品"""
        mock_get.return_value.json.return_value = {
            "ok": True,
            "result": {"username": "test_bot"},
        }
        mock_get.return_value.raise_for_status = MagicMock()
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

    @patch("src.notifier.requests.get")
    @patch("src.notifier.requests.post")
    def test_notify_price_drop(self, mock_post, mock_get):
        """測試通知價格降低"""
        mock_get.return_value.json.return_value = {
            "ok": True,
            "result": {"username": "test_bot"},
        }
        mock_get.return_value.raise_for_status = MagicMock()
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

    @patch("src.notifier.requests.get")
    @patch("src.notifier.requests.post")
    def test_notify_batch(self, mock_post, mock_get):
        """測試批次通知"""
        mock_get.return_value.json.return_value = {
            "ok": True,
            "result": {"username": "test_bot"},
        }
        mock_get.return_value.raise_for_status = MagicMock()
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

    @patch("src.notifier.requests.get")
    @patch("src.notifier.requests.post")
    def test_notify_new_product_within_budget(self, mock_post, mock_get):
        """測試通知預算內新商品上架"""
        mock_get.return_value.json.return_value = {
            "ok": True,
            "result": {"username": "test_bot"},
        }
        mock_get.return_value.raise_for_status = MagicMock()
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

        result = notifier.notify_new_product(product, is_within_budget=True)
        self.assertTrue(result)
        mock_post.assert_called_once()

        # 檢查訊息內容包含「有預算內目標商品上架」
        # 有圖片時使用 caption，沒有圖片時使用 text
        call_data = mock_post.call_args[1]["json"]
        message_text = call_data.get("caption") or call_data.get("text", "")
        self.assertIn("有預算內目標商品上架", message_text)

    @patch("src.notifier.requests.get")
    @patch("src.notifier.requests.post")
    def test_notify_price_drop_to_budget(self, mock_post, mock_get):
        """測試通知降價至預算範圍"""
        mock_get.return_value.json.return_value = {
            "ok": True,
            "result": {"username": "test_bot"},
        }
        mock_get.return_value.raise_for_status = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        notifier = TelegramNotifier()
        product = {
            "id": "test123",
            "title": "測試商品",
            "price_jpy": 800,  # 新價格
            "price_twd": 400,  # 新價格在預算內（max_ntd=500）
            "image_url": "https://example.com/image.jpg",
            "product_url": "https://example.com/product",
        }

        # 原本價格 600 TWD（超過預算 500），現在降到 400 TWD（在預算內）
        result = notifier.notify_price_drop(
            product, old_price_jpy=1000, old_price_twd=600, max_ntd=500
        )
        self.assertTrue(result)
        mock_post.assert_called_once()

        # 檢查訊息內容包含「降價至預算範圍」
        # 有圖片時使用 caption，沒有圖片時使用 text
        call_data = mock_post.call_args[1]["json"]
        message_text = call_data.get("caption") or call_data.get("text", "")
        self.assertIn("降價至預算範圍", message_text)

    @patch("src.notifier.requests.get")
    @patch("src.notifier.requests.post")
    def test_notify_price_drop_within_budget(self, mock_post, mock_get):
        """測試通知預算內商品降價（保持原樣）"""
        mock_get.return_value.json.return_value = {
            "ok": True,
            "result": {"username": "test_bot"},
        }
        mock_get.return_value.raise_for_status = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        notifier = TelegramNotifier()
        product = {
            "id": "test123",
            "title": "測試商品",
            "price_jpy": 800,  # 新價格
            "price_twd": 300,  # 新價格在預算內
            "image_url": "https://example.com/image.jpg",
            "product_url": "https://example.com/product",
        }

        # 原本價格 400 TWD（也在預算內），現在降到 300 TWD
        result = notifier.notify_price_drop(
            product, old_price_jpy=1000, old_price_twd=400, max_ntd=500
        )
        self.assertTrue(result)
        mock_post.assert_called_once()

        # 檢查訊息內容包含「價格降低」（不是「降價至預算範圍」）
        # 有圖片時使用 caption，沒有圖片時使用 text
        call_data = mock_post.call_args[1]["json"]
        message_text = call_data.get("caption") or call_data.get("text", "")
        self.assertIn("價格降低", message_text)
        self.assertNotIn("降價至預算範圍", message_text)

    @patch("src.notifier.requests.get")
    @patch("src.notifier.requests.post")
    def test_notify_new_product_includes_ignore_link(self, mock_post, mock_get):
        """測試通知訊息包含 /ignore 連結"""
        mock_get.return_value.json.return_value = {
            "ok": True,
            "result": {"username": "test_bot"},
        }
        mock_get.return_value.raise_for_status = MagicMock()
        mock_post.return_value.status_code = 200
        mock_post.return_value.raise_for_status = MagicMock()

        notifier = TelegramNotifier()
        product = {
            "id": "m12345678",
            "title": "測試商品",
            "price_jpy": 1000,
            "price_twd": 200,
            "image_url": "https://example.com/image.jpg",
            "product_url": "https://example.com/product",
        }

        notifier.notify_new_product(product)
        call_data = mock_post.call_args[1]["json"]
        message_text = call_data.get("caption") or call_data.get("text", "")
        self.assertIn("/ignore m12345678", message_text)
        self.assertIn("t.me/test_bot", message_text)

    @patch("src.notifier.requests.get")
    @patch("src.notifier.requests.post")
    def test_notify_price_drop_includes_ignore_link(self, mock_post, mock_get):
        """測試降價通知訊息包含 /ignore 連結"""
        mock_get.return_value.json.return_value = {
            "ok": True,
            "result": {"username": "test_bot"},
        }
        mock_get.return_value.raise_for_status = MagicMock()
        mock_post.return_value.status_code = 200
        mock_post.return_value.raise_for_status = MagicMock()

        notifier = TelegramNotifier()
        product = {
            "id": "m87654321",
            "title": "測試商品",
            "price_jpy": 800,
            "price_twd": 160,
            "image_url": "https://example.com/image.jpg",
            "product_url": "https://example.com/product",
        }

        notifier.notify_price_drop(product, old_price_jpy=1000)
        call_data = mock_post.call_args[1]["json"]
        message_text = call_data.get("caption") or call_data.get("text", "")
        self.assertIn("/ignore m87654321", message_text)
        self.assertIn("t.me/test_bot", message_text)


if __name__ == "__main__":
    unittest.main()
