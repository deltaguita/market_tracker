"""
Database migration system for SQLite.

Provides version tracking and automatic schema migrations.
Designed to be lightweight and simple, without external ORM dependencies.
"""

import sqlite3
import logging
from datetime import datetime
from typing import Dict, Callable, Optional

logger = logging.getLogger(__name__)


class MigrationError(Exception):
    """遷移過程中發生的錯誤"""
    pass


class VersionDetectionError(MigrationError):
    """無法檢測當前版本"""
    pass


class DatabaseMigrator:
    """
    資料庫遷移管理器
    
    負責：
    - 版本檢測（V0 全新、V1 舊版、V2 新版）
    - 遷移執行（依版本順序執行待處理遷移）
    - 版本記錄（維護 schema_version 表）
    """
    
    CURRENT_VERSION = 2  # 目標版本號
    
    def __init__(self, db_path: str):
        """
        初始化遷移器
        
        Args:
            db_path: 資料庫檔案路徑
        """
        self.db_path = db_path
        self._migrations: Dict[int, Callable[[sqlite3.Connection], None]] = {}
        self._register_migrations()
    
    def _register_migrations(self) -> None:
        """註冊所有遷移腳本"""
        self._migrations[2] = self._migrate_v1_to_v2
    
    def get_current_version(self) -> int:
        """
        取得當前 schema 版本
        
        檢測邏輯：
        1. 如果 schema_version 表存在，讀取最新版本
        2. 如果表不存在但 products 表存在：
           - 檢查是否有 source 欄位 → V2
           - 沒有 source 欄位 → V1
        3. 如果都不存在 → V0（全新資料庫）
        
        Returns:
            當前版本號 (0, 1, 或 2)
        
        Raises:
            VersionDetectionError: 無法檢測版本時
        """
        try:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            cursor = conn.cursor()
            
            # 1. 檢查 schema_version 表是否存在
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='schema_version'
            """)
            schema_version_exists = cursor.fetchone() is not None
            
            if schema_version_exists:
                # 讀取最新版本
                cursor.execute(
                    "SELECT MAX(version) FROM schema_version"
                )
                result = cursor.fetchone()
                if result and result[0] is not None:
                    conn.close()
                    logger.debug(f"Detected schema version from table: {result[0]}")
                    return result[0]
                # 表存在但沒有記錄，繼續檢查 products 表結構
                logger.debug("schema_version table exists but empty, checking products table structure")
            
            # 2. 檢查 products 表是否存在
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='products'
            """)
            if cursor.fetchone():
                # 檢查是否有 source 欄位
                cursor.execute("PRAGMA table_info(products)")
                columns = [row[1] for row in cursor.fetchall()]
                conn.close()
                
                if "source" in columns:
                    # 有 source 欄位 → V2
                    logger.debug("Detected V2 schema (has source column)")
                    return 2
                else:
                    # 沒有 source 欄位 → V1
                    logger.debug("Detected V1 schema (no source column)")
                    return 1
            
            # 3. 都不存在 → V0（全新資料庫）
            conn.close()
            logger.debug("No existing tables, treating as V0 (fresh database)")
            return 0
            
        except sqlite3.Error as e:
            raise VersionDetectionError(f"Failed to detect schema version: {e}")
    
    def migrate(self) -> None:
        """
        執行所有待處理的遷移
        
        從當前版本依序執行到目標版本。
        """
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        try:
            self._ensure_version_table(conn)
        finally:
            conn.close()
        
        current_version = self.get_current_version()
        target_version = self.CURRENT_VERSION
        
        if current_version >= target_version:
            logger.info(f"Database is already at version {current_version}, no migration needed")
            return
        
        logger.info(f"Current version: {current_version}, target version: {target_version}")
        
        # 處理 V0（全新資料庫）情況
        if current_version == 0:
            logger.info("Detected fresh database (V0), initializing to V2 schema")
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            try:
                conn.execute("BEGIN TRANSACTION")
                self._create_v2_schema(conn)
                self._record_version(conn, 2, "Initial V2 schema")
                conn.commit()
                logger.info("Database initialized to V2 schema")
            except Exception as e:
                conn.rollback()
                logger.error(f"Failed to initialize V2 schema: {e}")
                raise MigrationError(f"Failed to initialize V2 schema: {e}") from e
            finally:
                conn.close()
            return
        
        # 依序執行待處理的遷移
        for version in range(current_version + 1, target_version + 1):
            if version in self._migrations:
                logger.info(f"Executing migration to version {version}")
                self._execute_migration(version, self._migrations[version])
            else:
                logger.warning(f"No migration function registered for version {version}, skipping")
        
        logger.info(f"Migration completed. Database is now at version {target_version}")
    
    def _ensure_version_table(self, conn: sqlite3.Connection) -> None:
        """
        確保版本表存在
        
        建立 schema_version 表用於追蹤資料庫版本。
        
        Args:
            conn: 資料庫連線
        """
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL,
                description TEXT
            )
        """)
        logger.debug("Ensured schema_version table exists")
    
    def _record_version(
        self, 
        conn: sqlite3.Connection, 
        version: int, 
        description: str = ""
    ) -> None:
        """
        記錄遷移版本
        
        Args:
            conn: 資料庫連線
            version: 版本號
            description: 遷移描述
        """
        cursor = conn.cursor()
        applied_at = datetime.now().isoformat()
        cursor.execute(
            """INSERT OR REPLACE INTO schema_version 
               (version, applied_at, description) 
               VALUES (?, ?, ?)""",
            (version, applied_at, description)
        )
        logger.info(f"Recorded schema version {version}: {description}")
    
    def _execute_migration(
        self, 
        version: int, 
        migration_func: Callable[[sqlite3.Connection], None]
    ) -> None:
        """
        安全執行單一遷移
        
        使用交易確保原子性，失敗時回滾。
        
        Args:
            version: 目標版本號
            migration_func: 遷移函數
        """
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        try:
            conn.execute("BEGIN TRANSACTION")
            logger.info(f"Starting migration to version {version}")
            
            migration_func(conn)
            
            self._record_version(conn, version, f"Migration to version {version}")
            conn.commit()
            logger.info(f"Migration to version {version} completed successfully")
        except Exception as e:
            conn.rollback()
            logger.error(f"Migration to version {version} failed: {e}")
            raise MigrationError(f"Failed to migrate to version {version}: {e}") from e
        finally:
            conn.close()
    
    def _migrate_v1_to_v2(self, conn: sqlite3.Connection) -> None:
        """
        V1 到 V2 的遷移邏輯
        
        變更內容：
        - 新增 source 欄位（預設 "mercari_jp"）
        - 新增 price_usd, variant_name, lowest_price_usd 欄位
        - 重建表以支援複合主鍵 (id, source)
        - 建立 price_history 表
        - 建立必要索引
        
        Args:
            conn: 資料庫連線
        """
        cursor = conn.cursor()
        
        # 檢查 products 表是否存在
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='products'
        """)
        products_exists = cursor.fetchone() is not None
        
        if not products_exists:
            # 如果 products 表不存在，直接建立 V2 schema
            logger.info("Products table does not exist, creating V2 schema directly")
            self._create_v2_schema(conn)
            return
        
        # 檢查是否已經是 V2 schema
        cursor.execute("PRAGMA table_info(products)")
        columns = [row[1] for row in cursor.fetchall()]
        if "source" in columns:
            logger.info("Products table already has V2 schema, skipping migration")
            return
        
        logger.info("Starting V1 to V2 migration")
        
        # 1. 建立備份表
        cursor.execute("""
            CREATE TABLE products_backup_v1 AS 
            SELECT * FROM products
        """)
        logger.debug("Created backup table products_backup_v1")
        
        # 2. 刪除舊的 products 表
        cursor.execute("DROP TABLE products")
        logger.debug("Dropped old products table")
        
        # 3. 建立新的 V2 schema products 表
        self._create_v2_schema(conn)
        
        # 4. 從備份表遷移資料，設定 source = "mercari_jp"
        cursor.execute("""
            INSERT INTO products (
                id, source, title, price_jpy, price_twd, price_usd,
                image_url, product_url, variant_name,
                first_seen, last_updated,
                lowest_price_jpy, lowest_price_twd, lowest_price_usd
            )
            SELECT 
                id, 'mercari_jp', title, price_jpy, price_twd, NULL,
                image_url, product_url, NULL,
                first_seen, last_updated,
                lowest_price_jpy, lowest_price_twd, NULL
            FROM products_backup_v1
        """)
        migrated_count = cursor.rowcount
        logger.info(f"Migrated {migrated_count} products from V1 to V2")
        
        # 5. 刪除備份表
        cursor.execute("DROP TABLE products_backup_v1")
        logger.debug("Dropped backup table")
        
        logger.info("V1 to V2 migration completed successfully")
    
    def _create_v2_schema(self, conn: sqlite3.Connection) -> None:
        """
        建立 V2 schema（products 表和 price_history 表及索引）
        
        如果 products 表已存在但結構不是 V2，會先刪除舊表再重建。
        
        Args:
            conn: 資料庫連線
        """
        cursor = conn.cursor()
        
        # 檢查 products 表是否存在及其結構
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='products'
        """)
        products_exists = cursor.fetchone() is not None
        
        if products_exists:
            # 檢查表結構是否為 V2
            cursor.execute("PRAGMA table_info(products)")
            columns = [row[1] for row in cursor.fetchall()]
            if "source" not in columns:
                # 表存在但不是 V2，需要先刪除
                logger.warning("Products table exists but is not V2 schema, dropping and recreating")
                cursor.execute("DROP TABLE products")
        
        # 建立 products 表（V2 schema）
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
        logger.debug("Created products table with V2 schema")
        
        # 建立 price_history 表
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
        logger.debug("Created price_history table")
        
        # 建立索引
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_products_source 
            ON products(source)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_products_id_source 
            ON products(id, source)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_price_history_product 
            ON price_history(product_id, source)
        """)
        logger.debug("Created indexes for V2 schema")
