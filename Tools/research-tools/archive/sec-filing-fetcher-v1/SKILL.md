---
name: sec-filing-fetcher
description: Fetch SEC financial filings (10-Q, 10-K) for US-listed companies, parse financial statements, and produce a timeseries JSON + multi-sheet XLSX. Supports both initial setup and incremental updates. Use when the user mentions a stock ticker alongside words like 財報, 10-Q, 10-K, SEC, 抓財報, 財務數據, annual report, quarterly report, or asks to update/backfill financial data.
---

# SEC Filing Fetcher

## 你的任務

幫使用者建立或更新某支美股的財務數據檔案。

輸入：Ticker（必填）+ 起始季度（選填，未指定時詢問）
輸出：
- `~/Investment_Data/financials/{TICKER}/{TICKER}_financials.json`
- `~/Investment_Data/financials/{TICKER}/{TICKER}_financials.xlsx`
- `~/Investment_Data/financials/{TICKER}/filings/{TICKER}_{期間}_{類型}.htm`（原始申報文件）

---

## 執行流程

### Step 1 — 確認參數

確認以下兩個參數，缺一補問：
- **Ticker**：如 `MU`、`NVDA`、`TSMC`（美股代號）
- **起始季度**：格式 `Q{1-4} FY{YYYY}`，例如 `Q1 FY2024`。若使用者未提供，詢問之。

---

### Step 2 — 審計現有資料

執行 `python3 {skill_dir}/scripts/audit.py --ticker {TICKER} --base-dir ~/Investment_Data/financials --start {起始季度}`

腳本會輸出：
```
STATUS: new          → 從未建立過，進入「全新建立」
STATUS: up_to_date   → 已是最新，告知使用者並結束
STATUS: missing [{Q1_FY2024, Q2_FY2024, ...}]  → 有缺漏，列出需補齊的季度
```

---

### Step 3 — 取得 SEC Filing 清單

使用 `data.sec.gov` REST API 查詢所有 10-Q / 10-K：

```bash
curl -s -A "Mozilla/5.0 (research tool) claude-code/1.0 contact@example.com" \
  "https://data.sec.gov/submissions/CIK{CIK_PADDED}.json" \
  | python3 {skill_dir}/scripts/fetch.py --mode list --ticker {TICKER}
```

**CIK 查詢方式**（如不知道 CIK）：
```bash
curl -s "https://efts.sec.gov/LATEST/search-index?q=%22{TICKER}%22&forms=10-K" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); ..."
```

或直接 Web Search `{TICKER} SEC EDGAR CIK`。

輸出：符合起始季度之後的所有 10-Q / 10-K 清單（期間、accession number、HTM 主檔名）。

---

### Step 4 — 逐季抓取、解析、合併

對每個需要補齊的季度，依序執行：

**4a. 下載原始申報文件**
```bash
python3 {skill_dir}/scripts/fetch.py \
  --ticker {TICKER} \
  --accession {ACCESSION_NUMBER} \
  --out-dir ~/Investment_Data/financials/{TICKER}/filings/
```
儲存為 `{TICKER}_{期間}_{類型}.htm`（例如 `MU_Q1_FY2026_10Q.htm`）。

**4b. 解析財務報表**
```bash
python3 {skill_dir}/scripts/parse.py \
  --file ~/Investment_Data/financials/{TICKER}/filings/{HTM_FILE} \
  --ticker {TICKER} \
  --period {PERIOD}
```
輸出：包含該季度所有財務指標的 dict（依 schema.md 欄位定義）。

**4c. 合併進 JSON**
將解析結果合併進 `{TICKER}_financials.json` 的 timeseries 結構（period-keyed dict）。
詳見 `references/schema.md` 了解 JSON 結構定義。

---

### Step 5 — 重建 XLSX

```bash
python3 {skill_dir}/scripts/build_xlsx.py \
  --json ~/Investment_Data/financials/{TICKER}/{TICKER}_financials.json \
  --out  ~/Investment_Data/financials/{TICKER}/{TICKER}_financials.xlsx
```

XLSX 固定包含 8 個 Sheet：
1. Overview（Metadata + Filing Registry）
2. Income Statement（periods 為欄，可往右延伸）
3. Balance Sheet
4. Cash Flow
5. Revenue Breakdown（產品別 + 部門別）
6. Segment P&L
7. Long Format (DB)（tidy data，適合匯入 Looker Studio / BigQuery）
8. Notable Events

---

### Step 6 — 回報結果

完成後輸出摘要，例如：
```
✓ MU financials 更新完成
  新增/補全季度：Q1 FY2024, Q2 FY2024, Q3 FY2024, Q4 FY2024, Q1 FY2025
  現有期間：Q1 FY2024 → Q1 FY2026（共 9 季）
  JSON：~/Investment_Data/financials/MU/MU_financials.json
  XLSX：~/Investment_Data/financials/MU/MU_financials.xlsx
  原始申報：~/Investment_Data/financials/MU/filings/（9 個 HTM 檔）
```

---

## 注意事項

- **SEC API User-Agent**：curl 必須帶 `-A "Mozilla/5.0 (research tool) claude-code/1.0 {email}"`，否則 403。
- **解析容錯**：不同公司的 10-Q HTML 結構不同，`parse.py` 無法保證 100% 自動提取。如有欄位解析失敗，列出失敗項目請使用者手動補填，不要中斷整個流程。
- **None 值**：無法取得的欄位填 `null`，JSON 和 XLSX 都顯示 `—`，Long Format 跳過。
- **段落名稱差異**：各公司的業務部門（Segment）名稱不同。第一次建立時，詢問使用者確認 Segment 結構，或從 10-K 的 Segment 說明段落自動提取。
- **備份機制**：每次更新 JSON 前，自動備份為 `{TICKER}_financials_backup_{YYYY-MM-DD}.json`。

---

## 相關資源

- `scripts/audit.py` — 審計現有資料完整性
- `scripts/fetch.py` — SEC 抓檔（listing + download）
- `scripts/parse.py` — HTML 解析器
- `scripts/build_xlsx.py` — XLSX 產生器
- `references/schema.md` — JSON timeseries 欄位定義
