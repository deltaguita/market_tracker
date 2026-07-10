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

## 用 Telegram 新增追蹤商品

直接傳訊息給 bot 即可，下一次 workflow 執行時會自動加入清單並開始追蹤：

```
/add <url>
/add <url> | <名稱>
/add <url> | <名稱> | <max_ntd>
```

- 只給 URL 時，名稱會自動從網址的 `keyword` 參數推導。
- `max_ntd` 為可選的台幣價格門檻（正整數）。
- 重複的網址會自動略過，不會重複加入。

## 授權

MIT License
