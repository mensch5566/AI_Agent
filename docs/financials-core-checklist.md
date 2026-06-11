# Financials Core Checklist — DRAFT v4

最後更新：2026-05-10
狀態：**草案 v4**，加回 NotebookLM `Parse_SEC_Filings` 指出的缺項

## v3 → v4 變更（依 SEC Reg G / CFA / XBRL guidance）

NotebookLM 提供的權威來源指出 v3 砍錯幾項、漏了幾項：

### IS 加回 7 項

| 項目                                       | 提案 uni_account                         | 預設  | 理由                                         |
| ---------------------------------------- | -------------------------------------- | --- | ------------------------------------------ |
| Discontinued Operations                  | `discontinued_operations`              | ✅   | XBRL 有專屬標籤，跟一般 net_income 不可混              |
| Income from Continuing Operations        | `income_from_continuing_ops`           | ✅   | XBRL 跨公司分析的關鍵 subtotal                     |
| Basic EPS - Continuing Ops               | `eps_basic_continuing`                 | ✅   | XBRL 跟一般 EPS 分開                            |
| Diluted EPS - Continuing Ops             | `eps_diluted_continuing`               | ✅   | 同上                                         |
| **Restructuring Charges**                | `restructuring_charges`                | ✅   | CFA：科技業最常見 Non-GAAP add-back               |
| **Amortization of Acquired Intangibles** | `amortization_of_acquired_intangibles` | ✅   | CFA：與一般 D&A 不同（收購代價 vs 運營資本投入），Non-GAAP 必拆 |
| **Goodwill Impairment**                  | `goodwill_impairment`                  | ✅   | SEC + CFA：併購頻繁公司必備（SNDK Q3-FY25 揭露 1830M）  |

### BS 加 2 項（ASC 842 強制）

| 項目                          | 提案 uni_account                | 預設  |
| --------------------------- | ----------------------------- | --- |
| Right of Use Assets         | `right_of_use_assets`         | ✅   |
| Long-term Lease Liabilities | `long_term_lease_liabilities` | ✅   |

### 移到 Future Work

- **Segment Reporting**（ASC Topic 280）：每個 reportable segment 的 revenue / profit / assets。**不適合塞進 `financial_facts`**，需獨立 `financial_segment` table。先列為 future work，不擋本次 schema 拍板。

### Non-GAAP Reconciliation Metadata（架構文件補）

每筆 Non-GAAP row 應該帶（不在 checklist 中，是 schema 欄位設計）：
- `most_directly_comparable_gaap_measure`
- `adjustment_label` / `adjustment_description`
- `tax_effect`（獨立 adjustment，禁止 "net of tax"）
- `recurring_or_nonrecurring_flag`
- `management_usefulness_statement`

詳見 `docs/financials-architecture-DRAFT.md` v0.3。

### 前端 SEC 合規規則（架構文件補）

| 規則 | 影響 |
|---|---|
| GAAP 數字必須優先或同等顯著於 Non-GAAP | UI 不能用粗體/大字/特殊色彩強調 Non-GAAP |
| Reconciliation table 從 GAAP 開始，不可從 Non-GAAP 開始 | 排版：GAAP value → adjustments → Non-GAAP value |
| 嚴禁呈現「Non-GAAP Income Statement」 | UI 不要有 "Non-GAAP P&L tab"，改用 reconciliation view |

詳見 `docs/financials-architecture-DRAFT.md` v0.3。

---

## v2 → v3 變更（21 項 demote）

收斂依據：「IS/BS/CF 主表少見、半導體公司幾乎沒、概念冗餘」三類項目 demote 到 long-tail bucket。

### IS 砍 6 項

| 砍掉的項目 | 理由 |
|---|---|
| `amortization_of_intangibles_is` | IS 主表少見，在 SG&A 或 CF 才看到 |
| `depreciation_and_amortization_is` | IS 主表少見，CF 才是 D&A 主場 |
| `asset_writedown_is` | 多數公司併進 "Other op expense" |
| `eps_basic_continuing` / `eps_diluted_continuing` | 只有 discontinued ops 時才存在 |
| `earnings_from_continuing_ops` (subtotal) | 沒 discontinued ops 時 = `net_income_total_pre_nci`，冗餘 |

### BS 砍 8 項

| 砍掉的項目 | 理由 |
|---|---|
| `trading_asset_securities` | 純 financial 業項目 |
| `long_term_loans_receivables` | 純 financial 業項目 |
| `total_cash_and_short_term_investments` (subtotal) | 主表少見 |
| `total_receivables` (subtotal) | 主表少見 |
| `deferred_tax_assets_current` | 多數公司不分流動/非流動 |
| `comprehensive_income_and_other_equity` | 太混雜，後續想細看再單獨升 |
| `total_common_equity` (subtotal) | 跟 `total_equity` 差只在 minority interest，多此一舉 |
| `total_common_shares_outstanding` (BS metadata) | 跟 `shares_outstanding_filing_date` 概念重複 |

### CF 砍 7 項

| 砍掉的項目 | 理由 |
|---|---|
| `cf_net_income_start` | 跟 IS `net_income` 同值，CF 只是再列一次，冗餘 |
| `amortization_goodwill_intangibles_cf` | 多數併進 D&A，不獨立列 |
| `depreciation_amortization_total_cf` (subtotal) | 沒拆 D 跟 A 時 = D&A，subtotal 沒意義 |
| `gain_loss_sale_of_asset` / `gain_loss_sale_of_investments` | 半導體公司罕見 |
| `change_in_unearned_revenues_cf` | 多數併進 "Δ Other operating assets" |
| `net_change_in_loans` | 純 financial 業項目 |

被砍的不是消失，是會走 long-tail bucket — 公司若有揭露，仍能寫入 facts 但不算核心 universal key。

---

## 用途

逐項決定每個 metric 是否納入核心 schema：
- ✅ = 納入核心，寫 `financial_facts`
- ❌ = 不納入（走 long-tail bucket）
- 派生指標一律進 `financial_metrics`，不在這份 checklist

我預設打 ✅ 是「現有 schema 已有 + 你之前同意 + 我判斷必要」共 **27 個**。其他 ⬜ 是新提案。

---

## Income Statement（24 候選）

### 營收與成本

| 分類           | SA label         | 提案 uni_account       | 確認  |
| ------------ | ---------------- | -------------------- | --- |
| item         | Revenues         | `revenue`            | ✅   |
| item         | Other Revenues   | `other_revenues`     | ✅   |
| item         | Cost Of Revenues | `cost_of_goods_sold` | ✅   |
| **subtotal** | Gross Profit     | `gross_profit`       | ✅   |

### 營業費用

| 分類           | SA label                                      | 提案 uni_account                         | 確認  |
| ------------ | --------------------------------------------- | -------------------------------------- | --- |
| item         | Selling General & Admin Expenses              | `selling_general_administrative`       | ✅   |
| item         | R&D Expenses                                  | `research_and_development`             | ✅   |
| item         | Restructuring Charges (NEW v4)                | `restructuring_charges`                | ✅   |
| item         | Amortization of Acquired Intangibles (NEW v4) | `amortization_of_acquired_intangibles` | ✅   |
| item         | Goodwill Impairment (NEW v4)                  | `goodwill_impairment`                  | ✅   |
| item         | Other Operating Expenses, Total               | `other_operating_expenses`             | ✅   |
| **subtotal** | Total Operating Expenses                      | `total_operating_expenses`             | ✅   |
| **subtotal** | Operating Income                              | `operating_income`                     | ✅   |

### 業外

| 分類           | SA label                              | 提案 uni_account                   | 確認  |
| ------------ | ------------------------------------- | -------------------------------- | --- |
| item         | Interest Expense                      | `interest_expense`               | ✅   |
| item         | Interest And Investment Income        | `interest_income`                | ✅   |
| **subtotal** | Net Interest Expenses                 | `net_interest_expense`           | ✅   |
| item         | Currency Exchange Gains (Loss)        | `currency_exchange_gain_loss`    | ✅   |
| item         | Other Non Operating Income (Expenses) | `other_nonoperating_income_loss` | ✅   |
| **subtotal** | EBT, Incl. Unusual Items              | `income_before_taxes`            | ✅   |
| item         | Income Tax Expense                    | `income_tax_expense`             | ✅   |

### 稅後與歸屬

| 分類           | SA label                                   | 提案 uni_account               | 確認  |
| ------------ | ------------------------------------------ | ---------------------------- | --- |
| **subtotal** | Income from Continuing Operations (NEW v4) | `income_from_continuing_ops` | ✅   |
| item         | Discontinued Operations (NEW v4)           | `discontinued_operations`    | ✅   |
| **subtotal** | Net Income to Company（pre-NCI）             | `net_income_total_pre_nci`   | ✅   |
| item         | Minority Interest（NCI portion）             | `net_income_nci`             | ✅   |
| **subtotal** | Net Income（parent）                         | `net_income`                 | ✅   |

### 每股資料 / 股數

| 分類   | SA label                               | 提案 uni_account            | 確認             |
| ---- | -------------------------------------- | ------------------------- | -------------- |
| item | Basic Weighted Average Shares Outst.   | `shares_basic_millions`   | ✅              |
| item | Diluted Weighted Average Shares Outst. | `shares_diluted_millions` | ✅              |
| item | Basic EPS                              | `eps_basic`               | ✅              |
| item | Basic EPS - Continuing Ops (NEW v4)    | `eps_basic_continuing`    | ✅              |
| item | Diluted EPS                            | `eps_diluted`             | ✅              |
| item | Diluted EPS - Continuing Ops (NEW v4)  | `eps_diluted_continuing`  | ✅              |
| ~~item~~ | ~~Dividend Per Share~~ | ~~`dividend_per_share`~~ | ❌ 不算 IS 科目 |

**IS 小計：23 確認（24 候選 - Dividend Per Share 砍掉，不屬 IS 科目；CF 已有 `dividends_paid` 為 source-of-truth，per-share 為 derived）**

---

## Balance Sheet（39 候選）

### Cash & ST Investments

| 分類   | SA label               | 提案 uni_account           | 確認  |
| ---- | ---------------------- | ------------------------ | --- |
| item | Cash And Equivalents   | `cash_and_equivalents`   | ✅   |
| item | Short Term Investments | `short_term_investments` | ✅   |

### Receivables

| 分類   | SA label            | 提案 uni_account        | 確認  |
| ---- | ------------------- | --------------------- | --- |
| item | Accounts Receivable | `accounts_receivable` | ✅   |
| item | Other Receivables   | `other_receivables`   | ✅   |

### Current Assets（其他）

| 分類           | SA label             | 提案 uni_account         | 確認  |
| ------------ | -------------------- | ---------------------- | --- |
| item         | Inventory            | `inventories`          | ✅   |
| item         | Other Current Assets | `other_current_assets` | ✅   |
| **subtotal** | Total Current Assets | `total_current_assets` | ✅   |

### Long-Term Assets

| 分類           | SA label                              | 提案 uni_account                   | 確認  |
| ------------ | ------------------------------------- | -------------------------------- | --- |
| item         | Gross Property, Plant & Equipment     | `ppe_gross`                      | ✅   |
| item         | Accumulated Depreciation              | `accumulated_depreciation`       | ✅   |
| **subtotal** | Net Property, Plant & Equipment       | `ppe_net`                        | ✅   |
| item         | Right of Use Assets (NEW v4, ASC 842) | `right_of_use_assets`            | ✅   |
| item         | Long-Term Investments                 | `long_term_investments`          | ✅   |
| item         | Goodwill                              | `goodwill`                       | ✅   |
| item         | Other Intangibles                     | `other_intangibles`              | ✅   |
| item         | Deferred Tax Assets (LT)              | `deferred_tax_assets_noncurrent` | ✅   |
| item         | Other Long-Term Assets                | `other_long_term_assets`         | ✅   |
| **subtotal** | Total Assets                          | `total_assets`                   | ✅   |

### Current Liabilities

| 分類           | SA label                             | 提案 uni_account                         | 確認  |
| ------------ | ------------------------------------ | -------------------------------------- | --- |
| item         | Accounts Payable                     | `accounts_payable`                     | ✅   |
| item         | Accrued Liabilities                  | `accrued_liabilities`                  | ✅（rename 對齊 us-gaap XBRL）|
| item         | Short-Term Borrowings                | `short_term_borrowings`                | ✅   |
| item         | Current Portion of LT Debt           | `current_portion_of_long_term_debt`    | ✅   |
| item         | Current Portion of Lease Obligations | `current_portion_of_lease_obligations` | ✅   |
| item         | Current Income Taxes Payable         | `income_taxes_payable_current`         | ✅   |
| item         | Unearned Revenue, Current            | `deferred_revenue_current`             | ✅   |
| item         | Other Current Liabilities            | `other_current_liabilities`            | ✅   |
| **subtotal** | Total Current Liabilities            | `total_current_liabilities`            | ✅   |

### Long-Term Liabilities

| 分類           | SA label                                      | 提案 uni_account                        | 確認  |
| ------------ | --------------------------------------------- | ------------------------------------- | --- |
| item         | Long-Term Debt                                | `long_term_debt`                      | ✅   |
| item         | Unearned Revenue Non-Current                  | `deferred_revenue_noncurrent`         | ✅   |
| item         | Pension & Other Post-Retire. Benefits         | `pension_post_retirement_obligations` | ✅   |
| item         | Def. Tax Liability, Non-Curr.                 | `deferred_tax_liabilities_noncurrent` | ✅   |
| item         | Capital Leases                                | `capital_lease_obligations`           | ✅   |
| item         | Long-term Lease Liabilities (NEW v4, ASC 842) | `long_term_lease_liabilities`         | ✅   |
| item         | Other Non-Current Liabilities                 | `other_noncurrent_liabilities`        | ✅   |
| **subtotal** | Total Liabilities                             | `total_liabilities`                   | ✅   |

### Equity

| 分類           | SA label                     | 提案 uni_account                 | 確認  |
| ------------ | ---------------------------- | ------------------------------ | --- |
| item         | Common Stock                 | `common_stock`                 | ✅   |
| item         | Additional Paid-in Capital   | `additional_paid_in_capital`   | ✅（TAG_MAP 已有）|
| item         | Treasury Stock               | `treasury_stock`               | ✅（TAG_MAP 已有）|
| item         | Accumulated OCI (NEW Phase B, NotebookLM) | `aoci`                | ✅   |
| item         | Retained Earnings            | `retained_earnings`            | ✅   |
| item         | Minority Interest            | `minority_interest_bs`         | ✅   |
| **subtotal** | Total Equity                 | `total_equity`                 | ✅   |
| **subtotal** | Total Liabilities And Equity | `total_liabilities_and_equity` | ✅   |

### BS Metadata

| 分類       | SA label                                        | 提案 uni_account                   | 確認  |
| -------- | ----------------------------------------------- | -------------------------------- | --- |
| metadata | Total Shares Out. on Filing Date（point-in-time） | `shares_outstanding_filing_date` | ✅   |
| metadata | Common Shares Out. at BS date（period-end，us-gaap:CommonStockSharesOutstanding；unit `millions_shares`；排除 BS footing；BVPS 分母）| `common_shares_outstanding` | ✅   |
| metadata | Total Debt（subtotal of ST + LT debt）            | `total_debt`                     | ✅   |

**BS 小計：39 候選（含 7 subtotals），預設 ✅ 9 個**

---

## Cash Flow Statement（26 候選）

### Operating

| 分類           | SA label                             | 提案 uni_account                     | 確認  |
| ------------ | ------------------------------------ | ---------------------------------- | --- |
| item         | Depreciation & Amortization          | `depreciation_amortization_cf`     | ✅   |
| item         | Asset Writedown & Restruc. Costs     | `asset_writedown_restructuring_cf` | ✅   |
| item         | Stock-Based Compensation             | `stock_based_compensation`         | ✅   |
| item         | Deferred Income Taxes (NEW Phase B, NotebookLM) | `deferred_income_taxes_cf` | ✅ |
| item         | Gain/Loss on Sale of Assets (NEW Phase B, NotebookLM) | `gain_loss_on_sale_cf` | ✅ |
| item         | Equity in Net Income of Affiliates (NEW Phase B, NotebookLM) | `equity_in_net_income_of_affiliates_cf` | ✅ |
| item         | Other Operating Activities           | `other_operating_activities_cf`    | ✅   |
| item         | Change In Accounts Receivable        | `change_in_accounts_receivable`    | ✅   |
| item         | Change In Inventories                | `change_in_inventories`            | ✅   |
| item         | Change In Accounts Payable           | `change_in_accounts_payable`       | ✅   |
| item         | Change In Income Taxes               | `change_in_income_taxes_cf`        | ✅   |
| item         | Change in Other Net Operating Assets | `change_in_other_operating_assets` | ✅   |
| **subtotal** | Cash from Operations                 | `cash_from_operating`              | ✅   |

### Investing

| 分類           | SA label                                | 提案 uni_account                           | 確認  |
| ------------ | --------------------------------------- | ---------------------------------------- | --- |
| item         | Capital Expenditure                     | `capex`                                  | ✅   |
| item         | Cash Acquisitions                       | `cash_acquisitions`                      | ✅   |
| item         | Divestitures                            | `divestitures`                           | ✅   |
| ~~item~~     | ~~Sale (Purchase) of Intangible assets~~    | ~~`sale_purchase_intangibles`~~              | ❌ NotebookLM：過於細瑣，併入 other_investing |
| ~~item~~     | ~~Invest. in Marketable & Equity Securit.~~ | ~~`invest_in_marketable_equity_securities`~~ | ❌ 同上 |
| item         | Other Investing Activities              | `other_investing_activities`             | ✅   |
| **subtotal** | Cash from Investing                     | `cash_from_investing`                    | ✅   |

### Financing

| 分類           | SA label                   | 提案 uni_account               | 確認  |
| ------------ | -------------------------- | ---------------------------- | --- |
| item         | Short Term Debt Issued     | `short_term_debt_issued`     | ✅   |
| item         | Long-Term Debt Issued      | `long_term_debt_issued`      | ✅   |
| ~~subtotal~~ | ~~Total Debt Issued~~      | ~~`total_debt_issued`~~      | ❌ NotebookLM：公司不會自己 subtotal，是 derived |
| item         | Short Term Debt Repaid     | `short_term_debt_repaid`     | ✅   |
| item         | Long-Term Debt Repaid      | `long_term_debt_repaid`      | ✅   |
| ~~subtotal~~ | ~~Total Debt Repaid~~      | ~~`total_debt_repaid`~~      | ❌ NotebookLM：同上，是 derived |
| item         | Issuance of Common Stock   | `issuance_of_common_stock`   | ✅   |
| item         | Repurchase of Common Stock | `repurchase_of_common_stock` | ✅   |
| item         | Common Dividends Paid      | `dividends_paid`             | ✅   |
| item         | Other Financing Activities | `other_financing_activities` | ✅   |
| **subtotal** | Cash from Financing        | `cash_from_financing`        | ✅   |

### CF Closing

| 分類           | SA label                          | 提案 uni_account       | 確認  |
| ------------ | --------------------------------- | -------------------- | --- |
| item         | Foreign Exchange Rate Adjustments | `fx_effect_on_cash`  | ✅   |
| **subtotal** | Net Change in Cash                | `net_change_in_cash` | ✅   |

### CF Supplemental

| 分類   | SA label             | 提案 uni_account         | 確認  |
| ---- | -------------------- | ---------------------- | --- |
| item | Cash Interest Paid   | `cash_interest_paid`   | ✅   |
| item | Cash Income Tax Paid | `cash_income_tax_paid` | ✅   |

**CF 小計：30 候選（含 5 subtotals），預設 ✅ 6 個**

---

## 不收進 facts 的派生指標清單（→ financial_metrics）

### IS 派生
- `gross_margin_pct`、`operating_margin_pct`、`net_margin_pct`、`profit_margin_pct`
- `effective_tax_rate`
- `ebit`、`ebitda`、`ebita`、`ebitdar`
- `ebitda_margin_pct`
- `revenue_per_share`
- `payout_ratio`

### BS 派生
- `net_debt` (= Total Debt - Cash & ST I)
- `book_value_per_share`、`tangible_book_value`、`tangible_book_value_per_share`
- `cash_per_share`
- `current_ratio`、`quick_ratio`
- `roe`、`roa`、`roic`
- `debt_to_equity`、`net_debt_to_equity`
- `cash_conversion_cycle`

### CF 派生
- `free_cash_flow` (= OCF - capex)
- `levered_free_cash_flow`、`unlevered_free_cash_flow`
- `free_cash_flow_to_firm`、`free_cash_flow_to_equity`
- `fcf_per_share`
- `change_in_net_working_capital_total`
- `net_capital_expenditure` (= capex - disposals)
- `net_debt_issued_repaid`

---

## 統計（v5 — Phase B NotebookLM 修正 2026-05-10）

| Statement | 候選總數 | 確認 ✅ | 砍 ❌ |
|---|---|---|---|
| IS | 24 | 23 | 1（Dividend Per Share）|
| BS | 41 | 41 | 0（+APIC, +Treasury Stock, +AOCI，跟 TAG_MAP 對齊）|
| CF | 30 | 26 | 4（total_debt_issued/repaid subtotals + 2 個過細 Investing items）|
| **總計** | **95** | **90** | **5** |

> v4 → v5 變更（依 NotebookLM `Parse_SEC_Filings` SEC/CFA/XBRL guidance）：
> - **加 4 個**：`aoci`、`deferred_income_taxes_cf`、`gain_loss_on_sale_cf`、`equity_in_net_income_of_affiliates_cf`
> - **加 2 個對齊 TAG_MAP**：`additional_paid_in_capital`、`treasury_stock`（已在 BS_TAG_MAP，補上 checklist）
> - **砍 4 個**：CF 的 `total_debt_issued`、`total_debt_repaid` subtotals + `sale_purchase_intangibles` + `invest_in_marketable_equity_securities`
> - **rename**：`accrued_expenses` → `accrued_liabilities`（對齊 us-gaap XBRL `AccruedLiabilitiesCurrent`）

---

## 已 LOCK — schema 拍板

從 2026-05-10 起本 checklist **作為核心 schema 的權威來源**。

新加 metric → 必須在這份文件登記、勾 ✅ 後才能進 IS_TAG_MAP / BS_TAG_MAP / CF_TAG_MAP。

降級為 long-tail bucket（如本次的 dividend_per_share） → 走長尾流程。

打勾完丟回給我，我接著做：
1. 從 ✅ 列表 promote 成正式 `docs/financials-view-schema.md`
2. 改 CLAUDE.md 規則（dual-key + long-tail bucket）
3. 擴 parse-10QK-gaap 的 IS_TAG_MAP / BS_TAG_MAP / CF_TAG_MAP
4. 擴兩個 NLM skill 的 canonical key 集合
5. 加 long-tail bucket 處理邏輯到三個 skill
