# Market Tracker
免 server 商品追蹤系統，

## 簡介

* 自動追蹤商品價格變動、新品上架，並透過 Telegram 發送通知。
* 不需要架設任何 server，只需要github action runner 就能依照排程執行。
* 費用：0

## 設定

1. 設定 GitHub Secrets：
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`

2. 編輯 `config/urls.json` 設定追蹤網址

3. Workflow 會自動執行（每 6 小時）

## 授權

MIT License
