# compose-financials 台股 Q4 單季（IS/CF）支援 — Design Spec

- Date: 2026-07-08
- Status: implemented（2026-07-08，branch feat/compose-tw-q4）
- Tier: T1（單一 skill 的 loader 擴充；但輸出屬 financials 資料展示鏈，正確性紀律按 P6 執行）
- 前版 spec：`2026-07-03-compose-financials-tw-design.md`（compose 台股 v2，本 spec 反轉其中「TW 刻意排除 derive」一條）

## 1. 背景與問題

`compose-financials --market tw` 目前只讀兩個來源（`loaders.py` TW 分支）：

1. as-reported facts：`parse-twse-ixbrl/{T}_twse_facts.json` 經 `_shared/twse_canonical_facts.emit_canonical_facts()` in-memory 攤平（`source="gaap_facts"`）。
2. derive-analytics：最新 run 的 `{T}_analytics.json`（`source="analytics"`，RATIO）。

台股 iXBRL 揭露為累計：`_period_label` 把年報 IS/CF relabel 成 `FY{Y}`，**as-reported 層根本不存在 `Q4_FY{Y}` 的 IS/CF 節點**。而 compose 的欄位視窗 driver 是 `idx.available_quarters("revenue", "GAAP", "IS")`（`cli.py:119`）——IS revenue 沒有 Q4 label → 整頁沒有 Q4 欄。結果：台燿 6274 的 Financials.md 季度欄是 Q1/Q2/Q3 跳格（…Q3 FY25 → Q1 FY26），Q4 永遠缺席。

derive-base 其實已把 Q4 單季算好（`Q4_FY_MINUS_9M`）：6274 最新 run（`derive-base/2026-07-07-1608/6274_derived.json`）有 229 筆 `period_kind="derived_q4"`，IS 26 keys + CF 10 keys，version=GAAP、unit=TWD_thousands，例 `Q4_FY2025 revenue = 9,124,783`。derive-analytics 同 run 也有 198 筆 Q4 ratio rows（gross_margin_pct、dso、roe…），**已經被 TW loader 載入**，只因沒有 Q4 欄而從未渲染。

前版 spec 與 SOP §9.2/§9.3 明文「compose TW 只 as-reported、刻意排除 derive」，把 Q4 單季全貌推給 Financial Viewer 前端。使用者 2026-07-08 拍板反轉此決策：**台股 Q4 單季非靠 derive 不可，compose 應該補上**。

## 2. 目標

- `--market tw` 的 Financials.md 出現完整 Q4 欄：IS/CF 來自 derive-base `derived_q4`，BS 用 as-reported 年末值（`Q4_FY{Y}` label 本來就有），ratio 由已載入的 analytics Q4 rows 自動填。
- 季度欄從 Q1/Q2/Q3 跳格變成 Q1–Q4 連續。
- 美股路徑 zero-diff；台股既有欄位值 zero-diff（欄位視窗因納入 Q4 而平移屬預期）。

## 3. 非目標（YAGNI）

- **不動 Q2/Q3 單季來源**：官方揭露 `__q` 值優先於反推值，維持 as-reported（使用者拍板「只補 Q4」）。
- **不載入 derive-base 的 identity-fill rows**（`quarter_duration`/`ytd_duration`/`fy_annual_duration`，6274 全部是 D&A `IDENTITY_DA_DEP_PLUS_AMORT` 共 29 筆）：屬另一類補洞，本輪明確排除，未來要補走獨立決策。
- **不做 Q4 EPS**：derive-base 不還原 Q4 每股值（加權股數非加性）→ Q4 EPS 格顯示 `—` 是預期，非 bug。
- **不改前端**：Financial Viewer 早就顯示 derive Q4（讀 Supabase），本改動是 compose 向前端收斂，無前端 delta。
- **不改美股分支、contract、sections、charts、periods、resolve**。

## 4. 設計

### 4.1 唯一 code 改動面：`loaders.py` TW 分支

在現有兩個來源之後新增第三個：

```python
# derive-base derived_q4 (IS/CF single-quarter reconstruction) — the only
# derive_base rows loaded for TW; BS Q4 stays as-reported (year-end).
db = latest_run_dir(base / "derive-base")
dbj = _read_json(db / f"{ticker}_derived.json") if db else None
if dbj:
    for r in dbj.get("derived_metrics", []):
        if r.get("period_kind") != "derived_q4":
            continue
        if r.get("statement") not in ("IS", "CF"):
            continue
        value = r["value"]
        if r["uni_account"] in _SIGN_FLIP_TO_POSITIVE_OUTFLOW:
            value = -value          # 翻回 as-reported 慣例（見 §4.2）
        out.append(_rec("derive_base", r["statement"], r.get("version", "GAAP"),
                        r["uni_account"], r["period"], value, r.get("unit"),
                        r.get("period_kind")))
```

- `source="derive_base"`：`resolve._PRECEDENCE` 已有 `derive_base=1`（低於 `gaap_facts=0`）→ 若未來 as-reported 出現同 key，揭露值自動贏，不需新 code。
- `statement in ("IS","CF")` 是防禦性過濾：目前 derived_q4 無 BS row，但 fail-closed。
- **derive-base 缺席不得完全靜默**（argue 收斂改）：`load_all` 容忍缺檔（照舊回退、不 raise），但 `market=="tw"` 且找不到 derive-base run/json 時，CLI 印一行 stderr warning（`derive-base run not found; Q4 columns absent`）——Q4 欄靜默消失正是本次要修的 bug 樣態，誤配置不可被無聲吞掉。有載入時印出所用 run 的時間戳（資料夾名），供鮮度診斷。

### 4.2 符號正規化（必要，否則是真 bug）

derive-base 走 `twse_json_adapter.adapt_twse_facts`，把 `_SIGN_FLIP_TO_POSITIVE_OUTFLOW`（目前 = `{"capital_expenditures"}`）翻成正流出（6274 `derived_q4 capex = +120,900`）；compose TW 顯示層是 as-reported 慣例（Q1 `capex = −302,099`）。直接合併會讓同一列 Q4 為正、Q1–Q3 為負。

**規則**（argue 收斂後修訂）：

1. 合併 derived_q4 時，對翻號集合內的 key 取負號。
2. **不 import 私有底線名**：在 `twse_json_adapter` re-export 公開常數（`SIGN_FLIP_TO_POSITIVE_OUTFLOW = _SIGN_FLIP_TO_POSITIVE_OUTFLOW`），loaders 用公開名。私有名當跨模組 API 是耦合反模式；公開 re-export 保留單一真相源、去掉底線耦合。
3. **定位**：此負號是 **display-convention normalization**（把 derive adapter 的引擎慣例還原成 as-reported 顯示慣例），與既有 `_pct_fraction` 的 `/100`（cli.py:58）同性質，**不是** compose 計算財務指標，不違反 render-only 鐵律。範圍嚴格限定為 adapter 曾翻正的 key。
4. 已實測 capex 是 adapter **唯一**翻號 key（`_SIGN_FLIP_TO_POSITIVE_OUTFLOW={"capital_expenditures"}`，twse_json_adapter.py:40）；6274 derived_q4 其餘 CF key（dividends_paid 全期=0、各淨流量）維持 as-reported 帶號，無第二個分歧。

註：FCF（`free_cash_flow`）來自 analytics，其 Q4 值是 derive 引擎口徑（capex 正流出下的 CFO−capex），數值本身正確，不受本翻號影響——翻號只作用於 derive_base 的 facts 顯示列。

### 4.3 自然產生的效果（零額外 code，實作時逐項驗證）

1. `available_quarters` 撿到 `Q4_FY{Y}`（derived_q4 revenue 是 IS/GAAP，as-reported IS 無任何 Q4_FY label → 無碰撞）→ Q4 欄出現，12 季視窗自然平移。
2. BS 的 Q4 欄：as-reported 年末值（`Q4_FY{Y}` label 既存）直接命中。
3. 三率/ratio 的 Q4 欄：analytics Q4 rows（已載入）直接命中。**明寫為有意行為**（argue 收斂補）：Q4 label 的 analytics rows 是三種 period_kind 的混合——`derived_q4`（單季 flow ratio，115 筆）、`instant_period_end`（年末時點比率如 current_ratio，28 筆）、`ttm_duration`（TTM 口徑如 ROE，55 筆）——全部以 RATIO statement 索引、不會誤填三表 fact 格；這正是每種比率的正確口徑，測試鎖定之。
4. Q4 EPS：無 row → `—`（IS fact line 缺值走 `fmt_value` None→`—`，sections.py:31；`⏳` 只出現在整列全空的 RATIO line，sections.py:116-120——兩者路徑不同，與佔位符紀律無衝突）。
5. 圖表（margins/revenue/bs-structure）吃同一個 q_window，`_chart_label` 已支援 Q4 → 自動含 Q4。

### 4.4 Q4 EPS 說明註

台股頁 IS section 的來源註尾端加一句（僅 `market=="tw"`）：「Q4 單季 IS/CF 由 derive-base 自年報−9M 還原；Q4 EPS 不還原（加權股數非加性），留空為預期。」

**實作落點（argue 收斂修正原描述）**：`SOURCE_NOTE` 是 `contract.py:163` 的單一全域常數，`sections.py:127` **無條件**接到每個 section 尾端、完全不看 market。原 spec「加一行條件字串即可」低估了——正確做法是在 `render_section` 內組 local source_note，守衛條件為 `market=="tw"` **且僅 IS section**（`spec["key"]=="is"`），否則該句會重複出現在 BS/CF/RATIO 各表。文字放 sections.py local，不動 contract。

## 5. 文件同批更新（否則 SOP 自打臉）

1. **SOP `SOPs/Research/SEC Parse — facts+edges+linkbase 解讀 SOP.md`**：
   - 頂端 tip「人類要一頁全貌」條與 §9.2 warning、§9.3 分界、Cross-references 的 compose 行：由「compose TW 只 as-reported、看不到 Q2/Q3/Q4 單季」改為「compose TW = as-reported + derive-base Q4 單季（IS/CF，capex 翻回負號）；Q2/Q3 仍用官方 `__q`；Q4 EPS 留空」。
   - 涵蓋範圍行加 2026-07-08 更新記述。
2. **`compose-financials/SKILL.md`**：「範圍」表、CHANGELOG 加 v2.1 條目、「不做的事」中「台股三表刻意排除 derive」改為「台股 Q2/Q3 用官方揭露單季；Q4 單季讀 derive-base（唯一 derive facts 來源）」。**注意 stale 宣稱有兩處以上**（argue 收斂補）：除「不做的事」段外，CHANGELOG v2 敘述「台股三表刻意排除 `derive_base`」（≈line 130）是第二處；實作時 grep `排除.*derive|excludes.*derive` 全檔清點，一併改。
3. **`loaders.py` module docstring**（argue 收斂補）：現 docstring 明寫 "it deliberately excludes derive_base … so the TW three statements stay as-reported"，改動後自打臉，必須同步改為「TW 額外載入 derive-base 的 derived_q4（IS/CF）；Q2/Q3 維持官方 `__q`」。
4. 本 spec 存檔於 `AI_Agent/docs/superpowers/specs/`。

## 6. 測試（TDD，先紅後綠；argue 收斂後具體化）

**既有反向測試必須改寫（紅測的第一刀）**：`test_tw_loader.py` 現有 `test_tw_excludes_derive_base_from_statements` 斷言 `not any(source=="derive_base")`——這正是被本 spec 反轉的舊不變量，改動後必然 FAIL。改寫為新不變量：「derived_q4 已載入（IS/CF）；derived_q2/q3/identity-fill/BS 未載入」。

**fixture 必須擴充**：現 `_mk_tw_vault` 只造 `parse-twse-ixbrl`，無 derive-base run dir（`latest_run_dir` 回 None）。擴充：加 `derive-base/{run}/{T}_derived.json` stub，內容至少含 derived_q4 revenue、derived_q4 capex（**正值**，驗翻號）、一筆 derived_q2、一筆 identity-fill row（驗過濾）。

測項：

1. **Q4 rows 載入**：TW load_all 輸出含 `source="derive_base"`、`period="Q4_FY{Y}"`、`uni_account="revenue"`（fixture 值）。
2. **capex 翻號**：fixture 中正值的 derived_q4 `capital_expenditures` 進 record list 後為**負**。
3. **範圍過濾**：`derived_q2`/`derived_q3`/identity-fill rows 不被載入。
4. **優先序**：構造 gaap_facts 與 derive_base 同 key 衝突 fixture，斷言 as-reported 贏（resolve 既有行為的 TW 迴歸鎖）。
5. **TW compose 整合測試**（loader 單測不足以證明 Q4 欄真的出現在 Financials.md）：走 `cli.compose(market="tw")` 全路徑，覆蓋中文公司資料夾 glob、q_window 含 Q4 label、Q4 EPS 格為 `—`、IS source-note 含 Q4 說明句且 BS/CF section **不含**該句。
6. **analytics Q4 kind 鎖定**：Q4 label 的 analytics rows（`derived_q4`/`instant_period_end`/`ttm_duration`）全部進 RATIO、不誤填三表 fact 格。
7. **美股 zero-diff**：既有 US 測試全綠。`test_frontend_parity.py` 已查證只檢查 CONTRACT 條件列 key 集合、不含 rendered golden → 不受 Q4 視窗影響，無需更新。

## 7. 回歸 gate

- 美股：`pytest tests/` 全綠 + 對既有 US ticker 重跑 compose，diff 僅 frontmatter `updated`。
- 台股：6274 重跑，預期 diff = ①新增 Q4 欄（含視窗平移擠掉最舊季）②IS source-note 新句③frontmatter。既有 Q1/Q2/Q3 欄的值 **byte-identical**。
- Skill 鏡像同步：canonical `CC_Switch_Config/skills/compose-financials` 改完同步到 `.claude/skills`（既有鏡像紀律）。

## 8. 替代方案（已否決）

- **A. Q2/Q3/Q4 全走 derive**：口徑統一但把官方揭露單季換成反推值，違反「揭露值優先」紀律，多此一舉。→ 否決（使用者拍板）。
- **B. 不改 compose，Q4 只在前端看**：即前版設計。使用者明確反轉。→ 否決。
- **C. 在 emit_canonical_facts 層合併 derive**：污染「as-reported SSOT 攤平器」的單一職責（該模組同時餵 Supabase `sec_financial_facts`，絕不可混入 derive 值）。→ 否決，合併只發生在 compose 私有的 loaders 層。

## 9. 已知風險與緩解

| 風險 | 緩解 |
|---|---|
| 翻號集合未來加 key，compose 忘記跟 | import 公開 re-export 的同一個 set（§4.2），單一源 |
| derive-base run 過舊（facts 更新後沒重跑 derive）→ Q4 欄與 Q1–Q3 不同鮮度 | CLI 印出所用 derive-base run 時間戳；SKILL.md workflow 註明「facts 更新後先重跑 derive 再 compose」。（argue 記錄：skeptic 提議進一步比對 derive-base `metadata.input_files.twse_facts.sha256` 自動偵測 mismatch；architect 判 YAGNI。本輪收斂：只印 timestamp，sha256 比對留作未來選項，若實際發生過鮮度事故再升級。） |
| derive-base 缺席 → 頁面靜默退回無 Q4 | §4.1 已改：CLI stderr warning，不再完全靜默 |
| 12 季視窗被 Q4 擠掉最舊季，使用者誤以為掉資料 | 預期行為；`--quarters` 可調大 |
| derived_q4 將來出現 BS row | loaders 已過濾 statement ∈ {IS, CF}，fail-closed |

## 10. Argue 收斂記錄（2026-07-08，run `argue_1783441057889_1668e6`）

- 參與者：GPT-5.5（skeptic）× Opus（architect）。註：architect 首輪輸出因 JSON 被 code-fence 包裹遭 runner 判淘汰，但其完整分析保存在 raw 檔並納入本收斂——兩模型**獨立**得出高度一致的修正集。
- 兩邊一致（已全部修入 v2）：缺 derive-base 要 warning（§4.1）；sign-flip 改公開契約 + 定位為 display normalization（§4.2）；analytics Q4 三種 period_kind 混合明寫為有意（§4.3.3）；source-note 落點修正為 render_section local + IS-only 守衛（§4.4）；文件清點補 loaders.py docstring 與 SKILL.md 第二處 stale 宣稱（§5）；既有反向測試改寫 + fixture 擴充 + 整合測試（§6）；filter 管 scope、precedence 管碰撞的分層獲雙方確認正確（§8 註）。
- 機制可行性雙方確認：available_quarters 撿 Q4 無碰撞、Q4 EPS `—` 路徑正確、charts 同窗、BS 年末命中、capex 為唯一翻號分歧。
- 分歧解決：stale-run sha256 比對（skeptic 0.82 提議 vs architect YAGNI）→ 收斂為只印 timestamp（§9）。architect 的 OPEN O1（frontend_parity golden）已實查：該測試只檢查 CONTRACT key 集合，不受影響。O2（eps key 疑慮）不成立：6274 as-reported 有 `eps_basic`/`eps_diluted`。
