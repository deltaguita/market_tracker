# Market Tracker
商品追蹤系統

## 簡介

自動追蹤商品價格變動，透過 Telegram 發送通知。

## 設定

1. 設定 GitHub Secrets：
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`

2. 編輯 `config/urls.json` 設定追蹤網址

3. Workflow 會自動執行（每 6 小時）

## 授權

MIT License
