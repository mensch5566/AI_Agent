# Design — parse-SEC-supplement Stage-B-always（雙源獨立直接抽取互相 cross-check 收斂）

Status: **v4 — MVP（period-anchor 確定性版）BUILDING；full 雙源值比對 = Phase 2**
Date: 2026-06-12（v4 — user 拍板先做 MVP；v3 full 設計保留於 §3–§4 當 Phase 2 藍圖）
Author: Claude
Scope: `parse-SEC-supplement` skill（canonical `~/CC_Switch_Config/skills/parse-SEC-supplement/`）

---

## §0 MVP 範圍（user 2026-06-12 拍板，本次 build）

dei_period_label() 已 ship、已修 SNDK 的原始 XBRL 期別 bug。MVP **不**做 full 雙源值比對（member 對帳 + scale 正規化 + per-cell value compare = 成本/假陽性主源，全部 defer Phase 2，見 §3–§4）。MVP 只做一件高槓桿、確定性、零 NLM 的事：

**period-anchor 驗證 pass —— 用獨立絕對日期錨偵測「期別標籤錯位（含整批均勻 shift）」，Tier-1 gate production。**

### §0.1 為什麼不用月份算術 / 不用 NLM
- **月份算術不行**：`derive_period_label()` 對 52/53-週 filer 自身會重現 SNDK bug（SNDK Q1 結束 2025-10-03，月份算術算成 Q2）。獨立 witness 用它 = 用錯誤驗錯誤。
- **NLM 不需要**：period 不是「值」，是 filer 在 submission header 與 instance dei 兩處的宣告。我們手上已有**兩個獨立、確定性、免費**的來源（EDGAR `reportDate` ⟂ instance `dei` focus）+ 跨 filing 序列。NLM 幻覺風險對 period anchor 沒有加分。NLM 的真正價值在 full 值比對（Phase 2）。

### §0.2 MVP 核心演算法：13 週錨點
- **FYE 錨**：每份 10-K 的 `reportDate` = 該財年真實末日（直接、繞過 fy_end config、52/53 精確）。額外備援：EDGAR submissions 的 company-level `fiscalYearEnd`（MMDD）。
- **每份 10-Q**：取最近一個 prior FYE 錨，`q = round((reportDate − anchor.reportDate).days / 91.25)`（13 週一季，round 容差吸收第 53 週 ±7d）。
  - `q ∈ {1,2,3}` → `expected = Q{q}_FY{anchor.fy + 1}`。
  - 比對 **resolved period label**（實際用的，dei 或 fallback 皆可）vs expected。
- **均勻 shift 也抓得到**：純內部序列一致性對「全部 +1 季」是盲的；10-K reportDate 提供**絕對**錨 → 均勻 shift 會讓每份 10-Q 對不上 expected → 全部 flag。

### §0.3 MVP 判級
| 情況 | 級別 | 動作 |
|---|---|---|
| `q∈{1,3}`、resolved label ≠ anchor-expected | **Tier-1 `period_label_anomaly`** | flag + **gate production upsert** |
| 10-K 的 FP 不是 FY | **Tier-1** | flag + gate |
| 無 prior FYE 錨（window 無 10-K）/ `q∉{1,3}`（疑缺 10-K） | Tier-2 `anchor_gap` advisory | 不阻塞，統計 |
| `dei_present=False`（走 fallback 路徑） | Tier-2 advisory | 不阻塞，提示該 filing 期別未經 dei 確認 |

### §0.4 MVP 輸出 / 鐵律合規
- `{T}_period_anchor_validation.json` + 報告：Tier-1 置頂（含 accession + reportDate + resolved vs expected）、Tier-2 advisory、summary（match rate）。
- production upsert path **gate 未解 Tier-1**。
- **零 derive**：只比對日期、數天數、round 出季序、字串相等。不算任何財務衍生值。✅ 鐵律合規。

### §0.5 MVP 不做（Phase 2，見 §3–§4 full 設計保留）
member 對帳層、scale 正規化、per-cell 值比對、NLM always-run、conflict 值級分級。等實際出現「XBRL 值掛錯維度」案例再開 Phase 2 工單。

---

## §1 問題（為什麼要改）— 已 re-baseline（review round-1）

parse-SEC-supplement 目前是 **XBRL-primary + NLM-fallback（gap-triggered）**：

| Stage | 做什麼 | 觸發 |
|---|---|---|
| A — `parse_def_xml` + `parse_instance_xbrl` + `extract_supplement_v3` | 從 XBRL instance doc **直接抽** segment/geo/customer 維度值 → `{T}_supplement_facts_v3.json` + `coverage_gaps.json` | 永遠跑 |
| B — `extract_supplement`（NLM 讀 10-Q/10-K 原文）+ `cross_check_supplement` | NLM **直接讀**原文補值 → `{T}_supplement_facts.json` + cross_check.md | **只在 Stage A 有 coverage gap 時跑** |

**缺陷**：`coverage_gaps` 只抓得到「**漏抽（missing）**」，抓不到「**抽錯但有值（wrong-but-present）**」。

**實證起點（SNDK，2026-06-12）**：SNDK Q3_FY2026 的 segment 值是對的（filer 真實揭露），但**期別標籤錯位**（52/53-週財曆 + 缺 ticker_config → fy_end 預設 12 → 整批季別 shift 一季）。資料齊全、無 coverage gap → Stage B 不觸發 → 錯誤靜默上 production。

**⚠ re-baseline（review round-1 Opus 指正）**：SNDK 的**XBRL 側**錯位，**已被現已 shipped 的 `dei_period_label()`（`parse_instance_xbrl.py:114`，直接讀 filer `dei:DocumentFiscalPeriodFocus`，52/53-週安全）一行修掉**，**不需要**本設計的重機制。因此本設計真正要對付的是 **post-dei 殘留錯誤類**：

1. **NLM-side period 標錯**：NLM facts 的 period 來自 agent 打進檔名的字串（`extract_supplement.py:57 infer_period_from_filename`），不是獨立讀檔 → 可能繼承同一心智錯位。
2. **XBRL wrong-but-present**：值有、但 member 映射錯 / sign·weight 錯 / axis 歸錯 → coverage 不缺、dei 期別也對，但值掛錯維度。
3. **跨源只有一邊揭露**：XBRL 有 NLM 漏、或 NLM 有 XBRL 漏（小公司沒打 segment XBRL tag）。

→ 需要一個**對「抽錯但有值」也有效、且兩源期別獨立**的驗證機制。

## §2 原則（user 2026-06-12 拍板，鐵律）

- **parse skill 永不 derive**：parse-* 只從原文**直接拿值**，不加總、不算比率、不反推、不用月份算術推季別。derive 是 derive-base/derive-analytics 的事。
- 因此驗證**不可用 derive 當手段**：❌「把 segment 加總比合併」「算營業利益率設合理性邊界」這些是 derive，不能進 parse 的驗證層。
- ✅ 正解 = **雙源「直接抽取」互相 cross-check**：XBRL instance（filer tag 的值）與 NLM 讀原文（同文件印出的值）都是「filer 揭露了什麼」的直接讀取，只是兩條路徑。比對兩者 = **純驗證、零 derive**。容差 / 單位換算 / 字串正規化 **都只是比較前處理，不是 derive**。

## §3 設計：Stage-B-always

### §3.1 流程變更
- Stage A（XBRL）**和** Stage B（NLM）**都永遠跑**（不再 gap-triggered）。
- 兩者各自產出**獨立的直接抽取結果**：
  - `{T}_supplement_facts_v3.json`（XBRL-primary，現有）
  - `{T}_supplement_facts.json`（NLM-derived，現有）
- **NLM 必須獨立讀 period anchor（修 B1）**：NLM prompt 增加「從文件封面直接讀 `DocumentFiscalPeriodFocus` + `DocumentFiscalYearFocus` + period-end 日期」，寫進 row，**不再信任 agent 打的檔名字串**。→ 兩源各有**獨立**的期別讀取，才比得出錯位。
- **修 `period_end_from_period()` 日曆假設（修 B1 孿生 bug）**：`extract_supplement.py:66` 硬編 `Q3→09-30` 等日曆季末，對 52/53-週 filer（LITE fy_end=6、SNDK）會寫錯 `period_end`。改成用 filing 真實 period-end（XBRL contextRef end date / NLM 讀封面），不可用日曆推。
- 新增 **XBRL↔NLM cross-check 收斂** pass（取代現有 XBRL-driven 的 `validate_against_nlm`，改 set-union 雙向）。

### §3.2 配對與比對（核心，修 B1）
**period 是被比對的屬性，不是 join key。**

- **配對 identity（period-independent）**：`(axis_key, member_key, uni_account, period_end, period_kind, unit_family)` —— 用真實 `period_end` 日期錨定，**不用 period label**。
  - 為何 `period_end` 而非 label：label 正是被懷疑的欄位；用它當 key 會讓錯位的兩列永遠不相遇（B1 的根因）。
  - `period_kind` 進 key（修 Q4 8-K 同含 Q4+FY 誤配）。
- **比對完成後，斷言 period label 一致**：兩源同一 `period_end` 配上、值一致，但**兩源的 period label 不同** → `period_label_disagreement`（**Tier-1 最高優先 conflict**，正是 SNDK 型錯位的指紋）。
- **set-union 雙向（修 Codex BLOCKER）**：收斂 pass 必須涵蓋 NLM-only（XBRL 無、NLM 有的可用 disclosure），不可只跑 XBRL-driven。

### §3.2a member 對帳層（first-class，修 B2）
XBRL `member` 是 qname（`us-gaap:DataCenterMember`，經 `_lab.xml` resolve 成 "Data Center"）；NLM `source_account` 是 PDF 印出字串（"Datacenter" / "DCAI" / "Data Center and AI"）。**直接字串比對系統性對不齊** → 真比對被靜默變成假 `xbrl_only` + 假 `nlm_only`。

- 對帳順序（cascade）：`matched_by_qname_label`（normalize：去空白/大小寫/連字號）→ `matched_by_alias`（吃 `edges.aliases[]` + `_lab.xml` 多 label role：terse/total/verbose）→ `matched_by_axis_equiv`（如 product↔end_market，沿用 `validate_against_nlm` 既有 remap）→ `unmapped_member`。
- **`unmapped_member` 不算 conflict**：進獨立 `mapping_gap` 桶，餵 alias/config backlog。
- **報 match-rate 指標**：「% of XBRL members 找到 NLM 對應」。match-rate 低本身就是紅旗，必須印出，不可靜默吞成單源桶。

### §3.2b 單位正規化（修 D1 scale，review CONCERN）
容差比較**前**必須先把兩源轉到 base unit：
- 用每列自己的 `unit` 欄 + **SEC 側為單位權威**（CLAUDE.md「NLM↔SEC unit 對照」規則）決定 rescale。
- unit **family 不同**（如一邊 USD 一邊 shares/pct）→ `unit_mismatch` 桶，不比數值。
- 同 family 跨 scale（NLM thousands vs XBRL millions）→ 轉同基準再比；記 `scale_conversion`。
- tolerance 把 XBRL `decimals` 納入（disclosed 精度決定 rounding 容忍），不只固定 floor。

### §3.2c 收斂規則（per 配對 cell）
| 情況 | 判定 | 動作 |
|---|---|---|
| 兩源都有、period_end 配上、值一致（容差內）、label 一致 | ✅ confident | 採 XBRL；provenance `cross_checked: true` |
| 兩源都有、值一致但 **label 不同** | ❌ `period_label_disagreement`（Tier-1）| flag must-review；**gate production upsert** |
| 兩源都有、值不一致（過容差、同 unit family）| ❌ `hard_conflict`（Tier-1）| flag must-review；**gate production upsert**；不靜默選邊 |
| member 對不齊 | ⚠ `mapping_gap`（Tier-2）| 進 alias/config backlog；不阻塞 |
| unit 無法 canonicalize | ⚠ `scale_gap`（Tier-2）| 修 parser；不阻塞 |
| 只有 XBRL（NLM 漏）| ⚠ `nlm_only`（Tier-2）| 採 XBRL；標 `nlm_unconfirmed`；統計 |
| 只有 NLM（XBRL 無此維度）| ⚠ `xbrl_missing`（Tier-2）| 採 NLM；標 |

- **容差（D1）**：canonicalize 後 `tol = max(abs(xbrl) * 0.005, FLOOR[unit_class], decimals_unit)`；FLOOR = `{millions:1, thousands:1, pct:0.5pp}`（pct 放寬到 0.5pp，filer 常印「approximately 14%」）。
- **period 權威**：XBRL 用 `dei_period_label()`（已實作）；NLM 用 §3.1 新增的封面獨立讀取。兩源**獨立**標期才有比對意義。

### §3.3 輸出
- `{T}_supplement_validation.md`（重構）：
  - **頂部：Tier-1 must-fix**（`period_label_disagreement` + `hard_conflict`）—— ship 前必清。
  - 中段：Tier-2 advisory（`mapping_gap` / `scale_gap` / `nlm_only` / `xbrl_missing`）+ member match-rate。
  - **最下方：`structural_advisory_only`**（sum-sanity，見 D4）—— 明標「不可作 correctness gate / conflict resolution / canonical input」。
  - 每列帶 `accession`（修 Codex BLOCKER：period 歸屬錯的根因在 accession，不寫 review 人看不到錯在哪）。
- 收斂後 canonical facts：per cell 標 cross-check 狀態於 provenance。
- **gate**：抽取不阻塞；但 **production upsert 阻塞未解 Tier-1**（T3 不 ship unresolved hard conflict）。

## §4 決議（user 拍板 + 雙模型 review round-1 收斂）

- **D1 容差** → 見 §3.2b/§3.2c：canonicalize unit 後 `max(abs*0.5%, FLOOR, decimals_unit)`，pct floor 放寬 0.5pp。
- **D2 conflict** → **純報告 + 分級 + Tier-1 gate upsert**。不靜默選邊；但分 Tier-1（must-fix：label 不符 / hard value conflict）vs Tier-2（advisory：mapping/scale/single-source），否則 backlog 不可操作。
- **D3 cadence** → **每期都跑 NLM** + run-folder cache，**cache key = `accession + source_id + prompt_version + extractor_schema_version`**（修 Codex：只用 accession 會在 prompt/schema 變更後供舊 schema）。
- **D4 sum-sanity** → **`structural_advisory_only`**。主驗證 = §3.2c 雙源直接抽取。sum-sanity（`Σ(child·weight)=parent`，filer 自報 parent vs 自報 children，皆直接讀）保留為**純報告**：永不 gate、永不選邊、永不改 canonical、永不宣稱 validation pass、**不可作為改值的唯一依據**（只能促使重讀原文）。做不到此隔離就移除。
- **D5 ticker_config 缺漏** → **分 mode**（修 review：原 fail-closed 太粗會擋掉本來能跑的 XBRL-only）：
  - `production`（default）：缺 config → **fail-closed**（「ticker X 缺 NLM config，無法雙源驗證」），禁 upsert。
  - `exploratory --xbrl-only-unverified`：可產 XBRL-only artifact，明標 `validation_status=unverified`，**禁 production upsert**。
  - 關鍵分界：缺 config 擋的是「**宣稱已雙源驗證**」與「production ship」，**不是** XBRL 抽取本身。
- **D6（新）period 為被比對屬性** → 見 §3.2：join on `period_end`-anchored identity，period label 不一致 = Tier-1 conflict。這是修 B1 命門的核心。
- **D7（新）member 對帳層** → 見 §3.2a：cascade 對帳 + match-rate；unmapped ≠ conflict。修 B2。
- **D8（新）NLM 獨立讀 period + 修 `period_end_from_period()`** → 見 §3.1。兩源期別獨立 + period_end 不用日曆推。

## §5 Scope / Non-goals
- ✅ in: Stage B 永遠跑、XBRL↔NLM 獨立直接抽取 cross-check 收斂（period 為被比對屬性）、member 對帳層、單位正規化、conflict 分級 + Tier-1 gate、validation 報告重構、NLM 獨立讀 period anchor。
- ❌ out（屬下游 derive/audit，不進 parse）：合理性邊界（算 margin/成長率設閾值）、segment 加總對合併當驗證、任何「算出新數字當驗證手段」。
- ❌ out: 改 XBRL 抽取值本身（已是直接抽取）；改 schema（除非 provenance 加 cross-check 欄位 + period_end/accession）。

## §6 Build plan（T3 review-before-prod）
1. ~~design spec → user review~~（✅）→ ~~雙模型 review round-1~~（✅ 2 BLOCKER 已修進 v3）→ **雙模型 review round-2 確認 v3 收斂**（下一步）。
2. TDD：
   - cross-check 收斂 pass（合成雙源 fixture：agree / period_label_disagreement / hard_conflict / mapping_gap / scale_gap / nlm_only / xbrl_missing / 容差邊界 / 跨 scale）。
   - member 對帳 cascade（qname_label / alias / axis_equiv / unmapped）+ match-rate。
   - 單位 canonicalize（同 family 跨 scale / family mismatch）。
   - NLM 獨立 period anchor 讀取 + `period_end` 不用日曆推。
3. wire：extract_supplement_v3 always-chain Stage B + 收斂 pass（set-union 雙向）+ accession/prompt/schema-keyed cache（D3）+ validation 報告（Tier-1/2 + structural_advisory_only + accession 欄）。
4. mode gate（D5）：production fail-closed vs exploratory --xbrl-only-unverified。
5. 各 ticker 跑（work-profile NotebookLM；先 1 ticker 端到端證明，再全量）。
6. 人工清 Tier-1 conflict（real mismatch 修 raw NLM 或確認 XBRL）。
7. 收斂後 re-upsert（**Tier-1 gate；dimensional 快照替換已就緒**）+ 前端驗證。

## §7 風險 / 注意
- **B1 命門（已修）**：period 必須是被比對屬性 + NLM 獨立讀期，否則整套對 period-label 錯位是盲的。build 時不可退回 join-on-period。
- **B2 member 對帳（已修）**：對不齊會靜默吞成單源桶 → 必須 first-class + match-rate 監控。
- dei 已修 SNDK XBRL 路徑：本設計成本要對得起「post-dei 殘留錯誤類」（§1），不是重抓已修的 bug。
- NLM 幻覺：conflict 要人工判，不可自動信 NLM 覆蓋 XBRL。
- NLM 慢：全量跑耗時 → cache（key 含 prompt/schema 版本）。
- work-profile 依賴：headless/cron 可能無 NLM auth。
- 跨 ticker config 維護成本。
- **MVP 替代方案（review 提出，待評估）**：最省版本 = 只做「period-anchor cross-check」（NLM 只獨立讀封面 period focus + period_end，斷言對齊 XBRL dei），full value-level dual-compare 留給 coverage gap。能以小成本抓 period-shift class，避開 member/scale flood。若 round-2 認為 full 版成本不划算，退此 MVP。
