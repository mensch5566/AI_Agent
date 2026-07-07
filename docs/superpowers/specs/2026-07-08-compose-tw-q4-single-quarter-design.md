# compose-financials 台股 Q4 單季（IS/CF）支援 — Design Spec

- Date: 2026-07-08
- Status: draft（待 argue 收斂 + user 核可）
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
- derive-base 檔缺席時靜默跳過（與美股分支同慣例）：Q4 欄不出現，行為退回現狀，不報錯。

### 4.2 符號正規化（必要，否則是真 bug）

derive-base 走 `twse_json_adapter.adapt_twse_facts`，把 `_SIGN_FLIP_TO_POSITIVE_OUTFLOW`（目前 = `{"capital_expenditures"}`）翻成正流出（6274 `derived_q4 capex = +120,900`）；compose TW 顯示層是 as-reported 慣例（Q1 `capex = −302,099`）。直接合併會讓同一列 Q4 為正、Q1–Q3 為負。

**規則**：合併 derived_q4 時，對 `_SIGN_FLIP_TO_POSITIVE_OUTFLOW` 內的 key 取負號。**直接 `from _shared.twse_json_adapter import _SIGN_FLIP_TO_POSITIVE_OUTFLOW`**（loaders.py 已為 `emit_canonical_facts` 建好 `_shared` 的 sys.path），不 hardcode 字面集合——set 之後長大不會漏。

註：FCF（`free_cash_flow`）來自 analytics，其 Q4 值是 derive 引擎口徑（capex 正流出下的 CFO−capex），數值本身正確，不受本翻號影響——翻號只作用於 derive_base 的 facts 顯示列。

### 4.3 自然產生的效果（零額外 code，實作時逐項驗證）

1. `available_quarters` 撿到 `Q4_FY{Y}`（derived_q4 revenue 是 IS/GAAP）→ Q4 欄出現，12 季視窗自然平移。
2. BS 的 Q4 欄：as-reported 年末值（`Q4_FY{Y}` label 既存）直接命中。
3. 三率/ratio 的 Q4 欄：analytics Q4 rows（已載入）直接命中。
4. Q4 EPS：無 row → `—`。
5. 圖表（margins/revenue/bs-structure）吃同一個 q_window → 自動含 Q4。

### 4.4 Q4 EPS 說明註

台股頁 IS section 的來源註尾端加一句（僅 `market=="tw"`）：「Q4 單季 IS/CF 由 derive-base 自年報−9M 還原；Q4 EPS 不還原（加權股數非加性），留空為預期。」實作落點：`render_section` 的 source-note 已有 market 參數，加一行條件字串即可；不動 contract。

## 5. 文件同批更新（否則 SOP 自打臉）

1. **SOP `SOPs/Research/SEC Parse — facts+edges+linkbase 解讀 SOP.md`**：
   - 頂端 tip「人類要一頁全貌」條與 §9.2 warning、§9.3 分界、Cross-references 的 compose 行：由「compose TW 只 as-reported、看不到 Q2/Q3/Q4 單季」改為「compose TW = as-reported + derive-base Q4 單季（IS/CF，capex 翻回負號）；Q2/Q3 仍用官方 `__q`；Q4 EPS 留空」。
   - 涵蓋範圍行加 2026-07-08 更新記述。
2. **`compose-financials/SKILL.md`**：「範圍」表、CHANGELOG 加 v2.1 條目、「不做的事」中「台股三表刻意排除 derive」改為「台股 Q2/Q3 用官方揭露單季；Q4 單季讀 derive-base（唯一 derive facts 來源）」。
3. 本 spec 存檔於 `AI_Agent/docs/superpowers/specs/`。

## 6. 測試（TDD，先紅後綠）

加在 `tests/test_tw_loader.py`（fixture 走既有 conftest 模式）：

1. **Q4 rows 載入**：TW load_all 輸出含 `source="derive_base"`、`period="Q4_FY2025"`、`uni_account="revenue"`、value=9,124,783（fixture 值）。
2. **capex 翻號**：derived_q4 `capital_expenditures` 進 record list 後為**負**。
3. **範圍過濾**：`derived_q2`/`derived_q3`/identity-fill rows 不被載入。
4. **優先序**：構造 gaap_facts 與 derive_base 同 key 衝突 fixture，斷言 as-reported 贏（resolve 既有行為的 TW 迴歸鎖）。
5. **整合**：compose 6274（或 fixture）輸出含 `Q4 FY25` 欄；Q4 EPS 格為 `—`；IS source-note 含 Q4 說明句。
6. **美股 zero-diff**：既有 US 測試全綠（不加新測試，跑既有 suite 即回歸 gate）。

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
| `_SIGN_FLIP_TO_POSITIVE_OUTFLOW` 未來加 key，compose 忘記跟 | 直接 import 同一個 set，單一源 |
| derive-base run 過舊（facts 更新後沒重跑 derive）→ Q4 欄與 Q1–Q3 不同鮮度 | CLI 印出所用 derive-base run 時間戳；SKILL.md workflow 註明「facts 更新後先重跑 derive 再 compose」 |
| 12 季視窗被 Q4 擠掉最舊季，使用者誤以為掉資料 | 預期行為；`--quarters` 可調大 |
| derived_q4 將來出現 BS row | loaders 已過濾 statement ∈ {IS, CF}，fail-closed |
