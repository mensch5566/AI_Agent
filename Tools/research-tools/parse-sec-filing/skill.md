---
name: parse-sec-filing
description: Parse SEC 10-Q and 10-K filings for US-listed companies, extract key financial metrics, and validate them against Supabase. Use when the user mentions a US stock ticker together with SEC, 10-Q, 10-K, 財報, filing, or asks to verify filing-based financial data.
---

# parse-sec-filing — 美股 SEC 10-Q/10-K 財務數據解析

用於解析美股上市公司的 SEC 10-Q (季報) 和 10-K (年報) 財務表單，自動提取關鍵指標並與 Supabase 驗證。

## 使用方式

```
/parse-sec-filing <ticker> [form_type] [file_path]
```

## 參數

- **ticker** (必須)：股票代號，如 `SNDK` (SanDisk)、`MU` (Micron)、`NVDA` (Nvidia)
- **form_type** (可選)：`10-Q` 或 `10-K`，預設 `10-Q`
- **file_path** (可選)：SEC filing HTML/XML 文件路徑。若不提供，會自動從 SEC Edgar 下載

## 工作流程

### Step 1: 取得 SEC Filing
- 若無檔案，自動從 SEC Edgar API 查詢並下載最新 10-Q/10-K
- Edgar API 端點：`https://data.sec.gov/api/xbrl/`

### Step 2: 解析 Financial Statements
從以下表單提取指標：
- **Consolidated Balance Sheet**：資產、負債、權益
- **Consolidated Statements of Earnings**：營收、毛利、營業利益、淨利、EPS
- **Consolidated Statements of Cash Flows**：營業現金流、投資現金流、融資現金流

### Step 3: 與 Supabase 比對
- 查詢 financial_facts 表中該 ticker 最新期別數據
- 自動處理單位差異（SEC 用千位或百萬位）
- 驗證提取的數據準確性

### Step 4: 輸出驗證報告
```
✅ 驗證成功：12 項匹配
❌ 需調查：2 項不匹配
ⓘ 未找到：1 項指標
```

## 支援的指標

**資產負債表：**
- total_assets（總資產）
- total_current_assets（流動資產）
- total_liabilities（總負債）
- total_current_liabilities（流動負債）
- stockholders_equity（股東權益）

**損益表：**
- operating_revenue（營業收入）
- gross_profit（毛利）
- operating_income（營業利益）
- income_before_taxes（稅前利潤）
- net_income（淨利）
- eps_basic（基本 EPS）
- eps_diluted（稀釋 EPS）

**現金流量表：**
- operating_cash_flow（營業現金流）
- investing_cash_flow（投資現金流）
- financing_cash_flow（融資現金流）

## 範例

**用法 1：自動下載最新 10-Q**
```
/parse-sec-filing SNDK 10-Q
```

**用法 2：指定年報**
```
/parse-sec-filing MU 10-K
```

**用法 3：本地檔案**
```
/parse-sec-filing NVDA 10-Q /path/to/10q.html
```

## 技術細節

**XBRL 解析：**
- 使用 lxml 解析 SEC 提交的 HTML iXBRL 文件
- 從 `<ix:nonfraction>` 和 `<ix:continuation>` 標籤提取數值
- 自動識別期別（Current Quarter、Prior Year Quarter 等）

**單位轉換：**
- SEC 通常以美元千位 (thousands) 提交
- 自動轉換至 Supabase 格式（確保單位一致）

**指標映射：**
- XBRL 標籤映射至標準指標名稱
- 優先匹配英文標籤（XBRL 標準）

## 使用場景

1. **季報驗證**：新季度 10-Q 發佈後，快速驗證財務數據
2. **年報審計**：下載 10-K，驗證年度財務數據
3. **多公司追蹤**：批量驗證投資組合中的多家公司財報
4. **數據質量檢查**：確保 Supabase 中的美股財務數據準確無誤

## 後續改進方向

- [ ] 自動從 SEC XBRL 實例文件 (instance.xml) 解析（比 HTML 更精確）
- [ ] 支援批量解析多家公司
- [ ] 匯出驗證報告為 CSV
- [ ] 建立 SEC filing 歷史追蹤表
- [ ] 支援 8-K、DEF 14A 等其他表單
- [ ] 與 Perplexity API 整合補充定性分析
