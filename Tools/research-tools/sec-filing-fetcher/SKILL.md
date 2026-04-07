---
name: sec-filing-fetcher
description: Fetch SEC financial filings (10-Q, 10-K) for US-listed companies via XBRL API, parse financial statements, and produce a timeseries JSON + multi-sheet XLSX. Supports both initial setup and incremental updates. Use when the user mentions a stock ticker alongside words like 財報, 10-Q, 10-K, SEC, 抓財報, 財務數據, annual report, quarterly report, or asks to update/backfill financial data.
---

# SEC Filing Fetcher (v2 — XBRL API)

## 你的任務

幫使用者建立或更新某支美股的財務數據檔案。

輸入：Ticker（必填）+ 起始季度（選填，未指定時詢問）
輸出：
- `~/AI_Agent/Investment_Data/financials/{TICKER}/{TICKER}_financials.json`
- `~/AI_Agent/Investment_Data/financials/{TICKER}/{TICKER}_financials.xlsx`
- `~/AI_Agent/Investment_Data/financials/{TICKER}/filings/{TICKER}_{期間}_{類型}.htm`（原始申報文件，選擇性下載）

資料來源：**SEC EDGAR XBRL API**（`data.sec.gov/api/xbrl/companyfacts`），結構化 JSON，不再使用 HTML 正則解析。

腳本位置：`~/AI_Agent/Tools/research-tools/sec-filing-fetcher/scripts/`

---

## 執行流程

### Step 1 — 確認參數

確認以下參數，缺一補問：
- **Ticker**：如 `MU`、`NVDA`、`SNDK`（美股代號）
- **起始季度**：格式 `Q{1-4}_FY{YYYY}`，例如 `Q1_FY2025`
- **CIK**：SEC EDGAR CIK（10 位零填充）。若不知道，用以下方式查：

```bash
curl -s -A "Mozilla/5.0 (research tool) claude-code/1.0 contact@example.com" \
  "https://efts.sec.gov/LATEST/search-index?q=%22{TICKER}%22&forms=10-K" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); hits=d['hits']['hits']; print(hits[0]['_source']['display_names'][0]) if hits else print('NOT FOUND')"
```

- **Fiscal Year End Month**（1-12）：從 submissions JSON 的 `fiscalYearEnd` 欄位取得（格式 MMDD，取前兩位）

---

### Step 2 — 執行 XBRL 提取

```bash
python3 ~/AI_Agent/Tools/research-tools/sec-filing-fetcher/scripts/xbrl_extract.py \
  --cik {CIK_PADDED} \
  --ticker {TICKER} \
  --fy-end-month {MONTH} \
  --start {START_PERIOD} \
  --out-dir ~/AI_Agent/Investment_Data/financials/{TICKER}/ \
  --exchange {EXCHANGE} \
  --company "{COMPANY_NAME}"
```

腳本自動執行：
1. 從 `data.sec.gov/api/xbrl/companyfacts` 下載結構化財務數據
2. 從 `data.sec.gov/submissions` 取得 filing 清單與期間資訊
3. 自動映射 XBRL CY frame → 公司 FY 季度
4. Q4 反推（全年 10-K 減去 9 個月 YTD）
5. 計算財務比率（current ratio, quick ratio, D/E 等）
6. 輸出 JSON（含 tidy/long format）

---

### Step 3 — 生成 XLSX（選擇性）

```bash
uv run --with openpyxl python3 ~/AI_Agent/Tools/research-tools/sec-filing-fetcher/scripts/build_xlsx.py
```

注意：`build_xlsx.py` 目前以 SNDK 的 JSON 結構為基礎，新標的可能需要微調。或者直接在 out-dir 裡寫一個簡單的 build script。

---

### Step 4 — 下載原始 HTM（選擇性）

原始 SEC filing 留作人工參考：

```bash
curl -s -A "Mozilla/5.0 (research tool) claude-code/1.0 contact@example.com" \
  "https://www.sec.gov/Archives/edgar/data/{CIK_NO_ZERO}/{ACCESSION_NO_DASH}/{PRIMARY_DOC}" \
  -o ~/AI_Agent/Investment_Data/financials/{TICKER}/filings/{TICKER}_{PERIOD}_{FORM}.htm
```

---

### Step 5 — 更新 tickers.json

新標的加入後，更新 viewer 的 ticker 清單：
```bash
# 編輯 ~/AI_Agent/Investment_Data/tickers.json 加入新 ticker
```

---

## XBRL Tag 解析策略

每個財務指標對應多個候選 XBRL tag（按優先順序），腳本自動選擇該公司有資料的第一個 tag。詳見 `xbrl_extract.py` 中的 `IS_TAG_MAP`、`BS_TAG_MAP`、`CF_TAG_MAP`。

若某公司使用非標準 tag（如公司自定義 extension tag），腳本會在輸出中標示缺失，需要人工補充。

---

## Q4 反推邏輯

當公司有 Q1~Q3 的 10-Q 和全年 10-K 時：
- **累加項**（Revenue, Net Income, Cash Flow 等）：Q4 = Full Year - 9-month YTD
- **加權平均**（EPS, Shares）：**不反推**，設為 null（加權平均不能相減）
- **Balance Sheet**：Q4 = 10-K 的 period_end 即為 Q4 ending balance

---

## JSON 結構

```json
{
  "metadata": { ... },
  "filings": { "Q1_FY2025": { "form", "period_end", "filing_date", "accession_number" }, ... },
  "income_statement": { "revenue": { "Q1_FY2025": 1883.0, ... }, ... },
  "balance_sheet": { "assets": { ... }, "liabilities": { ... }, "equity": { ... } },
  "cash_flow_statement": { "operating_activities": { ... }, ... },
  "financial_ratios": { "Q2_FY2025": { "current_ratio": 2.31, ... }, ... },
  "notable_events": [ ... ],
  "long_format": [ { "period", "period_end", "statement", "metric", "value", "unit" }, ... ]
}
```

---

## 注意事項

- **SEC API User-Agent**：curl 必須帶 `-A "Mozilla/5.0 (research tool) claude-code/1.0 {email}"`，否則 403
- **Rate Limit**：SEC API 限制 10 req/sec，腳本單次提取只需 2 次 API call
- **None 值**：無法取得的欄位填 `null`，JSON/XLSX 顯示 `—`，Long Format 跳過
- **備份機制**：每次更新 JSON 前，自動備份為 `{TICKER}_financials_backup_{YYYY-MM-DD}.json`
- **Financials Viewer**：`~/AI_Agent/Investment_Data/financials_viewer.html` 可瀏覽所有標的的財務報表（需 HTTP server）

---

## 相關檔案

- `scripts/xbrl_extract.py` — XBRL API 提取（主腳本）
- `scripts/build_xlsx.py` — XLSX 產生器
- `archive/sec-filing-fetcher-v1/` — 舊版（HTML 解析，已棄用）
