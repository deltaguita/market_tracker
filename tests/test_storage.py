#!/usr/bin/env python3
"""
測試 ProductStorage 類別
"""
import unittest
import os
import tempfile
import shutil
from src.storage import ProductStorage


class TestProductStorage(unittest.TestCase):
    def setUp(self):
        """每個測試前創建臨時資料庫"""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_products.db")
        self.storage = ProductStorage(db_path=self.db_path)

    def tearDown(self):
        """每個測試後清理臨時資料庫"""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_upsert_new_product(self):
        """測試新增商品"""
        product = {
            "id": "test123",
            "title": "測試商品",
            "price_jpy": 1000,
            "price_twd": 200,
            "image_url": "https://example.com/image.jpg",
            "product_url": "https://example.com/product",
        }
        self.storage.upsert_product(product)

        # 檢查商品是否已新增
        existing = self.storage.get_existing_products({"test123"})
        self.assertIn("test123", existing)
        self.assertEqual(existing["test123"]["title"], "測試商品")
        self.assertEqual(existing["test123"]["price_jpy"], 1000)

    def test_upsert_update_product(self):
        """測試更新商品"""
        # 先新增商品
        product1 = {
            "id": "test123",
            "title": "測試商品",
            "price_jpy": 1000,
            "price_twd": 200,
            "image_url": "https://example.com/image.jpg",
            "product_url": "https://example.com/product",
        }
        self.storage.upsert_product(product1)

        # 更新商品
        product2 = {
            "id": "test123",
            "title": "更新的商品",
            "price_jpy": 900,
            "price_twd": 180,
            "image_url": "https://example.com/image2.jpg",
            "product_url": "https://example.com/product",
        }
        self.storage.upsert_product(product2)

        # 檢查商品是否已更新
        existing = self.storage.get_existing_products({"test123"})
        self.assertEqual(existing["test123"]["title"], "更新的商品")
        self.assertEqual(existing["test123"]["price_jpy"], 900)
        # 最低價格應該是 900（因為 900 < 1000）
        self.assertEqual(existing["test123"]["lowest_price_jpy"], 900)

    def test_compare_products_new(self):
        """測試比較商品 - 新商品"""
        current_products = [
            {
                "id": "new1",
                "title": "新商品1",
                "price_jpy": 1000,
                "price_twd": 200,
                "image_url": "https://example.com/image.jpg",
                "product_url": "https://example.com/product1",
            }
        ]

        result = self.storage.compare_products(current_products)
        self.assertEqual(len(result["new"]), 1)
        self.assertEqual(len(result["price_dropped"]), 0)
        self.assertEqual(result["new"][0]["id"], "new1")

    def test_compare_products_price_drop(self):
        """測試比較商品 - 價格降低"""
        # 先新增商品
        product1 = {
            "id": "test123",
            "title": "測試商品",
            "price_jpy": 1000,
            "price_twd": 200,
            "image_url": "https://example.com/image.jpg",
            "product_url": "https://example.com/product",
        }
        self.storage.upsert_product(product1)

        # 價格降低
        product2 = {
            "id": "test123",
            "title": "測試商品",
            "price_jpy": 800,  # 價格降低
            "price_twd": 160,
            "image_url": "https://example.com/image.jpg",
            "product_url": "https://example.com/product",
        }

        current_products = [product2]
        result = self.storage.compare_products(current_products)

        self.assertEqual(len(result["new"]), 0)
        self.assertEqual(len(result["price_dropped"]), 1)
        self.assertEqual(result["price_dropped"][0]["old_price_jpy"], 1000)
        # 驗證 old_price_twd 是否正確返回
        self.assertIn("old_price_twd", result["price_dropped"][0])
        self.assertEqual(result["price_dropped"][0]["old_price_twd"], 200)

    def test_compare_products_no_price_drop(self):
        """測試比較商品 - 價格未降低（不應該觸發通知）"""
        # 先新增商品
        product1 = {
            "id": "test123",
            "title": "測試商品",
            "price_jpy": 1000,
            "price_twd": 200,
            "image_url": "https://example.com/image.jpg",
            "product_url": "https://example.com/product",
        }
        self.storage.upsert_product(product1)

        # 價格相同或更高
        product2 = {
            "id": "test123",
            "title": "測試商品",
            "price_jpy": 1200,  # 價格提高
            "price_twd": 240,
            "image_url": "https://example.com/image.jpg",
            "product_url": "https://example.com/product",
        }

        current_products = [product2]
        result = self.storage.compare_products(current_products)

        self.assertEqual(len(result["new"]), 0)
        self.assertEqual(len(result["price_dropped"]), 0)  # 價格提高，不應該觸發通知


if __name__ == "__main__":
    unittest.main()

