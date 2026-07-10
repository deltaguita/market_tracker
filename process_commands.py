#!/usr/bin/env python3
"""
commands.yml 的進入點：讀取 Telegram /add、/remove、/list 指令，
更新 config/urls.json，並以 data/commands_offset.txt marker 記住已處理的指令。

只使用標準庫，可用系統 python3 直接執行，不需 pip install。
"""

import os

from src.url_commands import process_commands


def main():
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not bot_token or not chat_id:
        print("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 未設定，略過指令處理")
        return

    summary = process_commands(bot_token, chat_id)

    if summary["added"]:
        print(f"新增 {len(summary['added'])} 筆：")
        for e in summary["added"]:
            print(f"  + {e['name']}: {e['url']}")
    if summary["removed"]:
        print(f"移除 {len(summary['removed'])} 筆：")
        for e in summary["removed"]:
            print(f"  - {e.get('name')}: {e.get('url')}")
    if summary["listed"]:
        print(f"回覆 /list {summary['listed']} 次")
    if not (summary["added"] or summary["removed"] or summary["listed"]):
        print("沒有待處理的指令")


if __name__ == "__main__":
    main()
