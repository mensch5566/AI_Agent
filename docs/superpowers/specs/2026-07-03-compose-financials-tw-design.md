# compose-financials 台股支援(v2)— 設計 spec

日期:2026-07-03
狀態:**v3 — Argue 共識版**(architect=Opus 4.8 vs skeptic=GPT-5.5,5 輪 early-stop,
16 claims 全數接受,verdict=GO-with-amendments;此前 v2 為 Fable 5 self-review 版)
Argue 紀錄:`~/.config/argue/compose-tw-summary.md`(request-id `compose-tw`)
上游:derive-A 已完成;`_shared/twse_canonical_facts.py` 已落地(`ccbde9d`)。
架構前提(使用者拍板):台美**共用** viewer/儲存層;幣別/scale 依申報單位顯示。

## 1. 背景與目標

`compose-financials` 是**純渲染層**:讀本地 Skill_Output JSON → 產
`{TICKER}/03_Working/Topics/Trackers/Financials.md`,AUTO-marker 幕等、不計算任何指標。
v1 只支援美股。

### 目標
1. `--market tw`:台股 ticker 產出同結構 Financials.md
2. 幣別/scale 資料驅動(依 raw data unit;仟元就仟元、百萬就百萬)
3. 三表 layout 台美共用 + 台股條件列;台股無來源區塊整段省略
4. 美股回歸 gate:**預期 diff 僅 3 項**(frontmatter 日期、FCF 列 ⏳→值、AAOI $M→$K)

### Non-goals
- Supabase Phase E、網頁 viewer 台股渲染、台股 Non-GAAP/segment 管道
- **本輪不修的既有死 key**(Argue 掃出,列 backlog 不動,避免炸 3-diff 預算):
  `fcf_margin`(應為 fcf_margin_pct)、`nonoperating_income_expense_net`、
  `net_working_capital`、`capex_ratio`、`cfo_to_net_income` —— 台美兩邊本來就恆 ⏳,
  留待獨立輪(見 §6 backlog)
- **analytics native-statement 化**(loaders.py:66 強制 RATIO 的解除)——會遷移 32 列/ticker,
  未預算的美股回歸風險,defer

## 2. 現況斷點(探索+Argue 證據,file:line 見 argue summary)

| # | 斷點 | 位置 |
|---|---|---|
| a | 來源路徑寫死 `SEC Filings` + `parse-10QK-gaap/{T}_gaap_facts.json` | `loaders.py:6,37` |
| b | 原始 facts reader 只吃 long-format;台股是 keyed-dict | `loaders.py:39` |
| c | 幣別/scale 寫死(`$M` 標題、`$` EPS、ylabel) | `contract.py:18/36/75/114/149`、`sections.py:31`、`charts.py:56,64` |
| d | CONTRACT 寫死美股列;台股獨有科目被丟、無來源區塊全空 | `contract.py:14-156` |
| e | **既有 bug**:FCF 列 key `("RATIO","fcf")` 但 analytics emit `free_cash_flow` → 美股頁 FCF 恆 ⏳ | `contract.py:90`、`loaders.py:65-68` |
| f | **幕等破洞**:`known_keys` 傳全 CONTRACT,被過濾區塊的舊 AUTO block 永不 prune;圖表在過濾前就畫 | `cli.py:101-117`、`markers.py:32-37` |

derive-base / analytics loader 不用改(schema 相同)。statement 詞彙相容已驗
(美股 facts 就是 IS/BS/CF;`emit_canonical_facts` 同)。quarter 窗已驗不會被 6M/9M 污染
(`periods.py` 過濾非 Q label)。

## 3. 設計

### 3.1 market-aware 來源(解 a+b;Argue 修訂:precedence + 排除 derive_base)

- CLI `--market {us,tw}`,default us(choices fail-closed)。us 路徑一字不動。
- tw base:glob `Khouse/Semiconductors/*/01_Source/MOPS Filings/Skill_Output/parse-twse-ixbrl/{ticker}_twse_facts.json`。
  **multi-hit → fail-loud**(列出所有命中,exit 非 0;不學 derive 的 silent hits[0])。
- **in-memory 攤平**:tw loader 讀 `{T}_twse_facts.json` → `emit_canonical_facts()` →
  long-format rows 走既有 `_rec` 路徑。持久化的 `_canonical.json` 是他用產物,compose 不讀。
- **⚠️ source tag = `gaap_facts`(precedence 0)**:resolve 的 source 優先序
  gaap_facts=0 < derive_base=1;台股 as-reported 列必須佔 precedence 0,否則同 cell 會輸給
  derive 列(其 capex 翻正)→ 污染 as-reported。
- **⚠️ 台股三表排除 derive_base 來源**(整個不載入):台股 CF 無 `__q` 揭露單季、Q4 IS 無
  揭露單季 → 若拿 derive_base 補,會滲入翻號 capex 與重建值,違反顯示層 as-reported 鐵律。
  **接受留白**:Q2/Q3/Q4 的 CF 單季欄與 Q4 的 IS 單季欄顯示 `—`(這是忠實揭露的代價;
  之後若要顯示重建值,另開輪帶「derived」標記設計)。analytics(RATIO)照常載入
  (margins/growth 等本來就以 derive 口徑呈現,與三表 as-reported 分區)。
- tw 的 nongaap/supplement:不探索。輸出路徑:glob 命中的中文名資料夾
  `03_Working/Topics/Trackers/Financials.md`,**mkdir parents**(目錄可能不存在)。

### 3.2 幣別/scale 資料驅動(解 c;Argue 修訂:限 money 列 + templating)

顯示單位 = 申報單位,formatter 由 record `unit` 查表:

| unit | 數值 | 符號 | 標題/ylabel 尾綴 |
|---|---|---|---|
| USD_millions | `{v:,.0f}` | $ | `$M` |
| USD_thousands | `{v:,.0f}` | $ | `$K` |
| TWD_thousands | `{v:,.0f}` | NT$ | `NT$ 仟元` |
| USD_per_share | `${v:.2f}` | $ | — |
| TWD_per_share | `NT${v:.2f}` | NT$ | — |
| Pure | 既有 pct/x 不動 | — | — |

- **multi-unit fail-loud 只掃 `fmt=='m'` 金額列、只限三表區塊**(IS 區塊內 EPS 列是
  per-share unit,屬正常混合,不得觸發;已驗 AAOI derive_base IS/CF unit 與 gaap 一致,
  真實 money-scale 混合不存在,guard 是保險)。derived 區塊尾綴取第一個 resolve 到的
  money row unit。
- **標題/ylabel 是寫死字串,需 templating**:CONTRACT title 改模板(如
  `季度損益表 Income Statement（{regime}，{unit_suffix}）`)由 renderer 代入;
  `charts.py` ylabel 改參數(拿掉寫死 `$M`)。
- 制度 token:美股 `GAAP`、台股 `IFRS`;record `version` 仍為內部 enum `GAAP`
  (gaap loader 本就 hardcode,`emit_canonical_facts` 不帶 version 亦可——由 tw loader
  `_rec` 時statement source 補),與顯示 label 解耦。
- 附帶修正:AAOI(USD_thousands filer)標題 `$M→$K`(修 bug,數值不變)。

### 3.3 CONTRACT(解 d+e;Argue 修訂)

- IS/BS/CF 沿用同一套 canonical 列(對齊前端 constants.ts)。
- **FCF 修正(最小版)**:`("RATIO","fcf")` → `("RATIO","free_cash_flow")`——騎在
  loaders 強制 RATIO 的現行為上,1 個美股預期 diff,gate 安全。native-statement 版
  (`("CF","free_cash_flow")`)defer(§1 Non-goals)。
- **台股條件列**(`markets=("tw",)` 標記 + `render_if_present`,僅有值才渲染)。完整
  NCI 家族 + 台股專有權益,精確錨點(對 contract.py 現有行號):
  - `legal_reserve`(法定盈餘公積)→ 錨在 BS 權益區 `retained_earnings`(contract.py:68)之前
  - `net_income_nci`(歸屬非控制權益淨利)→ 錨在 IS `net_income_total_pre_nci`(:30)之後、
    `net_income`(:32,歸屬母公司)之前 —— 順序 = 稅後淨利(含NCI)→ NCI 分配 → 母公司分配
  - `minority_interest_bs`(非控制權益, BS)→ 錨在 `total_equity`(:71,母公司口徑)之後、
    `total_equity_incl_nci` 之前
  - `total_equity_incl_nci`(權益總計含NCI)→ 錨在 `minority_interest_bs` 之後(即權益區最末)
  - **既有無條件列不動**:`net_income_total_pre_nci`(:30)、`net_income`(:32)已是美股
    無條件 IS 列;台股 cr 自然填值、ir 顯 `—`,不新增、不改。
  - oci 分項:**deferred**(等 2308/3081 顯示需求確認再加,避免臆測列)
  - **為何 NCI 家族設 `markets=("tw",)` 而非兩市場條件列**:美股也有 NCI 發行商(如 INTC
    有 `net_income_nci`),若設兩市場條件列,INTC 頁會**新增一列** → 破壞美股「僅 3 個預期
    diff」gate。本輪守 gate,故 NCI 條件列**限台股**;美股 NCI 列的補齊登記 backlog(§6)。
  - 「條件列隱藏」vs「⏳ placeholder」的紀律區分:**⏳ = 管道應產而未產**(催 derive 的
    to-do 契約);**條件列 = 該市場制度性不存在的科目**(非 to-do)→ 隱藏合理,spec 明文。
  - **frontend-parity delta**(§3.5 追蹤):此 4 條台股條件列(`legal_reserve`、
    `net_income_nci`、`minority_interest_bs`、`total_equity_incl_nci`)是 compose 先行、
    前端 constants.ts 尚未有 → 明確 tracked delta,§4 有 snapshot 測試鎖住。
- **區塊過濾**:`requires_source` 只掛 `margins-nongaap`(requires nongaap)。
  **bs-structure 不掛**(Argue 證據:cli.py:72-86 只讀 BS facts,台股填得滿——v2 誤設)。
  來源不存在 → 整段不渲染(不產 AUTO marker)。
- **正確的台股覆蓋陳述**(修 v2 錯誤宣稱):台股 analytics 缺 `bvps`(無股數)與
  `debt_to_equity`(聯亞無借款;台達電待驗)→ 該列 ⏳;backlog 死 key 列(§1)台美同樣 ⏳。

### 3.4 渲染管線(解 f;Argue 修訂)

- **過濾 pre-pass 先行**:markets / render_if_present / requires_source 過濾在
  `_maybe_chart` 之前、`order`/`known_keys` 構建之前完成——否則被過濾區塊仍會畫圖
  (stale assets)且 marker 永不清。
- **`known_keys` = 本次實際渲染的區塊集合**(不是全 CONTRACT)→ 被過濾區塊的舊
  AUTO block 會被 prune,幕等成立。

### 3.5 SSOT / sync

canonical = `~/CC_Switch_Config/skills/compose-financials/`,sync 4 mirrors;SKILL.md v2
條目(台股、`--market`、unit 驅動、區塊過濾、**frontend parity delta**:台股條件列為
compose 先行、constants.ts 未同步——記為 tracked temporary delta,網頁 viewer 輪補齊)。

## 4. 驗證

| Gate | 內容 |
|---|---|
| 美股回歸 | INTC/MU/LITE/SNDK Financials.md byte-diff,允許 diff 僅:frontmatter 日期、FCF 列 ⏳→值;AAOI 另 +`$M→$K`。PNG 不入 byte gate(驗 md 引用路徑 + 檔案存在) |
| 台股 smoke | 聯亞端到端:三表數字對 twse_facts.json(**capex 負**)、**無任何 derive_base 值滲入**(Q2-Q4 CF 留白)、無 Non-GAAP 區塊、bs-structure **有**渲染、NT$ 仟元標籤、IFRS token;台達電(cr)驗 total_equity_incl_nci 條件列 |
| 幕等 | 手寫 Observations 重跑保留;**被過濾區塊的舊 AUTO block 會被 prune**(先渲染全區塊再切 tw 模擬) |
| 單元測試 | tw loader(source=gaap_facts、排除 derive_base、負 capex)、稀疏單季欄如預期、unit formatter 6 種 + **EPS 不觸發 money fail-loud**、contract key↔emitter 對照 sweep(鎖住 §1 backlog 死 key 清單,防新增)、known_keys=rendered set prune、glob multi-hit fail-loud、title templating、美股 contract 缺省不變 |
| **conditional-row / frontend-parity snapshot** | (1)**條件列渲染**:餵 cr fixture(含 net_income_nci / minority_interest_bs / total_equity_incl_nci / legal_reserve 有值)→ 4 列都出現且錨點順序正確;餵 ir fixture(無這些值)→ 4 列都**不出現**(不留 `—`、不留空 marker)。(2)**parity delta 鎖**:斷言 `{compose TW 條件列 uni_account}` − `{constants.ts IS_ROWS∪BS_ROWS keys}` == 固定集合 `{legal_reserve, net_income_nci, minority_interest_bs, total_equity_incl_nci}`。任一方漂移(前端補了、或 compose 新增條件列未登記)→ 測試紅,強制同步/更新 delta。 |

## 5. 風險

| 風險 | 緩解 |
|---|---|
| formatter 動到美股數字 | 數值路徑不動只動標籤;byte gate 3-diff 預算 |
| derive_base 滲入台股三表 | tw loader 結構性不載入 + 單元測試 + smoke 斷言 |
| CONTRACT 旗標破壞既有 | opt-in 缺省=現行;單元測試鎖 |
| 過濾/prune 改動影響美股頁 | 美股來源齊全 → 過濾 no-op;byte gate 兜底 |
| 4 mirror 漂移 | 只改 canonical + sync,commit 驗 byte-identical |

## 6. Backlog(本輪明確不做,Argue 登記)

1. 死 key 修復輪:`fcf_margin→fcf_margin_pct`、`nonoperating_income_expense_net`、
   `net_working_capital`、`capex_ratio`、`cfo_to_net_income`(需逐一決定 emitter 補 or
   contract 改名;每項都是美股 diff,需自己的 gate 預算)
2. analytics native-statement 化(`("CF","free_cash_flow")` + 解除強制 RATIO)
3. 台股三表重建值顯示(帶 derived 標記的設計;現版留白)
4. 前端 constants.ts 台股條件列同步(網頁 viewer 輪)——含把 NCI 家族條件列從
   `markets=("tw",)` 升級為兩市場(屆時 INTC 等美股 NCI 發行商會新增列,需自己的 gate)
5. oci 分項條件列(待顯示需求)
6. 美股 NCI 列補齊(`net_income_nci` / `minority_interest_bs` 兩市場化)——本輪限台股以守
   3-diff gate,美股 NCI 發行商(INTC)的這兩列延後(與 backlog 4 同輪)

## 7. 實作順序(給 writing-plans)

1. unit formatter + title/ylabel templating(TDD;含 AAOI $K、IFRS token)→ 美股回歸 gate
2. FCF key 最小修 + contract key↔emitter sweep 測試(鎖 backlog 清單)
3. CONTRACT 旗標(markets/render_if_present/requires_source)+ **過濾 pre-pass +
   known_keys=rendered**(TDD)
4. tw 來源探索(multi-hit fail-loud)+ in-memory 攤平 loader(source=gaap_facts、
   排除 derive_base)+ `--market` CLI + mkdir parents(TDD)
5. 聯亞 + 台達電 端到端 smoke + 幕等(含 prune)驗證
6. SKILL.md v2(含 frontend parity delta 註記)+ sync mirrors + commit
