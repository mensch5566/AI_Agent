# derive 市場無關化(A 案)— 設計 spec

日期:2026-07-02
狀態:v2 — Argue 收斂修訂版(architect=Opus vs skeptic=GPT-5.5,6 輪,17 claims 全數接受,verdict=GO-with-amendments)
上游決策:使用者拍板「Derive 走 A 合併」(2026-07-02);parity 鐵律見 memory `feedback_tw_us_metric_parity`
Argue 紀錄:`~/.config/argue/derive-a-summary.md`(request-id `derive-a`)

## 0. 權威基準(Argue 修訂)

本 spec 針對的引擎是 **live canonical**:

- `/Users/mensch5566/CC_Switch_Config/skills/derive-base/scripts/`
- `/Users/mensch5566/CC_Switch_Config/skills/derive-analytics/scripts/`
- `/Users/mensch5566/AI_Agent/Tools/research-tools/_shared/sec_json_adapter.py`

`AI_Agent/tmp/derive-*` 是**過期 prototype**(無 BVPS、無 Q4 EPS approx 規則),
**禁止**作為任何 diff / 回歸 / 參數化盤點的基準。

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
`twse_json_adapter.py`,engine 邏輯一行不改。

`CompanyRow` 已有 `currency`(現在恆為 USD)與 `fiscal_year_end_month` 欄位,derive 目前
沒在用——這一輪把 currency 用起來。

## 3. parse-twse-ixbrl 命名對齊(慎重變更,已過 Argue)

### 原則

- **共有科目**:凡是概念存在於美股 core checklist(`docs/financials-core-checklist.md` +
  `docs/financials-view-schema.md`)的台股科目,一律改用美股 canonical 名。
- **台股獨有科目**(`legal_reserve`、`oci_fx_translation`、`long_term_payables`…):保留台股名。
  parity 的定義是「共有三表結構 + derive 指標一致」,不是硬把兩邊科目湊成相同集合。
- `source_account` 留 TWSE 原始概念(audit trail),與美股分工相同。

### 已確認的 rename(derive 關鍵路徑,實作 plan 第一步對照 SSOT 文件補全全表)

| 台股現名 | 美股 canonical |
|---|---|
| operating_revenue | revenue |
| cost_of_revenue | cost_of_goods_sold |
| r_and_d_expenses | research_and_development |
| basic_eps / diluted_eps | eps_basic / eps_diluted |
| cash_and_equivalents | cash_and_cash_equivalents |
| ppe_net | property_plant_equipment_net |
| capital_surplus | additional_paid_in_capital |
| operating_cash_flow | net_cash_from_operating |
| investing_cash_flow / financing_cash_flow | net_cash_from_investing / net_cash_from_financing |
| capex | capital_expenditures |

### Net income 家族(Argue 修訂:避免 total vs parent 撞名)

台股合併報表(cr)同時揭露 本期淨利(含 NCI 總額)、歸母、NCI 三個值;個體(ir)只有單一
net_income。映射:

| 台股揭露 | uni_account | 說明 |
|---|---|---|
| 歸屬母公司淨利(8610) | `net_income` | 與美股 NetIncomeLoss(歸母)同義 |
| 非控制權益(8620) | `net_income_nci` | 與美股同名;EBITDA consolidated add-back 用它 |
| 本期淨利總額(cr) | `net_income_total_pre_nci` | 台股揭露值保留,不參與共用 rules(美股無此 key) |
| ir 的 net_income | `net_income` | 個體報表無 NCI,直接同名,無撞名 |

### Debt 家族(Argue 修訂:rename 範圍必須涵蓋,否則 debt_to_equity / ROIC / net-debt 靜默跳過)

台股若有對應揭露(短期借款、一年內到期長期負債、長期借款),映射到美股 canonical:
`short_term_borrowings` / `current_portion_of_long_term_debt` / `long_term_debt` /
`current_debt`(面額聚合,若有直接揭露)。聯亞 3081 無借款 → 自然缺鍵、規則 fail-closed
跳過;台達電 2308 依實際揭露補全。

### xbrl_concept 保留(Argue 修訂)

台股 parse 目前輸出 `xbrl_concept: null` → §4 的 provenance / concept-drift guard 承諾會落空。
本輪 re-parse 時**一併填入來源 XBRL concept**(如 `ifrs-full:Revenue`)。此為純 audit
metadata 增補,不改任何 value;Gate 1 diff 規則相應允許 `xbrl_concept: null→值` 的差異。

### `__q` 後綴慣例保留

它是 parse 揭露層概念,由 adapter 消化。

### Blast radius(全部連動,一輪做完;Argue 修訂:比 v1 列的更廣)

1. `parse_ixbrl.py` XBRL_MAP / 科目名 map — rename(TDD,先改測試斷言)
2. `parse_ixbrl.py` **helper 常數**:`SCALE_EXEMPT_METRICS`(現含 `basic_eps`/`diluted_eps`,
   line 189)必須同步改名,否則 EPS 會被套上金額 scale 檢查
3. `parse-tw-crosscheck`:`CODE_TO_KEY` 值域、**`EPS_KEYS`**(cross_check_twse.py:44-45,
   含 `__q` 變體;不改則 EPS 永不 rescale 的保護失效)、`ticker_configs/{3081,2308}.json`
   的 `label_to_key` 值域、測試斷言
4. **repo-wide 舊名 grep**(`operating_revenue|basic_eps|cost_of_revenue|capex`…):清掉散落
   consumer,包含 scratchpad 驅動腳本;grep 結果為空才算完成
5. re-parse 聯亞(29 期)+ 台達電 → facts 檔全部重出
6. **twse-derive 同步 pin**(見 §10:它讀舊 key 名,rename 後跑會靜默錯讀)
7. **不重跑 NLM sweep**:數值一個都沒變。驗收 = Gate 1 機械 diff

## 4. twse_json_adapter.py(新檔,鏡像 sec_json_adapter)

位置:`AI_Agent/Tools/research-tools/_shared/twse_json_adapter.py`(canonical 與 CC_Switch_Config 同步,遵守既有 SSOT sync 流程)。

輸入:`{TICKER}_twse_facts.json`(parse-twse-ixbrl 輸出,§3 rename 後版本)
輸出:`FactRow` list + `CompanyRow(currency="TWD", ...)`——與 sec adapter 同型別

### 轉換規則

| # | 轉換 | 規則 |
|---|---|---|
| 1 | 容器 | `facts_by_period[p]["facts"][k]` 攤平成 row list |
| 2a | 期別命名 — IS/CF duration | Q1 ytd→`Q1_FY{Y}`(quarter_duration;Q1 YTD 即單季);Q2 ytd→`6M_FY{Y}`、Q3 ytd→`9M_FY{Y}`(ytd_duration);年報 IS/CF→`FY{Y}`(fy_annual_duration) |
| 2b | 期別命名 — BS instant(Argue 修訂,關鍵) | BS instant 一律標 `Q{n}_FY{Y}`:Q1/Q2/Q3 報表→`Q1/Q2/Q3_FY{Y}`,**年報的期末 BS→`Q4_FY{Y}`(不是 `FY{Y}`)**。rules_crossperiod `_emit_annual` 用 `Q4_FY{y}` label 查年末餘額,標錯則年度 ROE/ROA/asset_turnover/ROIC 全部靜默跳過 |
| 3 | `__q` 揭露單季 | `revenue__q`@Q2 → uni_account=`revenue`、period=`Q2_FY{Y}`、quarter_duration、status=**SOURCE_OF_TRUTH**(揭露值優先,已拍板)。engine(rules_q2q3.py:81 / rules_q4.py:109)看到單季已存在即跳過重建 |
| 4 | 單位 | top-level `TWD_thousands` 下放到每 row;EPS row 給 `TWD_per_share` |
| 5 | statement | `income_statement`→IS;`balance_sheet_*` 三段→BS;`cash_flow_*` 四段→CF(原 substatement 保留在 provenance 供 audit) |
| 6 | CF duration | 台股 CF 全 YTD,照實吐 `6M/9M/FY` ytd rows → engine 既有 `Q2=6M−Q1`、`Q3=9M−6M`、`Q4=FY−9M` 規則補單季,與美股 CF 行為完全同型 |
| 7 | **CF 符號正規化(Argue 修訂,關鍵)** | 台股 CF 為帶號加總慣例(3081 實值 capex=-502002、investing_cash_flow=-511174);美股 engine 假設 `capital_expenditures` 為**正的支出**(rules_ratios FCF 規則 coef=-1.0,註明 SEC 慣例)。adapter 必須把 capex 翻正;`net_cash_from_investing/financing` 維持帶號淨額(與美股同義,不翻)。逐一列出 sign-dependent 科目並各有 fixture 測試——**不翻則 FCF = CFO+\|capex\|,錯 2×capex** |
| 8 | **現金餘額排除(Argue 修訂,關鍵)** | `beginning_cash` / `ending_cash`(cash_flow_summary,period_kind 誤標 ytd)**不得進入餵給重建的 fact 流**——engine 選重建對象只看 statement∈{IS,CF}+unit(rules_q4.py:93-95,無 period_kind gate),不排除就會被 FY−9M 硬算。`net_change_in_cash` 是真 duration 流量,保留。舊 twse-derive 的 `CASH_BALANCE_KEYS` 排除清單即此用途 |
| 9 | provenance | 帶 `report_category`(ir/cr)、`xbrl_concept`(§3 補齊後)→ `source_account`/`xbrl_tag`、原 substatement、facts 檔 sha256 |
| 10 | version | 恆 `GAAP`(台股無 Non-GAAP 管道;IFRS 值走同一欄位語義) |

### `__q` 對帳(Argue 修訂:取代 v1 的錯誤假設)

`__q` 升格 SOURCE_OF_TRUTH 後 engine **跳過**重建 → 不會產生 derived candidate,
engine 的 conflicts 統計**永遠不會**比對「揭露單季 vs YTD 差」。因此 adapter(或
驗證腳本)必須自帶對帳:對每個有 `__q` 的 (period, uni_account),檢查
`__q 值 == ytd_n − ytd_{n−1}`(tol=0);差異列入驗證報告人工 audit(可能是官方
重編,不自動蓋)。

### 缺口對稱性(為什麼 engine 直接可用)

| 缺口 | 台股 | 美股 | engine 規則 |
|---|---|---|---|
| Q4 單季 | 年報只有 FY 累計 | 10-K 只有 FY | Q4_FY_MINUS_9M |
| CF 單季 | CF 只揭 YTD | 10-Q CF 只揭 YTD | Q2_6M_MINUS_Q1 / Q3_9M_MINUS_6M |
| Q4 EPS | 留空(見 §5 market gate) | 有 approx 規則(USD gate) | 台股明確關閉 |

## 5. engine 參數化(邏輯不改,寫死點改查表)

**盤點紀律(Argue 修訂)**:實作 plan 第一步對 **live engine**(§0 路徑)做完整 hardcode
盤點,以 grep 證據落檔;下表為已知項,**不得**視為完整清單。註解/docstring 內的 USD
字樣**僅在**測試、報告或生成的驗證產物依賴其內容時才列入盤點(純說明文字不改,避免
無意義 churn)。

| # | 寫死點 | 位置(live) | 改法 |
|---|---|---|---|
| 1 | Q4/Q2Q3 重建單位 allowlist `{USD_thousands, USD_millions}` | rules_q4 / rules_q2q3 | 加 `TWD_thousands`(統一 additive-money allowlist 常數,單處定義) |
| 2 | ratio scale map `_USD_SCALE` | rules_ratios | 改 `_MONEY_SCALE`(USD_* + TWD_thousands);shares map 不動 |
| 3 | per-share 單位字串 `USD_per_share` | rules_ratios(BVPS 輸出 unit 等) | 由 currency 推 `{currency}_per_share` |
| 4 | **Q4 EPS approx 規則(Argue 修訂,關鍵)** | rules_q4(`Q4_EPS_APPROX_FY_MINUS_Q1Q2Q3`,現為無條件 USD_per_share) | **加 market/currency gate:台股(TWD)不啟用**——台股 Q4 EPS 留空是既定紀律(memory `feedback_q4_eps_no_reconstruction`),「自動繼承」的說法錯誤,必須顯式關閉 |
| 5 | D&A 輸入 | derive-analytics EBITDA 需 `depreciation_and_amortization` | 新 identity 規則 `DA_DEP_PLUS_AMORT`(D&A = depreciation + amortization)。**Argue 修訂:此為共用層新規則,是美股回歸風險——scope 成「僅當該期無揭露的 depreciation_and_amortization 時才觸發」,並以 Gate 3 對 5 檔美股證明輸出 bit-identical**(美股若因此新增 row 即回歸失敗,需改為 TW-only gate 或另行設計) |
| 6 | 輸入檔路徑/檔名 | io_loader(寫死 `SEC Filings` + `{T}_gaap_facts.json`) | CLI 加 `--market tw\|us`(default us,fail-closed):tw 走 `MOPS Filings/Skill_Output/parse-twse-ixbrl/{T}_twse_facts.json` + twse adapter;us 行為完全不變 |
| 7 | tolerance / validation helpers | derive-* 內含單位的輔助檢查 | 盤點時一併納入 currency-aware 化 |

### 台股路徑的輸入差異

- 無 `edges_cal.json` / `gaap.json` → CALC_LINKBASE identity 規則自然無 candidates 跳過;
  STATIC_ALLOWLIST identities(gross_profit = revenue − cogs 等)照常適用
- 無 Non-GAAP 檔 → 本來就 optional
- 缺 input 的規則(BVPS 需股數、debt 系需借款科目)fail-closed 跳過(Argue 已對 code
  驗證:`_resolve_side` 用 dict.get + None-skip,不會 KeyError)

輸出落地:`.../01_Source/MOPS Filings/Skill_Output/derive-base/<ts>/{T}_derived.json`、
`derive-analytics/<ts>/{T}_analytics.json`——schema 與美股完全相同(cell_id / status /
provenance / rule_id),僅 unit 是 TWD 系。

## 6. 驗證計畫

### Gate 1 — rename 無值變

re-parse 後 diff:舊 facts 檔經 rename map 對翻 key 後,與新 facts 檔語義等值
(value / period_end / statement / sort_order / period_kind 全等)。唯一允許的例外:
`xbrl_concept` 由 null → 填入概念名(§3 增補)。任何其他差 → 停,查 parse。

### Gate 2 — 新舊 derive 交叉驗證(3081 + 2308 全期;Argue 修訂重分類)

| 類別 | 指標 | 判準 |
|---|---|---|
| 直接可比 | gross_margin、operating_margin、net_margin、effective_tax_rate、current_ratio | 新舊值一致(tol=浮點誤差) |
| **先過符號檢核才可比** | FCF | 前置:raw adapter 檢查證明 capital_expenditures 已翻正、investing/financing 慣例相容(§4 規則 7)。過了才比對 FCF 值 |
| **口徑不同(v1 誤列為可比,Argue 修訂)** | interest_coverage(新舊公式不同)、roe/roa(舊=單季NI/期末值 vs 新=TTM)、debt_to_equity(舊=總負債/權益 vs 新=借款/權益) | 以美股口徑為準(parity 鐵律),差異記錄在驗證報告,不算 fail |
| 舊有新無 | pretax_margin、opex_ratio、equity_ratio | 美股 rule set 沒有 → 隨 twse-derive 退役消失 |
| 新有舊無 | quick_ratio、cash_ratio、EBITDA 系、FCF margin、TTM 系、QoQ/YoY | 抽查數期人工核算 |

追加驗證(Argue 修訂):
- `__q` 對帳表(§4):全期 `__q == ytd 差`,例外人工 audit
- 無任何 `derived_q*` 的 beginning_cash / ending_cash row
- 台股輸出無 Q4 EPS row

### Gate 3 — 美股零回歸(對 live engine,禁 tmp/ 基準)

MU / LITE / INTC / SNDK / AAOI 各跑一次 derive-base + derive-analytics(live
CC_Switch_Config 引擎 + live fixtures),輸出的 `derived_metrics` / `analytics_metrics`
陣列與改動前語義等值(排除 `run_timestamp` 等 run metadata 後 deep-equal)。
DA_DEP_PLUS_AMORT 若使任何美股 ticker 新增 row → 回歸失敗(§5 規則 5 的 scope 重做)。
另記錄美股現行是否重建 ending_cash(現況文件化;台股排除是 adapter-only 行為,鐵律 2)。

## 7. twse-derive 退役

- **步驟 1(與 rename 同步,Argue 修訂)**:pin/停用 twse-derive(它讀舊 key 名,rename
  後執行會靜默錯讀)——在 skill 入口加 hard error 指向本 spec,或直接移出 manifest。
  rename 與 adapter 落地之間**不得有任何 live consumer 讀取新名 facts**。
- Gate 2 全過後:刪 `CC_Switch_Config/skills/twse-derive/` + `skills-manifest.json` 除名 +
  re-sync。舊輸出檔(`3081_twse_metrics.json`)保留在 Skill_Output 作歷史對照,不刪。

## 8. 測試策略

全程 TDD。新增/修改測試:

1. parse rename:改既有 parse 測試斷言為新名(先紅後綠);`SCALE_EXEMPT_METRICS` 新名
   下 EPS 免 scale 檢查的測試;xbrl_concept 填入測試
2. `twse_json_adapter` fixture 測試:期別翻譯(含 **年末 BS instant→Q4_FY**)、
   `__q`→單季 SOURCE_OF_TRUTH、單位下放、EPS per-share、statement 收斂、CF ytd、
   **capex 翻正(正支出)**、**beginning/ending_cash 不進重建流 + net_change_in_cash 保留**、
   cr 的 NI 家族三鍵、ir 無撞名
3. engine 參數化:TWD allowlist / `_MONEY_SCALE` / `{currency}_per_share` /
   **Q4 EPS market gate(TW 無 Q4 EPS row)** / DA_DEP_PLUS_AMORT(含「美股有揭露
   D&A 時不觸發」)各自單元測試 + 美股行為不變的回歸斷言
4. `parse-tw-crosscheck`:CODE_TO_KEY + EPS_KEYS 新值域測試(既有 22 測試更新)
5. `__q` 對帳邏輯測試(fixture:相符、不符兩型)
6. Gate 1/2/3 的 diff 腳本本身有測試;Gate 3 明確斷言基準來自 live 路徑(禁 tmp/)
7. 缺鍵 fail-closed:無股數 → 無 BVPS row;無借款 → 無 debt 系 row(斷言 skip 非 crash)

## 9. 風險與緩解

| 風險 | 緩解 |
|---|---|
| parse rename 改壞值 | Gate 1 機械 diff;parse 變更已過 Argue;TDD |
| 參數化改變美股行為 | Gate 3 live-engine deep-equal 零回歸;DA identity scope 條件 |
| capex/CF 符號翻錯 | §4 規則 7 fixture 測試 + Gate 2 raw sign 檢核前置 |
| `__q` 與 YTD 不一致未被發現 | §4 專屬對帳(engine conflicts 統計**抓不到**——v1 此處假設錯誤,已修訂) |
| adapter 期別翻錯 | fixture 測試逐 period_kind/label 斷言(含 Q4_FY BS instant);Gate 2 年度比率消失會立刻暴露 |
| rename→adapter 之間的危險窗口 | §7 步驟 1 同步 pin twse-derive;該窗口無任何 consumer 讀新名 facts |
| canonical/CC_Switch 兩份漂移 | 遵守既有 sync 流程,改 canonical 後 `sync-to-local.sh`,commit 兩 repo |
| 拿 tmp/ 舊引擎當基準 | §0 明定 live 路徑;Gate 3 斷言基準路徑 |

## 10. 實作順序(給 writing-plans;Argue 修訂:步驟 1 併入 twse-derive pin)

1. **Rename 前置**:live-engine hardcode 盤點落檔(§5)+ rename map 全表(對照 core
   checklist)+ **pin/停用 twse-derive(原子動作)**
2. parse rename TDD(含 SCALE_EXEMPT_METRICS、xbrl_concept 填入)→ re-parse → Gate 1
3. cross-check 連動更新(CODE_TO_KEY + EPS_KEYS + configs + 測試)+ repo-wide 舊名 grep 清零
4. `twse_json_adapter.py` TDD(含符號正規化、現金餘額排除、Q4_FY BS instant、`__q` 對帳)
5. engine 參數化 TDD(含 Q4 EPS market gate、DA identity scope)+ Gate 3(live 零回歸)
6. 3081/2308 跑新管道 → Gate 2 交叉驗證報告(含 `__q` 對帳表、無現金餘額重建、無 TW Q4 EPS)
7. twse-derive 刪除 + manifest + docs(skill.md CHANGELOG、STATUS.md、memory)

## 附錄:Argue 收斂摘要(2026-07-02,request-id derive-a)

- verdict:**GO-with-amendments**(雙方一致);17/17 claims resolved
- 關鍵抓漏:capex 符號(FCF 錯 2×capex)、年末 BS 必須 Q4_FY label、Q4 EPS approx
  規則需顯式 gate、beginning/ending_cash 會被錯誤重建、`__q` 對帳缺口(conflicts 統計
  抓不到)、NI 家族撞名、EPS helper 常數(SCALE_EXEMPT_METRICS / EPS_KEYS)、
  twse-derive 危險窗口、tmp/ 過期引擎誤導風險
- 驗證為 sound 免修:engine fail-closed(dict.get + None-skip)、TTM 340–400 天窗對
  台股曆年季度無違反
