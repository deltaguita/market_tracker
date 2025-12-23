#!/usr/bin/env python3
"""
更新匯率腳本
從 API 獲取最新匯率並存入 SQLite 資料庫
此腳本應在 workflow 中執行，在所有爬蟲之前運行
"""
from src.exchange_rate import ExchangeRate


def main():
    """更新匯率"""
    print("=" * 60)
    print("更新匯率")
    print("=" * 60)

    exchange_rate = ExchangeRate()
    rate = exchange_rate.fetch_jpy_to_twd_rate_from_api()

    if rate:
        print(f"\n✓ 匯率更新成功: 1 JPY = {rate:.4f} TWD")
    else:
        print("\n✗ 匯率更新失敗")


if __name__ == "__main__":
    main()

