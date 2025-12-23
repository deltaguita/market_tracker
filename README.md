# Mercari 商品追蹤系統

自動追蹤 Mercari 商品，當有新商品上架或價格降低時，透過 Telegram Bot 發送通知（含圖片）。

## 功能特色

- 🔍 自動爬取 Mercari 商品列表（支援多頁翻頁）
- 📊 使用 SQLite 資料庫儲存商品資訊
- 🔔 新商品上架通知
- 💰 價格降低通知（含降價幅度）
- 📸 通知包含商品圖片
- ⏰ GitHub Actions 定時執行（每 6 小時）
- 🔄 自動 commit 資料庫更新到 Git

## 專案結構

```
market_tracker/
├── .github/
│   └── workflows/
│       └── track_products.yml      # GitHub Actions 定時任務
├── src/
│   ├── scraper.py                  # 商品爬蟲主程式
│   ├── notifier.py                 # Telegram 通知模組
│   └── storage.py                  # 商品資料儲存與比較
├── data/
│   └── products.db                 # 商品資料庫（SQLite）
├── config/
│   └── urls.json                   # 追蹤的網址列表
├── requirements.txt                # Python 依賴套件
├── main.py                         # 主程式
└── README.md                       # 本檔案
```

## 設定步驟

### 1. 建立 Telegram Bot

1. 在 Telegram 搜尋 `@BotFather`
2. 發送 `/newbot` 指令
3. 依照指示設定 Bot 名稱和 username（需以 `_bot` 結尾）
4. 取得 Bot Token
5. 對你的 Bot 發送任意訊息
6. 訪問 `https://api.telegram.org/bot<TOKEN>/getUpdates`
7. 從回應中找到 `chat.id`

### 2. 設定 GitHub Secrets

在 GitHub Repo 的 Settings → Secrets and variables → Actions 中新增：

- `TELEGRAM_BOT_TOKEN`: 你的 Telegram Bot Token
- `TELEGRAM_CHAT_ID`: 接收通知的 Chat ID

### 3. 設定追蹤網址

編輯 `config/urls.json`，加入要追蹤的商品搜尋網址：

```json
{
  "tracking_urls": [
    {
      "name": "レキ FX",
      "url": "https://jp.mercari.com/zh-TW/search?keyword=%E3%83%AC%E3%82%AD%20FX"
    }
  ]
}
```

**注意**：系統會自動在網址上補充 `&status=on_sale` 參數，確保只爬取銷售中的商品。

### 4. 本地測試

```bash
# 安裝依賴
pip install -r requirements.txt
# 或使用 --user 安裝（如果遇到權限問題）
python3 -m pip install --user -r requirements.txt

# 安裝 Playwright 瀏覽器
playwright install chromium

# 設定環境變數（複製範例檔案並填入實際值）
cp .env.example .env
# 編輯 .env 檔案，填入你的 TELEGRAM_BOT_TOKEN 和 TELEGRAM_CHAT_ID

# 測試環境變數是否正確讀取
python test_env.py

# 執行主程式
python main.py
```

**注意**：
- `.env` 檔案已加入 `.gitignore`，不會被提交到 Git
- 請使用 `.env.example` 作為範本
- 如果遇到 `ModuleNotFoundError: No module named 'dotenv'`，請執行：
  ```bash
  python3 -m pip install --user python-dotenv
  ```

## 工作原理

1. **爬取商品**：
   - 讀取 `config/urls.json` 中的追蹤網址
   - 自動補充 `&status=on_sale` 參數
   - 使用 Playwright 爬取所有頁面的商品
   - 提取商品 ID、名稱、價格、圖片、連結

2. **比較更新**：
   - 從 SQLite 資料庫讀取現有商品
   - 只比較兩次搜尋都出現的商品
   - 識別新商品和價格降低的商品
   - 更新資料庫（只保留最新狀態）

3. **發送通知**：
   - 新商品上架：發送商品資訊和圖片
   - 價格降低：發送降價資訊和降價幅度

4. **自動提交**：
   - GitHub Actions 自動 commit 更新的資料庫到 Git

## 資料庫結構

商品資料儲存在 `data/products.db`（SQLite），包含以下欄位：

- `id`: 商品唯一識別碼
- `title`: 商品名稱
- `price_jpy`: 日圓價格（最新）
- `price_twd`: 台幣價格（最新）
- `image_url`: 商品圖片 URL
- `product_url`: 商品頁面連結
- `first_seen`: 首次發現時間
- `last_updated`: 最後更新時間
- `lowest_price_jpy`: 歷史最低日圓價格
- `lowest_price_twd`: 歷史最低台幣價格

## 排程設定

GitHub Actions 預設每 6 小時執行一次（UTC 時間）。可在 `.github/workflows/track_products.yml` 中修改 `cron` 設定。

## 注意事項

- 商品消失（不在搜尋結果中）不會觸發通知，也不會從資料庫刪除
- 只追蹤銷售中的商品（`status=on_sale`）
- 每個商品只保留最新狀態，不保留歷史版本
- 價格降低判斷基準：當前價格低於歷史最低價

## 授權

MIT License

