# compose-financials 台股支援(v2)— 設計 spec

日期:2026-07-03
狀態:v1 草稿(設計已口頭過;Fable 5 self-review 後定稿)
上游:derive-A 已完成(台股 derive 輸出與美股同 schema);`_shared/twse_canonical_facts.py`
已落地(commit `ccbde9d`)——台股三表 facts 可忠實攤成美股 long-format。
架構前提(使用者拍板):台美 **共用** Financials Viewer / 儲存層;compose 的 layout
(CONTRACT)須與前端 `financials-v2/constants.ts` 保持同一套 canonical 列。

## 1. 背景與目標

`compose-financials` 是**純渲染層**:讀本地 Skill_Output JSON → 產
`{TICKER}/03_Working/Topics/Trackers/Financials.md`(三表 + margins/growth/liquidity/
wc-cycle/returns 圖表區塊),AUTO-marker 幕等、不計算任何指標。v1 只支援美股。

### 目標(這一輪)
1. `--market tw`:台股 ticker(聯亞 3081、台達電 2308)能產出同結構 Financials.md
2. 幣別/scale **資料驅動**(使用者拍板:依 raw data 的 unit 顯示,仟元就仟元、百萬就百萬)
3. 三表 layout 台美共用 + 台股條件列;台股無來源的區塊整段省略
4. 美股輸出零回歸(唯一例外:§3.2 的 thousands-ticker 標籤修正,屬修 bug)

### Non-goals(下一輪)
- Supabase Phase E(共用表 + market/currency 欄 migration + upsert)
- 網頁 Financial Viewer 的台股渲染
- 台股 Non-GAAP / segment 來源(管道不存在,非 compose 職責)

## 2. 現況斷點(探索結論,file:line 見探索報告)

| # | 斷點 | 位置 |
|---|---|---|
| a | 來源路徑寫死 `01_Source/SEC Filings/Skill_Output` + `parse-10QK-gaap/{T}_gaap_facts.json` | `loaders.py:6,37` |
| b | 原始 facts reader 只吃 long-format `facts: [...]`;台股是 keyed-dict | `loaders.py:39` |
| c | 幣別/scale 寫死:`$M` 標題、`$` EPS 前綴、`m` fmt 不讀 unit、圖表 ylabel `$M` | `contract.py:18/36/75/114/149`、`sections.py:20,31`、`charts.py:56,64` |
| d | CONTRACT 是寫死美股列清單:台股獨有科目被靜默丟、Non-GAAP/segment 對台股全空 | `contract.py:14-156` |

derive-base / analytics loader **不用改**(derive-A 後 schema 相同)。

## 3. 設計

### 3.1 market-aware 來源探索(解 a+b)

- CLI 加 `--market {us,tw}`,default `us`(與 derive CLI 一致,fail-closed by choices)。
- `us`:現行路徑,一字不動。
- `tw`:base = glob `Khouse/Semiconductors/*/01_Source/MOPS Filings/Skill_Output/parse-twse-ixbrl/{ticker}_twse_facts.json`
  (`*` 對中文公司名資料夾;與 derive 的 `discover_sources_tw` 同 pattern)。
- **台股原始 facts 讀法:in-memory 攤平,不依賴持久化檔**。tw loader 讀
  `{T}_twse_facts.json` → 呼叫 `_shared.twse_canonical_facts.emit_canonical_facts()` →
  得到與美股同 shape 的 `facts: [...]` → 走既有 `_rec` 路徑。
  - Why in-memory:單一資料源(twse_facts.json),無「持久化 canonical 檔過期」問題。
  - 已持久化的 `{T}_twse_facts_canonical.json` 保留為**其他 ad-hoc consumer 的便利產物**
    (由 `twse_canonical_facts.py` CLI 產),compose 不讀它、也不負責更新它。
- as-reported 紀律:emit_canonical_facts 不翻 capex 符號、保留 beginning/ending_cash——
  顯示層忠實對 PDF(與 derive 的 adapter 刻意不同,該檔案 docstring 已載明)。
- tw 的 nongaap / supplement 來源:**不探索**(管道不存在),對應區塊整段省略(§3.3)。
- 輸出路徑:tw 寫 `Khouse/Semiconductors/{中文名}/03_Working/Topics/Trackers/Financials.md`
  (中文名資料夾 = glob 命中的那個 ticker 資料夾;相對結構與美股相同)。

### 3.2 幣別/scale 資料驅動(解 c)

原則(使用者拍板):**顯示單位 = 申報單位**,不轉換、不 hardcode。

- 每筆 record 已帶 `unit`(`USD_millions` / `USD_thousands` / `TWD_thousands` /
  `USD_per_share` / `TWD_per_share` / `Pure`)。formatter 由 unit 查表:

| unit | 數值 | 幣別符號 | 區塊標題 / 圖表 ylabel 尾綴 |
|---|---|---|---|
| USD_millions | `{v:,.0f}` | $ | `$M` |
| USD_thousands | `{v:,.0f}` | $ | `$K` |
| TWD_thousands | `{v:,.0f}` | NT$ | `NT$ 仟元` |
| USD_per_share | `${v:.2f}` | $ | — |
| TWD_per_share | `NT${v:.2f}` | NT$ | — |
| Pure | 既有 pct/x 邏輯不動 | — | — |

- 區塊標題的單位尾綴(如 `（GAAP，$M）`)改為 render 時由該區塊實際 resolve 到的
  money-unit 決定。**multi-unit fail-loud 只限三表區塊**(單一 filer 單一申報 scale 有保證);
  derived 區塊(margins/returns 等)混 pct 與 money 屬正常,其 money 尾綴取該區塊第一個
  resolve 到的 money row 的 unit(EBITDA/FCF 繼承 ticker scale,天然單一)。
- **標題的制度 token 也 market 驅動**:美股 `GAAP`、台股 `IFRS`(台股用 TIFRS,標 GAAP
  是錯的)。注意:record 的 `version` 欄位仍沿用 pipeline 內部 enum `GAAP`(意為
  「官方申報主值」vs `NON_GAAP`),與顯示制度 label 解耦——台股 loader 產 record 時
  `version="GAAP"`(ValueIndex 需要),顯示層才轉 IFRS 字樣。
- **附帶修正(美股)**:AAOI 等 thousands-ticker 現被硬標 `$M` → 修正為 `$K`。
  這是修 bug:數值本來就沒縮放,只有標籤錯。millions-ticker(INTC/MU/LITE/SNDK)輸出
  **byte 不變**(回歸驗證)。
- 圖表:`charts.py` 的 ylabel 由呼叫端傳入 unit 尾綴,拿掉寫死 `$M`。

### 3.3 CONTRACT:共用三表 + 台股條件列(解 d)

- IS/BS/CF 沿用**同一套** canonical 列(與前端 constants.ts 對齊,不 fork 台股變體)。
- **台股條件列**(僅 `market=tw` 且該 uni_account 有值時渲染;插在權益區既有列之後):
  `legal_reserve`(法定盈餘公積)、`total_equity_incl_nci` + `net_income_total_pre_nci`
  (cr 合併報表家族鍵;ir 無值自然不顯)、`oci_fx_translation` 等 oci 分項(OCI 小節)。
  實作:CONTRACT line 加可選 `markets` 標記(缺省 = 兩市場)+ `render_if_present` 旗標;
  renderer 據此過濾。美股行為不變(新增旗標對既有列缺省不生效)。
- **區塊級過濾**:CONTRACT section 加可選 `requires_source` 標記——`margins-nongaap`
  requires `nongaap`、`bs-structure`(segment)requires `supplement`。來源不存在 →
  **整段不渲染**(含 AUTO marker 都不產生),而非渲染一堆 `⏳`。美股不受影響(來源都在)。
- 台股拿到的區塊:三表 + margins-gaap + netsales-total + growth + liquidity + wc-cycle +
  returns(analytics 874 rows 全部填得滿,除 bvps 缺股數維持 `⏳`)。
- **附帶修正(美股既有 bug)**:CF 區塊的 Free Cash Flow 列 contract key 是
  `("RATIO","fcf")`,但 analytics 實際 emit 的 uni_account 是 `free_cash_flow` →
  此列在美股頁**一直渲染 `⏳`**(從未 resolve 過)。本輪改為 `("RATIO","free_cash_flow")`
  (analytics loader 把所有 analytics rows 強制標 statement=RATIO,故 RATIO 對)。
  此修正會讓美股 byte-diff gate 多一個**預期 diff**(FCF 列 ⏳→數值),與 AAOI `$K` 同列
  「修 bug 型預期 diff」。

### 3.4 SSOT / sync

- canonical = `~/CC_Switch_Config/skills/compose-financials/`,改完
  `bash scripts/sync-to-local.sh` → 4 mirror 同步;兩 repo commit(若涉 AI_Agent 端測試)。
- SKILL.md:v2 條目(台股支援、`--market`、unit 驅動、區塊過濾)、scope 表台股改 in-scope。

## 4. 驗證

| Gate | 內容 |
|---|---|
| 美股零回歸 | millions-ticker(INTC/MU/LITE/SNDK)改動前後 **Financials.md** byte-diff 相同,允許的預期 diff 僅:frontmatter `updated:` 日期、FCF 列 ⏳→數值(§3.3 bug 修);AAOI 另有 `$M→$K` 標籤 diff。**PNG 圖檔不入 byte gate**(matplotlib 輸出非 byte-stable),改驗 md 中的圖檔引用路徑不變 + 圖檔存在 |
| 台股 smoke | 聯亞 3081 端到端產出 Financials.md:三表數字抽查對 `twse_facts.json`(as-reported,capex 負)、無 Non-GAAP/segment 區塊、單位標籤 NT$ 仟元、EPS NT$;台達電 2308(cr)驗家族列顯示 |
| 幕等 | 聯亞頁手寫一段 Observations → 重跑 → 手寫內容原樣保留 |
| 單元測試 | tw loader(in-memory 攤平)、unit formatter 查表(6 種 unit)、multi-unit fail-loud、markets/render_if_present/requires_source 過濾、美股 contract 缺省不變 |

## 5. 風險

| 風險 | 緩解 |
|---|---|
| 改 formatter 動到美股數字 | 美股 byte-diff 零回歸 gate;fmt 數值路徑(`{v:,.0f}`)不動,只動符號/標籤 |
| CONTRACT 加旗標破壞既有渲染 | 旗標全部 opt-in、缺省行為 = 現行;單元測試鎖 |
| 台股中文資料夾 glob 撞多檔 | 同 derive:sorted 取第一 + 命中數 >1 時警告 |
| 4 mirror 漂移 | 只改 canonical + sync 腳本,commit 驗 byte-identical |

## 6. 實作順序(給 writing-plans)

1. unit formatter 查表 + 標題/ylabel 資料驅動(TDD;含 AAOI $K 修正)→ 美股回歸 gate
2. CONTRACT 旗標(markets / render_if_present / requires_source)+ renderer 過濾(TDD)
3. tw 來源探索 + in-memory 攤平 loader + `--market` CLI(TDD)
4. 聯亞 + 台達電 端到端 smoke + 幕等驗證
5. SKILL.md v2 + sync mirrors + commit 兩 repo
