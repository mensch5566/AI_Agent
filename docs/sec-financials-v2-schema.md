# SEC Financials v2 — Canonical Dictionary

最後更新：2026-05-16
狀態：v1 起手版，AAOI 基礎；INTC / SNDK onboarding 時擴展

> 這份文件是 SEC 美股 financials 的 **canonical uni_account dictionary**，對應 Supabase `sec_financial_*` 表。
>
> 配套文件：
> - `tmp/financials-viewer-redesign-plan.md` §20 (v5.1) — 整體 schema / adapter 設計
> - `docs/financials-view-schema.md` — 全市場 metric dictionary authority（這份是 SEC v2 section 的 detail）
> - `docs/financials-data-rules.md` — 行為規則（quarterly/annual、derive 紀律）
>
> 編輯紀律：**任何 uni_account 異動（新增 / 改名 / 刪除）必須先在此文件登記並打勾「確認」**，之後才能加進 IS_TAG_MAP / 寫進 DB / 在前端讀取。

---

## 0. 圖例與全域規則

| 符號 | 意思 |
|---|---|
| ✅ | 已 ingest 入庫並驗證 |
| ⬜ | dictionary 已定，等 ingest |
| ❌ | XBRL 無，需 NLM fallback 或 8-K |

### 0.1 統一 statement 值

| statement | 對應 SEC report 區塊 | 落點表 |
|---|---|---|
| `IS` | Income Statement (3 statements 之 P&L) | facts / metrics |
| `BS` | Balance Sheet | facts / metrics |
| `CF` | Cash Flow Statement | facts / metrics |
| `RATIO` | direct disclosed ratio (8-K / 10-K text) | facts (SOURCE_OF_TRUTH) / metrics (DERIVED) |
| `SEGMENT` | dimensional disclosure | dimensional_facts only |

### 0.2 統一 version 值

| version | 意思 |
|---|---|
| `GAAP` | XBRL primary / 10-Q / 10-K 三大表揭露 |
| `NON_GAAP` | 8-K Exhibit 99.1 / press release 揭露的管理層調整值 |

### 0.3 統一 period_kind 值

| period_kind | 意思 | 例 |
|---|---|---|
| `quarter_duration` | 單季 duration（IS / CF / RATIO） | Q1_FY2025 revenue |
| `fy_annual_duration` | 全年 duration | FY2024 revenue |
| `ytd_duration` | YTD 累積 duration（10-Q 6M / 9M） | 9M_FY2025 cogs |
| `instant_period_end` | 期末 instant（BS 一律用此） | Q4_FY2024 total_assets / FY2024 total_assets |
| `derived_q4` | metrics-only：FY − Q1 − Q2 − Q3 還原值 | Q4_FY2024 revenue |

### 0.4 統一 unit 值

| canonical unit | 涵蓋 raw value |
|---|---|
| `USD_thousands` | `USD_thousands` / `thousands of USD` / `USD` + decimals=-3 |
| `USD_millions` | `USD_millions` / `millions of USD` / `USD` + decimals=-6 |
| `USD` | `USD` 純美元（no decimals scaling） |
| `USD_per_share` | `USD_per_share` / `USD/share` / 在 EPS context 下的 `USD` |
| `millions_shares` | `millions_shares` |
| `thousands_shares` | `thousands_shares` |
| `Pure` | `Pure` / `percent` / `Percent`（pct 一律存小數，0~1） |

adapter 必須 canonicalize 到上述七種之一；其他 raw value 寫 validation error。

---

## 1. Income Statement (IS)

### 1.1 核心 universal keys

科目順序 = 美股 P&L 由上而下標準順序。

| 順 | uni_account | XBRL tag (常見) | 說明 | 確認 |
|---|---|---|---|---|
| 1 | `revenue` | `us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax` / `Revenues` | top-line 銷貨收入 | ✅ |
| 2 | `cost_of_goods_sold` | `us-gaap:CostOfGoodsAndServicesSold` / `CostOfRevenue` | 銷貨成本（含服務） | ✅ |
| 3 | `gross_profit` | `us-gaap:GrossProfit` | 營業毛利 | ✅ |
| 4 | `selling_general_administrative` | `us-gaap:SellingGeneralAndAdministrativeExpense` (or SUM of S&M + G&A) | 銷管費用，**含 SG&A subtotal 缺漏時用 S&M+G&A sum** | ✅ |
| 5 | `research_and_development` | `us-gaap:ResearchAndDevelopmentExpense` | 研發費用 | ✅ |
| 6 | `amortization_of_acquired_intangibles` | `us-gaap:AmortizationOfIntangibleAssets` | 無形資產攤銷 | ✅ |
| 7 | `total_operating_expenses` | `us-gaap:OperatingExpenses` | 營業費用合計 | ✅ |
| 8 | `operating_income` | `us-gaap:OperatingIncomeLoss` | 營業利益 | ✅ |
| 9 | `interest_income` | `us-gaap:InvestmentIncomeInterest` | 利息收入 | ✅ |
| 10 | `interest_expense` | `us-gaap:InterestExpense` / `InterestExpenseNonoperating` | 利息費用（含 nonoperating 變體） | ✅ |
| 11 | `interest_and_other_net` | `us-gaap:NonoperatingIncomeExpense` | 業外淨額 | ✅ |
| 12 | `other_nonoperating_income_expense` | `us-gaap:OtherNonoperatingIncomeExpense` | 其他業外 | ✅ |
| 13 | `income_before_taxes` | `us-gaap:IncomeLossFromContinuingOperationsBeforeIncomeTaxes...` | 稅前淨利 | ✅ |
| 14 | `income_tax_expense` | `us-gaap:IncomeTaxExpenseBenefit` | 所得稅 | ✅ |
| 15 | `net_income` | `us-gaap:NetIncomeLoss` | 淨利（attributable to parent） | ✅ |
| 16 | `net_income_available_to_common` | `us-gaap:NetIncomeLossAvailableToCommonStockholdersBasic` | 歸屬於母公司普通股東淨利（= net_income − below_line items 如 participating securities allocation；EPS numerator） | ✅ |
| 17 | `eps_basic` | `us-gaap:EarningsPerShareBasic` | 基本 EPS（unit=USD_per_share） | ✅ |
| 18 | `eps_diluted` | `us-gaap:EarningsPerShareDiluted` | 稀釋 EPS（unit=USD_per_share） | ✅ |
| 19 | `shares_basic_millions` | dei 或 instance fact (no GAAP tag) | 基本股數（百萬股） | ✅ |
| 20 | `shares_diluted_millions` | 同上 | 稀釋股數 | ✅ |

### 1.2 IS long-tail buckets

公司特殊揭露不在核心 key 時，配對應 bucket：

| Bucket uni_account | 涵蓋範圍 | rolls_up_to |
|---|---|---|
| `revenue_long_tail` | 營收細項拆分 | `revenue` |
| `cost_of_revenue_long_tail` | COGS 內細項（COGS-portion amortization 等獨立揭露） | `cost_of_goods_sold` |
| `operating_expense_long_tail` | OpEx 內非標準項（goodwill imp / restructuring / business sep） | `total_operating_expenses` |
| `nonoperating_long_tail` | OpInc 與稅前淨利之間（divestiture gain/loss / equity method 特例） | `income_before_taxes` |
| `below_line_long_tail` | NI 附近（discontinued ops / accounting change / participating securities allocation） | `net_income` |

**AAOI 實際出現的 long-tail**：`operating_expense_long_tail` 用於 SG&A 子科目分拆（`SellingAndMarketingExpense`, `GeneralAndAdministrativeExpense`），rolls_up_to=`selling_general_administrative`。

**LITE 實際出現的 long-tail**：`cost_of_revenue_long_tail` 用於 COGS-portion amortization（XBRL `CostOfGoodsAndServicesSoldAmortization`，PDF "Amortization of acquired developed intangibles"），rolls_up_to=`cost_of_goods_sold`。Lumentum 把無形資產攤銷拆 COGS-portion 獨立揭露於 gross profit 之上，跟核心 `amortization_of_acquired_intangibles`（總額）區分。

---

## 2. Balance Sheet (BS)

> period_kind 一律 `instant_period_end`。

### 2.1 核心 universal keys — 資產

| 順 | uni_account | XBRL tag | 確認 |
|---|---|---|---|
| 1 | `cash_and_cash_equivalents` | `us-gaap:CashAndCashEquivalentsAtCarryingValue` | ✅ |
| 2 | `accounts_receivable` | `us-gaap:AccountsReceivableNetCurrent` | ✅ |
| 3 | `inventories` | `us-gaap:InventoryNet` | ✅ |
| 4 | `other_current_assets` | `us-gaap:PrepaidExpenseAndOtherAssetsCurrent` | ✅ |
| 5 | `total_current_assets` | `us-gaap:AssetsCurrent` | ✅ |
| 6 | `ppe_gross` | `us-gaap:PropertyPlantAndEquipmentGross` | ✅ |
| 7 | `accumulated_depreciation` | `us-gaap:AccumulatedDepreciation...` | ✅ |
| 8 | `property_plant_equipment_net` | `us-gaap:PropertyPlantAndEquipmentNet` | ✅ |
| 9 | `operating_lease_rou_asset` | `us-gaap:OperatingLeaseRightOfUseAsset` | ✅ |
| 10 | `intangible_assets` | `us-gaap:FiniteLivedIntangibleAssetsNet` | ✅ |
| 11 | `deferred_tax_assets` | `us-gaap:DeferredIncomeTaxAssetsNet` | ✅ |
| 12 | `other_noncurrent_assets` | `us-gaap:OtherAssetsNoncurrent` | ✅ |
| 13 | `total_assets` | `us-gaap:Assets` | ✅ |

### 2.2 核心 universal keys — 負債

| 順 | uni_account | XBRL tag | 確認 |
|---|---|---|---|
| 1 | `accounts_payable` | `us-gaap:AccountsPayableCurrent` | ✅ |
| 2 | `accrued_liabilities` | `us-gaap:AccruedLiabilitiesCurrent` | ✅ |
| 3 | `income_taxes_payable_current` | `us-gaap:TaxesPayableCurrent` | ✅ |
| 4 | `current_portion_of_long_term_debt` | `us-gaap:LongTermDebtCurrent` | ✅ |
| 5 | `current_portion_of_lease_obligations` | `us-gaap:OperatingLeaseLiabilityCurrent` | ✅ |
| 6 | `deferred_revenue_current` | `us-gaap:ContractWithCustomerLiabilityCurrent` | ✅ |
| 7 | `total_current_liabilities` | `us-gaap:LiabilitiesCurrent` | ✅ |
| 8 | `long_term_debt` | `us-gaap:LongTermDebtNoncurrent` | ✅ |
| 9 | `operating_lease_noncurrent` | `us-gaap:OperatingLeaseLiabilityNoncurrent` | ✅ |
| 10 | `deferred_revenue_noncurrent` | `us-gaap:ContractWithCustomerLiabilityNoncurrent` | ✅ |
| 11 | `total_liabilities` | `us-gaap:Liabilities` | ✅ |

### 2.3 核心 universal keys — 權益

| 順 | uni_account | XBRL tag | 確認 |
|---|---|---|---|
| 1 | `common_stock` | `us-gaap:CommonStockValue` | ✅ |
| 2 | `additional_paid_in_capital` | `us-gaap:AdditionalPaidInCapital` | ✅ |
| 3 | `retained_earnings` | `us-gaap:RetainedEarningsAccumulatedDeficit` | ✅ |
| 4 | `aoci` | `us-gaap:AccumulatedOtherComprehensiveIncomeLossNetOfTax` | ✅ |
| 5 | `total_equity` | `us-gaap:StockholdersEquity` | ✅ |
| 6 | `total_liabilities_and_equity` | `us-gaap:LiabilitiesAndStockholdersEquity` | ✅ |

### 2.4 BS long-tail buckets

| Bucket | rolls_up_to |
|---|---|
| `current_asset_long_tail` | `total_current_assets` |
| `noncurrent_asset_long_tail` | `total_assets` − `total_current_assets` |
| `current_liability_long_tail` | `total_current_liabilities` |
| `noncurrent_liability_long_tail` | `total_liabilities` − `total_current_liabilities` |
| `equity_long_tail` | `total_equity` |

---

## 3. Cash Flow Statement (CF)

### 3.1 核心 universal keys — Operating

| uni_account | XBRL tag | 確認 |
|---|---|---|
| `net_income` (CF starting) | `us-gaap:NetIncomeLoss` | ✅ |
| `depreciation_and_amortization` | `us-gaap:DepreciationAndAmortization` | ✅ |
| `share_based_compensation` | `us-gaap:ShareBasedCompensation` | ✅ |
| `deferred_income_tax` | `us-gaap:DeferredIncomeTaxExpenseBenefit` | ✅ |
| `other_asset_impairment` | `us-gaap:AssetImpairmentCharges` | ✅ |
| `gain_loss_on_sale_cf` | `us-gaap:GainLossOnDispositionOfAssets1` | ✅ |
| `change_in_receivables` | `us-gaap:IncreaseDecreaseInAccountsReceivable` | ✅ |
| `change_in_inventories` | `us-gaap:IncreaseDecreaseInInventories` | ✅ |
| `change_in_accounts_payable` | `us-gaap:IncreaseDecreaseInAccountsPayable` | ✅ |
| `change_in_accrued_liabilities` | `us-gaap:IncreaseDecreaseInAccruedLiabilities` | ✅ |
| `net_cash_from_operating` | `us-gaap:NetCashProvidedByUsedInOperatingActivities` | ✅ |

### 3.2 核心 universal keys — Investing

| uni_account | XBRL tag | 確認 |
|---|---|---|
| `capital_expenditures` | `us-gaap:PaymentsToAcquirePropertyPlantAndEquipment` | ✅ |
| `net_cash_from_investing` | `us-gaap:NetCashProvidedByUsedInInvestingActivities` | ✅ |

### 3.3 核心 universal keys — Financing

| uni_account | XBRL tag | 確認 |
|---|---|---|
| `issuance_of_common_stock` | `us-gaap:ProceedsFromIssuanceOfCommonStock` | ✅ |
| `net_cash_from_financing` | `us-gaap:NetCashProvidedByUsedInFinancingActivities` | ✅ |

### 3.4 核心 universal keys — Supplemental

| uni_account | XBRL tag | 確認 |
|---|---|---|
| `cash_income_tax_paid` | `us-gaap:IncomeTaxesPaidNet` | ✅ |
| `cash_interest_paid` | `us-gaap:InterestPaidNet` | ✅ |
| `net_change_in_cash` | `us-gaap:CashCashEquivalentsRestrictedCash...PeriodIncreaseDecrease...` | ✅ |
| `ending_cash` | `us-gaap:CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents` | ✅ |

### 3.5 CF long-tail buckets

| Bucket | rolls_up_to |
|---|---|
| `operating_cf_long_tail` | `net_cash_from_operating` |
| `investing_cf_long_tail` | `net_cash_from_investing` |
| `financing_cf_long_tail` | `net_cash_from_financing` |

---

## 4. Ratios (RATIO)

direct disclosed ratios → `sec_financial_facts` (SOURCE_OF_TRUTH, version=GAAP|NON_GAAP)
derived ratios → `sec_financial_metrics` (DERIVED_FROM_DISCLOSED)

unit 一律 `Pure`，value 一律存小數（0~1）。

| uni_account | version | 公式（derived 時） | 確認 |
|---|---|---|---|
| `gross_margin_pct` | GAAP / NON_GAAP | `gross_profit / revenue` | ⬜ |
| `operating_margin_pct` | GAAP / NON_GAAP | `operating_income / revenue` | ⬜ |
| `net_margin_pct` | GAAP / NON_GAAP | `net_income / revenue` | ⬜ |
| `ebitda_margin_pct` | GAAP / NON_GAAP | `ebitda / revenue` | ⬜ |
| `adjusted_ebitda_margin_pct` | NON_GAAP | `adjusted_ebitda / revenue` | ⬜ |
| `effective_tax_rate` | GAAP | `income_tax_expense / income_before_taxes` | ⬜ |
| `roe` | GAAP | `net_income_TTM / avg_total_equity` | ⬜ |
| `roa` | GAAP | `net_income_TTM / avg_total_assets` | ⬜ |
| `current_ratio` | GAAP | `total_current_assets / total_current_liabilities` | ✅ |
| `cash_ratio` | GAAP | `cash_and_cash_equivalents / total_current_liabilities` | ✅ |

### 4.1 `RATIO_UNI_ACCOUNTS` allowlist

Non-GAAP IS array routing 用（§20.2）。adapter 在 `income_statement[]` 內看到下列 uni_account 一律 route 到 `statement='RATIO'`：

```python
RATIO_UNI_ACCOUNTS = {
    "gross_margin_pct",
    "operating_margin_pct",
    "net_margin_pct",
    "ebitda_margin_pct",
    "adjusted_ebitda_margin_pct",
    "effective_tax_rate",
}
```

Safety net：unit ∈ `PCT_UNITS` 且 `uni_account.endswith("_pct")` 或 `"margin" in uni_account` → 也 route 到 RATIO（防新 ratio 漏進 allowlist）。

---

## 5. Non-GAAP IS Spotlight Metrics

8-K Exhibit 99.1 揭露的核心 Non-GAAP IS（**不是完整 P&L**，是並列重點欄）：

| uni_account | source label (AAOI 範例) | 確認 |
|---|---|---|
| `revenue` | `Non-GAAP revenue` | ✅ |
| `gross_profit` | `Non-GAAP total gross profit (a)` | ✅ |
| `operating_income` | `Non-GAAP operating income/(loss)` | ⬜ (AAOI 未揭露) |
| `net_income` | `Non-GAAP net loss` / `Non-GAAP net income (loss)` | ✅ |
| `eps_diluted` | `Non-GAAP diluted net loss per share` | ✅ |
| `adjusted_ebitda` | `Adjusted EBITDA` | ✅ |

### 5.1 `NONGAAP_SPOTLIGHT_METRICS` 前端 const

```ts
export const NONGAAP_SPOTLIGHT_METRICS = [
  "revenue",
  "gross_profit",
  "operating_income",
  "net_income",
  "eps_diluted",
  "adjusted_ebitda",
];
```

公司未揭露 → 顯示 `—` + tag `not disclosed by management`。

---

## 6. Dimensional Facts (SEGMENT)

落點：`sec_financial_dimensional_facts`，不混 consolidated facts。

### 6.1 統一 axis 值

| axis | XBRL axis_qname (常見) | 對應 dashboard 區塊 |
|---|---|---|
| `product` | `srt:ProductOrServiceAxis` | 產品線拆分 |
| `geography` | `us-gaap:StatementGeographicalAxis` / `srt:StatementGeographicalAxis` | 地理分布 |
| `customer_concentration` | `srt:MajorCustomersAxis` / `us-gaap:MajorCustomersAxis` | 大客戶集中度 |
| `business_segment` | `us-gaap:StatementBusinessSegmentsAxis` | 事業部 |

### 6.2 統一 uni_account 值

| uni_account | unit | 適用 axis |
|---|---|---|
| `revenue` | `USD_thousands` | product / geography / business_segment |
| `revenue_pct_of_total` | `Pure`（0~1） | customer_concentration |
| `long_lived_assets` | `USD_thousands` | geography |
| `segment_operating_income` | `USD_thousands` | business_segment |
| `segment_assets` | `USD_thousands` | business_segment |

### 6.3 Member alias map

`Tools/research-tools/_shared/dimensional_aliases.py` 全域 alias map：

| canonical key | aliases |
|---|---|
| `data_center` | `Data Center`, `Datacenter`, `Data-Center`, `data center` |
| `5g` | `5G`, `5g` |
| `fttx` | `FTTx`, `fttx` |
| `ftth` | `FTTH`, `ftth`, `FTTH and Other` (注意：含 Other 是不同 member，不要 alias) |
| `catv` | `CATV`, `catv` |
| `telecom` | `Telecom` |
| `united_states` | `UNITED STATES`, `United States`, `U.S.` |
| `china` | `CHINA`, `China`, `PRC` |
| `taiwan` | `TAIWAN`, `Taiwan` |

新公司 ingest 時看到沒對到的 member → 加 alias 並 commit review。

---

## 7. Sign-Flip Concepts

parse-10QK-gaap 產出 `{TICKER}_sign_flip_concepts.json`，列出有 `negatedLabel` role 的 concept（XBRL 存正值，display 時要加括號顯示為負）。

落點：`sec_financial_companies.sign_flip_concepts jsonb`（array of strings）。

**AAOI 範例**（55 個 concept）：
```
aaoi:AccumulatedDepreciationDepletionAndAmortizationPropertyPlantAndEquipmentBeforeConstructionInProcess
aaoi:AmortizationOfDebtPremium
us-gaap:Depreciation
us-gaap:OperatingExpenses
...
```

前端 render 時：`if (xbrl_tag in sign_flip_concepts) → display value with parentheses`。

---

## 8. Confirmation Workflow

新增 / 改名 uni_account 流程：

1. 在此文件對應區塊新增 row，狀態 `⬜`
2. 在 PR / commit 內人工 review
3. 確認後改 `✅`
4. 加進 parser IS_TAG_MAP / IS_TAG_MAP 候選
5. 必要時重抽歷史資料
6. 寫進 `Tools/research-tools/_shared/sec_json_adapter.py` 的 canonical map

未走完流程的 uni_account：
- 不可加進 IS_TAG_MAP
- 不可寫進 DB
- 前端不可讀取

---

## 9. Coverage 進度

| Ticker | IS | BS | CF | RATIO | SEGMENT | last update |
|---|---|---|---|---|---|---|
| AAOI | ✅ 12 periods (Q1-Q3 + FY of FY23-25 + Q1_FY2026) | ✅ 13 quarter-ends | ✅ 12 periods | ⬜ disclosed 無 | ✅ product/geo/customer | 2026-05-16 |
| INTC | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | onboarding pending |
| SNDK | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | onboarding pending |
