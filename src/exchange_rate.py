"""
匯率獲取模組
提供日幣兌台幣的匯率查詢功能
從 SQLite 資料庫讀取匯率，避免重複 API 調用
"""
import sqlite3
import os
from typing import Optional
from datetime import datetime


class ExchangeRate:
    """匯率查詢類別"""

    def __init__(self, db_path: str = "data/exchange_rate.db"):
        self.db_path = db_path
        self.exchange_rate: Optional[float] = None
        self._initialize_db()

    def _initialize_db(self):
        """初始化資料庫，建立匯率表格"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS exchange_rates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    currency_pair TEXT NOT NULL UNIQUE,
                    rate REAL NOT NULL,
                    updated_at TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_currency_pair ON exchange_rates(currency_pair)")
            conn.commit()

    def fetch_jpy_to_twd_rate_from_api(self) -> float:
        """
        從 API 獲取日幣兌台幣的匯率並存入資料庫

        Returns:
            float: JPY 兌 TWD 的匯率（1 JPY = X TWD）
        """
        import requests
        try:
            response = requests.get("https://tw.rter.info/capi.php", timeout=10)
            response.raise_for_status()
            data = response.json()

            # 獲取 USD/JPY 和 USD/TWD 的匯率
            usd_jpy = data.get("USDJPY", {}).get("Exrate", 0)
            usd_twd = data.get("USDTWD", {}).get("Exrate", 0)

            if usd_jpy > 0 and usd_twd > 0:
                # 計算 JPY 兌 TWD：1 JPY = (USD/TWD) / (USD/JPY) TWD
                rate = usd_twd / usd_jpy
                now = datetime.now().isoformat()

                # 存入資料庫
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT OR REPLACE INTO exchange_rates 
                        (currency_pair, rate, updated_at, created_at)
                        VALUES (?, ?, ?, 
                            COALESCE((SELECT created_at FROM exchange_rates WHERE currency_pair = ?), ?))
                    """, ("JPY_TWD", rate, now, "JPY_TWD", now))
                    conn.commit()

                print(f"匯率獲取成功並存入資料庫: 1 JPY = {rate:.4f} TWD")
                self.exchange_rate = rate
                return rate
            else:
                print("警告: 無法從 API 獲取匯率，使用預設值 0.21")
                self.exchange_rate = 0.21
                return self.exchange_rate
        except Exception as e:
            print(f"獲取匯率失敗: {e}，使用預設值 0.21")
            self.exchange_rate = 0.21
            return self.exchange_rate

    def get_jpy_to_twd_rate_from_db(self) -> Optional[float]:
        """
        從資料庫讀取日幣兌台幣的匯率

        Returns:
            Optional[float]: JPY 兌 TWD 的匯率，如果資料庫中沒有則返回 None
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT rate, updated_at FROM exchange_rates 
                    WHERE currency_pair = 'JPY_TWD' 
                    ORDER BY updated_at DESC LIMIT 1
                """)
                result = cursor.fetchone()
                if result:
                    rate, updated_at = result
                    self.exchange_rate = rate
                    print(f"從資料庫讀取匯率: 1 JPY = {rate:.4f} TWD (更新時間: {updated_at})")
                    return rate
                else:
                    print("資料庫中沒有匯率資料")
                    return None
        except Exception as e:
            print(f"從資料庫讀取匯率失敗: {e}")
            return None

    def fetch_jpy_to_twd_rate(self) -> float:
        """
        獲取日幣兌台幣的匯率（優先從資料庫讀取）

        Returns:
            float: JPY 兌 TWD 的匯率（1 JPY = X TWD）
        """
        # 先嘗試從資料庫讀取
        rate = self.get_jpy_to_twd_rate_from_db()
        if rate is not None:
            return rate

        # 如果資料庫中沒有，則從 API 獲取（這種情況應該很少發生，因為 workflow 會先更新）
        print("資料庫中沒有匯率，嘗試從 API 獲取...")
        return self.fetch_jpy_to_twd_rate_from_api()

    def convert_jpy_to_twd(self, jpy_amount: int) -> int:
        """
        將日幣金額轉換為台幣

        Args:
            jpy_amount: 日幣金額

        Returns:
            int: 台幣金額（四捨五入到整數）
        """
        if self.exchange_rate is None:
            self.fetch_jpy_to_twd_rate()

        if self.exchange_rate:
            return int(jpy_amount * self.exchange_rate)
        else:
            return 0

    def get_rate(self) -> Optional[float]:
        """
        獲取當前匯率（如果尚未獲取則先獲取）

        Returns:
            Optional[float]: JPY 兌 TWD 的匯率
        """
        if self.exchange_rate is None:
            self.fetch_jpy_to_twd_rate()
        return self.exchange_rate


# 提供一個全局實例，方便直接使用
_exchange_rate_instance = None


def get_exchange_rate() -> ExchangeRate:
    """
    獲取全局匯率實例（單例模式）

    Returns:
        ExchangeRate: 匯率實例
    """
    global _exchange_rate_instance
    if _exchange_rate_instance is None:
        _exchange_rate_instance = ExchangeRate()
        _exchange_rate_instance.fetch_jpy_to_twd_rate()
    return _exchange_rate_instance
