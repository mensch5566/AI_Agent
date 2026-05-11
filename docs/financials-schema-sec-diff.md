# 美股 SEC schema 差異對照（待逐項確認）

> 用途：把現有 SEC pipeline (`xbrl_extract.py`) 實際輸出的 metric，跟 `financials-view-schema.md` 美股區塊（U-1～U-3）逐欄比對，作為「美股 schema 確認流程」的審核底稿。
>
> 流程：使用者逐列審核 → 打勾「採用方」→ 同步更新 `financials-view-schema.md`（schema doc 是正式來源）→ 才動 `xbrl_extract.py` 改 metric key。
>
> **規則**：未經此表確認的 metric 不得寫入 Supabase。

來源：
- pipeline 輸出 = `~/AI_Agent/Investment_Data/financials/LITE/LITE_financials.json`（GLW 結構相同）
- schema 規劃 = `docs/financials-view-schema.md` line 191-319

最後更新：2026-05-07

---

## IS（損益表）

| # | schema doc U-1 規劃 key | SEC pipeline 現有 key | 一致 | 提議動作 | 確認 |
|---|---|---|---|---|---|
| 1 | `operating_revenue` | `revenue` | ❌ | rename pipeline → `operating_revenue`（與台股一致）| ☐ |
| 2 | `cost_of_revenue` | `cost_of_goods_sold` | ❌ | rename pipeline → `cost_of_revenue` | ☐ |
| 3 | `gross_profit` | `gross_profit` | ✅ | — | ☐ |
| 4 | `r_and_d_expenses` | `research_and_development` | ❌ | rename pipeline → `r_and_d_expenses` | ☐ |
| 5 | `selling_general_admin_expenses` | `selling_general_administrative` | ❌ | rename pipeline → `selling_general_admin_expenses` | ☐ |
| 6 | `operating_income` | `operating_income` | ✅ | — | ☐ |
| 7 | `restructuring_charges` | `restructuring_charges` | ✅ | — | ☐ |
| 8 | `amortization_of_intangible_assets` | `amortization_of_intangible_assets` | ✅ | — | ☐ |
| 9 | `gain_loss_on_equity_investments` | （無） | ⚠️ schema 規劃但 JSON 缺 | 確認是否強制需要：少數公司有（INTC、MSFT），其他無。建議改為 optional，pipeline 有則寫 | ☐ |
| 10 | `interest_income` | `interest_income` | ✅ | — | ☐ |
| 11 | `interest_expense` | `interest_expense` | ✅ | — | ☐ |
| 12 | `other_nonoperating_income_expense` | `other_nonoperating_income_expense` | ✅ | — | ☐ |
| 13 | `income_before_taxes` | （無） | ⚠️ JSON 缺 | pipeline 補抽 `us-gaap:IncomeLossFromContinuingOperationsBeforeIncomeTaxes` | ☐ |
| 14 | `income_tax_expense` | `income_tax_expense` | ✅ | — | ☐ |
| 15 | `net_income` | `net_income` | ✅ | — | ☐ |
| 16 | `net_income_nci` | （無） | ⚠️ JSON 缺 | pipeline 補抽 `us-gaap:NetIncomeLossAttributableToNoncontrollingInterest`（多數公司無 NCI 可空） | ☐ |
| 17 | `basic_eps` | `eps_basic` | ❌ | rename pipeline → `basic_eps`（與台股一致） | ☐ |
| 18 | `diluted_eps` | `eps_diluted` | ❌ | rename pipeline → `diluted_eps`（與台股一致） | ☐ |
| 19 | `shares_basic_millions` | `shares_basic_millions` | ✅ | — | ☐ |
| 20 | `shares_diluted_millions` | `shares_diluted_millions` | ✅ | — | ☐ |

### IS：JSON 有但 schema 沒規劃的（多餘？）

| # | SEC pipeline 現有 key | 性質 | 提議動作 | 確認 |
|---|---|---|---|---|
| E1 | `gross_margin_pct` | derived | 從 financial_facts 拿掉，移到 U-2 `financial_metrics`（公式：`gross_profit / operating_revenue`） | ☐ |
| E2 | `operating_margin_pct` | derived | 同 → U-2 | ☐ |
| E3 | `net_margin_pct` | derived | 同 → U-2 | ☐ |
| E4 | `effective_tax_rate` | derived | 同 → U-2（公式：`income_tax_expense / income_before_taxes`） | ☐ |

---

## BS（資產負債表）

### Assets

| # | schema doc U-1 規劃 key | SEC pipeline 現有 key | 一致 | 提議動作 | 確認 |
|---|---|---|---|---|---|
| 1 | `cash_and_equivalents` | `cash_and_cash_equivalents` | ❌ | rename pipeline → `cash_and_equivalents`（與台股一致） | ☐ |
| 2 | `short_term_investments` | `short_term_investments` | ✅ | — | ☐ |
| 3 | `accounts_receivable` | （無） | ⚠️ JSON 缺 | pipeline 補抽 `us-gaap:AccountsReceivableNetCurrent` | ☐ |
| 4 | `inventories` | `inventories` | ✅ | — | ☐ |
| 5 | `other_current_assets` | `other_current_assets` | ✅ | — | ☐ |
| 6 | `total_current_assets` | `total_current_assets` | ✅ | — | ☐ |
| 7 | `ppe_net` | `property_plant_equipment_net` | ❌ | rename pipeline → `ppe_net`（與台股一致） | ☐ |
| 8 | `goodwill` | `goodwill` | ✅ | — | ☐ |
| 9 | `intangible_assets` | `intangible_assets` | ✅ | — | ☐ |
| 10 | `other_noncurrent_assets` | `other_noncurrent_assets` | ✅ | — | ☐ |
| 11 | `total_assets` | `total_assets` | ✅ | — | ☐ |

### Assets：JSON 有但 schema 沒規劃

| # | SEC pipeline 現有 key | 提議動作 | 確認 |
|---|---|---|---|
| E5 | `operating_lease_rou_asset` | 有實質意義，建議補進 schema doc U-1 | ☐ |
| E6 | `deferred_tax_assets` | 同 → 補進 U-1 | ☐ |

### Liabilities

| # | schema doc U-1 規劃 key | SEC pipeline 現有 key | 一致 | 提議動作 | 確認 |
|---|---|---|---|---|---|
| 1 | `accounts_payable` | `accounts_payable` | ✅ | — | ☐ |
| 2 | `deferred_revenue_current` | （無） | ⚠️ schema 規劃但 JSON 缺 | optional：少數公司有，pipeline 有則寫 | ☐ |
| 3 | `short_term_debt` | `current_debt` | ❌ | rename pipeline → `short_term_debt` | ☐ |
| 4 | `other_current_liabilities` | `other_current_liabilities` | ✅ | — | ☐ |
| 5 | `total_current_liabilities` | `total_current_liabilities` | ✅ | — | ☐ |
| 6 | `long_term_debt` | `long_term_debt` | ✅ | — | ☐ |
| 7 | `other_noncurrent_liabilities` | `other_noncurrent_liabilities` | ✅ | — | ☐ |
| 8 | `total_liabilities` | `total_liabilities` | ✅ | — | ☐ |

### Liabilities：JSON 有但 schema 沒規劃

| # | SEC pipeline 現有 key | 提議動作 | 確認 |
|---|---|---|---|
| E7 | `accrued_liabilities` | 有實質意義，建議補進 schema doc U-1 | ☐ |
| E8 | `operating_lease_noncurrent` | 同 → 補進 U-1 | ☐ |

### Equity

| # | schema doc U-1 規劃 key | SEC pipeline 現有 key | 一致 | 提議動作 | 確認 |
|---|---|---|---|---|---|
| 1 | `retained_earnings` | `retained_earnings` | ✅ | — | ☐ |
| 2 | `total_equity` | `total_equity` | ✅ | — | ☐ |

### Equity：JSON 有但 schema 沒規劃

| # | SEC pipeline 現有 key | 提議動作 | 確認 |
|---|---|---|---|
| E9 | `common_stock` | 補進 schema doc U-1 | ☐ |
| E10 | `additional_paid_in_capital` | 補進 schema doc U-1 | ☐ |
| E11 | `aoci` | 補進 schema doc U-1（accumulated other comprehensive income） | ☐ |
| E12 | `total_liabilities_and_equity` | derived（= total_assets），可考慮拿掉 | ☐ |

---

## CF（現金流量表）

| # | schema doc U-1 規劃 key | SEC pipeline 現有 key | 一致 | 提議動作 | 確認 |
|---|---|---|---|---|---|
| 1 | `operating_cash_flow` | `net_cash_from_operating` | ❌ | rename pipeline → `operating_cash_flow`（與 schema 一致） | ☐ |
| 2 | `investing_cash_flow` | `net_cash_from_investing` | ❌ | rename pipeline → `investing_cash_flow` | ☐ |
| 3 | `financing_cash_flow` | `net_cash_from_financing` | ❌ | rename pipeline → `financing_cash_flow` | ☐ |
| 4 | `capex` | `capital_expenditures` | ❌ | rename pipeline → `capex`（與台股一致） | ☐ |
| 5 | `depreciation_amortization` | `depreciation_and_amortization` | ❌（差 `_and_`） | rename pipeline → `depreciation_amortization` | ☐ |
| 6 | `stock_based_compensation` | `share_based_compensation` | ❌ | rename pipeline → `stock_based_compensation` | ☐ |
| 7 | `dividends_paid` | （無） | ⚠️ JSON 缺 | pipeline 補抽 `us-gaap:PaymentsOfDividends`（不發股利公司可空） | ☐ |
| 8 | `net_change_in_cash` | `net_change_in_cash`（在 cash_flow.* 而非單獨）| ✅（位置調整即可） | — | ☐ |
| 9 | `ending_cash` | `ending_cash`（在 cash_flow.*） | ✅ | — | ☐ |

### CF：JSON 有但 schema 沒規劃

| # | SEC pipeline 現有 key | 性質 | 提議動作 | 確認 |
|---|---|---|---|---|
| E13 | `goodwill_impairment` | adjustment | 補進 schema doc U-1 CF | ☐ |
| E14 | `other_asset_impairment` | adjustment | 補進 schema doc U-1 CF | ☐ |
| E15 | `change_in_receivables` | working capital | 補進 schema doc U-1 CF | ☐ |
| E16 | `change_in_inventories` | working capital | 補進 schema doc U-1 CF | ☐ |
| E17 | `change_in_accounts_payable` | working capital | 補進 schema doc U-1 CF | ☐ |
| E18 | `proceeds_from_debt` | financing detail | 補進 schema doc U-1 CF | ☐ |
| E19 | `repayments_of_debt`（GLW JSON 有） | financing detail | 補進 schema doc U-1 CF | ☐ |
| E20 | `free_cash_flow` | derived | 拿掉，移到 U-2 `financial_metrics`（公式：`operating_cash_flow + capex`） | ☐ |

---

## 總結：行動清單

如果使用者把上述全部勾完，pipeline code 要改的範圍：

### `xbrl_extract.py` rename map
```
revenue                          → operating_revenue
cost_of_goods_sold               → cost_of_revenue
research_and_development         → r_and_d_expenses
selling_general_administrative   → selling_general_admin_expenses
eps_basic                        → basic_eps
eps_diluted                      → diluted_eps
cash_and_cash_equivalents        → cash_and_equivalents
property_plant_equipment_net     → ppe_net
current_debt                     → short_term_debt
net_cash_from_operating          → operating_cash_flow
net_cash_from_investing          → investing_cash_flow
net_cash_from_financing          → financing_cash_flow
capital_expenditures             → capex
depreciation_and_amortization    → depreciation_amortization
share_based_compensation         → stock_based_compensation
```

### `xbrl_extract.py` 補抽
```
income_before_taxes  ← us-gaap:IncomeLossFromContinuingOperationsBeforeIncomeTaxes
net_income_nci       ← us-gaap:NetIncomeLossAttributableToNoncontrollingInterest
accounts_receivable  ← us-gaap:AccountsReceivableNetCurrent
dividends_paid       ← us-gaap:PaymentsOfDividends
```

### Derived metric 搬家（從 facts 移到 metrics）
```
gross_margin_pct, operating_margin_pct, net_margin_pct, effective_tax_rate, free_cash_flow
total_liabilities_and_equity（去掉，因為 = total_assets）
```

### `financials-view-schema.md` 美股區塊新增 metric（補進 U-1）
```
operating_lease_rou_asset, deferred_tax_assets
accrued_liabilities, operating_lease_noncurrent
common_stock, additional_paid_in_capital, aoci
goodwill_impairment, other_asset_impairment
change_in_receivables, change_in_inventories, change_in_accounts_payable
proceeds_from_debt, repayments_of_debt
```

### 完成判準
- 此表全部 ☐ 變 ☑
- `financials-view-schema.md` 美股區塊「確認」欄全部打勾
- `xbrl_extract.py` 重跑一次 GLW + LITE，diff 新舊 JSON 確認除了 rename 之外無數值漂移
- 才開始寫 Supabase upsert
