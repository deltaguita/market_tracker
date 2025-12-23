#!/usr/bin/env python3
"""
合併多個 SQLite 資料庫檔案
用於 Matrix Strategy 中合併各個 track job 的 products.db
"""
import sqlite3
import os
import sys
from pathlib import Path


def merge_databases(source_dbs: list, target_db: str):
    """
    合併多個來源資料庫到目標資料庫
    
    Args:
        source_dbs: 來源資料庫檔案路徑列表
        target_db: 目標資料庫檔案路徑
    """
    # 確保目標目錄存在
    os.makedirs(os.path.dirname(target_db), exist_ok=True)
    
    # 連接目標資料庫
    target_conn = sqlite3.connect(target_db)
    target_conn.execute("PRAGMA journal_mode=WAL")
    target_cursor = target_conn.cursor()
    
    # 確保目標資料庫有正確的 schema
    target_cursor.execute("""
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
    target_cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_id ON products(id)
    """)
    target_conn.commit()
    
    # 合併每個來源資料庫
    for source_db in source_dbs:
        if not os.path.exists(source_db):
            print(f"警告: {source_db} 不存在，跳過")
            continue
            
        print(f"合併 {source_db}...")
        source_conn = sqlite3.connect(source_db)
        source_cursor = source_conn.cursor()
        
        # 讀取所有商品
        source_cursor.execute("SELECT * FROM products")
        columns = [desc[0] for desc in source_cursor.description]
        
        for row in source_cursor.fetchall():
            product = dict(zip(columns, row))
            
            # 檢查目標資料庫中是否已存在
            target_cursor.execute(
                "SELECT id, lowest_price_jpy, lowest_price_twd FROM products WHERE id = ?",
                (product["id"],)
            )
            existing = target_cursor.fetchone()
            
            if existing:
                # 更新現有商品（保留最早 first_seen 和最低價格）
                existing_id, existing_lowest_jpy, existing_lowest_twd = existing
                
                # 取得現有的 first_seen
                target_cursor.execute(
                    "SELECT first_seen FROM products WHERE id = ?",
                    (product["id"],)
                )
                existing_first_seen = target_cursor.fetchone()[0]
                
                # 比較 first_seen，保留較早的
                if product.get("first_seen") and existing_first_seen:
                    if product["first_seen"] < existing_first_seen:
                        first_seen = product["first_seen"]
                    else:
                        first_seen = existing_first_seen
                else:
                    first_seen = product.get("first_seen") or existing_first_seen
                
                # 更新最低價格
                lowest_price_jpy = existing_lowest_jpy
                lowest_price_twd = existing_lowest_twd
                
                if product.get("lowest_price_jpy") and existing_lowest_jpy:
                    if product["lowest_price_jpy"] > 0:
                        if existing_lowest_jpy is None or existing_lowest_jpy <= 1:
                            lowest_price_jpy = product["lowest_price_jpy"]
                        else:
                            lowest_price_jpy = min(existing_lowest_jpy, product["lowest_price_jpy"])
                
                if product.get("lowest_price_twd") and existing_lowest_twd:
                    if product["lowest_price_twd"] > 0:
                        if existing_lowest_twd is None or existing_lowest_twd <= 1:
                            lowest_price_twd = product["lowest_price_twd"]
                        else:
                            lowest_price_twd = min(existing_lowest_twd, product["lowest_price_twd"])
                
                # 更新商品（使用最新的資料，但保留最早的 first_seen 和最低價格）
                target_cursor.execute("""
                    UPDATE products SET
                        title = ?,
                        price_jpy = ?,
                        price_twd = ?,
                        image_url = ?,
                        product_url = ?,
                        first_seen = ?,
                        last_updated = ?,
                        lowest_price_jpy = ?,
                        lowest_price_twd = ?
                    WHERE id = ?
                """, (
                    product.get("title"),
                    product.get("price_jpy"),
                    product.get("price_twd"),
                    product.get("image_url"),
                    product.get("product_url"),
                    first_seen,
                    product.get("last_updated"),
                    lowest_price_jpy,
                    lowest_price_twd,
                    product["id"]
                ))
            else:
                # 新增商品
                target_cursor.execute("""
                    INSERT INTO products (
                        id, title, price_jpy, price_twd, image_url, product_url,
                        first_seen, last_updated, lowest_price_jpy, lowest_price_twd
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    product["id"],
                    product.get("title"),
                    product.get("price_jpy"),
                    product.get("price_twd"),
                    product.get("image_url"),
                    product.get("product_url"),
                    product.get("first_seen"),
                    product.get("last_updated"),
                    product.get("lowest_price_jpy"),
                    product.get("lowest_price_twd")
                ))
        
        source_conn.close()
    
    target_conn.commit()
    target_conn.close()
    print(f"✓ 合併完成，目標資料庫: {target_db}")


def main():
    """主程式"""
    # 從 artifacts 目錄找到所有 products.db
    artifacts_dir = Path("artifacts")
    if not artifacts_dir.exists():
        print("錯誤: artifacts 目錄不存在")
        sys.exit(1)
    
    # 尋找所有 products.db 檔案
    source_dbs = []
    for db_file in artifacts_dir.rglob("products.db"):
        source_dbs.append(str(db_file))
    
    if not source_dbs:
        print("警告: 未找到任何 products.db 檔案")
        # 檢查是否有現有的資料庫
        if os.path.exists("data/products.db"):
            print("使用現有的 data/products.db")
            sys.exit(0)
        else:
            print("錯誤: 沒有可用的資料庫")
            sys.exit(1)
    
    print(f"找到 {len(source_dbs)} 個資料庫檔案:")
    for db in source_dbs:
        print(f"  - {db}")
    
    # 合併到目標資料庫
    target_db = "data/products.db"
    merge_databases(source_dbs, target_db)
    
    # 顯示統計
    conn = sqlite3.connect(target_db)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM products")
    count = cursor.fetchone()[0]
    conn.close()
    print(f"✓ 合併後共有 {count} 個商品")


if __name__ == "__main__":
    main()

