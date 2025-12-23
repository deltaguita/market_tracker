#!/usr/bin/env python3
"""
測試環境變數讀取
"""
try:
    from dotenv import load_dotenv
    import os

    # 載入 .env 檔案
    load_dotenv()

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    print("=" * 60)
    print("環境變數測試")
    print("=" * 60)
    print(f"TELEGRAM_BOT_TOKEN: {'✓ 已設定' if bot_token and bot_token != 'your_bot_token_here' else '✗ 未設定（請編輯 .env 檔案）'}")
    print(f"TELEGRAM_CHAT_ID: {'✓ 已設定' if chat_id and chat_id != 'your_chat_id_here' else '✗ 未設定（請編輯 .env 檔案）'}")
    print("=" * 60)

    if bot_token and bot_token != 'your_bot_token_here' and chat_id and chat_id != 'your_chat_id_here':
        print("\n✓ 環境變數已正確設定，可以執行 main.py")
    else:
        print("\n⚠ 請編輯 .env 檔案，填入實際的 TELEGRAM_BOT_TOKEN 和 TELEGRAM_CHAT_ID")
        print("   範例檔案：.env.example")

except ImportError:
    print("✗ 錯誤：未安裝 python-dotenv")
    print("\n請執行以下指令安裝：")
    print("  python3 -m pip install --user python-dotenv")
    print("  或")
    print("  pip install python-dotenv")

