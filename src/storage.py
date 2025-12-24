import sqlite3
import os
from datetime import datetime
from typing import List, Dict, Optional, Set


class ProductStorage:
    def __init__(self, db_path: str = "data/products.db"):
        self.db_path = db_path
        self._ensure_db_exists()

    def _ensure_db_exists(self):
        """確保資料庫檔案和資料表存在"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        # 使用 WAL 模式以支援並發讀寫
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.execute("PRAGMA journal_mode=WAL")  # 啟用 WAL 模式
        cursor = conn.cursor()
        cursor.execute("""
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
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_id ON products(id)
        """)
        conn.commit()
        conn.close()

    def get_existing_products(self, product_ids: Set[str]) -> Dict[str, Dict]:
        """取得現有商品資料（只查詢當前搜尋結果中出現的商品）"""
        if not product_ids:
            return {}
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        placeholders = ",".join("?" * len(product_ids))
        cursor.execute(
            f"SELECT * FROM products WHERE id IN ({placeholders})", list(product_ids)
        )
        columns = [desc[0] for desc in cursor.description]
        products = {}
        for row in cursor.fetchall():
            product = dict(zip(columns, row))
            products[product["id"]] = product
        conn.close()
        return products

    def upsert_product(self, product: Dict):
        """新增或更新商品（只保留最新狀態）"""
        now = datetime.now().isoformat()
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()

        # 檢查商品是否已存在
        cursor.execute(
            "SELECT id, lowest_price_jpy, lowest_price_twd FROM products WHERE id = ?",
            (product["id"],),
        )
        existing = cursor.fetchone()

        if existing:
            # 更新現有商品
            existing_id, existing_lowest_jpy, existing_lowest_twd = existing

            # 更新最低價格（只更新有實際價格的部分，避免 0 或 1 的誤判）
            new_price_jpy = product["price_jpy"]
            new_price_twd = product["price_twd"]

            # 如果舊的最低價是 0 或 1（可能是初始值或錯誤值），直接使用新價格
            if existing_lowest_jpy is None or existing_lowest_jpy <= 1:
                lowest_price_jpy = new_price_jpy if new_price_jpy > 0 else None
            else:
                # 只比較有實際價格的情況
                if new_price_jpy > 0:
                    lowest_price_jpy = min(existing_lowest_jpy, new_price_jpy)
                else:
                    lowest_price_jpy = existing_lowest_jpy

            if existing_lowest_twd is None or existing_lowest_twd <= 1:
                lowest_price_twd = new_price_twd if new_price_twd > 0 else None
            else:
                if new_price_twd > 0:
                    lowest_price_twd = min(existing_lowest_twd, new_price_twd)
                else:
                    lowest_price_twd = existing_lowest_twd

            cursor.execute(
                """
                UPDATE products SET
                    title = ?,
                    price_jpy = ?,
                    price_twd = ?,
                    image_url = ?,
                    product_url = ?,
                    last_updated = ?,
                    lowest_price_jpy = ?,
                    lowest_price_twd = ?
                WHERE id = ?
            """,
                (
                    product["title"],
                    product["price_jpy"],
                    product["price_twd"],
                    product["image_url"],
                    product["product_url"],
                    now,
                    lowest_price_jpy,
                    lowest_price_twd,
                    product["id"],
                ),
            )
        else:
            # 新增商品
            lowest_price_jpy = (
                product["price_jpy"] if product["price_jpy"] > 0 else None
            )
            lowest_price_twd = (
                product["price_twd"] if product["price_twd"] > 0 else None
            )

            cursor.execute(
                """
                INSERT INTO products (
                    id, title, price_jpy, price_twd, image_url, product_url,
                    first_seen, last_updated, lowest_price_jpy, lowest_price_twd
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    product["id"],
                    product["title"],
                    product["price_jpy"],
                    product["price_twd"],
                    product["image_url"],
                    product["product_url"],
                    now,
                    now,
                    lowest_price_jpy,
                    lowest_price_twd,
                ),
            )

        conn.commit()
        conn.close()

    def compare_products(self, current_products: List[Dict]) -> Dict[str, List[Dict]]:
        """
        比較當前商品與資料庫中的商品
        只比較兩次搜尋都出現的商品
        返回: {"new": [...], "price_dropped": [...]}
        """
        current_ids = {p["id"] for p in current_products}
        existing_products = self.get_existing_products(current_ids)

        new_products = []
        price_dropped_products = []

        for product in current_products:
            product_id = product["id"]
            if product_id not in existing_products:
                # 新商品
                new_products.append(product)
                self.upsert_product(product)
            else:
                # 已存在的商品，檢查價格是否降低
                existing = existing_products[product_id]
                # 只以日幣價格作為比價基準（避免匯率變動造成的誤判）
                price_dropped = False
                old_price_jpy = existing["lowest_price_jpy"]
                new_price_jpy = product["price_jpy"]

                # 只檢查日圓價格是否降低（需要兩個價格都 > 0 且不為 None）
                if (
                    old_price_jpy is not None
                    and old_price_jpy > 0
                    and new_price_jpy is not None
                    and new_price_jpy > 0
                ):
                    if new_price_jpy < old_price_jpy:
                        price_dropped = True

                # 只有在日幣價格確實降低時才通知
                if price_dropped:
                    price_dropped_products.append(
                        {
                            "product": product,
                            "old_price_jpy": old_price_jpy,
                        }
                    )
                self.upsert_product(product)

        return {"new": new_products, "price_dropped": price_dropped_products}
