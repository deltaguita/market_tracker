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

## 用 Telegram 管理追蹤商品

直接傳訊息給 bot 即可。有一個獨立的輕量 workflow 每 10 分鐘處理一次指令
（與爬蟲解耦），處理後會更新清單並回覆你：

```
/add <url>
/add <url> | <名稱>
/add <url> | <名稱> | <max_ntd>
/remove <名稱>
/remove <url>
/list
```

- `/add` 只給 URL 時，名稱會自動從網址的 `keyword` 參數推導；重複的網址會自動略過。
- `/remove` 以名稱精確比對移除；名稱重複時請改用完整 URL。
- `/list` 回傳目前追蹤清單。
- `max_ntd` 為可選的台幣價格門檻（正整數）。
- 每則指令只會執行一次（以 `data/commands_offset.txt` 記錄已處理的訊息），不會重工或洗版。

> 註：指令生效與回覆約需數分鐘（受 GitHub Actions 排程延遲影響），並非即時。

## 授權

MIT License
