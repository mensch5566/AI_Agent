# derive 市場無關化(A 案)— 設計 spec

日期:2026-07-02
狀態:設計已口頭核准(五節逐節過),本文件為正式 spec
上游決策:使用者拍板「Derive 走 A 合併」(2026-07-02);parity 鐵律見 memory `feedback_tw_us_metric_parity`

## 1. 背景與目標

### 問題

台股(TWSE iXBRL)與美股(SEC XBRL)目前是兩條 derive 管道:

- 美股:`derive-base`(Q4/Q2/Q3 重建 + identities)+ `derive-analytics`(ratios + TTM/crossperiod),吃 `sec_json_adapter.FactRow`
- 台股:`twse-derive`(單季重建 + 13 比率),自己一套 code、自己一套比率定義(ROE/ROA/debt_to_equity 口徑都跟美股不同)

雙軌違反 parity 鐵律:**台美最終三表科目結構(uni_account)與 derive 指標必須一致,管道差異只能存在於抽取層**。

### 目標(這一輪)

1. 台股 facts 收斂進美股 derive code path:一份 rules engine 跑兩邊
2. parse-twse-ixbrl 的 uni_account 命名對齊美股 canonical(共有科目)
3. 聯亞 3081 + 台達電 2308 跑通新管道並交叉驗證
4. 退役 `twse-derive`

### Non-goals(下一輪)

- compose-financials 台股支援(已拍板要做,另開一輪)
- 台股 Supabase Phase E(twse_financial_* 表 + upsert)
- 台股前端 Financials 面板
- SG&A 對齊(台股 推銷費用/管理費用 分列 vs 美股 selling_general_administrative 合併;derive 不需要它,延到 compose 輪決策,傾向鏡像美股「sum 補核心 + 子科目留 long-tail」作法)

## 2. 架構總覽

```
美股: parse-10QK-gaap ──► sec_json_adapter ──┐
                                              ├─► FactRow list ─► rules engine(邏輯不改,只參數化)
台股: parse-twse-ixbrl ──► twse_json_adapter ─┘      │
                                                     ├─► derive-base    → {T}_derived.json
                                                     └─► derive-analytics → {T}_analytics.json
```

核心洞察:美股 derive 從不直接讀 parse JSON,而是經 `_shared/sec_json_adapter.py` 轉成
`FactRow`(period / period_kind / period_end / unit / uni_account / value / statement /
version / source_account / provenance)。rules engine(rules_q4 / rules_q2q3 /
rules_identity / rules_ratios / rules_crossperiod)只認 FactRow。台股只需要一個對稱的
`twse_json_adapter.py`,engine 一行邏輯不改。

`CompanyRow` 已有 `currency`(現在恆為 USD)與 `fiscal_year_end_month` 欄位,derive 目前
沒在用——這一輪把 currency 用起來。

## 3. parse-twse-ixbrl 命名對齊(慎重變更,走 Argue)

### 原則

- **共有科目**:凡是概念存在於美股 core checklist(`docs/financials-core-checklist.md` +
  `docs/financials-view-schema.md`)的台股科目,一律改用美股 canonical 名。
- **台股獨有科目**(`legal_reserve`、`oci_fx_translation`、`long_term_payables`…):保留台股名。
  parity 的定義是「共有三表結構 + derive 指標一致」,不是硬把兩邊科目湊成相同集合。
- `source_account` 照舊留 TWSE 原始概念(audit trail),與美股分工相同。

### 已確認的 rename(derive 關鍵路徑,實作 plan 第一步對照 SSOT 文件補全全表)

| 台股現名 | 美股 canonical |
|---|---|
| operating_revenue | revenue |
| cost_of_revenue | cost_of_goods_sold |
| r_and_d_expenses | research_and_development |
| basic_eps / diluted_eps | eps_basic / eps_diluted |
| net_income_parent(cr) | net_income(美股 NetIncomeLoss 本即歸母口徑,語義正確) |
| cash_and_equivalents | cash_and_cash_equivalents |
| ppe_net | property_plant_equipment_net |
| capital_surplus | additional_paid_in_capital |
| operating_cash_flow | net_cash_from_operating |
| investing_cash_flow / financing_cash_flow | net_cash_from_investing / net_cash_from_financing |
| capex | capital_expenditures |

`__q` 後綴慣例保留(如 `revenue__q`)——它是 parse 揭露層概念,由 adapter 消化。

### Blast radius(全部連動,一輪做完)

1. `parse_ixbrl.py` XBRL_MAP / 科目名 map — rename(TDD,先改測試斷言)
2. `parse-tw-crosscheck`:`CODE_TO_KEY` 值域 + `ticker_configs/{3081,2308}.json` 的 `label_to_key` 值域
3. re-parse 聯亞(29 期)+ 台達電 → facts 檔全部重出
4. **不重跑 NLM sweep**:數值一個都沒變。驗收 = before/after JSON diff 證明「僅 key 名改變、
   value/period_end/statement 完全不動」(機械 diff 腳本,鍵名經 map 對翻後兩檔必須全等)

## 4. twse_json_adapter.py(新檔,鏡像 sec_json_adapter)

位置:`AI_Agent/Tools/research-tools/_shared/twse_json_adapter.py`(canonical 與 CC_Switch_Config 同步,遵守既有 SSOT sync 流程)。

輸入:`{TICKER}_twse_facts.json`(parse-twse-ixbrl 輸出,§3 rename 後版本)
輸出:`FactRow` list + `CompanyRow(currency="TWD", ...)`——與 sec adapter 同型別

### 轉換規則

| # | 轉換 | 規則 |
|---|---|---|
| 1 | 容器 | `facts_by_period[p]["facts"][k]` 攤平成 row list |
| 2 | 期別命名 | Q1 ytd→`Q1_FY{Y}`(period_kind=quarter_duration;Q1 YTD 即單季);Q2 ytd→`6M_FY{Y}`、Q3 ytd→`9M_FY{Y}`(ytd_duration);年報→`FY{Y}`(fy_annual_duration);BS→instant_period_end |
| 3 | `__q` 揭露單季 | `revenue__q`@Q2 → uni_account=`revenue`、period=`Q2_FY{Y}`、period_kind=quarter_duration、status=**SOURCE_OF_TRUTH**(揭露值優先,已拍板)。engine 看到單季已存在就不重建,只補缺口 |
| 4 | 單位 | top-level `TWD_thousands` 下放到每 row;EPS row 給 `TWD_per_share` |
| 5 | statement | `income_statement`→IS;`balance_sheet_*` 三段→BS;`cash_flow_*` 四段→CF(原 substatement 保留在 provenance 供 audit) |
| 6 | CF | 台股 CF 全 YTD,照實吐 `6M/9M/FY` ytd rows → engine 既有 `Q2=6M−Q1`、`Q3=9M−6M`、`Q4=FY−9M` 規則補單季,與美股 CF 行為完全同型 |
| 7 | provenance | 帶 `report_category`(ir/cr)、`xbrl_concept`、原 statement、facts 檔 sha256 |
| 8 | version | 恆 `GAAP`(台股無 Non-GAAP 管道;IFRS 值走同一欄位語義) |

### 缺口對稱性(為什麼 engine 直接可用)

| 缺口 | 台股 | 美股 | engine 規則 |
|---|---|---|---|
| Q4 單季 | 年報只有 FY 累計 | 10-K 只有 FY | Q4_FY_MINUS_9M |
| CF 單季 | CF 只揭 YTD | 10-Q CF 只揭 YTD | Q2_6M_MINUS_Q1 / Q3_9M_MINUS_6M |
| Q4 EPS | 不反推留空 | 不反推留空(既有紀律) | 自動繼承 |

## 5. engine 參數化(邏輯不改,寫死點改查表)

| # | 寫死點 | 位置 | 改法 |
|---|---|---|---|
| 1 | Q4/Q2Q3 重建單位 allowlist `{USD_thousands, USD_millions}` | `rules_q4.py:47-50`(rules_q2q3 同) | 加 `TWD_thousands`(統一 additive-money allowlist 常數,單處定義) |
| 2 | ratio scale map `_USD_SCALE` | `rules_ratios.py:130-131` | 改 `_MONEY_SCALE = {USD_*, TWD_thousands, ...}`;shares map 不動 |
| 3 | per-share 單位字串 `USD_per_share` | rules_ratios BVPS 等 | 由輸入 row 的 currency 推 `{currency}_per_share` |
| 4 | D&A 輸入 | EBITDA 規則需 `depreciation_and_amortization` | 新 identity 規則 `DA_DEP_PLUS_AMORT`(D&A = depreciation + amortization,市場無關;美股分開揭露的公司同樣受益)。derive 層允許運算 |
| 5 | 輸入檔路徑/檔名 | `io_loader.py`(寫死 `SEC Filings` + `{T}_gaap_facts.json`) | CLI 加 `--market tw\|us`(default us,fail-closed):tw 走 `MOPS Filings/Skill_Output/parse-twse-ixbrl/{T}_twse_facts.json` + twse adapter;us 行為完全不變 |

### 台股路徑的輸入差異

- 無 `edges_cal.json` / `gaap.json` → CALC_LINKBASE identity 規則自然無 candidates 跳過;
  STATIC_ALLOWLIST identities(gross_profit = revenue − cogs 等)照常適用
- 無 Non-GAAP 檔 → 本來就 optional
- 缺 input 的規則(BVPS 需股數、debt 系需借款科目)fail-closed 跳過,不硬湊

輸出落地:`.../01_Source/MOPS Filings/Skill_Output/derive-base/<ts>/{T}_derived.json`、
`derive-analytics/<ts>/{T}_analytics.json`——schema 與美股完全相同(cell_id / status /
provenance / rule_id),僅 unit 是 TWD 系。

## 6. 驗證計畫

### Gate 1 — rename 無值變

re-parse 後 diff:舊 facts 檔經 rename map 對翻 key 後,與新 facts 檔逐 byte 等值
(value / period_end / statement / sort_order / period_kind 全等)。任何差 → 停,查 parse。

### Gate 2 — 新舊 derive 交叉驗證(3081 + 2308 全期)

| 類別 | 指標 | 判準 |
|---|---|---|
| 直接可比 | gross_margin、operating_margin、net_margin、effective_tax_rate、current_ratio、interest_coverage、FCF | 新舊值一致(tol=浮點誤差) |
| 口徑本來就不同 | roe/roa(舊=單季NI/期末值 vs 新=TTM)、debt_to_equity(舊=總負債/權益 vs 新=借款/權益) | 以美股口徑為準(parity 鐵律),差異記錄在驗證報告,不算 fail |
| 舊有新無 | pretax_margin、opex_ratio、equity_ratio | 美股 rule set 沒有 → 隨 twse-derive 退役消失(parity=美股集合為準) |
| 新有舊無 | quick_ratio、cash_ratio、EBITDA 系、FCF margin、TTM 系、QoQ/YoY | 抽查數期人工核算 |

### Gate 3 — 美股零回歸

MU / LITE / INTC / SNDK / AAOI 各跑一次 derive-base + derive-analytics,輸出的
`derived_metrics` / `analytics_metrics` 陣列與改動前語義等值(排除 `run_timestamp` 等
run metadata 後 deep-equal;參數化不得改變美股行為)。既有全部測試綠。

## 7. twse-derive 退役

Gate 2 全過後:刪 `CC_Switch_Config/skills/twse-derive/` + `skills-manifest.json` 除名 +
re-sync。舊輸出檔(`3081_twse_metrics.json`)保留在 Skill_Output 作歷史對照,不刪。

## 8. 測試策略

全程 TDD。新增/修改測試:

1. parse rename:改既有 parse 測試斷言為新名(先紅後綠)
2. `twse_json_adapter`:fixture 測試——期別翻譯、`__q`→單季 SOURCE_OF_TRUTH、單位下放、
   EPS per-share、statement 收斂、CF ytd、cr 的 net_income_parent→net_income
3. engine 參數化:TWD allowlist / scale map / `{currency}_per_share` / DA_DEP_PLUS_AMORT
   各自單元測試 + 美股行為不變的回歸斷言
4. `parse-tw-crosscheck`:CODE_TO_KEY 新值域測試(既有 22 測試更新)
5. Gate 1/2/3 的 diff 腳本本身有測試(拿小 fixture 驗 diff 邏輯)

## 9. 風險與緩解

| 風險 | 緩解 |
|---|---|
| parse rename 改壞值 | Gate 1 機械 diff;parse 變更走 Argue;TDD |
| 參數化改變美股行為 | Gate 3 byte-diff 零回歸 |
| `__q` 與重建值衝突未被發現 | engine 既有 conflicts 統計會抓;驗證報告必列 conflicts=0 |
| adapter 期別翻錯(Q2 ytd 誤標單季) | fixture 測試逐 period_kind 斷言;Gate 2 margins 對不上會立刻暴露 |
| canonical/CC_Switch 兩份漂移 | 遵守既有 sync 流程,改 canonical 後 `sync-to-local.sh`,commit 兩 repo |

## 10. 實作順序(給 writing-plans)

1. Rename map 全表(對照 core checklist,Argue 收斂)→ parse rename TDD → re-parse → Gate 1
2. cross-check 連動更新(CODE_TO_KEY + configs + 測試)
3. `twse_json_adapter.py` TDD
4. engine 參數化 TDD + Gate 3(美股零回歸)
5. 3081/2308 跑新管道 → Gate 2 交叉驗證報告
6. twse-derive 退役 + manifest + docs(skill.md CHANGELOG、STATUS.md、memory)
