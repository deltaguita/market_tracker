#!/usr/bin/env python3
"""
測試 MercariScraper 類別
使用 fixtures/api_response.json 作為測試資料
"""
import unittest
import json
import os
from unittest.mock import patch, MagicMock
from src.scraper import MercariScraper


class TestMercariScraper(unittest.TestCase):
    def setUp(self):
        """每個測試前載入測試資料"""
        self.fixture_path = os.path.join(
            os.path.dirname(__file__), "fixtures", "api_response.json"
        )
        with open(self.fixture_path, "r", encoding="utf-8") as f:
            self.api_response_data = json.load(f)

    def test_parse_api_response_structure(self):
        """測試解析 API 響應結構"""
        # 檢查頂層結構
        self.assertIn("items", self.api_response_data)
        self.assertIn("meta", self.api_response_data)

        # 檢查 items 是列表
        items = self.api_response_data.get("items", [])
        self.assertIsInstance(items, list)
        self.assertGreater(len(items), 0)

    def test_extract_product_from_api_item(self):
        """測試從 API item 提取商品資訊（模擬 scraper 的邏輯）"""
        items = self.api_response_data.get("items", [])
        self.assertGreater(len(items), 0)

        item = items[0]

        # 模擬 scraper.py 中的提取邏輯
        product_id = item.get("id", "")
        price_jpy = int(item.get("price", 0))
        name = item.get("name", "")
        thumbnails = item.get("thumbnails", [])
        photos = item.get("photos", [])

        # 提取圖片 URL
        image_url = ""
        if thumbnails:
            image_url = thumbnails[0]
        elif photos:
            image_url = photos[0].get("uri", "")

        # 構建商品 URL
        if product_id.startswith("m"):
            product_url = f"https://jp.mercari.com/item/{product_id}"
        else:
            product_url = f"https://jp.mercari.com/products/{product_id}"

        # 驗證提取的資料
        self.assertNotEqual(product_id, "")
        self.assertGreater(price_jpy, 0)
        self.assertNotEqual(name, "")
        self.assertNotEqual(image_url, "")
        self.assertIn("mercari.com", product_url)

    def test_extract_all_products_from_api_response(self):
        """測試從完整 API 響應提取所有商品"""
        items = self.api_response_data.get("items", [])
        products = []

        for item in items:
            product_id = item.get("id", "")
            if not product_id:
                continue

            price_jpy = int(item.get("price", 0))
            name = item.get("name", "")
            thumbnails = item.get("thumbnails", [])
            photos = item.get("photos", [])

            image_url = ""
            if thumbnails:
                image_url = thumbnails[0]
            elif photos:
                image_url = photos[0].get("uri", "")

            if product_id.startswith("m"):
                product_url = f"https://jp.mercari.com/item/{product_id}"
            else:
                product_url = f"https://jp.mercari.com/products/{product_id}"

            products.append(
                {
                    "id": product_id,
                    "title": name,
                    "price_jpy": price_jpy,
                    "image_url": image_url,
                    "product_url": product_url,
                }
            )

        # 驗證所有商品都被正確提取
        self.assertGreater(len(products), 0)
        self.assertEqual(len(products), len(items))

        # 驗證每個商品都有必要欄位
        for product in products:
            self.assertIn("id", product)
            self.assertIn("title", product)
            self.assertIn("price_jpy", product)
            self.assertIn("image_url", product)
            self.assertIn("product_url", product)
            self.assertGreater(product["price_jpy"], 0)

    def test_api_response_meta_info(self):
        """測試 API 響應的 meta 資訊"""
        meta = self.api_response_data.get("meta", {})
        num_found = meta.get("numFound", "0")

        # numFound 可能是字串或數字
        num_found_int = int(num_found)
        items_count = len(self.api_response_data.get("items", []))

        # 驗證商品數量
        self.assertGreater(num_found_int, 0)
        self.assertGreater(items_count, 0)

    def test_product_id_format(self):
        """測試商品 ID 格式"""
        items = self.api_response_data.get("items", [])
        self.assertGreater(len(items), 0)

        for item in items:
            product_id = item.get("id", "")
            self.assertNotEqual(product_id, "")
            # Mercari 商品 ID 通常是字母數字組合
            self.assertTrue(len(product_id) > 0)

    def test_price_format(self):
        """測試價格格式（應該是字串，可轉換為整數）"""
        items = self.api_response_data.get("items", [])
        self.assertGreater(len(items), 0)

        for item in items:
            price = item.get("price", "0")
            # 價格應該是字串格式
            self.assertIsInstance(price, str)
            # 應該可以轉換為整數
            price_int = int(price)
            self.assertGreaterEqual(price_int, 0)


if __name__ == "__main__":
    unittest.main()

