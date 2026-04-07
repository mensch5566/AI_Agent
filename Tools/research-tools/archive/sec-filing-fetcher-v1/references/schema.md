# JSON Schema — Financial Timeseries

## 頂層結構

```json
{
  "metadata":             { ... },
  "filings":              { "Q1_FY2026": { ... }, ... },
  "income_statement":     { "revenue": { "Q1_FY2026": 13643, ... }, ... },
  "balance_sheet":        { "assets": { ... }, "liabilities": { ... }, "equity": { ... } },
  "cash_flow_statement":  { "operating_activities": { ... }, ... },
  "revenue_by_product":   { "DRAM": { "Q1_FY2026": 10812, ... }, ... },
  "segment_data":         { "CMBU": { ... }, ..., "total": { ... } },
  "notable_events":       [ { "period": "Q1_FY2026", ... }, ... ]
}
```

---

## metadata

| 欄位 | 型別 | 說明 |
|---|---|---|
| company | string | 公司全名 |
| ticker | string | 股票代號（大寫） |
| exchange | string | 交易所（NASDAQ / NYSE / ...） |
| fiscal_year_end | string | 財政年度說明 |
| currency | string | 幣別（USD） |
| unit | string | 單位（millions_except_per_share） |
| last_updated | string | 最後更新日 YYYY-MM-DD |
| periods | array[string] | 所有期間，**由舊到新**，格式 Q{n}_FY{YYYY} |

## filings（每個 period 的申報資訊）

| 欄位 | 型別 | 說明 |
|---|---|---|
| form | string | 10-Q 或 10-K |
| period_end | string | 期末日 YYYY-MM-DD |
| filing_date | string | 申報日 YYYY-MM-DD |
| accession_number | string | SEC accession number |
| source_url | string | SEC EDGAR HTM URL |

---

## income_statement（所有欄位均為 period-keyed dict，值為數值或 null）

| 欄位 | 單位 | 說明 |
|---|---|---|
| revenue | M | 總營收 |
| cost_of_goods_sold | M | 銷貨成本 |
| gross_margin | M | 毛利 |
| gross_margin_pct | ratio | 毛利率（0.56 = 56%） |
| research_and_development | M | 研發費用 |
| selling_general_administrative | M | SG&A |
| other_operating_income_expense_net | M | 其他營業收支 |
| operating_income | M | 營業利益 |
| operating_margin_pct | ratio | 營業利益率 |
| interest_income | M | 利息收入 |
| interest_expense | M | 利息費用（負數） |
| interest_income_net | M | 淨利息收支 |
| other_nonoperating_income_expense | M | 其他非營業收支 |
| income_before_taxes | M | 稅前淨利 |
| income_tax_provision | M | 所得稅費用（負數） |
| effective_tax_rate | ratio | 有效稅率 |
| equity_in_net_income_of_investees | M | 被投資公司損益 |
| net_income | M | 淨利 |
| net_margin_pct | ratio | 淨利率 |
| eps_basic | USD | 基本每股盈餘 |
| eps_diluted | USD | 稀釋每股盈餘 |
| shares_basic_millions | M shares | 基本加權平均股數 |
| shares_diluted_millions | M shares | 稀釋加權平均股數 |

---

## balance_sheet

### assets

| 欄位 | 單位 |
|---|---|
| cash_and_cash_equivalents | M |
| short_term_investments | M |
| receivables | M |
| inventories | M |
| other_current_assets | M |
| total_current_assets | M |
| long_term_marketable_investments | M |
| property_plant_equipment_net | M |
| operating_lease_right_of_use | M |
| intangible_assets | M |
| deferred_tax_assets | M |
| goodwill | M |
| other_noncurrent_assets | M |
| total_assets | M |

### liabilities

| 欄位 | 單位 |
|---|---|
| accounts_payable_and_accrued_expenses | M |
| current_debt | M |
| other_current_liabilities | M |
| total_current_liabilities | M |
| long_term_debt | M |
| noncurrent_operating_lease_liabilities | M |
| noncurrent_unearned_gov_incentives | M |
| other_noncurrent_liabilities | M |
| total_liabilities | M |

### equity

| 欄位 | 單位 |
|---|---|
| common_stock | M |
| additional_capital | M |
| retained_earnings | M |
| treasury_stock | M（負數） |
| accumulated_other_comprehensive_income_loss | M |
| total_equity | M |
| total_liabilities_and_equity | M |

---

## cash_flow_statement

### operating_activities / investing_activities / financing_activities

每個 section 的欄位見 10-Q 現金流量表，欄位名稱用 snake_case。

### 頂層摘要欄位

| 欄位 | 說明 |
|---|---|
| fx_effect_on_cash | 匯率影響 |
| net_change_in_cash | 現金淨增減 |
| beginning_cash | 期初現金 |
| ending_cash | 期末現金 |
| free_cash_flow | OCF + CapEx（CapEx 為負數） |

---

## revenue_by_product

各產品線營收，key 為產品名稱（如 `DRAM`、`NAND`、`Other_NOR`），值為 period-keyed dict。
另含 `{product}_mix_pct`（ratio）和 `total`。

**注意**：不同公司產品線不同，建立時依實際財報調整 key 名稱。

---

## segment_data

每個業務部門一個 key（如 `CMBU`、`CDBU`），plus `total`。

每個部門包含：

| 欄位 | 型別 |
|---|---|
| full_name | string（常數） |
| description | string（常數） |
| revenue | period-keyed dict |
| revenue_mix_pct | period-keyed dict（ratio） |
| operating_income | period-keyed dict |
| operating_margin_pct | period-keyed dict（ratio） |
| depreciation_amortization | period-keyed dict |
| goodwill | period-keyed dict |

`total` 包含：`revenue`、`operating_income`、`unallocated`。

**注意**：不同公司 Segment 結構不同，建立時依實際財報調整。

---

## notable_events

每筆事件的欄位：

| 欄位 | 說明 |
|---|---|
| period | 所屬期間（如 Q1_FY2026） |
| category | 分類（Debt / Manufacturing / Legislation / Litigation / Capital Return / ...） |
| date | 事件日期 YYYY-MM-DD |
| description | 事件描述 |

---

## Period 命名規範

- 格式：`Q{n}_FY{YYYY}`
- 例：`Q1_FY2026`、`Q4_FY2025`（Q4 = 財政年度末，即 10-K）
- `periods` 陣列由舊到新排列
- 新增季度 = 在所有 dict 中新增對應 key，不改動舊資料
