# Financials Architecture — DRAFT v0.4

最後更新：2026-05-10
狀態：**草案**，等使用者確認後再 promote 成正式文件並修 CLAUDE.md

## v0.4 變更（XBRL anchoring 對齊）

NotebookLM 確認我們的 long-tail bucket 設計**等同 XBRL 業界的 "Anchoring" 機制**，但需補強：

- 每個 cell 加 `weight` 欄位（XBRL calculation weight，+1 / -1）
- 每個 long-tail cell 加 `long_tail_metadata` 區塊：
  - `is_recurring`：SEC two-year 復發檢視 flag
  - `last_occurrence_date`：上次發生的 period
  - `rolls_up_to`：顯式 anchor 到哪個核心 subtotal
- 補 **XBRL Anchoring 設計 rationale**（business case + SEC compliance）

## v0.3 變更（依 NotebookLM `Parse_SEC_Filings` SEC Reg G / CFA / XBRL guidance）

- 補 **Non-GAAP Reconciliation Metadata schema**（5 個強制欄位）
- 補 **前端 SEC 合規規則**（GAAP 優先、reconciliation 從 GAAP 起、禁完整 Non-GAAP P&L）
- 新增 **Segment Reporting** 為 future work（單獨 `financial_segment` table）

## v0.2 變更

- **棄用 `uni_account = null` 表示 supplement** 的設計
- 改用 **long-tail bucket** 制：每個 IS/BS/CF section 配一個 long-tail bucket uni_account
- 好處：(1) 前端知道哪個區塊渲染 (2) 跨公司仍可比（bucket + core other 加總）(3) `uni_account` 永遠有值，DB schema 更乾淨

這份文件試圖一次解決三個糾結：
1. 「核心 vs 公司特殊」 metric 的處理規則
2. 「PDF-faithful 顯示」 vs 「跨公司可比」 的衝突
3. Wiki ingest 怎麼用同一份資料

---

## 核心架構：Dual-Key Long Format

每筆財務 cell 同時帶**兩個 key** + 計算用的 weight：

```jsonc
// 核心 cell（uni_account 是核心 key）
{
  "period":         "Q1_FY2026",
  "source_account": "Net revenue",                          // ← PDF 原文 label
  "uni_account":    "revenue",                              // ← 核心 universal key
  "value":          13577,
  "weight":         1,                                       // ← XBRL calculation weight
  "type":           "GAAP",
  "unit":           "USD_millions",
  "ordinal":        1                                        // ← PDF 上順序
}

// Long-tail cell（uni_account 是 bucket = anchor parent）
{
  "period":         "Q3_FY2025",
  "source_account": "Goodwill impairment",                  // ← PDF 原文 label
  "uni_account":    "operating_expense_long_tail",          // ← bucket = anchor 到 OpEx 區塊
  "value":          1830,
  "weight":         1,                                       // ← +1：費用方向（加進 total OpEx）
  "type":           "GAAP",
  "unit":           "USD_millions",
  "ordinal":        7,
  "long_tail_metadata": {
    "is_recurring":         "UNKNOWN",                       // RECURRING / NON_RECURRING / UNKNOWN
    "last_occurrence_date": "Q3_FY2025",                     // 上次發生的 period
    "rolls_up_to":          "total_operating_expenses"       // 顯式聲明 anchor target
  }
}
```

兩個 key 都永遠有值。差別在於：

| uni_account 類型 | 意思 | 多半用 |
|---|---|---|
| **核心 key**（如 `revenue`, `gross_profit`, `operating_income`） | 公司 P&L 的標準位置，跨公司可比 | 跨公司分析、derive-analytics |
| **Long-tail bucket**（如 `operating_expense_long_tail`） | 公司特殊揭露項目，bucket 名告訴前端要放哪個區塊 | statement view 渲染 + reconciliation 細項 |

### `weight` 欄位 — XBRL calculation weight

`weight` 告訴下游 derive-analytics 跟 frontend 怎麼把這個 cell roll up 到 parent subtotal：

| 情境 | weight |
|---|---|
| Revenue / 收入類 → roll up 到 revenue | +1 |
| COGS / 費用類 → roll up 到 OpEx subtotal | +1（在 OpEx context）|
| COGS → roll up 到 gross_profit calculation | -1（從 revenue 扣）|
| 「Gain on divestiture」在 long-tail OpEx bucket | -1（gain 扣減費用）|
| 「Loss on divestiture」在同 bucket | +1（loss 增加費用）|

Schema 上每個 row 一個固定 weight，**對應到該 cell 的 `rolls_up_to` parent 的 calculation 方向**。

### `long_tail_metadata` 欄位 — 僅 long-tail bucket cells 帶

| 欄位 | 用途 |
|---|---|
| `is_recurring` | SEC two-year look-back/forward 規則：過去/未來 2 年內若再發生不可標 NON_RECURRING |
| `last_occurrence_date` | 上次發生 period，給跨期復發追蹤用 |
| `rolls_up_to` | 顯式聲明 anchor 到哪個核心 subtotal（不只靠 bucket name 隱含） |

核心 cell（uni_account 是 universal key）**不需要** `long_tail_metadata`，因為它已經是核心。

---

## Three Layers of View

| Layer | 用什麼 key | 包含哪些 cells | 用途 |
|---|---|---|---|
| **資料層**（JSON / Supabase） | 兩個都存 | 全部 | 唯一 source of truth |
| **Statement View**（前端個股頁、Wiki 個股頁） | `uni_account` 決定區塊 + `ordinal` 排序 + `source_account` 顯示 | 全部 | PDF-faithful，每家公司原貌呈現 |
| **Comparison View**（跨公司並列、ROIC 計算、derive-analytics） | `uni_account` | 核心 key 直接用；long-tail bucket 跟對應的核心「other」加總 | 跨公司可比 |

→ 同一份資料，不同 view 切換不同邏輯。**沒有資料 duplication，沒有「另一張表」**。

---

## XBRL Anchoring — 我們的 long-tail bucket 等同這個機制

NotebookLM 確認 XBRL/ESEF 業界對「公司特殊科目」的標準處理方式叫 **Anchoring（錨定）**：

```
標準流程：
1. 公司在 10-K iXBRL 揭露非標準科目（如 "Goodwill impairment"）
2. 公司必須建立 "Extension Element"（如 sndk:GoodwillImpairment）
3. Extension 必須 anchor 到最接近的標準 us-gaap parent（如 us-gaap:OperatingExpenses）
4. 必須提供 calculation relationship（roll up 到 parent，帶 weight）
```

我們的設計對應：

| XBRL 概念 | 我們的實作 |
|---|---|
| Extension element name (`sndk:GoodwillImpairment`) | `source_account` 欄位（"Goodwill impairment"，PDF 原文） |
| Anchor target (`us-gaap:OperatingExpenses`) | `uni_account` = `operating_expense_long_tail` bucket，bucket 名隱含 anchor 到 OpEx 區塊 |
| Calculation weight | `weight` 欄位（+1 / -1） |
| Roll-up relationship | `rolls_up_to` 欄位（顯式聲明 anchor target subtotal） |

→ **設計上對齊國際標準，不是我們自己發明**。

### 跟 Bloomberg / FactSet 等資料商的對應

業界資料商處理這類資料的標準做法：
1. **建立內部 standard COA**（chart of accounts）
2. 用 NLP / 語意相似度，把公司原始科目 mapping 到內部 COA
3. **保留 parent-child 階層**（不直接 sum 成 catch-all）

我們的 long-tail bucket = 內部 COA 的 anchor parent，每筆 long-tail cell 的 `source_account` 保留原文，`weight` + `rolls_up_to` 保留階層關係。**完全對齊資料商實作模式**。

## Long-Tail Bucket 機制

Long-tail bucket 是「按 IS/BS/CF section 分類的 catch-all」，每個 section 一個 bucket。

### Bucket 清單（共 12 個）

#### IS（4 個）

| Bucket uni_account | 涵蓋範圍 | 範例 |
|---|---|---|
| `revenue_long_tail` | 公司特殊揭露的營收細項（罕見）| (rare) |
| `operating_expense_long_tail` | 介於 gross_profit 跟 operating_income 之間的特殊項目 | Goodwill impairment、Business separation costs |
| `nonoperating_long_tail` | 介於 operating_income 跟 income_before_taxes 之間的特殊項目 | Gain/Loss on divestiture、Equity method investments 特例 |
| `below_line_long_tail` | 在 net_income 附近的特殊項目（罕見）| 特殊 discontinued ops、accounting changes |

#### BS（5 個）

| Bucket | 涵蓋 |
|---|---|
| `current_asset_long_tail` | Total Current Assets 內，沒對到核心 key |
| `noncurrent_asset_long_tail` | Total Noncurrent Assets 內 |
| `current_liability_long_tail` | Total Current Liabilities 內 |
| `noncurrent_liability_long_tail` | Total Noncurrent Liabilities 內 |
| `equity_long_tail` | Total Equity 區塊內 |

#### CF（3 個）

| Bucket | 涵蓋 |
|---|---|
| `operating_cf_long_tail` | Cash from Operating 區塊 |
| `investing_cf_long_tail` | Cash from Investing 區塊 |
| `financing_cf_long_tail` | Cash from Financing 區塊 |

### 處理流程

```
NLM/PDF 揭露的科目 X
    ↓
Layer 1: ticker_config 字典 hard match 命中核心 key
    ↓ miss
Layer 2: LLM fuzzy match → 對核心 confidence ≥0.85 → 走核心
    ↓ miss
Layer 3: LLM 判斷 X 屬於哪個 IS/BS/CF section → 配對應 bucket
        + 同時判斷 weight（+1/-1）跟 rolls_up_to（哪個核心 subtotal）
        例：「Goodwill impairment」→ 介於 OpEx 跟 OpIncome 之間 → operating_expense_long_tail
                                  → weight=+1（費用方向）
                                  → rolls_up_to=total_operating_expenses
    ↓ 都判斷不出區塊
Layer 4: misc_long_tail（最後的 catch-all）+ 進 audit queue 待人工
```

### Anchor 完整性檢查（compose 階段）

compose skill 應該驗證：
- 每個 long-tail cell **必須有** `weight` + `rolls_up_to`
- `rolls_up_to` 指向的 subtotal 必須是核心 schema 內的 uni_account
- 同 period 同 ticker 的所有 cells anchor 到同一個 parent 的，加總（含 weight）應該 ≈ parent 的揭露值（容許小幅 rounding）

不通過驗證的 cell 進 reconciliation_warnings.md，待人工處理。

### 核心 "other" vs long-tail bucket 的差別

注意這兩個**不同**：

| | uni_account | 何時用 |
|---|---|---|
| 核心 "other" | `other_operating_expense` | 公司**明確寫**了一行叫 "Other operating expense" 的揭露 |
| 長尾 bucket | `operating_expense_long_tail` | 公司寫了某項（如 Goodwill impairment），不在我們核心字典，**但能判斷它屬於 OpEx 區塊** |

兩個並存於 Supabase。Comparison view 加總時兩個都算「業外其他」。

---

## ROIC AI Scope as Core Reference

我們採用 ROIC.AI 的科目集合作為 universal core 字典。從圖片擷取出來的清單（待擴展、待你打勾確認）：

### Income Statement (~25 source-of-truth items)

| ROIC.AI label | uni_account | 備註 |
|---|---|---|
| Sales/Revenue/Turnover | `revenue` | top-line |
| Sales & Services Revenue | `revenue_sales_services` | sub-breakdown |
| Cost of Revenue | `cost_of_revenue` | （取代我們的 `cost_of_goods_sold`）|
| Cost of Goods & Services | `cost_of_goods_services` | sub-breakdown |
| Gross Profit | `gross_profit` | |
| Other Operating Income | `other_operating_income` | |
| Selling, General & Admin | `selling_general_administrative` | |
| Research & Development | `research_and_development` | |
| Other Operating Expense | `other_operating_expense` | |
| Operating Expenses | `operating_expenses_total` | subtotal |
| Operating Income (Loss) | `operating_income` | |
| Non-Operating (Income)/Loss | `nonoperating_income_loss` | |
| Interest Expense | `interest_expense` | |
| Interest Income | `interest_income` | |
| Interest Expense, Net | `interest_expense_net` | subtotal |
| Other Non-Op (Income)/Loss | `other_nonoperating_income_loss` | |
| Income (Loss) From Affiliates | `income_from_affiliates` | |
| Discontinued Operations | `discontinued_operations` | |
| Extraord. & Accounting Changes | `extraordinary_items` | |
| Pretax Income | `income_before_taxes` | |
| Income Tax Expense | `income_tax_expense` | |
| Minority Interest | `minority_interest` | |
| Net Income, GAAP | `net_income` | (parent attributable) |
| Preferred Dividends | `preferred_dividends` | |
| Other Adjustments | `other_adjustments_to_ni` | |
| Net Income Avail to Common | `net_income_to_common` | |
| Depreciation Expense | `depreciation_expense_is` | （CF 也有，需 disambiguation） |
| Dividend per Share | `dividend_per_share` | |
| Basic Weighted Avg Shares | `shares_basic_weighted_millions` | |
| Diluted Weighted Avg Shares | `shares_diluted_weighted_millions` | |
| Basic EPS, GAAP | `eps_basic` | |
| Basic EPS from Cont Ops | `eps_basic_continuing` | |
| Diluted EPS, GAAP | `eps_diluted` | |
| Diluted EPS from Cont Ops | `eps_diluted_continuing` | |

> **Derived（不放 financial_facts，放 financial_metrics）**：EBIT、EBITDA、EBITA、Gross Margin %、Profit Margin %、EBITDA Margin %、Sales per Employee

### Balance Sheet (~50 source-of-truth items)

需要逐項列。現在先列 top-level 跟最重要的：

```
Cash & Cash Equivalents, ST Investments, Total Cash & ST I,
Accounts/Notes/Loans/Other Receivable, Receivables Subtotal,
Raw/WIP/Finished/Other Inventories, Inventory Subtotal,
Prepaid / Misc / ST Hedging / ST Held-for-Sale / ST Deferred Tax → Other ST Assets,
Total Current Assets,
PP&E (gross / accumulated dep / net),
LT Investments / Receivables → LT Inv subtotal,
Goodwill, Other Intangibles → Total Intangibles,
LT Deferred Tax / LT Hedging / Misc LT → Other LT Assets,
Total Noncurrent Assets, Total Assets,

Accounts Payable, Accrued Taxes, Interest & Dividends Payable, Other Payables → Payables subtotal,
ST Borrowings / ST Finance Leases → ST Debt,
Deferred Revenue / Derivatives / Deferred Tax / Misc → Other ST Liabilities,
Total Current Liabilities,
LT Borrowings / LT Finance Leases → LT Debt,
Accrued / Pension / LT Deferred Revenue / LT Deferred Tax / LT Hedging / LT Misc → Other LT Liabilities,
Total Noncurrent Liabilities, Total Liabilities,

Preferred Equity, Common Stock, APIC, Treasury Stock → Share Capital subtotal,
Retained Earnings, Other Equity, Equity Before Minority Interest,
Minority Interest, Total Equity, Total Liabilities & Equity,

Shares Outstanding (point-in-time), Capital Leases Total
```

> **Derived（不放 facts）**：Net Debt、Net Debt to Equity、Tangible Common Equity Ratio、Current Ratio、Cash Conversion Cycle

### Cash Flow Statement (~35 source-of-truth items)

```
Net Income (CF starting),
D&A, SBC, Deferred Income Taxes, Asset Impairment, Other Non-Cash → Non-Cash Items subtotal,
ΔAccts Receiv / ΔInventories / ΔPrepaid / ΔAccts Payable / ΔOther → Working Cap Change subtotal,
Cash from Operating Activities,

Capex, Disp of Fixed / Disp of Intangible → Disposals subtotal,
Acq of Fixed / Acq of Intangible → Acquisitions subtotal,
ΔFixed & Intang subtotal,
Increase / Decrease in Capital Stock → Equity Repurchase subtotal,
ΔLT Investments,
Cash from Divestitures, Cash for Acq of Subs, Cash for JVs, Other Investing,
Net Cash from Acq & Div subtotal,
Net Cash from Disc Ops (investing),
Cash from Investing Activities,

Dividends Paid,
Cash from Debt / Repayments of Debt → Net Cash from Debt subtotal,
Other Financing,
Net Cash from Disc Ops (financing),
Cash from Financing Activities,

FX Effect,
Net Change in Cash
```

> **Derived（不放 facts）**：Free Cash Flow、FCF to Firm、FCF to Equity、FCF per Basic Share、Price/FCF、Cash Flow to Net Income

---

## 對既有 schema 的影響

| 現有檔案 | 改動 |
|---|---|
| `docs/financials-view-schema.md` | 大幅擴展（~50 → ~110 items）；新增「ROIC.AI label」欄；保留「確認」打勾欄 |
| `docs/financials-data-rules.md` | 加 dual-key 規則 + statement/comparison view 邊界 + supplement 處理規則 |
| `CLAUDE.md`「未確認的指標不得寫入」 | 改成：「`uni_account` 必須是 schema 已確認的 universal key；沒對到的 row 仍可寫入但 uni_account 留 null」|
| `parse-10QK-gaap` IS_TAG_MAP / BS_TAG_MAP / CF_TAG_MAP | 大幅擴展，對齊 ROIC.AI scope |
| `parse-sec-cross-check` GAAP_IS_METRIC_KEYS | 同步擴展 |
| `parse-8k-nongaap` NONGAAP_METRIC_KEYS | 同步擴展（Non-GAAP 的特殊版本） |

---

## CLAUDE.md 規則修訂提案

**目前**：
```
未確認的指標不得寫入、計算或前端讀取
```

**修訂為**：
```
每筆財務 cell 必須包含：
- source_account（PDF 原文 label，永遠有）
- uni_account（屬於以下兩種之一）：
  1. docs/financials-view-schema.md 已確認的核心 universal key
  2. 12 個 long-tail bucket（{section}_long_tail）之一 + misc_long_tail catch-all
- weight（XBRL calculation weight，+1 或 -1）
- value, type, unit, ordinal

Long-tail cell 額外必須帶 long_tail_metadata：
- is_recurring（RECURRING / NON_RECURRING / UNKNOWN）
- last_occurrence_date
- rolls_up_to（顯式 anchor 到核心 subtotal uni_account）

不允許：
- 自由創造新的 uni_account 名稱（任何不認得的科目 → LLM 判定 section → 配對應 bucket）
- 沒有 weight 的 cell（compose 階段拒絕寫入）
- long-tail cell 沒有 rolls_up_to 的（同上）
- rolls_up_to 指向不存在於核心 schema 的 uni_account

Long-tail cell 的下游限制：
- 不得進核心 derive-analytics 公式（margins、ROE 等）的「核心 key 計算」
- 但**可以**透過 weight + rolls_up_to 加總到核心 subtotal（例如所有 anchor 到 total_operating_expenses 的 long-tail cells，乘以各自 weight 後加總，加進 OpEx 總額）
- comparison view 把 long-tail bucket 跟對應的核心 "other" 視為同一概念加總
- statement view 用 source_account 原文顯示，按 ordinal 排在該 section 末尾
- wiki ingest 個股頁全部顯示，跨公司 synthesis 頁忽略

升級 long-tail bucket 內某個 source_account 為核心 key：
1. 在 schema 文件登記
2. 打勾「確認」
3. 加 IS_TAG_MAP / cross-check label_to_key / 8-K label_to_key_nongaap 候選
4. 重抽歷史（既有資料的該 source_account row 從 bucket 切到核心 key）
```

---

## Frontend Statement View 渲染邏輯

```python
def render_company_is(rows):
    # 1. 按 IS section 分組（從 uni_account 推斷 section）
    sections = {
        "revenue":             [],   # revenue, revenue_sales_services, revenue_long_tail, ...
        "cost":                [],   # cost_of_revenue, ..., (還沒有 cost_long_tail bucket)
        "gross_profit":        [],
        "operating_expense":   [],   # R&D, SG&A, other_operating_expense, operating_expense_long_tail
        "operating_income":    [],
        "nonoperating":        [],   # interest_*, other_nonop, nonoperating_long_tail
        "pretax":              [],
        "tax":                 [],
        "below_line":          [],   # NCI, preferred dividends, below_line_long_tail
        "net_income":          [],
        "per_share":           [],   # EPS, shares
    }
    for row in rows:
        section = uni_account_to_section(row.uni_account)
        sections[section].append(row)

    # 2. 每個 section 內按 ordinal 排序（PDF 順序），long-tail 自然排在 ordinal 較後的位置
    for section in sections:
        sections[section].sort(key=lambda r: r.ordinal)

    # 3. 渲染：用 source_account 當 label（PDF-faithful），long-tail row 可加視覺提示（斜體/灰色）
    for section in section_order:
        for row in sections[section]:
            label = row.source_account
            is_long_tail = row.uni_account.endswith("_long_tail")
            render_row(label, row.value, italic=is_long_tail)
```

→ 前端不需要 hard-code「Goodwill impairment 放哪」。**bucket name 編碼了 section，ordinal 編碼了 section 內順序，source_account 提供顯示 label**。新公司來了，bucket 機制自動處理。

## Wiki Ingest 對應（暫不細寫）

使用者表示 Wiki 那邊比較沒問題，先不擔心。基本對應：個股頁用 statement view 邏輯；synthesis 頁用 comparison view 邏輯。等 architecture 拍板後再寫具體 wiki ingest 改動。

---

## Non-GAAP Reconciliation Metadata Schema（v0.3 新增）

依 SEC Reg G / Item 10(e) 強制要求，每筆 Non-GAAP cell 除了 value 還必須帶以下 metadata：

```jsonc
{
  "period":         "Q1_FY2026",
  "source_account": "Non-GAAP gross profit",
  "uni_account":    "gross_profit",
  "value":          4961,
  "type":           "NON_GAAP",                       // ← 跟 GAAP 區分
  "unit":           "USD_millions",

  "non_gaap_metadata": {
    "comparable_gaap_measure": "gross_profit",         // ← 對應的 GAAP 科目
    "comparable_gaap_value":   4672,                   // 該期 GAAP 值
    "adjustments": [                                   // ← reconciliation 明細
      {
        "label":               "Restructuring charges",
        "description":         "Q1 FY26 cost-reduction program",
        "value":               156,                    // 加回的金額
        "tax_effect":          null,                   // 此項是否含稅效應（gross 標 null）
        "recurring_flag":      "RECURRING",            // RECURRING / NON_RECURRING / UNKNOWN
        "comparable_gaap_line": "restructuring_charges"
      },
      {
        "label":               "Stock-based compensation",
        "description":         "SBC expense add-back",
        "value":               89,
        "tax_effect":          null,
        "recurring_flag":      "RECURRING",
        "comparable_gaap_line": null                   // SBC 在 IS 不單獨揭露，在 CF
      },
      {
        "label":               "Tax effect of adjustments",
        "description":         "Tax impact at 12% non-GAAP rate",
        "value":               -29,                    // 通常負數（adjustments 加回後 tax 也要扣）
        "tax_effect":          true,                   // ← 標明是 tax adjustment 本身
        "recurring_flag":      "RECURRING",
        "comparable_gaap_line": "income_tax_expense"
      }
    ],
    "management_usefulness_statement": "Management believes Non-GAAP gross profit excludes the impact of one-time restructuring and stock-based compensation, providing a clearer view of underlying operating performance."
  }
}
```

### 5 個強制 metadata 欄位

| 欄位 | SEC 來源 | 規則 |
|---|---|---|
| `comparable_gaap_measure` | Reg G | Performance measure → reconciles to Net Income / line on IS；Liquidity → Cash from Ops |
| `adjustment.label` + `adjustment.description` | Item 10(e) | 不可用 "Other"；明確說明 nature & purpose |
| `adjustment.tax_effect` | C&DI 102.11 | 必須以 gross of tax 列 + tax 作為**獨立**調整項，不可用 "net of tax" |
| `adjustment.recurring_flag` | Item 10(e)(1)(ii)(B) | 過去/未來 2 年內若再發生不可標 NON_RECURRING |
| `management_usefulness_statement` | Item 10(e)(1)(i)(C) | 管理層為何認為這 metric 有用的說明 |

→ 對 `parse-8k-nongaap` skill 影響：擴抽 reconciliation table 的 adjustments 明細，不只是 final Non-GAAP 值。**這是這個 skill 之後要擴展的項目**。

---

## 前端 SEC 合規規則（v0.3 新增）

雖然我們的前端不是 SEC 公開揭露，但這些規則仍應遵守，避免誤導使用者：

### 規則 1：GAAP 必須優先或同等顯著於 Non-GAAP

| 不可以 | 可以 |
|---|---|
| Non-GAAP 排在 GAAP 前面 | GAAP 排前、Non-GAAP 後 |
| Non-GAAP 用粗體/大字/突出色彩，GAAP 普通 | 兩者同樣排版 |
| 只展示 Non-GAAP 圖表，不展示 GAAP 對應圖表 | 兩者並列展示 |

### 規則 2：Reconciliation 必須從 GAAP 開始

```
✅ 正確：
  GAAP Operating Income     -301
  + Restructuring charges    156
  + SBC                       89
  + Amortization of intang.   89
  + Other adjustments         15
  = Non-GAAP Operating Income  48

❌ 錯誤：
  Non-GAAP Operating Income   48
  - Restructuring charges    156
  ...
  = GAAP Operating Income   -301
```

### 規則 3：嚴禁完整 "Non-GAAP Income Statement"

SEC C&DI 102.10(c) 明文：「**presenting a Non-GAAP income statement** comprised of Non-GAAP measures and includes all or most of the line items and subtotals found in a GAAP income statement」屬於賦予 Non-GAAP 不當顯著性。

→ **UI 設計修正**：

| 錯誤設計 | 正確設計 |
|---|---|
| 「Non-GAAP P&L tab」並列「GAAP P&L tab」，各自完整 P&L | **預設只顯示 GAAP P&L**；Non-GAAP 用 reconciliation table 從 GAAP 出發呈現 |
| 「切換 GAAP / Non-GAAP view」滑軌 | **同頁同表**：GAAP 主表 + 重點科目（rev / GP / OI / NI / EPS）併列 GAAP 跟 Non-GAAP 兩欄 |
| Goodwill impairment 在 Non-GAAP 表 = 0 看不出來 | reconciliation 明確列「+ Goodwill impairment 1830」當 adjustment |

### 對使用者的取捨：彈性 vs 合規

使用者早先想要「打開網頁看完整 Non-GAAP P&L」直覺，跟 SEC 規則有衝突。

**建議妥協**：
- 個股頁主表 = GAAP P&L（PDF-faithful，按 statement view 邏輯渲染）
- 重點科目（revenue、operating_income、net_income、EPS、shares）併列 GAAP / Non-GAAP 兩欄，方便對照
- 「Non-GAAP Reconciliation」區塊獨立，從 GAAP 出發列 adjustments 到 Non-GAAP
- **不單獨呈現完整 Non-GAAP P&L**

這樣既滿足你「不用打開 PDF 對照」的初衷，也符合 SEC 對 Non-GAAP 顯著性的規範。

---

## Segment Reporting（Future Work, v0.3 列入）

ASC Topic 280 要求每個 reportable segment 揭露：
- Segment Revenue
- Segment Profit/Loss（公司可用 non-GAAP measure，但要遵 Reg G）
- Segment Total Assets
- Segment 其他重要項目（如 R&D、capex 等視 CODM 揭露決定）

半導體業 segment 結構（範例）：
- INTC: DCAI / Foundry / NEX / CCG / Mobileye / Other
- SNDK: Client / Datacenter / Consumer / Other
- AVGO: Semiconductor Solutions / Software
- NVDA: Data Center / Gaming / Pro Visualization / Auto / OEM & Other

→ **不適合塞進 `financial_facts`**（它是 consolidated 維度），需要獨立表：

```jsonc
// financial_segment 表 schema (proposed)
{
  "ticker":           "INTC",
  "period":           "Q1_FY2026",
  "segment_name":     "Datacenter and AI",     // ← 公司原本的 segment 名稱
  "segment_uni":      "data_center",            // ← 統一 segment key（為跨公司比較）
  "metric":           "segment_revenue",
  "value":            4040,
  "unit":             "USD_millions",
  "type":             "GAAP",                   // 或 NON_GAAP
  "source_filing":    "10-Q"
}
```

未來 skill：
- `parse-segment-info` — 從 10-K Item 8 / Note "Segment Information" 抽
- 跨公司 segment uni_account 字典：`data_center`、`client_compute`、`networking`、`automotive`、`memory`、`foundry` 等

**列入 future work，不擋本次 schema 拍板**。

---

## Open Questions（等使用者拍板）

1. **架構整體（dual-key + 12 long-tail buckets + section-based rendering）OK 嗎？** ← 最關鍵
2. **`cost_of_revenue` vs `cost_of_goods_sold`**：ROIC.AI 用前者，我們現有 schema 用後者。要 rename 嗎？
3. **Net income 雙層命名**：ROIC.AI 有 `Net Income IBM`（before NCI）跟 `Net Income GAAP`（after NCI）。我們現有 `net_income_total_pre_nci` + `net_income`。對齊？
4. **Sub-breakdown 進核心還是 bucket？** 例如 BS 的 Raw Materials / WIP / Finished Goods（公司不一定揭露細項）。我傾向：**進核心 schema**，因為這是會計上有名稱的標準科目，公司沒揭露就缺值，但不該歸 long-tail。你？
5. **Subtotal 進核心還是 bucket？** 如「Receivables 小計」「Other ST Assets 小計」。我傾向：**進核心**，跨公司比較有用。你？
6. **Number of Employees**：不是會計科目，是公司基本資料。建議放 `financial_companies` 或獨立 `company_metadata` 表，不放 facts。
7. **Schema 大幅擴展的回填**：現有 INTC、SNDK、2454 的歷史資料要不要重抽以補新 metric？我傾向：**先擴 schema + IS_TAG_MAP，下次新財報來時自動有；舊資料不主動回填，等各別 ticker 需要再個別重抽**。
8. **misc_long_tail catch-all**：要不要保留一個「連 section 都判不出來」的最後 bucket？我傾向：**要**，否則 LLM 為了強行配對會誤判。

---

## 不在這份 draft 處理的事

- Supabase 表 schema migration（等架構拍板再做）
- 既有資料的 backfill（同上）
- 前端 statement view / comparison view 實作（前端工程議題，獨立討論）
- Wiki ingest 模板修訂（等架構拍板再修 wiki-ingest skill）
