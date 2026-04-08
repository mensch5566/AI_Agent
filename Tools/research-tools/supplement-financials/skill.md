# supplement-financials — 從 NotebookLM 補足非 XBRL 財務指標

在 XBRL 官方管道跑完後，從 NotebookLM 提取 Segments、Non-GAAP 等數據，寫入對應的 Supabase 表。

## 使用方式

```
/supplement-financials <ticker> <period> [--notebook <name>]
```

## 參數

- **ticker**（必須）：股票代號，如 `2454`（聯發科）、`SNDK`
- **period**（必須）：期別，如 `Q4_FY2025`
- **--notebook**（可選）：NotebookLM 筆記本名稱。未提供時會列出可用筆記本請用戶選擇

## 寫入規則

| 數據類型 | 表 | source |
|---|---|---|
| Segments（業務拆分）| `financial_supplement` | `NB_SUPPLEMENTED` |
| Non-GAAP 指標（EPS、利潤率）| `financial_supplement` | `NB_SUPPLEMENTED` |
| 員工人數、其他 KPI | `financial_supplement` | `NB_SUPPLEMENTED` |
| 前瞻 Guidance（下季營收指引等）| `financial_guidance` | `GUIDANCE_EARNINGS_CALL` |

**只要不是 XBRL 直接給出的數值，不放 `financial_facts`。**

## 執行流程

### Step 1：確認 NotebookLM 筆記本

- 若已提供 `--notebook`，用名稱在 NotebookLM 中搜尋對應筆記本
- 若未提供，列出所有可用筆記本讓用戶選擇
- 確認找到後顯示筆記本名稱

### Step 2：查詢 Segments

對每個已知業務分部，查詢：

```
查詢：{ticker} {period} 各業務分部（segment）的營收數字是多少？
```

提取格式：
```
financial_supplement:
  category = 'segment'
  metric   = 'segment_{name}_revenue'（name 全小寫，空格換底線）
  dimension = 原始分部名稱（如 "Mobile", "Connectivity"）
  value    = 數值（千元 for 台股，千美元 for 美股）
  unit     = 'TWD_thousands' 或 'USD_thousands'
```

### Step 3：查詢 Non-GAAP 指標

```
查詢：{ticker} {period} Non-GAAP EPS、Non-GAAP 毛利率、Non-GAAP 營業利益率
```

提取格式：
```
financial_supplement:
  category = 'non_gaap'
  metric   = 'eps_non_gaap' / 'gross_margin_non_gaap' / 'operating_margin_non_gaap'
  dimension = NULL
  value    = 數值
```

### Step 4：查詢 Earnings Call Guidance（若有）

```
查詢：{ticker} {period} earnings call 給出的下一季 guidance（營收、EPS 指引）
```

提取格式（寫入 `financial_guidance`）：
```
financial_guidance:
  period           = 下一期（如 Q1_FY2026）
  metric           = 'revenue_guidance_mid' / 'eps_guidance_mid'
  announcement_date = 當期 earnings call 日期
  source           = 'GUIDANCE_EARNINGS_CALL'
```

### Step 5：確認並寫入

- 列出所有提取的數值，來源引用（文件名 + 關鍵字）
- 確認無誤後寫入 Supabase
- 若有不確定的數字，標記為 `notes = 'needs_review'`

## 引用規範

每筆數據必須附來源：
- **優先**：可構造的 URL（SEC filing、TWSE MOPS）
- **備選**：文件名 + ≤5 英文單字 / ≤10 中文字搜尋關鍵字

## 範例

```
/supplement-financials 2454 Q4_FY2025 --notebook 聯發科研究筆記
/supplement-financials SNDK Q3_FY2026 --notebook SNDK Research
```

## 執行後狀態

```
✅ financial_supplement：
   - segment_mobile_revenue        Q4_FY2025  87,234 千元
   - segment_connectivity_revenue  Q4_FY2025  43,112 千元
   - eps_non_gaap                  Q4_FY2025     73.5 元

✅ financial_guidance：
   - revenue_guidance_mid  Q1_FY2026  155,000~165,000 千元
```
