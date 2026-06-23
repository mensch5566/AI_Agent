# parse-twse-ixbrl rewrite — 台股 iXBRL 財務數據管道（設計稿）

**日期**：2026-06-21
**狀態**：設計稿（待 Argue 5 輪收斂 + user review）
**範圍**：打掉重來 `parse-twse-ixbrl`（名字沿用、內容全換）。台股 iXBRL → 本地 JSON → derive → upsert(`twse_financial_*`) → 前端獨立面板。
**測試標的**：聯亞 3081（2019Q1+，小型光電）+ 台達電 2308（2021Q1+，大型電源）。

---

## 1. 背景與範圍

台股無公開 XBRL API（不像美股 SEC companyfacts）；使用者手動從 MOPS 下載 iXBRL `.html` 到本地 `Khouse/Semiconductors/{TICKER}/01_Source/MOPS Filings/XML/`。

**只做 iXBRL `.html` 單一格式**：
- 聯亞 3081：保留 2019Q1→最新（iXBRL `.html`，29 期）；**捨棄 2014–2018 的 18 個純 `.xml`**（舊 fr0/ifrs-2010 taxonomy + 元/千元雙單位，複雜度高、價值低）。
- 台達電 2308：2021Q1→最新（21 期，本來就全是 iXBRL `.html`，無舊格式）。

檔名格式差異（`ci-ir` 聯亞 vs `ci-cr` 台達電）= 報表子類碼不同，**parser 不依賴此碼**，直接讀 XBRL 概念。

### 三表概念分佈（iXBRL `name=` 屬性）
| 表 | 命名空間 | 範例概念 |
|---|---|---|
| 損益表 IS | `ifrs-full:*` | Revenue / GrossProfit / ProfitLossFromOperatingActivities / ProfitLossBeforeTax / ProfitLoss |
| 資產負債 BS | `tifrs-bsci-ci:*`（台灣特有）+ `ifrs-full:Assets/Liabilities/Equity` | Assets / Liabilities / Equity / 各流動科目 |
| 現金流 CF | `ifrs-full:CashFlows*`（營業）+ `tifrs-SCF:*`（投資/籌資） | CashFlowsFromUsedInOperatingActivities / tifrs-SCF:NetCashFlowsFromUsedInInvestingActivities |
| 附註/其他 | `tifrs-notes:*` / `tifrs-es:*` / `tifrs-ar:*` | 不進三表（除非升核心） |

單位：iso4217:TWD。**TWD 貨幣 fact 的 iXBRL 屬性為 `unitRef=TWD` `scale="3"` `decimals="-3"`（已 Argue 樣本驗證，非 scale=0）。** 顯示值即千元；parser 依 iXBRL 語意處理 scale/decimals/sign，canonical 存 `TWD_thousands`（確認 scale=3 後存顯示千元，不要乘成 base 元）。EPS / Shares / Pure / metadata 走各自 unit-class；statement-eligible TWD fact 若 scale/unit 異常要 fail loud。

**report_category（個別 vs 合併）— Argue 樣本驗證 + user 釐清**：TWSE iXBRL 在兩層標示報表類別：(1) 檔名中段碼 `-ir-`=個體(individual) / `-cr-`=合併(consolidated)；(2) 檔內 `tifrs-notes:ReportCategory` = "Individual report" / "Consolidated report"。**有子公司的公司同時申報合併+個體兩份,投資分析用合併;無子公司的公司只申報個體,其個體即總表。**
- **聯亞 3081 = 個體(`ir`)**:user 確認**聯亞無子公司 → 個體即總表,正確且完整,維持不動**(非「下錯版本」)。個體報表結構上無 NCI。
- **台達電 2308 = 合併(`cr`)**:有子公司,合併為準,正確。
- **onboard 規則(per period,非 per ticker)**:逐期挑檔 —— **某期若同時有 `-cr-`(合併)與 `-ir-`(個體)→ 優先 `cr`;只有 `ir` → 用 `ir`**。
- `report_category` 為 first-class 欄位(**per filing/period**)；機制目的 = 防「有合併卻誤用個體」與「個體/合併混入同一未標記序列」。NCI 概念只在合併出現。

**⚠ 時間序列基準轉換（temporal report_category transition）— user 前瞻需求**：
report_category 是 per-period 屬性,所以同一 ticker 的序列**可中途切換基準**（個體→合併:公司新增子公司開始申報合併；或合併→個體:divest 所有子公司）。設計天然吸收,不需改 code：
- **逐期檔案選擇**自動處理:轉換點起該期出現 `-cr-` 檔 → parser 自動改用合併;之前期維持個體。反向對稱。
- **basis-transition marker**:偵測序列中 report_category 改變的期,標記「基準變更點」並寫進 metadata。合併納入子公司 → 營收/資產**不連續**、NCI 開始出現。
- **下游紀律**:derive YoY / 前端 trend **不得盲算跨基準變更點的 YoY/環比**;需標註斷點（或在該轉換期的 YoY 標 not-comparable）。
- **footing / NCI per-period driven**:合併期自動套 NCI(A=L+Equity 已含、owners-NCI 拆分);個體期無 NCI。標籤驅動,切換零改 code。
- **聯亞現況**:全期個體(無子公司)。此機制是為「將來某期變合併」預留,**現在不觸發**。

---

## 2. 已定案決策（user 拍板）

1. **儲存層**：另開 `twse_financial_*` 新表，與美股 `sec_financial_*` 完全分離（cik/us-gaap/audit-cell 那套不污染台股；upsert/API 另寫一份但大量參考美股）。
2. **uni_account 詞彙**：**核心鍵重用**（revenue / gross_profit / operating_income / income_before_taxes / net_income / total_assets / total_liabilities / total_equity / CFO 等經濟意義相同的行沿用美股核心 key）；**台股特有 → TW long-tail bucket**。
3. **Pipeline 範圍（2026-06-23 修訂）**：**parse（純抽取、零運算）→ NLM cross-check（tolerance=0 雙源驗證）→ twse-derive（fork：單季還原 + 比率）+ 自洽 footing 驗證**。
   - **parse 不能有任何運算**（比照美股鐵律）：單季還原、比率、Q4 EPS **全部移出 parse**，只輸出 iXBRL 直接揭露的值（YTD 累計 first-class）。
   - **加 NLM cross-check**（user 決定）：比照美股 `parse-sec-cross-check`，把 parse 抽出的值跟 NotebookLM 讀 PDF 的值做 tolerance=0 比對，產 audit。雖然 iXBRL 即官方，但 user 要雙源收斂為正確答案（一貫原則）。
   - footing 仍為唯讀驗證閘（不寫值）。
4. **前端：延後（user 決定 SSOT data 先做完）**。最終形態仍為獨立 route + 重用 financials-v2 資料驅動表格渲染引擎 + 新 `TW_ROWS`；但**本輪先把 parse → cross-check → derive → upsert(twse_financial_*) 的 SSOT 資料層做完**，前端之後再接。
5. **derive = fork**：複製規則邏輯成 `twse-derive`（讀 TW JSON、輸出 `twse_financial_metrics`），**不動已 production 的美股 derive 引擎**（隔離 > DRY，符合「大改動前不改壞原本」）。

---

## 3. 鐵律（專案層級，沿用美股紀律）

- **parse 永不運算**：parse（①–④）只輸出 iXBRL 直接揭露的 YTD 累計值（source-of-truth），**不做任何相加減**。單季還原（Q2=H1−Q1…）一律在 ⑥twse-derive。
- **footing_check（⑤）只驗證、不寫值**：A=L+權益、GP−營業費用=OI、CFO+CFI+CFF=Δcash 等是**唯讀斷言閘**（類比美股 cal_sum_sanity），**絕不把任何 derived 值寫回 parse 輸出 JSON**。
- **值不丟 LLM**：concept→uni_account 是確定性對照表；LLM 只在「未對到的台灣特有科目」判 section→bucket（同美股 long-tail cascade）。
- **canonical = SSOT**：skill 寫在 `~/CC_Switch_Config/skills/parse-twse-ixbrl/`，改完 `bash scripts/sync-to-local.sh`。
- **production 寫入需授權**：upsert 預設 dry-run + gate；`--apply` 需 user 明確授權，先看 diff、不縮 production。

---

## 4. 架構（7 個隔離模組）

```
01_Source/MOPS Filings/XML/{TICKER}-{YYYY}Q{N}.html (iXBRL)
   │
 ① ixbrl_extract.py     讀 ix:nonFraction → (concept, raw_value, sign, scale, contextRef, unitRef, decimals)
   │                     解析 <xbrli:context>：period(instant/duration start-end)、entity、dimension member
   │                     輸出原始 fact 清單（含每 fact 的 context 解析結果）
 ② concept_map.py       concept(prefix:name) → uni_account
   │                     - 核心對照表（CONCEPT_TO_UNI）：IS/BS/CF 三表
   │                     - 維度過濾：只取 consolidated 無維度成員的「面額」fact（排除 segment/member 拆分）
   │                     - 未對到 → 標 unmapped（交 LLM cascade 判 section→TW long-tail bucket）
 ③ normalize.py         - 單位統一 TWD_thousands（scale-aware；每 row 帶 unit，不 hardcode）
   │                     - 期別判定：context duration 對應 period（YTD 累計）→ period_kind
   │                     - 揀「當期欄」：同 concept 多 context 時取本期，排除比較期/前期
   │                     - 符號正規化（XBRL weight vs 顯示符號）
 ④ build_twse_facts.py  輸出 {TICKER}_twse_facts.json
   │                     row schema 對齊美股 facts：{period, period_end, period_kind, statement,
   │                     uni_account, source_account, value, weight, unit, long_tail_metadata?}
   │                     + metadata（ticker, company, exchange=TWSE, currency=TWD, periods, units）
 ⑤ footing_check.py     自洽驗證（唯讀，0 容差）：BS A=L+Equity(total,已含NCI)、IS GP−OperatingExpense=OI /
   │                     OI+營業外=稅前 / 稅前−稅=稅後、CF CFO+CFI+CFF+FX=Δcash。產 report；有 ❌ exit≠0、不出殘缺 JSON。
 ⑥ twse_cross_check     NLM(NotebookLM 讀 PDF) vs parse facts，tolerance=0 → audit md。比照美股
   │  (NEW, user 決定)   parse-sec-cross-check：unmapped label cascade、sign-flip 容許、人工 audit 回寫。
 ⑦ twse-derive (fork)   讀 facts.json（+ 已 audit 修正）→ 單季還原（Q2=H1−Q1 / Q3=9M−H1 / Q4=FY−9M，
   │                     同 concept+unit guard）+ ratios。**Q4 EPS / WASO 不反推留空**（加權股數非加性）。
   │                     輸出 {TICKER}_twse_metrics.json（對齊 twse_financial_metrics）。
 ⑧ upsert_twse.py       讀 facts + metrics → 寫 twse_financial_* 表。dry-run gate（coverage/footing）；
        │                 --apply 需授權。
   ⏸ 前端 /financials-tw 延後（SSOT data 先）。
        ▼
   前端 /financials-tw/[ticker]：新 API route 讀 twse_financial_* → 重用 financials-v2 表格 renderer + TW_ROWS
```

### 模組契約（各自獨立、可單測）
| 模組 | 輸入 | 輸出 | 依賴 |
|---|---|---|---|
| ① ixbrl_extract | iXBRL `.html` 路徑 | raw facts（concept/value/context dict）| lxml |
| ② concept_map | raw facts | (mapped facts, unmapped list) | CONCEPT_TO_UNI 表 |
| ③ normalize | mapped facts | normalized facts（千元、period、單期欄）| — |
| ④ build_twse_facts | normalized facts + unmapped(經 LLM 分類) | `{T}_twse_facts.json` | — |
| ⑤ footing_check | facts.json | report + exit code | — |
| ⑥ twse-derive | facts.json | `{T}_twse_metrics.json` | 共用 ratio 規則模組 |
| ⑦ upsert_twse | facts + metrics | twse_financial_* rows | supabase client |

---

## 5. concept → uni_account 對照（核心鍵重用）

確定性對照表 `CONCEPT_TO_UNI`（first-match，類比美股 IS_TAG_MAP）。範例（非完整，spec 後補全清單）：

| uni_account（核心，重用美股）| TW concept |
|---|---|
| revenue | ifrs-full:Revenue（候選清單防 RevenueFromSaleOfGoods 同期撞，ordered + fail-closed dedup）|
| cost_of_goods_sold | **tifrs-bsci-ci:OperatingCosts**（Argue 驗證:ifrs-full:CostOfSales 兩樣本皆缺;Delta Rev−OperatingCosts=GrossProfit 精準）。ifrs-full:CostOfSales 列 fallback |
| gross_profit | ifrs-full:GrossProfit（候選防 tifrs-bsci-ci:GrossProfitLossFromOperations 同期撞）|
| research_and_development | ifrs-full:ResearchAndDevelopmentExpense |
| **total_operating_expenses** | **ifrs-full:OperatingExpense**（揭露的營業費用總額 = 推銷+管理+研發+ECL；Argue 驗證 Delta=30,543,568）。footing GP−OperatingExpense=OI **用此揭露總額**,絕不 re-sum 子項 |
| operating_income | ifrs-full:ProfitLossFromOperatingActivities |
| income_before_taxes | ifrs-full:ProfitLossBeforeTax |
| income_tax_expense | ifrs-full:IncomeTaxExpenseContinuingOperations |
| net_income_total_pre_nci | ifrs-full:ProfitLoss |
| net_income | ifrs-full:ProfitLossAttributableToOwnersOfParent |
| net_income_nci | ifrs-full:ProfitLossAttributableToNoncontrollingInterests（**僅合併報表有**）|
| total_assets | ifrs-full:Assets |
| total_liabilities | ifrs-full:Liabilities |
| total_equity | ifrs-full:Equity（**已含 NCI**）|
| (CFO) | ifrs-full:CashFlowsFromUsedInOperatingActivities |
| (CFI) | tifrs-SCF:NetCashFlowsFromUsedInInvestingActivities |
| (CFF) | **tifrs-SCF:CashFlowsFromUsedInFinancingActivities**（Argue 修正:非 NetCashFlows...Financing）|

**推銷/管理/研發 → 各自存 source row + `operating_expense_long_tail`(含 Delta 的 IFRS9/ECL 減損行)。`selling_general_administrative` 的 sum 是 derive → 由 display 層算,parser 絕不寫此 sum 進 facts**(Argue 修正:summing 屬 derive)。

**台股特有 → TW long-tail bucket**（如營業外收支細項、特定台灣揭露行）：uni_account = `{section}_long_tail`，帶 `long_tail_metadata{rolls_up_to, is_recurring, last_occurrence_date}` + weight。未認得科目由 LLM 判 section 配 bucket（不自由創造核心 key）。

---

## 6. 台股特有處理（已納入美股教訓）

| 議題 | 處理 | 對應美股坑 |
|---|---|---|
| 費用結構（推銷/管理/研發分開）| 推銷+管理 sum → 核心 SG&A；子值入 operating_expense_long_tail；研發 → 核心 R&D | 美股 SG&A 子科目合併處理 |
| 單位 | 每 row `unit=TWD_thousands`，前端讀 row unit | 美股 hardcode scale 丟精度 |
| YTD 累計 | parse 只出 H1/9M/FY 累計（first-class）；單季 derive 還原 | 美股 YTD first-class |
| Q4 EPS / WASO | **不反推、留空**（加權股數非加性，空白=預期非 bug）| 美股 Q4 EPS 不反推（AAOI 實證）|
| 歸屬母公司 vs NCI | **僅合併報表**:net_income=歸屬母公司(post-NCI)、net_income_total_pre_nci=ProfitLoss、net_income_nci 分開。**BS footing = A = L + Equity(total),Equity 已含 NCI,不另加 NCI 項**(Argue 修正:+NCI 會雙計;Delta A=L+Equity 精準 foot)。NCI row / owners-NCI 拆分 conditional on report_category=Consolidated（個別報表如聯亞無 NCI）| 美股是 +NCI(minority_interest_bs);**台股相反,Equity 已含** |
| 維度拆分 fact | concept_map 只取無維度成員的合併面額 fact，排除 segment/member | 美股 companyfacts 已 collapse(台股要主動濾)|
| OpEx 加總 | 以面額 OI 為準；footing 驗 GP−費用=OI，不用元件硬湊 | 美股 GAAP OpEx ≠ GP−OI |
| is_long_tail 前端 | TW panel 從頭把 TW long-tail bucket 註冊進 TW_ROWS row config | 美股 is_long_tail 無對應 key 被丟/雙顯 |

---

## 7. 儲存：`twse_financial_*` 表

平行美股 schema（精簡）：
- `twse_financial_companies`：ticker(代號)、company_name、exchange=TWSE、currency=TWD、fiscal_year_end_month（台股=12）。**無 cik**。
- `twse_financial_facts`：三表 long-format（period/period_kind/statement/uni_account/source_account/value/weight/unit/display_label/ordinal）。
- `twse_financial_metrics`：derive 輸出（單季 + ratios，statement 含 RATIO）。
- （維度/edges 表視需要，MVP 可先不做 segment 維度）。

upsert gate（dry-run）：coverage（display-eligible 有 ordinal）+ footing pass。

---

## 8. 前端：獨立 route + 重用渲染引擎

- 新 route `app/financials-tw/[ticker]/`（暫名）+ 新 API `app/api/financials-tw/`（讀 twse_financial_*）。
- **重用** financials-v2 的資料驅動表格 renderer（認 uni_account+display_label+ordinal）。
- **新寫** `TW_ROWS`（台股 IS/BS/CF row 配置，含 TW long-tail bucket 註冊位置）。
- 不加美股 viewer 的 market 切換（避免耦合污染已 production 美股）。

---

## 9. 測試策略（TDD，雙 ticker）

- 單測：① context 解析（instant/duration/比較期）、② concept_map（核心命中 + 未對到 → unmapped）、③ normalize（單位千元、單期欄揀選、符號）、⑤ footing 斷言、⑥ derive 單季 telescoping + Q4 EPS 留空。
- e2e：聯亞 3081（2019Q1+）+ 台達電 2308（2021Q1+）全期跑通；footing 0 ❌；抽查值對得上已知（如台達電年營收量級）。
- 兩 ticker 科目差異大（小型光電 vs 大型電源）→ 用來 harden concept_map 與 long-tail 分類。

---

## 10. 範圍外 / 未來

- segment / 維度揭露（台股 supplement）：MVP 不做，未來另議。
- pre-iXBRL 純 `.xml`（2014–2018）：不做。
- NLM cross-check：不做（iXBRL 即官方）。
- 自動下載 MOPS：不做（user 手動下載）。

---

## 11. 待 Argue 收斂的開放點（給 5 輪 architect↔skeptic）

1. concept_map 維度過濾：如何穩健只取「合併面額」fact（context 無 explicitMember）而不漏掉合法行?
2. 「揀當期欄」規則：iXBRL 一份檔含本期 + 去年同期 + 期初餘額多個 context，如何 deterministic 選對 period 對應的 fact（尤其 BS instant 的期末 vs 期初）?
3. footing 容差：台股是否有 rounding 導致需要 ±1 千元容差，還是嚴格 0?
4. derive fork 與美股 ratio 規則的共用程度：抽共用 pure-function ratio 模組（兩邊 import）是否比完全複製更安全?
5. TW long-tail bucket 集合是否直接重用美股 12 bucket，還是台股需要不同 section 切分?

---

## 12. Argue 收斂結論（2026-06-21，status=consensus，score 91.93，7 輪，18/18 claims，0 rejected）

architect(Claude/opus) ↔ skeptic(Codex/GPT-5.5),兩 agent ground 在實際 3081+2308 2026Q1 樣本。以下為 **binding 修訂**(已驗證)，覆蓋上文任何衝突處。Transcript：`~/.config/argue/twse-parser.{result.json,summary.md,jsonl}`。

### A. 解析層（必改）
1. **raw-bytes + namespace-aware XML 解析**：把 iXBRL `.html` 當 raw bytes 用 namespace-aware XML parser 讀，保留 camelCase inline-XBRL 屬性（`contextRef` `unitRef` `scale` `decimals` `sign`）。不可用一般 HTML lower-casing parser（會吃掉駝峰屬性）。
2. **scale=3 / decimals=-3**（非 scale=0）。見 §1 修訂。
3. **face filter = 解析後 context 無 `xbrldi:explicitMember`** + 期別符合 + statement 概念 allowlist / table-role gate。**不可用 context-id 字串比對**。`tifrs-notes` / `tifrs-ar` / `tifrs-es` 的 fact **不進三表 map、也不進 LLM long-tail cascade**。
4. **deterministic 當期選擇**（grounded in 2026Q1 樣本）：
   - IS/CF flow → 無維度 duration `From20260101To20260331`
   - BS stock → 無維度 instant `AsOf20260331`
   - **排除報告日 instants**（如 `AsOf20260422` / `AsOf20260429`，即使日期較晚）→ 不可用 global-latest-date。
   - 期別由 filing period 推導（非猜最新）。
5. **duplicate policy（強制）**：完全相同 fact → suppress；衝突 fact → **fail-closed**。跨概念同-uni 撞期（3081 有 `Revenue` vs `RevenueFromSaleOfGoods`、`GrossProfit` vs `tifrs-bsci-ci:GrossProfitLossFromOperations`）→ **per-uni ordered 候選清單 + 同期 fail-closed dedup**。

### B. 概念對照（必改，見 §5 修訂）
- COGS → `tifrs-bsci-ci:OperatingCosts`（CostOfSales fallback）；新增 `total_operating_expenses` → `ifrs-full:OperatingExpense`；CFF → `tifrs-SCF:CashFlowsFromUsedInFinancingActivities`。
- SG&A 子項各存 source/long-tail（含 Delta IFRS9/ECL 行,不可丟）；**SG&A sum 不寫進 parse**。
- EPS：`ifrs-full:BasicEarningsLossPerShare` + diluted 直接取；**2308 的 continuing-operations EPS 變體不可重複寫進 plain EPS 核心 row**。Q4 EPS/WASO 不反推（正確）。

### C. footing 驗證（validation-only，見 §3/§6）
- 預設 **strict 0**（在 ix @sign 正規化、ordered 概念選擇、dedup、正確 identity 項之後）；**±1 TWD_thousands 僅作 logged soft-warn / override，不得 silent 接受**。
- BS：`Assets = Liabilities + Equity(total)`（**不加 NCI**）。
- CF：`signed CFO + CFI + CFF + FX_effect = signed Δcash`，且 `SCF cash_begin + net_change = SCF cash_end`，用 `tifrs-SCF:CashAndCashEquivalentsAtBeginningOfPeriod` / `...AtEndOfPeriod`（**不可 global-instant 推 begin cash**）。
- footing 仍 **唯讀**,不寫 derived 值回 facts。

### D. report_category first-class（見 §1）
per-filing 標記 Individual / Consolidated；兩者不混；合併優先。NCI/owners 拆分 conditional on Consolidated。

### E. derive / bucket（tradeoff，採納）
- twse-derive MVP 維持隔離(fork)；ratio 若要共用只抽 **state-free pure function** 且兩邊(SEC+TW)都有測試覆蓋才共用。
- **不可預設 12 bucket 足夠**:先做 unmapped-concept inventory(scope 限 `ifrs-full`/`tifrs-bsci-ci`/`tifrs-SCF` 的 face context;排除 notes/ar/es)再定 TW bucket 集合。

### 已釐清（Argue 浮出 → user 確認）
- **聯亞 3081 = 個體報表**:user 確認**聯亞無子公司,個體即總表,維持不動**。onboard 規則:有子公司用合併(`cr`)、無子公司用個體(`ir`)。`report_category` 照標。

---

## 13. 實作起點與重構需求（2026-06-23，隔壁已建初版 + user 決策）

隔壁 session 已在 `~/CC_Switch_Config/skills/parse-twse-ixbrl/` 建：`fetch_ixbrl.py`（MOPS 下載，archive-first）、`parse_ixbrl.py`（**parse+derive 合一**，32KB，含 XBRL_MAP）、`run.sh`、`skill.md`。**獨立收斂到多數 Argue 結論**（COGS=tifrs-bsci-ci:OperatingCosts、OperatingExpense 核心、CFF concept、EPS continuing 變體去重、context 點/期間 + 略過維度 member、值不丟 LLM、ir/cr、缺檔降級不寫假單季）。

**user 決策（2026-06-23）→ 需重構：**
1. **parse 必須純抽取、零運算**（比照美股鐵律）：把 `parse_ixbrl.py` 內的**單季還原、比率、`_derive_q4_eps_from_annual`** 全部移出。parse 只輸出 iXBRL 直接揭露的值（含 YTD 累計 first-class、年報 FY direct）。
2. **derive 拆成獨立 `twse-derive`**（fork）：單季還原 + ratios 搬到這裡；**Q4 EPS 改為留空**（不再 FY−9M 反推；加權股數非加性、AAOI 實證會錯）。
3. **新增 `twse_cross_check`**（NLM 雙源，比照 parse-sec-cross-check）。
4. **新增 `upsert_twse` + `twse_financial_*` 表**（SSOT 入庫）。
5. **前端延後**。
**可沿用**：`fetch_ixbrl.py`（下載）、`XBRL_MAP`（concept 對照，已對多數）、context 選擇邏輯、ir/cr 處理。

**待辦微調（Argue robustness）**：scale 改 fail-loud（目前直接取顯示值=千元，靠 scale 永遠=3，脆）；footing 確認用 total Equity（A=L+Equity，不另加 NCI）還是 parent+NCI（等價但需一致）。
