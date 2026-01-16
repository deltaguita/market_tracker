#!/usr/bin/env python3
"""
測試 AmazonScraper 類別

測試 Amazon 爬蟲的核心功能：
- ASIN 提取
- 變體 ID 格式
- 價格解析
- 加購區塊識別
"""
import unittest
from scrapers.amazon.scraper import AmazonScraper


class TestAmazonScraper(unittest.TestCase):
    """Amazon 爬蟲單元測試"""

    def setUp(self):
        """每個測試前初始化爬蟲（不啟動瀏覽器）"""
        self.scraper = AmazonScraper(headless=True)

    def test_source_name(self):
        """測試來源名稱"""
        self.assertEqual(self.scraper.source_name, "amazon_us")

    # ===== ASIN 提取測試 =====
    
    def test_get_product_id_dp_format(self):
        """測試從 /dp/ 格式 URL 提取 ASIN"""
        url = "https://www.amazon.com/dp/B013HLGTL2"
        asin = self.scraper.get_product_id(url)
        self.assertEqual(asin, "B013HLGTL2")

    def test_get_product_id_gp_product_format(self):
        """測試從 /gp/product/ 格式 URL 提取 ASIN"""
        url = "https://www.amazon.com/gp/product/B013HLGTL2"
        asin = self.scraper.get_product_id(url)
        self.assertEqual(asin, "B013HLGTL2")

    def test_get_product_id_with_query_params(self):
        """測試從帶查詢參數的 URL 提取 ASIN"""
        url = "https://www.amazon.com/dp/B013HLGTL2?ref=something&tag=test"
        asin = self.scraper.get_product_id(url)
        self.assertEqual(asin, "B013HLGTL2")

    def test_get_product_id_with_product_name(self):
        """測試從帶商品名稱的 URL 提取 ASIN"""
        url = "https://www.amazon.com/Zippo-Hand-Warmer-12-Hour/dp/B013HLGTL2"
        asin = self.scraper.get_product_id(url)
        self.assertEqual(asin, "B013HLGTL2")

    def test_get_product_id_lowercase_asin(self):
        """測試小寫 ASIN 會被轉換為大寫"""
        url = "https://www.amazon.com/dp/b013hlgtl2"
        asin = self.scraper.get_product_id(url)
        self.assertEqual(asin, "B013HLGTL2")

    def test_get_product_id_invalid_url(self):
        """測試無效 URL 返回 None"""
        url = "https://www.amazon.com/some-page"
        asin = self.scraper.get_product_id(url)
        self.assertIsNone(asin)

    def test_get_product_id_empty_url(self):
        """測試空 URL 返回 None"""
        asin = self.scraper.get_product_id("")
        self.assertIsNone(asin)

    def test_get_product_id_none_url(self):
        """測試 None URL 返回 None"""
        asin = self.scraper.get_product_id(None)
        self.assertIsNone(asin)

    # ===== 變體 ID 正規化測試 =====

    def test_normalize_variant_identifier_simple(self):
        """測試簡單變體名稱正規化"""
        result = self.scraper._normalize_variant_identifier("Black")
        self.assertEqual(result, "black")

    def test_normalize_variant_identifier_with_spaces(self):
        """測試帶空格的變體名稱正規化"""
        result = self.scraper._normalize_variant_identifier("High Polish Chrome")
        self.assertEqual(result, "high_polish_chrome")

    def test_normalize_variant_identifier_with_special_chars(self):
        """測試帶特殊字元的變體名稱正規化"""
        result = self.scraper._normalize_variant_identifier("Black/Silver (2-Pack)")
        self.assertEqual(result, "blacksilver_2pack")

    def test_normalize_variant_identifier_empty(self):
        """測試空變體名稱返回 default"""
        result = self.scraper._normalize_variant_identifier("")
        self.assertEqual(result, "default")

    def test_normalize_variant_identifier_none(self):
        """測試 None 變體名稱返回 default"""
        result = self.scraper._normalize_variant_identifier(None)
        self.assertEqual(result, "default")

    def test_normalize_variant_identifier_long_name(self):
        """測試過長變體名稱會被截斷"""
        long_name = "A" * 100
        result = self.scraper._normalize_variant_identifier(long_name)
        self.assertLessEqual(len(result), 50)

    # ===== USD 價格解析測試 =====

    def test_parse_usd_price_standard(self):
        """測試標準 USD 價格解析"""
        price = self.scraper._parse_usd_price("$19.99")
        self.assertEqual(price, 19.99)

    def test_parse_usd_price_with_comma(self):
        """測試帶逗號的 USD 價格解析"""
        price = self.scraper._parse_usd_price("$1,234.56")
        self.assertEqual(price, 1234.56)

    def test_parse_usd_price_with_usd_prefix(self):
        """測試帶 USD 前綴的價格解析"""
        price = self.scraper._parse_usd_price("USD 19.99")
        self.assertEqual(price, 19.99)

    def test_parse_usd_price_no_symbol(self):
        """測試無符號的價格解析"""
        price = self.scraper._parse_usd_price("19.99")
        self.assertEqual(price, 19.99)

    def test_parse_usd_price_integer(self):
        """測試整數價格解析"""
        price = self.scraper._parse_usd_price("$20")
        self.assertEqual(price, 20.0)

    def test_parse_usd_price_empty(self):
        """測試空字串返回 None"""
        price = self.scraper._parse_usd_price("")
        self.assertIsNone(price)

    def test_parse_usd_price_none(self):
        """測試 None 返回 None"""
        price = self.scraper._parse_usd_price(None)
        self.assertIsNone(price)

    # ===== 加購區塊選擇器測試 =====

    def test_addon_section_selectors_defined(self):
        """測試加購區塊選擇器已定義"""
        self.assertIsInstance(self.scraper.ADDON_SECTION_SELECTORS, list)
        self.assertGreater(len(self.scraper.ADDON_SECTION_SELECTORS), 0)
        
        # 驗證關鍵選擇器存在
        expected_selectors = [
            '#similarities_feature_div',
            '#sims-fbt',
            '#sp_detail',
        ]
        for selector in expected_selectors:
            self.assertIn(selector, self.scraper.ADDON_SECTION_SELECTORS)

    def test_addon_section_texts_defined(self):
        """測試加購區塊文字標識已定義"""
        self.assertIsInstance(self.scraper.ADDON_SECTION_TEXTS, list)
        self.assertGreater(len(self.scraper.ADDON_SECTION_TEXTS), 0)
        
        # 驗證關鍵文字存在
        expected_texts = [
            'frequently bought together',
            'customers who viewed this item also viewed',
        ]
        for text in expected_texts:
            self.assertIn(text, self.scraper.ADDON_SECTION_TEXTS)


class TestAmazonScraperConstants(unittest.TestCase):
    """測試 Amazon 爬蟲常數設定"""

    def test_us_zip_code(self):
        """測試美國郵遞區號設定"""
        self.assertEqual(AmazonScraper.US_ZIP_CODE, "19720")

    def test_asin_patterns(self):
        """測試 ASIN 提取模式已定義"""
        self.assertIsInstance(AmazonScraper.ASIN_PATTERNS, list)
        self.assertGreater(len(AmazonScraper.ASIN_PATTERNS), 0)


if __name__ == "__main__":
    unittest.main()
