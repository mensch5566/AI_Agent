# Financials View — Supabase 表結構清單

> 這份文件是 `Financials Viewer` 的 metric dictionary。
> 
> 用途：
> - 定義每個 `key` 對應的 statement、含義、XBRL 標籤與是否允許入庫
> - 作為 `key -> meaning/source` 的正式對照表
> 
> 不處理行為規則：
> - `Quarterly / Annual` 應如何顯示
> - 哪些值可否由年報反推成 Q4 單季
> - derived 值應進哪張表
> 
> 上述行為規則統一放在 [financials-data-rules.md](./financials-data-rules.md)。

> **核檢規則**：任何表結構異動（新增 / 修改 / 刪除指標），都必須先在此表更新並獲得確認（最後欄打勾），才可執行。未確認的指標不得寫入、計算或在前端讀取。
> 
> **圖例**：✅ 已抽取入庫　⬜ XBRL 有，尚未抽取　❌ XBRL 無，需補充

最後更新：2026-05-16

---

# 美股（SEC / US-GAAP）— v2 (`sec_financial_*` tables)

**Authority dictionary**: [`docs/sec-financials-v2-schema.md`](./sec-financials-v2-schema.md)

這份 v2 dictionary 取代過去的「US section」。對應 Supabase 表：

| 表 | 用途 |
|---|---|
| `sec_financial_companies` | 公司 metadata + filings index + sign_flip_concepts |
| `sec_financial_facts` | direct disclosed facts only（GAAP + NON_GAAP，含 statement=IS/BS/CF/RATIO） |
| `sec_financial_metrics` | derived 值（Q4 single quarter / GM% / OM% / ROE / ...） |
| `sec_financial_dimensional_facts` | segment / geography / customer concentration 等多軸 facts |
| `sec_financial_edges` | calc / presentation / def_linkbase edges（audit + future use） |

**v2 紀律重點**（細節見 [`financials-data-rules.md`](./financials-data-rules.md) §SEC v2）：

- **disclosed ratio**（8-K 揭露的 GM% 等）→ `sec_financial_facts(statement='RATIO', status='SOURCE_OF_TRUTH')`
- **derived ratio**（pipeline 計算）→ `sec_financial_metrics(statement='RATIO', status='DERIVED_FROM_DISCLOSED')`
- **derive-analytics 不可覆寫 facts 同 key**（先 SELECT 確認不存在再寫）
- **dimensional dedupe** 用 `member_key`（qname or normalized label）；`Data Center` ↔ `Datacenter` 自動合併
- **pct value 一律存小數**（DB 0.392；UI fmtPct → 39.2%）
- **unit canonical**：`USD_thousands` / `USD_millions` / `USD_per_share` / `millions_shares` / `Pure` 五種
- **period_kind**：`quarter_duration` / `fy_annual_duration` / `ytd_duration` / `instant_period_end` / `derived_q4`（後者 metrics-only）
- **BS 一律 `instant_period_end`**；IS/CF/RATIO 一律 duration
- **uni_account 新增 / 改名 / 刪除**：先在 `sec-financials-v2-schema.md` 登記並打勾，未確認不可入庫

v2 完整 uni_account 清單見 [`sec-financials-v2-schema.md`](./sec-financials-v2-schema.md)。

### v2 ingest 進度

| Ticker | IS | BS | CF | RATIO | SEGMENT | last update |
|---|---|---|---|---|---|---|
| AAOI | ⬜ schema ready | ⬜ | ⬜ | ⬜ | ⬜ | ingest pending |
| INTC | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | pending |
| SNDK | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | pending |

---

# 台股（TWSE / TIFRS）

## 1. `financial_facts` — XBRL 官方原始數據

- **source tag**：`XBRL_TWSE`
- **規則**：只放 XBRL 直接標記的數值，不放計算值
- **XBRL 標籤來源**：`tifrs-fr1-m1-ci-cr`（合併財報）

### 損益表（IS）

> 科目順序依聯發科合併綜合損益表 PDF 排列（代碼 4000～9850）

| 代碼 | IS/BS | 指標 | 說明 | XBRL 標籤 | 狀態 | 確認 |
|---|---|---|---|---|---|---|
| 4000 | IS | `operating_revenue` | 營業收入 | `ifrs-full:Revenue` | ✅ | ✅ |
| 5000 | IS | `cost_of_revenue` | 營業成本 | `tifrs-bsci-ci:OperatingCosts` | ⬜ | ✅ |
| 5900 | IS | `gross_profit` | 營業毛利 | `tifrs-bsci-ci:GrossProfitLossFromOperations` | ⬜ | ✅ |
| 6100 | IS | `selling_expenses` | 推銷費用 | `ifrs-full:SellingExpense` | ⬜ | ✅ |
| 6200 | IS | `general_admin_expenses` | 管理費用 | `ifrs-full:AdministrativeExpense` | ⬜ | ✅ |
| 6300 | IS | `r_and_d_expenses` | 研究發展費用 | `ifrs-full:ResearchAndDevelopmentExpense` | ⬜ | ✅ |
| 6450 | IS | `expected_credit_loss` | 預期信用減損利益（損失） | ⬜ 待確認標籤 | ⬜ | |
| — | IS | `operating_expenses` | 營業費用合計 | `ifrs-full:OperatingExpense` | ⬜ | ✅ |
| 6900 | IS | `operating_income` | 營業利益 | `ifrs-full:ProfitLossFromOperatingActivities` | ⬜ | ✅ |
| 7100 | IS | `interest_income` | 利息收入 | `ifrs-full:RevenueFromInterest` | ⬜ | |
| 7010 | IS | `other_income` | 其他收入 | `ifrs-full:OtherRevenue` | ⬜ | |
| 7020 | IS | `other_gains_losses` | 其他利益及損失 | `ifrs-full:OtherGainsLosses` | ⬜ | |
| 7050 | IS | `interest_expense` | 財務成本（利息費用） | `ifrs-full:FinanceCosts` | ⬜ | ✅ |
| 7060 | IS | `equity_method_income` | 採用權益法認列之關聯企業及合資損益之份額 | `ifrs-full:ShareOfProfitLossOfAssociatesAndJointVenturesAccountedForUsingEquityMethod` | ⬜ | |
| — | IS | `non_operating_income_expense` | 營業外收入及支出合計 | `tifrs-bsci-ci:NonoperatingIncomeAndExpenses` | ⬜ | |
| 7900 | IS | `income_before_taxes` | 稅前淨利 | `ifrs-full:ProfitLossBeforeTax` | ✅ | |
| 7950 | IS | `income_tax_expense` | 所得稅費用 | `ifrs-full:IncomeTaxExpenseContinuingOperations` | ⬜ | |
| 8200 | IS | `net_income` | 本期淨利（含少數股東） | `ifrs-full:ProfitLoss` | ✅ | |
| 8311 | IS | `oci_remeasurement_defined_benefit` | 確定福利計畫之再衡量數 | `ifrs-full:OtherComprehensiveIncomeThatWillNotBeReclassifiedToProfitOrLossNetOfTax` | ⬜ | |
| 8316 | IS | `oci_fvoci_equity` | 透過其他綜合損益按公允價值衡量之權益工具投資未實現評價損益 | `ifrs-full:OtherComprehensiveIncomeBeforeTaxGainsLossesFromInvestmentsInEquityInstruments` | ⬜ | |
| 8361 | IS | `oci_fx_translation` | 國外營運機構財務報表換算之兌換差額 | `ifrs-full:OtherComprehensiveIncomeBeforeTaxExchangeDifferencesOnTranslation` | ⬜ | |
| 8367 | IS | `oci_fvoci_debt` | 透過其他綜合損益按公允價值衡量之債務工具投資未實現評價損益 | `ifrs-full:OtherComprehensiveIncomeThatWillBeReclassifiedToProfitOrLossNetOfTax` | ⬜ | |
| — | IS | `other_comprehensive_income` | 本期其他綜合損益（稅後淨額） | `ifrs-full:OtherComprehensiveIncome` | ⬜ | |
| 8500 | IS | `total_comprehensive_income` | 本期綜合損益總額 | `ifrs-full:ComprehensiveIncome` | ⬜ | |
| 8610 | IS | `net_income_parent` | 淨利歸屬－母公司業主 | `ifrs-full:ProfitLossAttributableToOwnersOfParent` | ⬜ | |
| 8620 | IS | `net_income_nci` | 淨利歸屬－非控制權益 | `ifrs-full:ProfitLossAttributableToNoncontrollingInterests` | ⬜ | |
| 8710 | IS | `comprehensive_income_parent` | 綜合損益歸屬－母公司業主 | `ifrs-full:ComprehensiveIncomeAttributableToOwnersOfParent` | ⬜ | |
| 8720 | IS | `comprehensive_income_nci` | 綜合損益歸屬－非控制權益 | `ifrs-full:ComprehensiveIncomeAttributableToNoncontrollingInterests` | ⬜ | |
| 9710 | IS | `basic_eps` | 基本每股盈餘（本期淨利） | `ifrs-full:BasicEarningsLossPerShare` | ⬜ | |
| 9810 | IS | `diluted_eps` | 稀釋每股盈餘（本期淨利） | `ifrs-full:DilutedEarningsLossPerShare` | ⬜ | |

### 資產負債表（BS）— 資產

| IS/BS | 指標                               | 說明                  | XBRL 標籤                                                          | 狀態  | 確認  |
| ----- | -------------------------------- | ------------------- | ---------------------------------------------------------------- | --- | --- |
| BS    | `cash_and_equivalents`           | 現金及約當現金             | `ifrs-full:CashAndCashEquivalents`                               | ⬜   |     |
| BS    | `financial_assets_fvtpl_current` | 透過損益按公允價值衡量之金融資產－流動 | `ifrs-full:CurrentFinancialAssetsAtFairValueThroughProfitOrLoss` | ⬜   |     |
| BS    | `accounts_receivable`            | 應收帳款淨額              | `tifrs-bsci-ci:AccountsReceivableNet`                            | ⬜   |     |
| BS    | `inventories`                    | 存貨                  | `ifrs-full:Inventories`                                          | ⬜   |     |
| BS    | `prepaid_expenses`               | 預付款項                | `ifrs-full:CurrentPrepayments`                                   | ⬜   |     |
| BS    | `other_current_assets`           | 其他流動資產              | `ifrs-full:OtherCurrentAssets`                                   | ⬜   |     |
| BS    | `total_current_assets`           | 流動資產合計              | `ifrs-full:CurrentAssets`                                        | ✅   |     |
| BS    | `ppe_net`                        | 不動產、廠房及設備淨額         | `ifrs-full:PropertyPlantAndEquipment`                            | ⬜   |     |
| BS    | `right_of_use_assets`            | 使用權資產               | `ifrs-full:RightofuseAssets`                                     | ⬜   |     |
| BS    | `intangibles_and_goodwill`       | 無形資產及商譽             | `ifrs-full:IntangibleAssetsAndGoodwill`                          | ⬜   |     |
| BS    | `equity_method_investments`      | 採用權益法之投資            | `ifrs-full:InvestmentAccountedForUsingEquityMethod`              | ⬜   |     |
| BS    | `deferred_tax_assets`            | 遞延所得稅資產             | `ifrs-full:DeferredTaxAssets`                                    | ⬜   |     |
| BS    | `other_noncurrent_assets`        | 其他非流動資產             | `ifrs-full:OtherNoncurrentAssets`                                | ⬜   |     |
| BS    | `total_noncurrent_assets`        | 非流動資產合計             | `ifrs-full:NoncurrentAssets`                                     | ⬜   |     |
| BS    | `total_assets`                   | 資產總計                | `ifrs-full:Assets`                                               | ✅   |     |

### 資產負債表（BS）— 負債

| IS/BS | 指標                             | 說明           | XBRL 標籤                                                  | 狀態  | 確認  |
| ----- | ------------------------------ | ------------ | -------------------------------------------------------- | --- | --- |
| BS    | `short_term_borrowings`        | 短期借款         | `ifrs-full:ShorttermBorrowings`                          | ⬜   |     |
| BS    | `accounts_payable`             | 應付帳款         | `ifrs-full:TradeAndOtherCurrentPayablesToTradeSuppliers` | ⬜   |     |
| BS    | `contract_liabilities_current` | 合約負債－流動      | `ifrs-full:CurrentContractLiabilities`                   | ⬜   |     |
| BS    | `current_tax_liabilities`      | 本期所得稅負債      | `ifrs-full:CurrentTaxLiabilities`                        | ⬜   |     |
| BS    | `lease_liabilities_current`    | 租賃負債－流動      | `tifrs-bsci-ci:CurrentLeaseLiabilities`                  | ⬜   |     |
| BS    | `other_current_liabilities`    | 其他流動負債       | `ifrs-full:OtherCurrentLiabilities`                      | ⬜   |     |
| BS    | `total_current_liabilities`    | 流動負債合計       | `ifrs-full:CurrentLiabilities`                           | ✅   |     |
| BS    | `long_term_debt`               | 長期借款（含一年內到期） | `tifrs-bsci-ci:LongtermLiabilitiesCurrentPortion`        | ⬜   |     |
| BS    | `lease_liabilities_noncurrent` | 租賃負債－非流動     | `ifrs-full:NoncurrentFinanceLeaseLiabilities`            | ⬜   |     |
| BS    | `deferred_tax_liabilities`     | 遞延所得稅負債      | `ifrs-full:DeferredTaxLiabilities`                       | ⬜   |     |
| BS    | `other_noncurrent_liabilities` | 其他非流動負債      | `ifrs-full:OtherNoncurrentLiabilities`                   | ⬜   |     |
| BS    | `total_noncurrent_liabilities` | 非流動負債合計      | `ifrs-full:NoncurrentLiabilities`                        | ⬜   |     |
| BS    | `total_liabilities`            | 負債總計         | `ifrs-full:Liabilities`                                  | ✅   |     |

### 資產負債表（BS）— 權益

| IS/BS | 指標                              | 說明           | XBRL 標籤                                                           | 狀態  | 確認  |
| ----- | ------------------------------- | ------------ | ----------------------------------------------------------------- | --- | --- |
| BS    | `common_stock`                  | 股本           | `ifrs-full:IssuedCapital`                                         | ⬜   |     |
| BS    | `capital_surplus`               | 資本公積         | `ifrs-full:CapitalReserve`                                        | ⬜   |     |
| BS    | `legal_reserve`                 | 法定盈餘公積       | `ifrs-full:StatutoryReserve`                                      | ⬜   |     |
| BS    | `retained_earnings`             | 未分配盈餘        | `tifrs-bsci-ci:UnappropriatedRetainedEarningsAaccumulatedDeficit` | ⬜   |     |
| BS    | `other_equity`                  | 其他權益         | `ifrs-full:OtherEquityInterest`                                   | ⬜   |     |
| BS    | `equity_attributable_to_parent` | 歸屬母公司業主之權益合計 | `ifrs-full:EquityAttributableToOwnersOfParent`                    | ⬜   |     |
| BS    | `non_controlling_interests`     | 非控制權益        | `ifrs-full:NoncontrollingInterests`                               | ⬜   |     |
| BS    | `total_equity`                  | 權益總計         | `ifrs-full:Equity`                                                | ✅   |     |

### 現金流量表（CF）

| IS/BS | 指標                     | 說明                 | XBRL 標籤                                                                        | 狀態  | 確認  |
| ----- | ---------------------- | ------------------ | ------------------------------------------------------------------------------ | --- | --- |
| CF    | `operating_cash_flow`  | 營業活動淨現金流入（出）       | `ifrs-full:CashFlowsFromUsedInOperatingActivities`                             | ⬜   |     |
| CF    | `investing_cash_flow`  | 投資活動淨現金流入（出）       | `tifrs-SCF:NetCashFlowsFromUsedInInvestingActivities`                          | ⬜   |     |
| CF    | `financing_cash_flow`  | 融資活動淨現金流入（出）       | `tifrs-SCF:CashFlowsFromUsedInFinancingActivities`                             | ⬜   |     |
| CF    | `capex`                | 購置不動產廠房設備（資本支出，負值） | `ifrs-full:PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities` | ⬜   |     |
| CF    | `depreciation_expense` | 折舊費用（調節項）          | `ifrs-full:AdjustmentsForDepreciationExpense`                                  | ⬜   |     |
| CF    | `amortization_expense` | 攤銷費用（調節項）          | `ifrs-full:AdjustmentsForAmortisationExpense`                                  | ⬜   |     |
| CF    | `dividends_paid`       | 支付股利               | `ifrs-full:DividendsPaidClassifiedAsFinancingActivities`                       | ⬜   |     |
| CF    | `net_change_in_cash`   | 本期現金及約當現金增減        | `ifrs-full:IncreaseDecreaseInCashAndCashEquivalents`                           | ⬜   |     |
| CF    | `ending_cash`          | 期末現金及約當現金          | `tifrs-SCF:CashAndCashEquivalentsAtEndOfPeriod`                                | ⬜   |     |

---

## 2. `financial_metrics` — 派生計算指標

- **source tag**：`COMPUTED_FROM_XBRL_TWSE`
- **規則**：只放從 `financial_facts` 計算出來的比率，不放原始數值

| IS/BS | 指標                     | 計算公式                                               | 前置條件                  | 狀態  | 確認  |
| ----- | ---------------------- | -------------------------------------------------- | --------------------- | --- | --- |
| IS    | `gross_margin_pct`     | `gross_profit / operating_revenue × 100`           | 需抽 `gross_profit`     | ⬜   |     |
| IS    | `operating_margin_pct` | `operating_income / operating_revenue × 100`       | 需抽 `operating_income` | ⬜   |     |
| IS    | `pretax_margin`        | `income_before_taxes / operating_revenue × 100`    | —                     | ✅   |     |
| IS    | `net_margin_pct`       | `net_income / operating_revenue × 100`             | —                     | ✅   |     |
| IS    | `r_and_d_ratio`        | `r_and_d_expenses / operating_revenue × 100`       | 需抽 `r_and_d_expenses` | ⬜   |     |
| BS    | `current_ratio`        | `total_current_assets / total_current_liabilities` | —                     | ✅   |     |
| BS    | `debt_to_equity`       | `total_liabilities / total_equity`                 | —                     | ✅   |     |
| BS    | `equity_ratio`         | `total_equity / total_assets`                      | —                     | ✅   |     |
| IS+BS | `roe`                  | `net_income / total_equity × 100`                  | —                     | ✅   |     |
| IS+BS | `roa`                  | `net_income / total_assets × 100`                  | —                     | ✅   |     |
| CF    | `free_cash_flow`       | `operating_cash_flow + capex`（capex 為負值）           | 需抽 CF 指標              | ⬜   |     |
| CF    | `fcf_margin`           | `free_cash_flow / operating_revenue × 100`         | 需抽 CF 指標              | ⬜   |     |

---

## 3. `financial_supplement` — 非 XBRL 補充數據

- **source tag**：`NB_SUPPLEMENTED`
- **規則**：只放 XBRL 沒有的數值（Segments、Non-GAAP）。TIFRS 比率不放這裡

| IS/BS | 指標                                 | 說明                                             | 來源                        | 狀態  | 確認  |
| ----- | ---------------------------------- | ---------------------------------------------- | ------------------------- | --- | --- |
| IS    | `segment_mobile_revenue`           | 手機分部營收                                         | Earnings Call（官方佔比 × 總營收） | ✅   |     |
| IS    | `segment_smart_edge_revenue`       | 智慧邊緣平台分部營收                                     | Earnings Call（官方佔比 × 總營收） | ✅   |     |
| IS    | `segment_power_ic_revenue`         | 電源管理 IC 分部營收                                   | Earnings Call（官方佔比 × 總營收） | ✅   |     |
| IS    | `segment_iot_compute_asic_revenue` | IoT/運算/ASIC 子分部（Smart Edge 細分）                 | UBS 分析師估算                 | ✅   |     |
| IS    | `segment_smart_home_revenue`       | 智慧家庭子分部（Smart Edge 細分）                         | UBS 分析師估算                 | ✅   |     |
| IS    | `eps_non_gaap`                     | Non-TIFRS EPS                                  | Earnings Call             | ✅   |     |
| IS    | `operating_margin_non_gaap`        | Non-TIFRS 營業利益率                                | Earnings Call             | ✅   |     |
| IS    | `gross_margin`                     | ⚠️ 暫存：TIFRS 毛利率，待步驟 4 `gross_margin_pct` 完成後刪除 | Earnings Call（暫存）         | ⚠️  |     |

---

## 4. `financial_guidance` — 法說會前瞻指引

- **source tag**：`GUIDANCE_EARNINGS_CALL`
- **規則**：period 填下一期，不填當期

| IS/BS | 指標                          | 說明         | 來源                  | 狀態  | 確認  |
| ----- | --------------------------- | ---------- | ------------------- | --- | --- |
| IS    | `revenue_guidance_low`      | 下季營收指引下限   | Earnings Call       | ✅   |     |
| IS    | `revenue_guidance_high`     | 下季營收指引上限   | Earnings Call       | ✅   |     |
| IS    | `revenue_guidance_mid`      | 下季營收指引中間值  | Earnings Call + 自己算 | ✅   |     |
| IS    | `gross_margin_guidance_mid` | 下季毛利率指引中間值 | Earnings Call       | ✅   |     |
| IS    | `opex_ratio_guidance`       | 下季營業費用率指引  | Earnings Call       | ✅   |     |

---

# 美股（SEC / US GAAP）

> ⚠️ 美股管道尚未建置，以下為規劃中的結構，待確認後才可實作。

## U-1. `financial_facts` — XBRL 官方原始數據

- **source tag**：`XBRL_SEC`
- **規則**：只放 SEC XBRL（10-Q/10-K）直接標記的 US GAAP 數值

### 損益表（IS）

| IS/BS | 指標                               | 說明                      | US GAAP 標籤（參考）                                                | 狀態  | 確認  |
| ----- | -------------------------------- | ----------------------- | ------------------------------------------------------------- | --- | --- |
| IS    | `operating_revenue`              | Net Revenue / Net Sales | `us-gaap:Revenues`                                            | ⬜   |     |
| IS    | `cost_of_revenue`                | Cost of Revenue         | `us-gaap:CostOfRevenue`                                       | ⬜   |     |
| IS    | `gross_profit`                   | Gross Profit            | `us-gaap:GrossProfit`                                         | ⬜   |     |
| IS    | `r_and_d_expenses`               | R&D Expenses            | `us-gaap:ResearchAndDevelopmentExpense`                       | ⬜   |     |
| IS    | `selling_general_admin_expenses` | SG&A                    | `us-gaap:SellingGeneralAndAdministrativeExpense`              | ⬜   |     |
| IS    | `operating_income`               | Operating Income        | `us-gaap:OperatingIncomeLoss`                                 | ⬜   |     |
| IS    | `restructuring_charges`          | Restructuring Charges   | `us-gaap:RestructuringCharges`                                | ⬜   |     |
| IS    | `amortization_of_intangible_assets` | Amortization of Intangibles | `us-gaap:AmortizationOfIntangibleAssets`                  | ⬜   |     |
| IS    | `gain_loss_on_equity_investments` | Gains (Losses) on Equity Investments, net | `us-gaap:EquitySecuritiesFvNiGainLoss` / similar | ⬜   |     |
| IS    | `interest_income`                | Interest Income         | `us-gaap:InvestmentIncomeInterest` / similar                  | ⬜   |     |
| IS    | `interest_expense`               | Interest Expense        | `us-gaap:InterestExpense`                                     | ⬜   |     |
| IS    | `other_nonoperating_income_expense` | Other Non-operating Income/Expense | `us-gaap:OtherNonoperatingIncomeExpense` / similar | ⬜   |     |
| IS    | `income_before_taxes`            | Income Before Tax       | `us-gaap:IncomeLossFromContinuingOperationsBeforeIncomeTaxes` | ⬜   |     |
| IS    | `income_tax_expense`             | Income Tax Expense      | `us-gaap:IncomeTaxExpenseBenefit`                             | ⬜   |     |
| IS    | `net_income`                     | Net Income              | `us-gaap:NetIncomeLoss`                                       | ⬜   |     |
| IS    | `net_income_nci`                 | Net Income Attributable to Non-controlling Interests | `us-gaap:NetIncomeLossAttributableToNoncontrollingInterest` | ⬜   |     |
| IS    | `basic_eps`                      | Basic EPS               | `us-gaap:EarningsPerShareBasic`                               | ⬜   |     |
| IS    | `diluted_eps`                    | Diluted EPS             | `us-gaap:EarningsPerShareDiluted`                             | ⬜   |     |
| IS    | `shares_basic_millions`          | Weighted Average Basic Shares (Millions) | `us-gaap:WeightedAverageNumberOfSharesOutstandingBasic` | ⬜   |     |
| IS    | `shares_diluted_millions`        | Weighted Average Diluted Shares (Millions) | `us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding` | ⬜   |     |

### 資產負債表（BS）— 資產

| IS/BS | 指標                        | 說明                       | US GAAP 標籤（參考）                                  | 狀態  | 確認  |
| ----- | ------------------------- | ------------------------ | ----------------------------------------------- | --- | --- |
| BS    | `cash_and_equivalents`    | Cash and Equivalents     | `us-gaap:CashAndCashEquivalentsAtCarryingValue` | ⬜   |     |
| BS    | `short_term_investments`  | Short-term Investments   | `us-gaap:ShortTermInvestments`                  | ⬜   |     |
| BS    | `accounts_receivable`     | Accounts Receivable, net | `us-gaap:AccountsReceivableNetCurrent`          | ⬜   |     |
| BS    | `inventories`             | Inventories              | `us-gaap:InventoryNet`                          | ⬜   |     |
| BS    | `other_current_assets`    | Other Current Assets     | `us-gaap:OtherAssetsCurrent`                    | ⬜   |     |
| BS    | `total_current_assets`    | Total Current Assets     | `us-gaap:AssetsCurrent`                         | ⬜   |     |
| BS    | `ppe_net`                 | PP&E, net                | `us-gaap:PropertyPlantAndEquipmentNet`          | ⬜   |     |
| BS    | `goodwill`                | Goodwill                 | `us-gaap:Goodwill`                              | ⬜   |     |
| BS    | `intangible_assets`       | Intangible Assets, net   | `us-gaap:IntangibleAssetsNetExcludingGoodwill`  | ⬜   |     |
| BS    | `other_noncurrent_assets` | Other Non-current Assets | `us-gaap:OtherAssetsNoncurrent`                 | ⬜   |     |
| BS    | `total_assets`            | Total Assets             | `us-gaap:Assets`                                | ⬜   |     |

### 資產負債表（BS）— 負債與權益

| IS/BS | 指標                             | 說明                            | US GAAP 標籤（參考）                               | 狀態  | 確認  |
| ----- | ------------------------------ | ----------------------------- | -------------------------------------------- | --- | --- |
| BS    | `accounts_payable`             | Accounts Payable              | `us-gaap:AccountsPayableCurrent`             | ⬜   |     |
| BS    | `deferred_revenue_current`     | Deferred Revenue, current     | `us-gaap:DeferredRevenueCurrent`             | ⬜   |     |
| BS    | `short_term_debt`              | Short-term Debt               | `us-gaap:ShortTermBorrowings`                | ⬜   |     |
| BS    | `other_current_liabilities`    | Other Current Liabilities     | `us-gaap:OtherLiabilitiesCurrent`            | ⬜   |     |
| BS    | `total_current_liabilities`    | Total Current Liabilities     | `us-gaap:LiabilitiesCurrent`                 | ⬜   |     |
| BS    | `long_term_debt`               | Long-term Debt                | `us-gaap:LongTermDebtNoncurrent`             | ⬜   |     |
| BS    | `other_noncurrent_liabilities` | Other Non-current Liabilities | `us-gaap:OtherLiabilitiesNoncurrent`         | ⬜   |     |
| BS    | `total_liabilities`            | Total Liabilities             | `us-gaap:Liabilities`                        | ⬜   |     |
| BS    | `retained_earnings`            | Retained Earnings             | `us-gaap:RetainedEarningsAccumulatedDeficit` | ⬜   |     |
| BS    | `total_equity`                 | Total Stockholders' Equity    | `us-gaap:StockholdersEquity`                 | ⬜   |     |

### 現金流量表（CF）

| IS/BS | 指標                          | 說明                       | US GAAP 標籤（參考）                                       | 狀態  | 確認  |
| ----- | --------------------------- | ------------------------ | ---------------------------------------------------- | --- | --- |
| CF    | `operating_cash_flow`       | Cash from Operations     | `us-gaap:NetCashProvidedByUsedInOperatingActivities` | ⬜   |     |
| CF    | `investing_cash_flow`       | Cash from Investing      | `us-gaap:NetCashProvidedByUsedInInvestingActivities` | ⬜   |     |
| CF    | `financing_cash_flow`       | Cash from Financing      | `us-gaap:NetCashProvidedByUsedInFinancingActivities` | ⬜   |     |
| CF    | `capex`                     | Capital Expenditures（負值） | `us-gaap:PaymentsToAcquirePropertyPlantAndEquipment` | ⬜   |     |
| CF    | `depreciation_amortization` | D&A（調節項）                 | `us-gaap:DepreciationDepletionAndAmortization`       | ⬜   |     |
| CF    | `stock_based_compensation`  | SBC（調節項）                 | `us-gaap:ShareBasedCompensation`                     | ⬜   |     |
| CF    | `dividends_paid`            | Dividends Paid           | `us-gaap:PaymentsOfDividends`                        | ⬜   |     |
| CF    | `net_change_in_cash`        | Net Change in Cash       | `us-gaap:CashCashEquivalentsAndShortTermInvestments` | ⬜   |     |
| CF    | `ending_cash`               | Ending Cash              | `us-gaap:CashAndCashEquivalentsAtCarryingValue`      | ⬜   |     |

---

## U-2. `financial_metrics` — 派生計算指標

- **source tag**：`COMPUTED_FROM_XBRL_SEC`

| IS/BS | 指標                     | 計算公式                                               | 狀態  | 確認  |
| ----- | ---------------------- | -------------------------------------------------- | --- | --- |
| IS    | `gross_margin_pct`     | `gross_profit / operating_revenue × 100`           | ⬜   |     |
| IS    | `operating_margin_pct` | `operating_income / operating_revenue × 100`       | ⬜   |     |
| IS    | `pretax_margin`        | `income_before_taxes / operating_revenue × 100`    | ⬜   |     |
| IS    | `net_margin_pct`       | `net_income / operating_revenue × 100`             | ⬜   |     |
| IS    | `r_and_d_ratio`        | `r_and_d_expenses / operating_revenue × 100`       | ⬜   |     |
| BS    | `current_ratio`        | `total_current_assets / total_current_liabilities` | ⬜   |     |
| BS    | `debt_to_equity`       | `total_liabilities / total_equity`                 | ⬜   |     |
| BS    | `equity_ratio`         | `total_equity / total_assets`                      | ⬜   |     |
| IS+BS | `roe`                  | `net_income / total_equity × 100`                  | ⬜   |     |
| IS+BS | `roa`                  | `net_income / total_assets × 100`                  | ⬜   |     |
| CF    | `free_cash_flow`       | `operating_cash_flow + capex`                      | ⬜   |     |
| CF    | `fcf_margin`           | `free_cash_flow / operating_revenue × 100`         | ⬜   |     |

---

## U-3. `financial_supplement` — 非 XBRL 補充數據

- **source tag**：`NB_SUPPLEMENTED`

| IS/BS | 指標                          | 說明                                | 來源                                | 狀態  | 確認  |
| ----- | --------------------------- | --------------------------------- | --------------------------------- | --- | --- |
| IS    | `segment_*_revenue`         | 各業務分部營收（依公司而異）                    | Earnings Call / 10-K Segment Note | ⬜   |     |
| IS    | `eps_non_gaap`              | Non-GAAP EPS                      | Earnings Release                  | ⬜   |     |
| IS    | `gross_margin_non_gaap`     | Non-GAAP Gross Margin（若與 GAAP 不同） | Earnings Release                  | ⬜   |     |
| IS    | `operating_margin_non_gaap` | Non-GAAP Operating Margin         | Earnings Release                  | ⬜   |     |

---

## U-4. `financial_guidance` — 法說會前瞻指引

- **source tag**：`GUIDANCE_EARNINGS_CALL`

| IS/BS | 指標                          | 說明           | 來源                  | 狀態  | 確認  |
| ----- | --------------------------- | ------------ | ------------------- | --- | --- |
| IS    | `revenue_guidance_low`      | 下季營收指引下限     | Earnings Call       | ⬜   |     |
| IS    | `revenue_guidance_high`     | 下季營收指引上限     | Earnings Call       | ⬜   |     |
| IS    | `revenue_guidance_mid`      | 下季營收指引中間值    | Earnings Call + 自己算 | ⬜   |     |
| IS    | `gross_margin_guidance_mid` | 下季毛利率指引中間值   | Earnings Call       | ⬜   |     |
| IS    | `eps_guidance_low`          | 下季 EPS 指引下限  | Earnings Call       | ⬜   |     |
| IS    | `eps_guidance_high`         | 下季 EPS 指引上限  | Earnings Call       | ⬜   |     |
| IS    | `eps_guidance_mid`          | 下季 EPS 指引中間值 | Earnings Call + 自己算 | ⬜   |     |

---

# 待處理（依序完成，每步都要先在此表確認）

## 台股

| 步驟  | 動作                                                                                                                                                                                                                                                                                | 涉及表                    | 前置條件      | 確認  |
| --- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------- | --------- | --- |
| 1   | `batch_parse.py` 補抽 IS 指標：`gross_profit`、`cost_of_revenue`、`operating_income`、`operating_expenses`、`r_and_d_expenses`、`selling_expenses`、`general_admin_expenses`、`income_tax_expense`、`net_income_parent`、`basic_eps`、`diluted_eps`                                              | `financial_facts`      | —         |     |
| 2   | `batch_parse.py` 補抽 BS 指標：`cash_and_equivalents`、`accounts_receivable`、`inventories`、`ppe_net`、`intangibles_and_goodwill`、`retained_earnings`、`equity_attributable_to_parent`、`short_term_borrowings`、`accounts_payable`、`total_noncurrent_assets`、`total_noncurrent_liabilities` | `financial_facts`      | —         |     |
| 3   | `batch_parse.py` 補抽 CF 指標：`operating_cash_flow`、`investing_cash_flow`、`financing_cash_flow`、`capex`、`depreciation_expense`、`amortization_expense`、`ending_cash`                                                                                                                   | `financial_facts`      | —         |     |
| 4   | 補算 `financial_metrics` 中的 ⬜ 指標                                                                                                                                                                                                                                                    | `financial_metrics`    | 步驟 1～3 完成 |     |
| 5   | 刪除 `financial_supplement` 中的暫存 `gross_margin`                                                                                                                                                                                                                                     | `financial_supplement` | 步驟 4 完成   |     |

## 美股（暫緩，台股完成後再處理）

| 步驟  | 動作                       | 涉及表 | 前置條件     | 確認  |
| --- | ------------------------ | --- | -------- | --- |
| 1   | 確認美股整體結構（本文件美股各節）後，才開始建置 | 全部  | 美股各節全部確認 |     |
