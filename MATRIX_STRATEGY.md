# Matrix Strategy 並行處理方案

## 概述

這個方案使用 GitHub Actions 的 Matrix Strategy，讓每個追蹤 URL 在獨立的 runner 中並行處理，避免 "too many requests" 錯誤。

## 優點

1. **並行處理**：多個 URL 同時處理，提高效率
2. **隔離失敗**：一個 URL 失敗不影響其他（`fail-fast: false`）
3. **控制並行數**：通過 `max-parallel` 限制同時執行的 job 數量
4. **延遲啟動**：每個 job 根據 index 延遲啟動，避免同時發起請求
5. **獨立通知**：每個 URL 獨立發送通知，不需要等待所有 URL 完成

## 架構

### 檔案結構

- `main_single.py`：處理單一 URL 的程式
- `.github/workflows/track_products_matrix.yml`：使用 Matrix Strategy 的 workflow

### Workflow 流程

1. **prepare job**：讀取 `config/urls.json`，動態生成 matrix
2. **update-exchange-rate job**：更新匯率（只執行一次）
3. **track job**（並行）：
   - 根據 matrix 為每個 URL 創建一個 job
   - 每個 job 延遲啟動（間隔 30 秒）
   - 獨立處理、更新資料庫、發送通知

## 配置

### 調整並行數

在 `track_products_matrix.yml` 中修改：

```yaml
strategy:
  max-parallel: 3  # 調整為你想要的並行數
```

### 調整延遲間隔

在 `track_products_matrix.yml` 中修改：

```yaml
- name: Staggered delay
  run: |
    DELAY=$(( ${{ matrix.url_index }} * 30 ))  # 調整 30 為你想要的秒數
    sleep ${DELAY}
```

## SQLite 並發處理

SQLite 支援並發讀寫，但需要注意：

1. **WAL 模式**：SQLite 預設使用 WAL（Write-Ahead Logging），支援多個讀取和一個寫入
2. **重試機制**：如果遇到鎖定，會自動重試
3. **Git 衝突**：多個 job 同時 commit 可能會有衝突，已加入 `git pull --rebase` 處理

## 使用方式

### 啟用 Matrix Strategy

1. 將 `track_products_matrix.yml` 重命名為 `track_products.yml`（備份舊的）
2. 或者保留兩個 workflow，分別用於不同場景

### 測試

```bash
# 本地測試單一 URL
URL_INDEX=0 python main_single.py
```

## 與原方案的比較

| 特性 | 原方案（順序） | Matrix 方案（並行） |
|------|---------------|---------------------|
| 執行時間 | 所有 URL 順序執行 | 並行執行，總時間更短 |
| 失敗隔離 | 一個失敗可能影響後續 | 完全隔離 |
| 並發控制 | 無 | 可控制並行數 |
| 延遲控制 | 程式內建 | 每個 job 獨立延遲 |
| 複雜度 | 簡單 | 稍複雜 |

## 注意事項

1. **GitHub Actions 限制**：
   - 免費帳號：最多 20 個並行 job
   - 付費帳號：根據方案不同

2. **資料庫衝突**：
   - 多個 job 同時寫入可能會有短暫鎖定
   - 已加入重試機制和 `git pull --rebase`

3. **通知頻率**：
   - 每個 URL 獨立發送通知
   - 如果有多個 URL，會收到多條通知

## 建議

- **少量 URL（< 5）**：可以使用 Matrix 方案，並行數設為 2-3
- **大量 URL（> 10）**：建議使用 Matrix 方案，並行數設為 3-5，並增加延遲間隔
- **測試階段**：先用少量 URL 測試，確認無誤後再擴展

