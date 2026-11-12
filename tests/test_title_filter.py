#!/usr/bin/env python3
"""
測試標題過濾
"""

import unittest
from src.title_filter import matches_title, filter_products

TRION = [["mammut", "マムート"], ["trion", "トリオン"]]


class TestMatchesTitle(unittest.TestCase):
    def test_no_rule_passes_everything(self):
        self.assertTrue(matches_title("anything", None))
        self.assertTrue(matches_title("anything", []))

    def test_brand_and_model_match(self):
        self.assertTrue(matches_title("MAMMUT Trion Spine 35", TRION))

    def test_japanese_aliases_match(self):
        self.assertTrue(matches_title("マムート トリオン スパイン 35", TRION))

    def test_mixed_language_aliases_match(self):
        self.assertTrue(matches_title("マムート Trion 35L", TRION))

    def test_brand_only_rejected(self):
        self.assertFalse(matches_title("MAMMUT Xeron IN Hooded Jacket", TRION))

    def test_model_only_rejected(self):
        self.assertFalse(matches_title("Trion Nordwand 他社", TRION))

    def test_two_aliases_of_same_group_not_enough(self):
        self.assertFalse(matches_title("MAMMUT マムート ジャケット", TRION))

    def test_similar_katakana_rejected(self):
        self.assertFalse(matches_title("マムート ファーストトリトン18", TRION))

    def test_case_insensitive(self):
        self.assertTrue(matches_title("mammut TRION 28", TRION))
        self.assertTrue(matches_title("MAMMUT trion 28", [["Mammut"], ["TRION"]]))

    def test_fullwidth_latin(self):
        self.assertTrue(matches_title("ＭＡＭＭＵＴ Ｔｒｉｏｎ", TRION))

    def test_empty_title(self):
        self.assertFalse(matches_title("", TRION))


class TestFilterProducts(unittest.TestCase):
    def test_filters_and_preserves_order(self):
        products = [
            {"id": "1", "title": "MAMMUT Trion 28"},
            {"id": "2", "title": "MAMMUT Jacket"},
            {"id": "3", "title": "マムート トリオン 38"},
        ]
        result = filter_products(products, TRION)
        self.assertEqual([p["id"] for p in result], ["1", "3"])

    def test_no_rule_returns_all(self):
        products = [{"id": "1", "title": "x"}]
        self.assertEqual(filter_products(products, None), products)


if __name__ == "__main__":
    unittest.main()
