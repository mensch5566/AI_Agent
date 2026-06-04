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
| `derived_q2` | metrics-only：6M − Q1 單季還原值 | Q2_FY2025 net_cash_from_operating |
| `derived_q3` | metrics-only：9M − 6M 單季還原值 | Q3_FY2025 net_cash_from_operating |
| `derived_q4` | metrics-only：FY − 9M（或 FY − Q1Q2Q3）還原值 | Q4_FY2024 revenue |
| `ttm_duration` | metrics-only（EL2）：quarterly 滾動 12 個月比率（ROE/ROA = TTM分子 ÷ 平均餘額），period 標 TTM 結束季 | Q3_FY2025 roe |

### 0.4 統一 unit 值

| canonical unit | 涵蓋 raw value |
|---|---|
| `USD_thousands` | `USD_thousands` / `thousands of USD` / `USD` + decimals=-3 |
| `USD_millions` | `USD_millions` / `millions of USD` / `USD` + decimals=-6 |
| `USD` | `USD` 純美元（no decimals scaling） |
| `USD_per_share` | `USD_per_share` / `USD/share` / 在 EPS context 下的 `USD` |
| `millions_shares` | `millions_shares` |
| `thousands_shares` | `thousands_shares` |
| `Pure` | `Pure` / `percent` / `Percent`。**三種 display category**：pct-style（margins / ETR，存小數 0~1）；multiple-style（current/cash/quick ratio、debt_to_equity、interest_coverage、`net_debt_to_ebitda`、`asset_turnover`，倍數、**可超過 1 或為負**，`RATIO_AS_MULTIPLE` 顯示 `x`）；days-style（`dso`/`dio`/`dpo`/`ccc`，存天數本身、CCC 可負，`RATIO_AS_DAYS` 顯示 `days`、chart 獨立軸）。days/x 都是 display category，DB `unit` 仍 `Pure` |

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
| 9 | `interest_income` | `us-gaap:InvestmentIncomeInterest` / `InterestIncomeOther` / `InterestAndDividendIncomeOperating`（**MU ticker-override**: `InvestmentIncomeNet` — Micron face-of-IS「Interest income」用此 tag，語意較廣故只對 MU prepend，`TICKER_IS_TAG_OVERRIDES`）| 利息收入 | ✅ |
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
| 2 | `accounts_receivable` | `us-gaap:AccountsReceivableNetCurrent`（標準）；**ticker override**：LITE = `us-gaap:ContractWithCustomerAssetNet`（ASC 606，見註）| ✅ |
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

> **註 — `accounts_receivable` 的 LITE ASC 606 ticker override**：LITE 採用 ASC 606（FY2018 起）把 BS「Accounts receivable, net」改用 `us-gaap:ContractWithCustomerAssetNet`（標準 `AccountsReceivableNetCurrent` 在 companyfacts 只到 2018-06-30）。parse-10QK-gaap 用 **`TICKER_BS_TAG_OVERRIDES`（ticker-specific，非全域 fallback）** 處理：標準 tag 仍優先，LITE 額外 append contract-asset tag。所以 LITE production 的 `source_account=ContractWithCustomerAssetNet` 是**合約內**來源，非 schema 外。依據：filing lab.xml label = 「Accounts receivable, net」+ BS 流動資產 roll-up 對帳 diff=0。其他 issuer 若也這樣報需顯式加 override（見 `parse-10QK-gaap/SKILL.md` 2026-06-02 CHANGELOG）。

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

### 3.6 CF derived (derive-analytics, NOT facts)

| uni_account | version | formula | unit | 確認 |
|---|---|---|---|---|
| `free_cash_flow` | GAAP | `net_cash_from_operating - capital_expenditures` | USD（per-ticker scale，沿用輸入 facts 的 unit）。**`provenance.basis = GAAP_INPUTS_DERIVED_NON_GAAP_MEASURE`**（FCF 是 SEC named non-GAAP measure / Reg G，非 GAAP line item；前端 `NONGAAP_DERIVED_ROWS` 標記） | ✅ |
| `ebitda` | GAAP | `(net_income + net_income_nci[optional]) + interest_expense + income_tax_expense + depreciation_and_amortization`（**SEC C&DI 103.01 bottom-up，必須從 GAAP net income，非 operating income**；base 用**合併淨利** net_income+NCI（無 NCI → +0），與合併加回項一致；D&A 取 CF 非現金加回）。**derived non-GAAP measure**：`version='GAAP'` 但 `provenance.basis='GAAP_INPUTS_DERIVED_NON_GAAP_MEASURE'`，非 GAAP filing line item | USD（per-ticker scale，FROM_INPUTS）| ✅ |

- **絕對值衍生（非比率）**：derive-analytics 第一個 numerator-only 絕對值 rule（rule_id `FCF_CFO_MINUS_CAPEX`）。statement=`CF`、`status=DERIVED_FROM_DISCLOSED`、寫 `sec_financial_metrics`（**不污染 facts**）。
- **sign convention**：SEC `capital_expenditures`（`PaymentsToAcquirePropertyPlantAndEquipment`）存**正值** cash outflow → `FCF = CFO − capex`（**禁用** TWSE 的相加 pattern）。負 FCF（capex-heavy 季）正常輸出。
- **period_kind**：CF-derived → duration（quarterly `quarter_duration ∪ derived_q2/q3/q4`；annual `fy_annual_duration`）。YTD（6M/9M）skip。
- 只 GAAP（無 NON_GAAP CF facts，引擎自動 skip 該 version）。前端進 `CF_ROWS`（Cash from Operating / capex 之後），渲染為 derived cell（italic muted）。

---

## 4. Ratios (RATIO)

direct disclosed ratios → `sec_financial_facts` (SOURCE_OF_TRUTH, version=GAAP|NON_GAAP)
derived ratios → `sec_financial_metrics` (DERIVED_FROM_DISCLOSED)

unit 一律 `Pure`，分三種 display category：pct-style（margins / ETR，存小數 0~1）；multiple-style（current/cash/quick ratio、debt_to_equity、interest_coverage、`net_debt_to_ebitda`、`asset_turnover`，倍數、**可 >1 或為負**，`RATIO_AS_MULTIPLE` 顯示 `x`）；days-style（`dso`/`dio`/`dpo`/`ccc`，存天數本身、CCC 可負，`RATIO_AS_DAYS` 顯示 `days`）。前端 `fmtValue` / `chartGroupOf` 依此分流顯示與 chart 分軸。**`dpo` 是 COGS-proxy DPO**（真 purchases = COGS + Δinventory，會引入 derived-on-derived，不適合 core key）。`ccc` 是 derived-on-derived（= dio+dso−dpo），provenance.inputs 用三個 component 的 metrics cell_id 追溯。

| uni_account | version | 公式（derived 時） | 確認 |
|---|---|---|---|
| `gross_margin_pct` | GAAP / NON_GAAP | `gross_profit / revenue` | ⬜ |
| `operating_margin_pct` | GAAP / NON_GAAP | `operating_income / revenue` | ⬜ |
| `net_margin_pct` | GAAP / NON_GAAP | `net_income / revenue` | ⬜ |
| `fcf_margin_pct` | GAAP | `(net_cash_from_operating - capital_expenditures) / revenue`。**`provenance.basis = GAAP_INPUTS_DERIVED_NON_GAAP_MEASURE`**（繼承 FCF 的非-GAAP 性質；前端標記） | ✅ |
| `ebitda_margin_pct` | GAAP | `((net_income + net_income_nci[optional]) + interest_expense + income_tax_expense + D&A) / revenue`（= EBITDA/revenue，SEC C&DI 103.01 bottom-up，base 用合併淨利 net_income+NCI；D&A 取 CF；除 NCI 外 required，缺 D&A → skip）。**derived non-GAAP**：`provenance.basis='GAAP_INPUTS_DERIVED_NON_GAAP_MEASURE'` | ✅ |
| `adjusted_ebitda_margin_pct` | NON_GAAP | `adjusted_ebitda / revenue` | ⬜ |
| `effective_tax_rate` | GAAP | `income_tax_expense / income_before_taxes` | ⬜ |
| `roe` | GAAP | `net_income_TTM / avg_total_equity` | ⬜ |
| `roa` | GAAP | `net_income_TTM / avg_total_assets` | ⬜ |
| `roic` | GAAP | `NOPAT_TTM / avg_invested_capital`；NOPAT = operating_income × (1 − TTM_tax/TTM_pretax)；invested capital = total_equity + 有息債（st_borrow+cur_ltd+ltd，exact-value dedup）− cash − short_term_investments。required：equity/cash/operating_income/tax+pretax；optional-as-0：sti+債三項。**pretax≤0 / tax_rate<0 或 >1 / avg invested capital≤0 → skip**（不 clamp）。只存 roic（NOPAT 放 provenance）。cash-rich 公司 IC 變小、ROIC 可能墊高（caveat）| ✅ |
| `current_ratio` | GAAP | `total_current_assets / total_current_liabilities` | ✅ |
| `cash_ratio` | GAAP | `cash_and_cash_equivalents / total_current_liabilities` | ✅ |
| `quick_ratio` | GAAP | `(cash_and_cash_equivalents + short_term_investments[optional] + accounts_receivable) / total_current_liabilities` | ✅ |
| `debt_to_equity` | GAAP | `(short_term_borrowings + current_portion_of_long_term_debt + long_term_debt) / total_equity` | ✅ |
| `interest_coverage` | GAAP | `(income_before_taxes + interest_expense) / interest_expense` | ✅ |
| `net_debt_to_ebitda` | GAAP | `net_debt(期末 BS) / EBITDA(視窗)`（EL2 槓桿，x-multiple）。net_debt = 有息債（st_borrow+cur_ltd+ltd，exact-value dedup）− cash − short_term_investments（cash required；債/sti optional-as-0；**可為負＝淨現金，emit**）。EBITDA = inline 重算（季度 trailing-4 單季 / 年度 FY 的 Σ(net_income+net_income_nci[opt]+interest_expense+income_tax_expense)[IS] + Σ depreciation_and_amortization[CF]，同 EBITDA 口徑）。period_kind：quarterly `ttm_duration`（在 `TTM_RATIO_ROWS`）/ annual `fy_annual_duration`；`period_start = day_after(EBITDA 視窗起點 BS instant)`，缺 anchor 降級 None（不影響 emit）。**skip（不 clamp）**：EBITDA≤0 / 任一 EBITDA 單期 component 缺 / cash 缺。**`provenance.basis = GAAP_INPUTS_DERIVED_NON_GAAP_MEASURE`**（net debt 與 EBITDA 皆 SEC non-GAAP measure，非 GAAP line item；前端 `NONGAAP_DERIVED_ROWS` 標記）。⚠️ **net debt 口徑 caveat**：採 liquid-asset-adjusted（額外減 `short_term_investments`，與 ROIC invested-capital 口徑一致）；比最嚴格的「debt − cash&equivalents」低，跨 vendor 的 net-debt/EBITDA 比較需留意| ✅ |
| `asset_turnover` | GAAP | `revenue_TTM / avg_total_assets`（EL2，x-multiple，display Pure）| ✅ |
| `dso` | GAAP | `365 × avg_accounts_receivable / revenue_TTM`（EL2，days，display Pure）| ✅ |
| `dio` | GAAP | `365 × avg_inventories / cost_of_goods_sold_TTM`（EL2，days）| ✅ |
| `dpo` | GAAP | `365 × avg_accounts_payable / cost_of_goods_sold_TTM`（EL2，days，COGS 為採購代理）| ✅ |
| `ccc` | GAAP | `dio + dso − dpo`（EL2，days，可為負；缺任一 component → skip）| ✅ |
| `revenue_yoy` | GAAP | `(revenue − revenue_year_ago) / revenue_year_ago`（EL2 YoY，pct；prior>0 else skip；quarterly=quarter_duration/derived_q2/q3/q4、annual=fy_annual_duration，**非 ttm**；period_start=None）| ✅ |
| `net_income_yoy` | GAAP | `(net_income − year_ago) / year_ago`（同上）| ✅ |
| `eps_diluted_yoy` | GAAP | `(eps_diluted − year_ago) / year_ago`（同上；EPS 無 derived_q4 → Q4 不出）| ✅ |

#### debt_to_equity / interest_coverage 口徑（EL1 composite，2026-06-01）

需要 **EL1 線性組合引擎**，不是 single (num,den) tuple。EL1 rule schema 應讓 numerator / denominator 都可由 linear terms 組成；本批兩個指標的 denominator 仍是單一 required term，對稱設計是為避免未來 `net_debt / EBITDA` 等指標 refactor，不代表目前 denominator 已有 composite 需求。

- **`debt_to_equity` = interest-bearing debt / total_equity**（不是 total_liabilities — 後者是 liabilities-to-equity）
  - numerator terms（皆 BS，coefficient +1，**optional**：缺項視為 0，因為公司可能真的沒有該類債）：
    `short_term_borrowings`、`current_portion_of_long_term_debt`、`long_term_debt`
  - denominator：`total_equity`（BS，**required**）
  - lease 暫不含（`*_lease_*` 留給未來 `lease_adjusted_debt_to_equity`）
  - period_kind：BS-derived → `instant_period_end`（annual Q4→FY remap）；unit `Pure`，顯示倍數 `x`
  - skip/NM policy：`total_equity <= 0`（負權益）→ skip（比率無意義）；numerator 全缺（無任何 debt）→ skip（不是 0 債就硬給 0）
  - **dedup**：部分發行人（LITE）把同一筆 current debt 同時掛在 `ShortTermBorrowings` 和 `LongTermDebtCurrent` 兩個 XBRL tag（數值完全相等）。numerator 對**數值相等**的 term 只計一次（`RatioRule.dedup_numerator_by_value`），避免 double-count。LITE Q2_FY2026 驗證：(3240.2 once + 47.1)/846.6 = 3.88，非雙計 7.71。
  - ⚠️ 已知限制：(1) `short_term_borrowings`(10) / `current_portion_of_long_term_debt`(25) 覆蓋不全；optional-as-0 在公司有短債但 parse 未抽到時會低估 debt（LTD 為主項）。(2) dedup-by-exact-value 會在「兩筆真的不同的債剛好小數精確相等」時誤合（機率極低）。
- **`interest_coverage` = EBIT / interest_expense**，EBIT = `income_before_taxes + interest_expense`（**不是 operating_income 冒充**）
  - numerator terms（皆 IS，+1，required）：`income_before_taxes`、`interest_expense`
  - denominator：`interest_expense`（IS，required）
  - period_kind：IS-derived → duration（quarterly `quarter_duration ∪ derived_q2/q3/q4`；annual `fy_annual_duration`）；unit `Pure`，顯示倍數 `x`
  - skip/NM policy：`interest_expense <= 0`（無利息費用 / 符號異常）→ skip（除以 0 或負無意義）
  - ⚠️ interest_expense 符號：需確認 parse 端存正值（費用）。EBIT = IBT + interest_expense 假設 interest_expense 為正。
  - ⚠️ convention caveat：這是教科書 / vendor 常見的 times-interest-earned 口徑，但 `income_before_taxes` 已包含 interest income 與其他非營業損益；現金多或非營業收入大的公司會被墊高，可能高估「營業償息能力」。若需要更保守的 operating view，未來另設 `operating_interest_coverage = operating_income / interest_expense`，不可混稱為標準 interest coverage。
- **`quick_ratio` = (cash + short_term_investments + accounts_receivable) / total_current_liabilities**（EL1 composite，BS-derived，2026-06-01）
  - numerator terms（皆 BS）：`cash_and_cash_equivalents`(+1, required)、`short_term_investments`(+1, **optional**)、`accounts_receivable`(+1, required)；denominator：`total_current_liabilities`(required)。
  - **`short_term_investments` optional 的依據**：已查證 AAOI/SNDK 的 BS **完全無**任何 short-term-investments / marketable-securities 科目（連 long-tail 都沒有，parse 抽完整四 linkbase）→ 真的沒有，不是漏抽。所以 optional-as-0 對它們是**正確** quick ratio（cash+AR）/CL，非降級；LITE/INTC 則含其揭露的 `short_term_investments`。`cash` + `accounts_receivable` required（無 receivables 時 quick ratio 無意義 → skip，那只是 cash ratio）。
  - period_kind：BS-derived → `instant_period_end`（annual Q4→FY remap）；unit `Pure`，multiple-style 顯示 `x`（在 `RATIO_AS_MULTIPLE`）。skip：`total_current_liabilities == 0` → skip。
  - provenance.inputs 會顯示各期實際 resolve 了哪些 quick asset 科目（透明可審）。
- **`fcf_margin_pct` = (net_cash_from_operating − capital_expenditures) / revenue**（EL1 **跨 statement** composite，2026-06-01）
  - numerator terms：`net_cash_from_operating`(+1, CF)、`capital_expenditures`(−1, CF)；denominator：`revenue`(IS)。
  - **直接從 CFO/capex/revenue 算**（不依賴 materialize FCF 再除；代數等價、無兩段式 dependency）。
  - CF 與 IS 同期同為 duration、共享 period_kind/period_end → 一致性 guard 通過；YTD skip。pct-style（存小數，**可為負**），unit `Pure`，顯示 `%`（非 `RATIO_AS_MULTIPLE`）。
  - GAAP-only（無 NON_GAAP CF facts，引擎自動 skip 該 version）。skip policy：`revenue == 0` → skip；缺同期 revenue（如早年 Q4 revenue 無法重建）→ skip（LITE Q4_FY2020/FY2021 有 FCF 但無同期 revenue，正確 skip → 19 FCF rows 但 17 fcf_margin rows）。
  - ⚠️ 口徑 caveat：這條只等價於**本管道定義的 FCF**（`CFO − capex`）。若未來 parse 出 management-disclosed FCF（口徑可能不同），**不可**直接混進 `fcf_margin_pct`；應另設 direct/source-specific contract。facts-wins 只保護 disclosed `free_cash_flow` 絕對值，不改變這條 standard-formula 衍生。
- **`book_value_per_share` 暫緩**：需 period-end shares outstanding（instant），現只有 `shares_*_millions`（加權平均 duration）。等 parse 抽 instant shares contract 再做。

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
