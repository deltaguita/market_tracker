#!/usr/bin/env python3
"""
測試 merge_databases 的資料庫合併行為
重點：確保 ignored_products 忽略清單能通過合併流程存活
"""

import unittest
import os
import sqlite3
import tempfile
import shutil

from merge_databases import merge_databases


def _create_db(path, products=None, ignored_ids=None):
    """建立一個具有 products / ignored_products schema 的來源 DB"""
    conn = sqlite3.connect(path)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS products (
            id TEXT PRIMARY KEY,
            title TEXT,
            price_jpy INTEGER,
            price_twd INTEGER,
            image_url TEXT,
            product_url TEXT,
            first_seen TEXT,
            last_updated TEXT,
            lowest_price_jpy INTEGER,
            lowest_price_twd INTEGER
        )
        """
    )
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS ignored_products (product_id TEXT PRIMARY KEY)"
    )
    for p in products or []:
        cursor.execute(
            """
            INSERT INTO products (
                id, title, price_jpy, price_twd, image_url, product_url,
                first_seen, last_updated, lowest_price_jpy, lowest_price_twd
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                p["id"],
                p.get("title"),
                p.get("price_jpy"),
                p.get("price_twd"),
                p.get("image_url"),
                p.get("product_url"),
                p.get("first_seen"),
                p.get("last_updated"),
                p.get("lowest_price_jpy"),
                p.get("lowest_price_twd"),
            ),
        )
    for pid in ignored_ids or []:
        cursor.execute(
            "INSERT OR IGNORE INTO ignored_products (product_id) VALUES (?)", (pid,)
        )
    conn.commit()
    conn.close()


def _get_ignored(path):
    conn = sqlite3.connect(path)
    cursor = conn.cursor()
    cursor.execute("SELECT product_id FROM ignored_products")
    ids = {row[0] for row in cursor.fetchall()}
    conn.close()
    return ids


def _table_exists(path, name):
    conn = sqlite3.connect(path)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    )
    exists = cursor.fetchone() is not None
    conn.close()
    return exists


class TestMergeIgnoredProducts(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def _p(self, name):
        return os.path.join(self.temp_dir, name)

    def test_target_has_ignored_products_table_after_merge(self):
        src = self._p("src1.db")
        _create_db(src, ignored_ids=["m1"])
        target = self._p("target.db")

        merge_databases([src], target)

        self.assertTrue(_table_exists(target, "ignored_products"))

    def test_merges_ignored_ids_from_all_sources(self):
        src1 = self._p("src1.db")
        src2 = self._p("src2.db")
        _create_db(src1, ignored_ids=["m1", "m2"])
        _create_db(src2, ignored_ids=["m3"])
        target = self._p("target.db")

        merge_databases([src1, src2], target)

        self.assertEqual(_get_ignored(target), {"m1", "m2", "m3"})

    def test_preserves_existing_ignored_ids_in_target(self):
        # target 已有的忽略 id（模擬前一次 commit 累積的清單）必須保留
        target = self._p("target.db")
        _create_db(target, ignored_ids=["old1"])
        src = self._p("src1.db")
        _create_db(src, ignored_ids=["new1"])

        merge_databases([src], target)

        self.assertEqual(_get_ignored(target), {"old1", "new1"})

    def test_duplicate_ignored_ids_across_sources_and_target(self):
        # target 與多個 source 有重疊的忽略 id，應去重且不報錯
        target = self._p("target.db")
        _create_db(target, ignored_ids=["dup", "old"])
        src1 = self._p("src1.db")
        src2 = self._p("src2.db")
        _create_db(src1, ignored_ids=["dup", "a"])
        _create_db(src2, ignored_ids=["dup", "b"])

        merge_databases([src1, src2], target)

        self.assertEqual(_get_ignored(target), {"dup", "old", "a", "b"})

    def test_source_without_ignored_table_does_not_break(self):
        # 舊格式來源（只有 products 表）不應讓合併失敗
        src = self._p("src_legacy.db")
        conn = sqlite3.connect(src)
        conn.execute(
            """
            CREATE TABLE products (
                id TEXT PRIMARY KEY, title TEXT, price_jpy INTEGER,
                price_twd INTEGER, image_url TEXT, product_url TEXT,
                first_seen TEXT, last_updated TEXT,
                lowest_price_jpy INTEGER, lowest_price_twd INTEGER
            )
            """
        )
        conn.commit()
        conn.close()
        target = self._p("target.db")

        merge_databases([src], target)

        self.assertTrue(_table_exists(target, "ignored_products"))
        self.assertEqual(_get_ignored(target), set())


if __name__ == "__main__":
    unittest.main()
