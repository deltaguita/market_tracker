#!/usr/bin/env python3
"""
在 workflow 的 prepare job 第一步執行：讀取 Telegram /add 指令，
將新的追蹤商品寫入 config/urls.json（去重），之後才生成爬蟲 matrix。

只使用標準庫，可用系統 python3 直接執行，不需 pip install。
"""

import os

from src.url_commands import process_add_commands


def main():
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not bot_token or not chat_id:
        print("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 未設定，略過 /add 處理")
        return

    added = process_add_commands(bot_token, chat_id)
    if added:
        print(f"新增了 {len(added)} 個追蹤項目：")
        for entry in added:
            print(f"  - {entry['name']}: {entry['url']}")
    else:
        print("沒有新增的追蹤項目")


if __name__ == "__main__":
    main()
