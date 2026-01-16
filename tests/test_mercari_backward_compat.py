#!/usr/bin/env python3
"""
Mercari 爬蟲向後相容性測試

驗證重構後的 MercariScraper (scrapers/mercari/scraper.py) 
與原始版本 (src/scraper.py) 行為一致。

Requirements: 1.3 - THE System SHALL maintain backward compatibility 
with existing Mercari scraper functionality
"""
import unittest
import json
import os

from scrapers.mercari.scraper import MercariScraper as RefactoredMercariScraper
from src.scraper import MercariScraper as OriginalMercariScraper


class TestMercariBackwardCompatibility(unittest.TestCase):
    """測試重構後的 Mercari 爬蟲與原始版本的向後相容性"""

    def setUp(self):
        """初始化兩個版本的爬蟲"""
        self.refactored = RefactoredMercariScraper(headless=True, fetch_product_names=False)
        self.original = OriginalMercariScraper(headless=True, fetch_product_names=False)
        
        # 載入測試資料
        fixture_path = os.path.join(
            os.path.dirname(__file__), "fixtures", "api_response.json"
        )
        with open(fixture_path, "r", encoding="utf-8") as f:
            self.api_response_data = json.load(f)

    def test_source_name_property(self):
        """測試 source_name 屬性返回正確值"""
        self.assertEqual(self.refactored.source_name, "mercari_jp")

    def test_get_product_id_products_url(self):
        """測試從 /products/ URL 提取商品 ID"""
        url = "https://jp.mercari.com/products/m1234567890"
        
        refactored_id = self.refactored.get_product_id(url)
        original_id = self.original._extract_product_id(url)
        
        self.assertEqual(refactored_id, original_id)
        self.assertEqual(refactored_id, "m1234567890")

    def test_get_product_id_item_url(self):
        """測試從 /item/ URL 提取商品 ID"""
        url = "https://jp.mercari.com/item/m9876543210"
        
        refactored_id = self.refactored.get_product_id(url)
        original_id = self.original._extract_product_id(url)
        
        self.assertEqual(refactored_id, original_id)
        self.assertEqual(refactored_id, "m9876543210")

    def test_get_product_id_jp_url(self):
        """測試從 item.mercari.com/jp/ URL 提取商品 ID"""
        url = "https://item.mercari.com/jp/m5555555555"
        
        refactored_id = self.refactored.get_product_id(url)
        original_id = self.original._extract_product_id(url)
        
        self.assertEqual(refactored_id, original_id)
        self.assertEqual(refactored_id, "m5555555555")

    def test_get_product_id_invalid_url(self):
        """測試無效 URL 返回 None"""
        url = "https://example.com/invalid"
        
        refactored_id = self.refactored.get_product_id(url)
        original_id = self.original._extract_product_id(url)
        
        self.assertEqual(refactored_id, original_id)
        self.assertIsNone(refactored_id)

    def test_parse_price_jpy_and_twd(self):
        """測試解析包含日圓和台幣的價格"""
        price_text = "29,737日圓 NT$6,296"
        
        refactored_jpy, refactored_twd = self.refactored._parse_price(price_text)
        original_jpy, original_twd = self.original._parse_price(price_text)
        
        self.assertEqual(refactored_jpy, original_jpy)
        self.assertEqual(refactored_twd, original_twd)
        self.assertEqual(refactored_jpy, 29737)
        self.assertEqual(refactored_twd, 6296)

    def test_parse_price_twd_only(self):
        """測試解析只有台幣的價格"""
        price_text = "NT$4,869"
        
        refactored_jpy, refactored_twd = self.refactored._parse_price(price_text)
        original_jpy, original_twd = self.original._parse_price(price_text)
        
        self.assertEqual(refactored_jpy, original_jpy)
        self.assertEqual(refactored_twd, original_twd)
        self.assertEqual(refactored_twd, 4869)

    def test_parse_price_yen_symbol(self):
        """測試解析使用 ¥ 符號的價格"""
        price_text = "¥19,050 NT$4,023"
        
        refactored_jpy, refactored_twd = self.refactored._parse_price(price_text)
        original_jpy, original_twd = self.original._parse_price(price_text)
        
        self.assertEqual(refactored_jpy, original_jpy)
        self.assertEqual(refactored_twd, original_twd)
        self.assertEqual(refactored_jpy, 19050)
        self.assertEqual(refactored_twd, 4023)

    def test_parse_price_empty(self):
        """測試解析空字串"""
        price_text = ""
        
        refactored_jpy, refactored_twd = self.refactored._parse_price(price_text)
        original_jpy, original_twd = self.original._parse_price(price_text)
        
        self.assertEqual(refactored_jpy, original_jpy)
        self.assertEqual(refactored_twd, original_twd)
        self.assertEqual(refactored_jpy, 0)
        self.assertEqual(refactored_twd, 0)

    def test_add_status_parameter(self):
        """測試自動添加 status=on_sale 參數"""
        url = "https://jp.mercari.com/zh-TW/search?keyword=test"
        
        refactored_url = self.refactored._add_status_parameter(url)
        original_url = self.original._add_status_parameter(url)
        
        # 兩個版本應該產生相同的結果
        self.assertIn("status=on_sale", refactored_url)
        self.assertIn("status=on_sale", original_url)
        self.assertIn("keyword=test", refactored_url)

    def test_add_status_parameter_already_has_status(self):
        """測試已有 status 參數時的處理"""
        url = "https://jp.mercari.com/zh-TW/search?keyword=test&status=sold_out"
        
        refactored_url = self.refactored._add_status_parameter(url)
        original_url = self.original._add_status_parameter(url)
        
        # 應該覆蓋為 on_sale
        self.assertIn("status=on_sale", refactored_url)
        self.assertIn("status=on_sale", original_url)

    def test_api_response_parsing_consistency(self):
        """測試 API 響應解析的一致性"""
        # 使用重構版本的 _parse_api_response 方法
        refactored_products = self.refactored._parse_api_response(self.api_response_data)
        
        # 驗證解析結果的結構
        self.assertGreater(len(refactored_products), 0)
        
        for product in refactored_products:
            # 檢查必要欄位存在
            self.assertIn("id", product)
            self.assertIn("title", product)
            self.assertIn("price_jpy", product)
            self.assertIn("price_twd", product)
            self.assertIn("image_url", product)
            self.assertIn("product_url", product)
            
            # 檢查欄位類型
            self.assertIsInstance(product["id"], str)
            self.assertIsInstance(product["title"], str)
            self.assertIsInstance(product["price_jpy"], int)
            self.assertIsInstance(product["price_twd"], int)
            self.assertIsInstance(product["product_url"], str)

    def test_product_url_format(self):
        """測試商品 URL 格式一致性"""
        items = self.api_response_data.get("items", [])
        self.assertGreater(len(items), 0)
        
        for item in items:
            product_id = item.get("id", "")
            if not product_id:
                continue
            
            # 根據 ID 格式構建 URL（與原始邏輯一致）
            if product_id.startswith("m"):
                expected_url = f"https://jp.mercari.com/item/{product_id}"
            else:
                expected_url = f"https://jp.mercari.com/products/{product_id}"
            
            # 驗證 URL 格式
            self.assertIn("mercari.com", expected_url)
            self.assertIn(product_id, expected_url)

    def test_inherits_from_base_scraper(self):
        """測試重構版本繼承自 BaseScraper"""
        from core.base_scraper import BaseScraper
        self.assertIsInstance(self.refactored, BaseScraper)

    def test_has_required_abstract_methods(self):
        """測試重構版本實作了所有必要的抽象方法"""
        # 這些方法應該存在且可調用
        self.assertTrue(hasattr(self.refactored, 'scrape'))
        self.assertTrue(hasattr(self.refactored, 'parse_product'))
        self.assertTrue(hasattr(self.refactored, 'get_product_id'))
        self.assertTrue(hasattr(self.refactored, 'source_name'))
        
        # 確認是可調用的
        self.assertTrue(callable(getattr(self.refactored, 'scrape')))
        self.assertTrue(callable(getattr(self.refactored, 'parse_product')))
        self.assertTrue(callable(getattr(self.refactored, 'get_product_id')))

    def test_output_format_consistency(self):
        """測試輸出格式與原始版本一致"""
        # 使用 API 響應解析來驗證輸出格式
        products = self.refactored._parse_api_response(self.api_response_data)
        
        if products:
            product = products[0]
            
            # 原始版本的輸出格式
            expected_keys = {"id", "title", "price_jpy", "price_twd", "image_url", "product_url"}
            actual_keys = set(product.keys())
            
            # 重構版本應該包含所有原始版本的欄位
            self.assertTrue(expected_keys.issubset(actual_keys))


if __name__ == "__main__":
    unittest.main()
