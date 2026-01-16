"""
Storage service for multi-source product tracking.

Supports:
- Multiple sources (amazon_us, mercari_jp)
- Two tracking modes: latest_only and full_history
- Source-specific price comparison (USD for Amazon, JPY for Mercari)
"""

import sqlite3
import os
from datetime import datetime
from typing import List, Dict, Optional, Set, Tuple


class ProductStorage:
    """商品儲存服務"""
    
    # Valid source identifiers
    VALID_SOURCES = {"amazon_us", "mercari_jp"}
    
    def __init__(self, db_path: str = "data/products.db"):
        self.db_path = db_path
        self._run_migrations()
        self._ensure_db_exists()

    def _run_migrations(self) -> None:
        """執行資料庫遷移"""
        from core.migrator import DatabaseMigrator
        migrator = DatabaseMigrator(self.db_path)
        migrator.migrate()

    def _ensure_db_exists(self):
        """確保資料庫檔案和資料表存在"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.execute("PRAGMA journal_mode=WAL")
        cursor = conn.cursor()
        
        # 主商品表（新增 source, price_usd, variant_name, lowest_price_usd 欄位）
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id TEXT,
                source TEXT,
                title TEXT,
                price_jpy INTEGER,
                price_twd INTEGER,
                price_usd REAL,
                image_url TEXT,
                product_url TEXT,
                variant_name TEXT,
                first_seen TEXT,
                last_updated TEXT,
                lowest_price_jpy INTEGER,
                lowest_price_twd INTEGER,
                lowest_price_usd REAL,
                PRIMARY KEY (id, source)
            )
        """)
        
        # 價格歷史表（用於 full_history 模式）
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS price_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id TEXT,
                source TEXT,
                price_jpy INTEGER,
                price_twd INTEGER,
                price_usd REAL,
                observed_at TEXT,
                FOREIGN KEY (product_id, source) REFERENCES products(id, source)
            )
        """)
        
        # 索引
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_products_source ON products(source)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_products_id_source ON products(id, source)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_price_history_product 
            ON price_history(product_id, source)
        """)
        
        conn.commit()
        conn.close()


    def _validate_source(self, source: str) -> None:
        """驗證來源名稱"""
        if source not in self.VALID_SOURCES:
            raise ValueError(
                f"Invalid source: {source}. Must be one of {self.VALID_SOURCES}"
            )

    def _get_price_field(self, source: str) -> str:
        """根據來源返回對應的價格欄位名稱"""
        if source == "amazon_us":
            return "price_usd"
        else:  # mercari_jp
            return "price_jpy"

    def _get_lowest_price_field(self, source: str) -> str:
        """根據來源返回對應的最低價格欄位名稱"""
        if source == "amazon_us":
            return "lowest_price_usd"
        else:  # mercari_jp
            return "lowest_price_jpy"

    def _get_price_value(self, product: Dict, source: str) -> Optional[float]:
        """從商品資料中取得對應來源的價格"""
        price_field = self._get_price_field(source)
        return product.get(price_field)

    def get_existing_products(
        self, 
        product_ids: Set[str], 
        source: str
    ) -> Dict[str, Dict]:
        """取得現有商品資料（只查詢指定來源和 ID 的商品）"""
        if not product_ids:
            return {}
        
        self._validate_source(source)
        
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        placeholders = ",".join("?" * len(product_ids))
        cursor.execute(
            f"SELECT * FROM products WHERE id IN ({placeholders}) AND source = ?",
            list(product_ids) + [source]
        )
        columns = [desc[0] for desc in cursor.description]
        products = {}
        for row in cursor.fetchall():
            product = dict(zip(columns, row))
            products[product["id"]] = product
        conn.close()
        return products

    def get_product(self, product_id: str, source: str) -> Optional[Dict]:
        """取得單一商品資料"""
        self._validate_source(source)
        
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM products WHERE id = ? AND source = ?",
            (product_id, source)
        )
        row = cursor.fetchone()
        conn.close()
        
        if row:
            columns = [desc[0] for desc in cursor.description]
            return dict(zip(columns, row))
        return None


    def get_price_history(
        self, 
        product_id: str, 
        source: str
    ) -> List[Dict]:
        """取得商品的價格歷史記錄"""
        self._validate_source(source)
        
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        cursor.execute(
            """SELECT * FROM price_history 
               WHERE product_id = ? AND source = ? 
               ORDER BY observed_at ASC""",
            (product_id, source)
        )
        columns = [desc[0] for desc in cursor.description]
        history = [dict(zip(columns, row)) for row in cursor.fetchall()]
        conn.close()
        return history

    def _append_price_history(
        self, 
        product: Dict, 
        source: str
    ) -> None:
        """新增價格歷史記錄（用於 full_history 模式）"""
        now = datetime.now().isoformat()
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        
        cursor.execute(
            """INSERT INTO price_history 
               (product_id, source, price_jpy, price_twd, price_usd, observed_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                product["id"],
                source,
                product.get("price_jpy"),
                product.get("price_twd"),
                product.get("price_usd"),
                now
            )
        )
        
        conn.commit()
        conn.close()

    def _update_latest_price(
        self, 
        product: Dict, 
        source: str
    ) -> None:
        """更新商品最新價格（用於 latest_only 模式）"""
        now = datetime.now().isoformat()
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()

        # 檢查商品是否已存在
        cursor.execute(
            """SELECT id, lowest_price_jpy, lowest_price_twd, lowest_price_usd 
               FROM products WHERE id = ? AND source = ?""",
            (product["id"], source)
        )
        existing = cursor.fetchone()

        if existing:
            existing_id, existing_lowest_jpy, existing_lowest_twd, existing_lowest_usd = existing
            
            # 更新最低價格
            lowest_price_jpy = self._calculate_lowest_price(
                existing_lowest_jpy, product.get("price_jpy")
            )
            lowest_price_twd = self._calculate_lowest_price(
                existing_lowest_twd, product.get("price_twd")
            )
            lowest_price_usd = self._calculate_lowest_price(
                existing_lowest_usd, product.get("price_usd")
            )

            cursor.execute(
                """UPDATE products SET
                    title = ?,
                    price_jpy = ?,
                    price_twd = ?,
                    price_usd = ?,
                    image_url = ?,
                    product_url = ?,
                    variant_name = ?,
                    last_updated = ?,
                    lowest_price_jpy = ?,
                    lowest_price_twd = ?,
                    lowest_price_usd = ?
                WHERE id = ? AND source = ?""",
                (
                    product.get("title"),
                    product.get("price_jpy"),
                    product.get("price_twd"),
                    product.get("price_usd"),
                    product.get("image_url"),
                    product.get("product_url"),
                    product.get("variant_name"),
                    now,
                    lowest_price_jpy,
                    lowest_price_twd,
                    lowest_price_usd,
                    product["id"],
                    source
                )
            )
        else:
            # 新增商品
            self._insert_new_product(product, source, cursor, now)

        conn.commit()
        conn.close()


    def _calculate_lowest_price(
        self, 
        existing_lowest: Optional[float], 
        new_price: Optional[float]
    ) -> Optional[float]:
        """計算最低價格"""
        # 如果舊的最低價是 None 或 <= 1（可能是初始值或錯誤值）
        if existing_lowest is None or existing_lowest <= 1:
            return new_price if new_price and new_price > 0 else None
        
        # 只比較有實際價格的情況
        if new_price and new_price > 0:
            return min(existing_lowest, new_price)
        return existing_lowest

    def _insert_new_product(
        self, 
        product: Dict, 
        source: str, 
        cursor, 
        now: str
    ) -> None:
        """插入新商品記錄"""
        price_jpy = product.get("price_jpy")
        price_twd = product.get("price_twd")
        price_usd = product.get("price_usd")
        
        lowest_price_jpy = price_jpy if price_jpy and price_jpy > 0 else None
        lowest_price_twd = price_twd if price_twd and price_twd > 0 else None
        lowest_price_usd = price_usd if price_usd and price_usd > 0 else None

        cursor.execute(
            """INSERT INTO products (
                id, source, title, price_jpy, price_twd, price_usd,
                image_url, product_url, variant_name,
                first_seen, last_updated, 
                lowest_price_jpy, lowest_price_twd, lowest_price_usd
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                product["id"],
                source,
                product.get("title"),
                price_jpy,
                price_twd,
                price_usd,
                product.get("image_url"),
                product.get("product_url"),
                product.get("variant_name"),
                now,
                now,
                lowest_price_jpy,
                lowest_price_twd,
                lowest_price_usd
            )
        )

    def upsert_product(
        self, 
        product: Dict, 
        source: str,
        tracking_mode: str = "latest_only"
    ) -> None:
        """
        新增或更新商品
        
        Args:
            product: 商品資料
            source: 來源名稱 (amazon_us, mercari_jp)
            tracking_mode: "latest_only" 或 "full_history"
        """
        self._validate_source(source)
        
        # 確保商品記錄存在
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id FROM products WHERE id = ? AND source = ?",
            (product["id"], source)
        )
        exists = cursor.fetchone() is not None
        conn.close()
        
        if not exists:
            # 新商品，先建立記錄
            now = datetime.now().isoformat()
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            cursor = conn.cursor()
            self._insert_new_product(product, source, cursor, now)
            conn.commit()
            conn.close()
        
        # 根據模式更新價格
        if tracking_mode == "full_history":
            self._append_price_history(product, source)
            # 同時更新主表的最新價格
            self._update_latest_price(product, source)
        else:
            self._update_latest_price(product, source)


    def get_latest_price_from_history(
        self, 
        product_id: str, 
        source: str
    ) -> Optional[Dict]:
        """
        取得商品在 price_history 表中的最新價格記錄
        
        Args:
            product_id: 商品 ID
            source: 來源名稱
        
        Returns:
            最新的價格記錄，如果沒有則返回 None
        """
        self._validate_source(source)
        
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        cursor.execute(
            """SELECT price_jpy, price_twd, price_usd, observed_at 
               FROM price_history 
               WHERE product_id = ? AND source = ? 
               ORDER BY observed_at DESC 
               LIMIT 1""",
            (product_id, source)
        )
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {
                "price_jpy": row[0],
                "price_twd": row[1],
                "price_usd": row[2],
                "observed_at": row[3]
            }
        return None

    def detect_price_drop(
        self,
        product: Dict,
        source: str,
        tracking_mode: str = "latest_only"
    ) -> Optional[Dict]:
        """
        檢測商品是否降價
        
        在 full_history 模式下，比較新價格與 price_history 中的最新價格。
        在 latest_only 模式下，比較新價格與 products 表中的最低價格。
        
        Args:
            product: 當前商品資料
            source: 來源名稱
            tracking_mode: 追蹤模式
        
        Returns:
            如果降價，返回包含舊價格資訊的字典；否則返回 None
        """
        price_field = self._get_price_field(source)
        new_price = product.get(price_field)
        
        if new_price is None or new_price <= 0:
            return None
        
        if tracking_mode == "full_history":
            # full_history 模式：比較與 price_history 中最新價格
            latest_history = self.get_latest_price_from_history(product["id"], source)
            if latest_history:
                old_price = latest_history.get(price_field)
                if old_price is not None and old_price > 0 and new_price < old_price:
                    result = {
                        "product": product,
                        f"old_{price_field}": old_price,
                    }
                    # 對於 mercari_jp，也包含舊的 TWD 價格
                    if source == "mercari_jp" and latest_history.get("price_twd"):
                        result["old_price_twd"] = latest_history["price_twd"]
                    return result
        else:
            # latest_only 模式：比較與 products 表中的最低價格
            existing = self.get_product(product["id"], source)
            if existing:
                lowest_price_field = self._get_lowest_price_field(source)
                old_price = existing.get(lowest_price_field)
                if old_price is not None and old_price > 0 and new_price < old_price:
                    result = {
                        "product": product,
                        f"old_{price_field}": old_price,
                    }
                    # 對於 mercari_jp，也包含舊的 TWD 價格
                    if source == "mercari_jp" and existing.get("lowest_price_twd"):
                        result["old_price_twd"] = existing["lowest_price_twd"]
                    return result
        
        return None

    def compare_products(
        self, 
        current_products: List[Dict], 
        source: str,
        tracking_mode: str = "latest_only"
    ) -> Dict[str, List[Dict]]:
        """
        比較當前商品與資料庫中的商品
        
        Args:
            current_products: 當前爬取的商品列表
            source: 來源名稱 (amazon_us, mercari_jp)
            tracking_mode: "latest_only" 或 "full_history"
        
        Returns:
            {"new": [...], "price_dropped": [...]}
        """
        self._validate_source(source)
        
        current_ids = {p["id"] for p in current_products}
        existing_products = self.get_existing_products(current_ids, source)

        new_products = []
        price_dropped_products = []

        for product in current_products:
            product_id = product["id"]
            
            if product_id not in existing_products:
                # 新商品
                new_products.append(product)
                self.upsert_product(product, source, tracking_mode)
            else:
                # 已存在的商品，檢查價格是否降低
                # 必須在 upsert 之前檢測，否則會比較到剛寫入的價格
                price_drop_info = self.detect_price_drop(product, source, tracking_mode)
                
                if price_drop_info:
                    price_dropped_products.append(price_drop_info)
                
                self.upsert_product(product, source, tracking_mode)

        return {"new": new_products, "price_dropped": price_dropped_products}

    def get_price_history_count(self, product_id: str, source: str) -> int:
        """取得商品的價格歷史記錄數量"""
        self._validate_source(source)
        
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM price_history WHERE product_id = ? AND source = ?",
            (product_id, source)
        )
        count = cursor.fetchone()[0]
        conn.close()
        return count

    def get_product_count(self, source: str) -> int:
        """取得指定來源的商品數量"""
        self._validate_source(source)
        
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM products WHERE source = ?",
            (source,)
        )
        count = cursor.fetchone()[0]
        conn.close()
        return count
