# STATE.md — market_tracker

## Verified facts
- ignore 忽略清單存在 `data/products.db` 的 `ignored_products` 表（`product_id TEXT PRIMARY KEY`）。
- `compare_products()` (src/storage.py) 會讀 `get_ignored_ids()` 並跳過被忽略的商品，邏輯正確。
- Telegram `/ignore {id}` 由 `notifier.py` 產生可點連結，`telegram_commands.py` 在啟動時經 getUpdates 讀取並 `add_ignored()`。
- CI 流程（.github/workflows/track_products.yml）：`track` matrix job（每 URL 一個）跑 `main_single.py` → 上傳 `products.db` artifact → `finalize` job 跑 `merge_databases.py` 合併 → `git add data/products.db data/exchange_rate.db` commit 回 main。
- `finalize` 只用 artifacts/ 內的 products.db 當來源，target 是 checkout 出的 committed `data/products.db`（合併是 INTO target）。

## Root cause（已修）
- `merge_databases.py` 原本重建 DB 時只建/搬 `products` 表，完全沒處理 `ignored_products`，導致每次排程 commit 回去的 DB 不含忽略清單 → 下一輪忽略失效。
- 證據：committed `data/products.db` 只有 `products` 表（730 筆），`ignored_products` 表根本不存在。

## Fix applied（選項 1，本地程式改動，未動 CI）
- `merge_databases.py`：合併時 `CREATE TABLE IF NOT EXISTS ignored_products`，並對每個來源 `SELECT product_id` 後 `INSERT OR IGNORE` 進 target（容錯：舊格式來源無此表時捕捉 `sqlite3.OperationalError` 跳過）。累積、去重、保留 target 原有忽略 id。
- 新增 `tests/test_merge_databases.py`（5 個測試）。全套 32 tests OK。
- 獨立驗證者（code-review subagent）比對 6 項 Outcomes 全 PASS。

## General rules
- ignore 目前是「只增不刪」的累積模式，沒有 un-ignore 機制。若未來要撤銷忽略需另外設計。
- 動 DB 合併邏輯時，記得任何非 `products` 的表（未來若新增）都要在 merge 一併處理，否則會被 finalize 清掉。

## Open failures / TODO
- （選用）Telegram getUpdates 的 offset 檔 `data/telegram_offset.txt` 未被 commit，靠 Telegram ~24h 保留期意外讓 `/ignore` 短期可讀；非致命，未處理。

## Feature: 互動指令 workflow /add /remove /list（Option B，2026-07-11）
- 決策：把「設定層指令」從 scraper 解耦到獨立輕量 workflow。已**回退**先前把 `/add` 放進 scraper `prepare` 的耦合設計。
- `.github/workflows/commands.yml`：`*/10` 全天排程 + workflow_dispatch，`concurrency` 防重疊，`contents: write`，跑 `process_commands.py`（系統 python3、不 pip install），commit `config/urls.json` + `data/commands_offset.txt`（明確檔名）。
- `src/url_commands.py` 新增 `process_commands()`：統一處理 `/add`、`/remove`、`/list`。`process_add_commands()` 仍保留（供舊測試）。
- `process_commands.py`（root）= commands.yml 進入點；`process_new_urls.py` 已 `git rm`（prepare 不再處理指令）。
- scraper (`track_products.yml`) 現在**只讀不寫** `config/urls.json`：`prepare` 只有 checkout + matrix；`finalize` 不再下載/複製/commit urls.json，`git add` 僅 `data/products.db data/exchange_rate.db`。→ 唯一 urls.json writer 是 commands.yml，無 race。
- 測試：`tests/test_url_commands.py` 共 21 個（含 marker 冪等）。全套 55 tests OK（subagent 環境缺 playwright 會誤報 test_scraper import 失敗，非程式問題）。

## 指令冪等 / 記住已執行（重要）
- **核心機制**：commands.yml 用 committed 的 `data/commands_offset.txt` 當 high-water marker，記錄「已處理到哪個 update_id」。`getUpdates` **不帶 offset**（不推進 Telegram 全域 offset），只在應用層用 marker 過濾。
- 效果：`/list`、`/remove`、`/add` 每則只執行一次（10 分鐘排程不會重工/洗版）；marker **只為我們的指令推進**，`/ignore` 不碰。
- `/ignore` 不受影響：scraper 的 `main_single.py` → `process_ignore_commands()` 仍獨立讀取（用自己的 `data/telegram_offset.txt`，且未 commit）。兩個 getUpdates 讀取者都不確認 Telegram offset，故互不干擾。
- `/remove`：先名稱精確比對，找不到再用正規化 URL 比對；名稱重複則要求改用 URL。

## Feature: Telegram /add 新增追蹤商品（2026-07-11，已被 Option B 取代部分）
- 指令格式：`/add <url>`、`/add <url> | <名稱>`、`/add <url> | <名稱> | <max_ntd>`。只給 URL 時 name 由 query 的 `keyword` percent-decode 推導；max_ntd 需正整數。
- `src/url_commands.py`（**純 stdlib，用 urllib 不用 requests**）：`process_add_commands()` 讀 getUpdates、解析、URL 正規化去重後寫 `config/urls.json`。刻意不依賴 requests，好讓 CI `prepare` job 用系統 python3 直接跑、免 setup-python / pip install。
- `process_new_urls.py`（root）：prepare job 進入點，無 secrets 時 graceful skip。
- CI 流程：`prepare` job 第一步跑 `process_new_urls.py`（注入 TG secrets）→ 更新 urls.json → 上傳 `urls-config` artifact → 生成 matrix（新 URL 當輪納入）。`finalize` 下載 `urls-config` → 覆蓋 config/urls.json → `git add data/products.db data/exchange_rate.db config/urls.json` 一起 commit。
- 測試：`tests/test_url_commands.py`（14 個）。全套 46 tests OK。獨立 code-review subagent 比對 6 項 Outcomes 全 PASS。

## 冪等性 / 重入設計（重要）
- prepare 讀 getUpdates **不推進 Telegram offset**——因為 offset 是 bot 全域共享，若在 prepare 確認 offset 會連帶消費掉 track job 要處理的 `/ignore` 訊息。
- 因此同一則 `/add` 在 Telegram 保留期（~24h）內會被每輪重複讀到 → 靠 **URL 正規化去重** 確保不產生重複商品；已存在則**靜默略過不通知**，避免每 2h 洗版。
- 已知小限制：格式錯誤的 `/add`（parse error）會在保留期內每輪各回一次錯誤通知（非致命，屬 edge case）。若要根治需持久化「已處理 update_id」的本地標記檔並經 artifact→finalize commit（目前未做，為維持最小 CI 變更）。

## General rules（新增）
- 動 CI `finalize` commit 清單時：任何需要跨 job 從 prepare/track 帶到 finalize 的檔案，都要走 upload-artifact → download-artifact → 明確 `git add <file>`，禁止 `git add -A/./--all`。
- 新增「需在爬蟲前生效」的設定變更，必須放在 `prepare` 生成 matrix **之前**。

## Lessons learned
- 「功能邏輯對但跨執行失效」時，先查狀態在 CI/pipeline 的持久化路徑（artifact→merge→commit），而非只看單機程式邏輯。
- Telegram getUpdates 的 offset 是 bot 全域共享：多個 job/流程都讀同一 bot 時，任一處確認 offset 會影響其他處。要「各自獨立讀取」就都別確認 offset，改用應用層去重（URL / id）保證冪等。
