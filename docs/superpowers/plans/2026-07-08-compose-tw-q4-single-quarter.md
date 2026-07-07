# compose-financials 台股 Q4 單季支援 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `compose-financials --market tw` 的 Financials.md 出現完整 Q4 欄——IS/CF 讀 derive-base `derived_q4`（capex 翻回 as-reported 負號）、BS 用既有年末值、ratio 自動填。

**Architecture:** 唯一 render 邏輯改動在 `loaders.py` TW 分支（新增第三個來源 derive-base，只挑 `period_kind=="derived_q4"` 且 statement ∈ {IS,CF}）+ `sections.py` 的 TW-IS-only source-note。翻號集合走 `twse_json_adapter` 新增的公開 re-export。derive-base 缺席印 stderr warning、載入時印 run 時間戳。

**Tech Stack:** Python 3（無新依賴）、pytest。兩個 repo：`/Users/mensch5566/AI_Agent`（adapter + spec/plan）與 `/Users/mensch5566/CC_Switch_Config`（compose skill canonical；`~/.claude/skills`、`~/.cc-switch/skills` 是 byte-identical 鏡像，改完 rsync）。

**Spec:** `/Users/mensch5566/AI_Agent/docs/superpowers/specs/2026-07-08-compose-tw-q4-single-quarter-design.md`（v2 argued-converged，user 核可）

**Baseline:** compose tests 47 passed（2026-07-08 實測）。

---

## File Structure

| 檔案 | 動作 | 職責 |
|---|---|---|
| `AI_Agent/Tools/research-tools/_shared/twse_json_adapter.py` | Modify（+1 行） | 翻號集合公開 re-export |
| `CC_Switch_Config/skills/compose-financials/scripts/compose_financials/loaders.py` | Modify | TW 分支載入 derived_q4 + 翻號 + warning/timestamp；docstring 更新 |
| `CC_Switch_Config/skills/compose-financials/scripts/compose_financials/sections.py` | Modify | TW-IS-only Q4 說明註 |
| `CC_Switch_Config/skills/compose-financials/tests/test_tw_loader.py` | Modify | fixture 擴充、反向測試改寫、新測試（loader 單測 + compose 整合） |
| `CC_Switch_Config/skills/compose-financials/SKILL.md` | Modify | stale 宣稱兩處 + 範圍表 + CHANGELOG v2.1 |
| `Obsidian/SOPs/Research/SEC Parse — facts+edges+linkbase 解讀 SOP.md` | Modify | 涵蓋範圍行、快速索引 tip、§9.2 warning、Cross-references |

---

### Task 1: 翻號集合公開 re-export（AI_Agent repo）

**Files:**
- Modify: `/Users/mensch5566/AI_Agent/Tools/research-tools/_shared/twse_json_adapter.py:40`

- [ ] **Step 1: 加公開 re-export**

在 line 40 的 `_SIGN_FLIP_TO_POSITIVE_OUTFLOW = {"capital_expenditures"}` 之後緊接：

```python
# Public contract for display-layer consumers (compose-financials loaders):
# the exact set of CF keys this adapter flips to positive-outflow on derive ingest.
# Display layers use it to flip derived values BACK to as-reported sign convention.
SIGN_FLIP_TO_POSITIVE_OUTFLOW = _SIGN_FLIP_TO_POSITIVE_OUTFLOW
```

- [ ] **Step 2: 驗證 import**

```bash
cd /Users/mensch5566/AI_Agent/Tools/research-tools && python3 -c \
  "from _shared.twse_json_adapter import SIGN_FLIP_TO_POSITIVE_OUTFLOW as S; print(S)"
```
Expected: `{'capital_expenditures'}`

- [ ] **Step 3: Commit（AI_Agent repo）**

```bash
cd /Users/mensch5566/AI_Agent
git add Tools/research-tools/_shared/twse_json_adapter.py
git commit -m "feat(twse-adapter): public re-export SIGN_FLIP_TO_POSITIVE_OUTFLOW for display layers"
```

---

### Task 2: 紅測 — fixture 擴充 + 反向測試改寫 + 新 loader 測試

**Files:**
- Modify: `/Users/mensch5566/CC_Switch_Config/skills/compose-financials/tests/test_tw_loader.py`

背景：現有 `test_tw_excludes_derive_base_from_statements`（斷言 `not any(source=='derive_base')`）正是本次反轉的舊不變量，必須改寫。`_mk_tw_vault` 只造 parse-twse-ixbrl，無 derive-base run dir。

- [ ] **Step 1: 改寫 `_mk_tw_vault` 加 derive-base stub，並替換反向測試 + 新增測試**

用以下內容**整檔取代** `test_tw_loader.py`（保留原有兩個仍有效的測試，改寫一個、新增四個）：

```python
import json
from pathlib import Path
from compose_financials.loaders import load_all
from compose_financials.resolve import ValueIndex


def _mk_tw_vault(tmp: Path, with_derive=True):
    base = tmp / "Khouse/Semiconductors/聯亞/01_Source/MOPS Filings/Skill_Output"
    d = base / "parse-twse-ixbrl"
    d.mkdir(parents=True)
    (d / "3081_twse_facts.json").write_text(json.dumps({
        "ticker": "3081", "report_category": "ir", "unit": "TWD_thousands",
        "periods": ["Q1_FY2026"],
        "facts_by_period": {"Q1_FY2026": {"period_end": "2026-03-31", "report_category": "ir",
            "facts": {"revenue": {"value": 904389.0, "statement": "income_statement", "sort_order": 4000,
                                  "period_kind": "ytd", "xbrl_concept": "ifrs-full:Revenue"},
                      "total_assets": {"value": 5678137.0, "statement": "balance_sheet_assets",
                                  "sort_order": 1900, "period_kind": "instant", "xbrl_concept": "ifrs-full:Assets"}}}}}))
    if with_derive:
        run = base / "derive-base" / "2026-07-08-0001"
        run.mkdir(parents=True)
        (run / "3081_derived.json").write_text(json.dumps({
            "metadata": {"ticker": "3081"},
            "derived_metrics": [
                # 該載入：Q4 單季 IS / CF（capex 是 derive 引擎的「正流出」慣例）
                {"period": "Q4_FY2025", "period_kind": "derived_q4", "statement": "IS",
                 "version": "GAAP", "uni_account": "revenue", "value": 9124783.0,
                 "unit": "TWD_thousands"},
                {"period": "Q4_FY2025", "period_kind": "derived_q4", "statement": "CF",
                 "version": "GAAP", "uni_account": "capital_expenditures", "value": 120900.0,
                 "unit": "TWD_thousands"},
                # 不該載入：Q2/Q3 單季（官方 __q 優先）、identity-fill、BS row
                {"period": "Q2_FY2025", "period_kind": "derived_q2", "statement": "IS",
                 "version": "GAAP", "uni_account": "revenue", "value": 1.0,
                 "unit": "TWD_thousands"},
                {"period": "Q3_FY2025", "period_kind": "derived_q3", "statement": "IS",
                 "version": "GAAP", "uni_account": "revenue", "value": 2.0,
                 "unit": "TWD_thousands"},
                {"period": "Q1_FY2026", "period_kind": "quarter_duration", "statement": "CF",
                 "version": "GAAP", "uni_account": "depreciation_and_amortization", "value": 3.0,
                 "unit": "TWD_thousands"},
                {"period": "Q4_FY2025", "period_kind": "derived_q4", "statement": "BS",
                 "version": "GAAP", "uni_account": "total_assets", "value": 4.0,
                 "unit": "TWD_thousands"},
            ]}))
    return tmp


def test_tw_load_flattens_and_tags_gaap_facts(tmp_path):
    v = _mk_tw_vault(tmp_path)
    recs = load_all("3081", v, market="tw")
    rev = [r for r in recs if r["uni_account"] == "revenue" and r["source"] == "gaap_facts"]
    assert rev and rev[0]["version"] == "GAAP"
    assert rev[0]["unit"] == "TWD_thousands" and rev[0]["value"] == 904389.0
    assert rev[0]["statement"] == "IS"           # income_statement→IS
    ta = [r for r in recs if r["uni_account"] == "total_assets" and r["source"] == "gaap_facts"]
    assert ta and ta[0]["statement"] == "BS" and ta[0]["period"] == "Q1_FY2026"


def test_tw_loads_derived_q4_only(tmp_path):
    """反轉舊不變量：derived_q4（IS/CF）要載入；q2/q3/identity-fill/BS 不載。"""
    v = _mk_tw_vault(tmp_path)
    recs = load_all("3081", v, market="tw")
    db = [r for r in recs if r["source"] == "derive_base"]
    assert {(r["period"], r["uni_account"]) for r in db} == {
        ("Q4_FY2025", "revenue"), ("Q4_FY2025", "capital_expenditures")}
    q4rev = next(r for r in db if r["uni_account"] == "revenue")
    assert q4rev["statement"] == "IS" and q4rev["value"] == 9124783.0
    assert q4rev["version"] == "GAAP" and q4rev["kind"] == "derived_q4"


def test_tw_derived_q4_capex_sign_flipped(tmp_path):
    """derive 引擎 capex 為正流出；display 層必須翻回 as-reported 負號。"""
    v = _mk_tw_vault(tmp_path)
    recs = load_all("3081", v, market="tw")
    cx = next(r for r in recs if r["source"] == "derive_base"
              and r["uni_account"] == "capital_expenditures")
    assert cx["value"] == -120900.0


def test_tw_missing_derive_base_is_tolerated(tmp_path):
    """derive-base 缺席：不 raise、無 derive_base record（warning 由 stderr 出，不驗文字）。"""
    v = _mk_tw_vault(tmp_path, with_derive=False)
    recs = load_all("3081", v, market="tw")
    assert recs and not any(r["source"] == "derive_base" for r in recs)


def test_tw_precedence_gaap_facts_beats_derive_base():
    """resolve 既有優先序的 TW 迴歸鎖：同 key 碰撞時 as-reported 贏。"""
    recs = [
        {"source": "derive_base", "statement": "IS", "version": "GAAP",
         "uni_account": "revenue", "period": "Q4_FY2025", "value": 1.0,
         "unit": "TWD_thousands", "kind": "derived_q4"},
        {"source": "gaap_facts", "statement": "IS", "version": "GAAP",
         "uni_account": "revenue", "period": "Q4_FY2025", "value": 2.0,
         "unit": "TWD_thousands", "kind": None},
    ]
    idx = ValueIndex(recs)
    assert idx.get("revenue", "Q4_FY2025", "GAAP", "IS") == 2.0


def test_tw_analytics_q4_kinds_all_ratio(tmp_path):
    """analytics 的 Q4 rows 混三種 period_kind（有意行為）：全部進 RATIO、不誤填三表。"""
    v = _mk_tw_vault(tmp_path)
    base = v / "Khouse/Semiconductors/聯亞/01_Source/MOPS Filings/Skill_Output"
    run = base / "derive-analytics" / "2026-07-08-0001"
    run.mkdir(parents=True)
    (run / "3081_analytics.json").write_text(json.dumps({
        "metadata": {"ticker": "3081"},
        "analytics_metrics": [
            {"period": "Q4_FY2025", "period_kind": "derived_q4", "statement": "RATIO",
             "version": "GAAP", "uni_account": "gross_margin_pct", "value": 0.22, "unit": "Pure"},
            {"period": "Q4_FY2025", "period_kind": "instant_period_end", "statement": "RATIO",
             "version": "GAAP", "uni_account": "current_ratio", "value": 1.9, "unit": "Pure"},
            {"period": "Q4_FY2025", "period_kind": "ttm_duration", "statement": "RATIO",
             "version": "GAAP", "uni_account": "roe", "value": 0.25, "unit": "Pure"},
        ]}))
    recs = load_all("3081", v, market="tw")
    q4a = [r for r in recs if r["source"] == "analytics" and r["period"] == "Q4_FY2025"]
    assert len(q4a) == 3 and all(r["statement"] == "RATIO" for r in q4a)
    assert {r["kind"] for r in q4a} == {"derived_q4", "instant_period_end", "ttm_duration"}


def test_us_market_unchanged(tmp_path):
    # us 路徑仍讀 SEC Filings;無檔 → 空
    assert load_all("XXXX", tmp_path, market="us") == []
```

- [ ] **Step 2: 跑測試確認紅**

```bash
cd /Users/mensch5566/CC_Switch_Config/skills/compose-financials && python3 -m pytest tests/test_tw_loader.py -v
```
Expected: `test_tw_loads_derived_q4_only`、`test_tw_derived_q4_capex_sign_flipped` **FAIL**（loader 尚未載 derive-base，db 集合為空）；`test_tw_analytics_q4_kinds_all_ratio`、`test_tw_precedence_gaap_facts_beats_derive_base`、`test_tw_missing_derive_base_is_tolerated`、既有兩個 PASS。

- [ ] **Step 3: Commit 紅測**

```bash
cd /Users/mensch5566/CC_Switch_Config
git add skills/compose-financials/tests/test_tw_loader.py
git commit -m "test(compose-financials): red tests for TW derived_q4 loading (flip old exclude-derive invariant)"
```

---

### Task 3: loaders.py 實作（綠燈）

**Files:**
- Modify: `/Users/mensch5566/CC_Switch_Config/skills/compose-financials/scripts/compose_financials/loaders.py`

- [ ] **Step 1: 更新 module docstring**

把 line 4-6：

```python
market="tw" loads ONLY the twse facts (flattened in-memory to the US long-format via the
shared emitter, tagged source=gaap_facts) + derive-analytics — it deliberately excludes
derive_base / nongaap / supplement so the TW three statements stay as-reported."""
```

改為：

```python
market="tw" loads the twse facts (flattened in-memory to the US long-format via the
shared emitter, tagged source=gaap_facts) + derive-analytics + derive-base derived_q4
rows ONLY (Q4 single-quarter IS/CF; Q2/Q3 stay official __q disclosures, BS stays
as-reported year-end) — nongaap / supplement and all other derive_base row kinds are
deliberately excluded."""
```

- [ ] **Step 2: TW 分支插入 derive-base 載入（在 gaap_facts 迴圈之後、derive-analytics 之前）**

現在的 TW 分支（`if market == "tw":`）在 `for r in emit_canonical_facts(tf)["facts"]:` 迴圈結束後直接接 analytics。在兩者之間插入：

```python
        # derive-base derived_q4 (Q4 single-quarter IS/CF reconstruction) — the only
        # derive_base rows loaded for TW. Q2/Q3 stay official __q; BS stays as-reported.
        # Sign: the derive adapter normalizes these keys to positive-outflow for the
        # engine; display is as-reported, so flip them back (display-convention only).
        from _shared.twse_json_adapter import SIGN_FLIP_TO_POSITIVE_OUTFLOW
        db = latest_run_dir(base / "derive-base")
        dbj = _read_json(db / f"{ticker}_derived.json") if db else None
        if dbj:
            print(f"[compose] TW derive-base run: {db.name}", file=_sys.stderr)
            for r in dbj.get("derived_metrics", []):
                if r.get("period_kind") != "derived_q4":
                    continue
                if r.get("statement") not in ("IS", "CF"):
                    continue
                value = r["value"]
                if r["uni_account"] in SIGN_FLIP_TO_POSITIVE_OUTFLOW:
                    value = -value
                out.append(_rec("derive_base", r["statement"], r.get("version", "GAAP"),
                                r["uni_account"], r["period"], value, r.get("unit"),
                                r.get("period_kind")))
        else:
            print(f"[compose] WARNING: derive-base run not found for {ticker} — "
                  "Q4 columns absent", file=_sys.stderr)
```

注意：`import` 放函式內與既有 `from _shared.twse_canonical_facts import emit_canonical_facts` 同慣例（sys.path 由模組頂端的 ancestor walk 建好）。

- [ ] **Step 3: 跑 TW loader 測試確認綠**

```bash
cd /Users/mensch5566/CC_Switch_Config/skills/compose-financials && python3 -m pytest tests/test_tw_loader.py -v
```
Expected: 全部 PASS。

- [ ] **Step 4: 跑全 suite 確認無迴歸**

```bash
python3 -m pytest tests/ -q
```
Expected: 全綠（baseline 47 + 新增數）。

- [ ] **Step 5: Commit**

```bash
cd /Users/mensch5566/CC_Switch_Config
git add skills/compose-financials/scripts/compose_financials/loaders.py
git commit -m "feat(compose-financials): TW loads derive-base derived_q4 (IS/CF) with as-reported sign flip + missing-run warning"
```

---

### Task 4: sections.py TW-IS-only Q4 說明註 + compose 整合測試

**Files:**
- Modify: `/Users/mensch5566/CC_Switch_Config/skills/compose-financials/scripts/compose_financials/sections.py`
- Modify: `/Users/mensch5566/CC_Switch_Config/skills/compose-financials/tests/test_tw_loader.py`（追加整合測試）

- [ ] **Step 1: 追加整合紅測到 `test_tw_loader.py` 檔尾**

```python
def test_tw_compose_integration_q4_column(tmp_path):
    """走 cli.compose 全路徑：Q4 欄出現、EPS 為 —、Q4 註只在 IS section。"""
    from compose_financials.cli import compose
    v = _mk_tw_vault(tmp_path)
    rep = compose("3081", v, market="tw")
    doc = Path(rep["target"]).read_text(encoding="utf-8")
    # Q4 欄（_col_label: Q4_FY2025 → "Q4 FY25"）
    assert "Q4 FY25" in doc
    # IS section 含 Q4 說明註；整份文件恰好一次（不洩漏到 BS/CF/RATIO section）
    assert doc.count("Q4 EPS 不還原") == 1
    is_block = doc.split("<!-- AUTO:is START -->")[1].split("<!-- AUTO:is END -->")[0]
    assert "Q4 EPS 不還原" in is_block
    # EPS 列在 Q4 欄為 —（fixture 無任何 eps row → 整列 —，仍證明非 ⏳ 路徑）
    eps_row = next(l for l in is_block.splitlines() if "Diluted EPS" in l)
    assert "⏳" not in eps_row
```

- [ ] **Step 2: 跑確認紅**

```bash
cd /Users/mensch5566/CC_Switch_Config/skills/compose-financials && python3 -m pytest tests/test_tw_loader.py::test_tw_compose_integration_q4_column -v
```
Expected: FAIL 在 `doc.count("Q4 EPS 不還原") == 1`（註尚未實作；`Q4 FY25` 欄的斷言應已過——若這裡也 FAIL，先修 loader 再繼續）。

- [ ] **Step 3: 實作 sections.py**

(a) 在 `SOURCE_NOTE` import 之後（module level，約 line 5 之後）加常數：

```python
# TW-only note appended to the IS section: Q4 single-quarter provenance + EPS caveat.
TW_Q4_NOTE = ("Q4 單季 IS/CF 由 derive-base 自年報−9M 還原；"
              "Q4 EPS 不還原（加權股數非加性），留空為預期。")
```

(b) 把 `render_section` 尾端（line 127）：

```python
    body = "\n".join([*head, header, sep, *rows, "", SOURCE_NOTE])
```

改為：

```python
    note = SOURCE_NOTE
    if market == "tw" and spec["key"] == "is-quarterly":
        note = f"{SOURCE_NOTE}{TW_Q4_NOTE}"
    body = "\n".join([*head, header, sep, *rows, "", note])
```

- [ ] **Step 4: 跑整合測試 + 全 suite 確認綠**

```bash
python3 -m pytest tests/test_tw_loader.py -v && python3 -m pytest tests/ -q
```
Expected: 全 PASS。

- [ ] **Step 5: Commit**

```bash
cd /Users/mensch5566/CC_Switch_Config
git add skills/compose-financials/scripts/compose_financials/sections.py skills/compose-financials/tests/test_tw_loader.py
git commit -m "feat(compose-financials): TW IS-section Q4 provenance note + compose integration test"
```

---

### Task 5: 文件同批更新（SKILL.md + SOP）

**Files:**
- Modify: `/Users/mensch5566/CC_Switch_Config/skills/compose-financials/SKILL.md`
- Modify: `/Users/mensch5566/Obsidian/SOPs/Research/SEC Parse — facts+edges+linkbase 解讀 SOP.md`

- [ ] **Step 1: SKILL.md 清點 stale 宣稱**

```bash
grep -n "排除\|excludes\|as-reported" /Users/mensch5566/CC_Switch_Config/skills/compose-financials/SKILL.md
```

已知兩處必改（若 grep 出更多，一併改）：

(a) line 108（「不做的事」）：

```
- **台股已支援**（v2，`--market tw`）：走 TWSE iXBRL as-reported，不做跨市場 derive（台股三表刻意排除 `derive_base`）。
```
改為：
```
- **台股已支援**（v2.1，`--market tw`）：三表以 as-reported 為主；**Q4 單季 IS/CF 讀 derive-base `derived_q4`**（唯一的 derive facts 來源，capex 翻回 as-reported 負號），Q2/Q3 用官方揭露 `__q`，Q4 EPS 不還原（留空為預期）。
```

(b) line 130（CHANGELOG v2 敘述）：句尾補歷史註記，改為：

```
- **in-memory flatten**：透過 `_shared/twse_canonical_facts.emit_canonical_facts`（`source=gaap_facts`、as-reported）即時攤平成 canonical long-format，台股三表排除 `derive_base`（**v2 當時的設計；v2.1 起改載 `derived_q4`，見下**）。
```

(c) 範圍表的台股列（`| 台股 | **v2 in-scope**…`）：`v2` 改 `v2.1`，並在說明尾補「+ Q4 單季（derive-base）」。

(d) CHANGELOG 新增 v2.1 條目（放在「### v2 — 台股（TWSE iXBRL）in-scope」之前）：

```markdown
### v2.1 — 台股 Q4 單季（derive-base derived_q4）

反轉 v2「TW 刻意排除 derive」決策（user 拍板 2026-07-08；spec：`2026-07-08-compose-tw-q4-single-quarter-design.md`）。

- TW loader 新增第三來源：derive-base 最新 run 的 `derived_q4` rows（僅 IS/CF）→ Q4 欄出現、季度連續 Q1–Q4。
- capex 翻回 as-reported 負號（import `twse_json_adapter.SIGN_FLIP_TO_POSITIVE_OUTFLOW` 公開契約）。
- derive-base 缺席 → stderr warning（頁面退回無 Q4，不靜默）；載入時印 run 時間戳。
- Q4 EPS 不還原（股數非加性）→ `—`；IS section 加說明註。
- workflow 注意：**facts 更新後先重跑 derive-base/analytics 再 compose**，否則 Q4 欄鮮度落後。
```

- [ ] **Step 2: SOP 更新（4 處）**

檔案：`/Users/mensch5566/Obsidian/SOPs/Research/SEC Parse — facts+edges+linkbase 解讀 SOP.md`

(a) 涵蓋範圍（line 5）：`（2026-07-07 更新：…）` 前補 `2026-07-08 compose 台股補 Q4 單季（讀 derive-base）；`。

(b) 快速索引 tip（line 14）：

```
> - **人類要一頁全貌** → `compose-financials`（render-only）。美股讀上面三種 JSON；**台股(`--market tw`)只讀 as-reported facts、刻意排除 derive → 沒有 Q2/Q3/Q4 單季**（顯示 Q1 + 6M + 9M + FY 年報，見 §9.2/§9.3）。要單季全貌用 Financial Viewer 前端（讀 Supabase，含 derive）。
```
改為：
```
> - **人類要一頁全貌** → `compose-financials`（render-only）。美股讀上面三種 JSON；**台股(`--market tw`)讀 as-reported facts + derive-base 的 Q4 單季（IS/CF，capex 翻回 as-reported 負號）+ derive-analytics** → 季度欄 Q1–Q4 連續（Q2/Q3 用官方揭露 `__q`；Q4 EPS 不還原、留空）。
```

(c) §9.2 warning 塊末段（line 444 起）：

```
> **所以：`compose-financials --market tw` 只讀 as-reported facts（刻意排除 derive）→ 看不到 Q2/Q3/Q4 單季**，它顯示的是 Q1 + 6M + 9M + FY。想要台股單季全貌 → **Financial Viewer 前端**（讀 Supabase，含 derive 的 `derived_q2/q3/q4`），或直接讀 `{T}_derived.json`。
```
改為：
```
> **`compose-financials --market tw`（2026-07-08 起）：as-reported facts + derive-base `derived_q4`（IS/CF）**——Q4 欄由 derive 補、BS Q4 用 as-reported 年末值、Q2/Q3 用官方 `__q`，季度欄 Q1–Q4 連續。derive-base 缺席時 CLI 印 warning、頁面退回無 Q4。單季更完整口徑（含 derived_q2/q3）仍在 **Financial Viewer 前端** / `{T}_derived.json`。
```

(d) Cross-references（line 482）：

```
- `compose-financials` SKILL.md：`--market tw`（render-only，只 as-reported，見 §9.2）
```
改為：
```
- `compose-financials` SKILL.md：`--market tw`（render-only；as-reported + derive-base Q4 單季，見 §9.2）
```

- [ ] **Step 3: Commit（兩 repo 分開）**

```bash
cd /Users/mensch5566/CC_Switch_Config
git add skills/compose-financials/SKILL.md
git commit -m "docs(compose-financials): SKILL.md v2.1 - TW Q4 single-quarter via derive-base"
```
（Obsidian vault 每分鐘自動 commit+push，SOP 檔不需手動 commit。）

---

### Task 6: 鏡像同步 + 6274 實跑驗證 + 美股 zero-diff gate

**Files:**
- 鏡像：`~/.claude/skills/compose-financials/`、`~/.cc-switch/skills/compose-financials/`
- 實跑輸出：`Obsidian/Khouse/Semiconductors/台燿/03_Working/Topics/Trackers/Financials.md`

- [ ] **Step 1: rsync 鏡像**

```bash
for m in ~/.claude/skills ~/.cc-switch/skills; do
  rsync -a --delete --exclude '__pycache__' \
    /Users/mensch5566/CC_Switch_Config/skills/compose-financials/ "$m/compose-financials/"
done
md5 -q /Users/mensch5566/CC_Switch_Config/skills/compose-financials/scripts/compose_financials/loaders.py \
       ~/.claude/skills/compose-financials/scripts/compose_financials/loaders.py \
       ~/.cc-switch/skills/compose-financials/scripts/compose_financials/loaders.py
```
Expected: 三個 md5 相同。

- [ ] **Step 2: 6274 實跑（先記 baseline diff 基準）**

Obsidian vault 是 git repo，直接用 git diff 當驗證器：

```bash
cd /Users/mensch5566/.claude/skills/compose-financials/scripts
python3 -m compose_financials.cli 6274 --market tw
```
Expected stderr: `[compose] TW derive-base run: 2026-07-07-1608`（timestamp 行）。

- [ ] **Step 3: 驗證 6274 diff**

```bash
cd /Users/mensch5566/Obsidian
git diff --stat "Khouse/Semiconductors/台燿/03_Working/Topics/Trackers/Financials.md"
git diff "Khouse/Semiconductors/台燿/03_Working/Topics/Trackers/Financials.md" | head -80
```
人工核對（照 spec §7 gate）：
1. 出現 `Q4 FY22`~`Q4 FY25` 欄（12 季視窗平移，最舊季被擠掉屬預期）。
2. Q4 revenue 值對 anchor：`Q4_FY2025 = 9,124,783`。
3. CF 的 Capital Expenditures Q4 欄為**負值**。
4. Diluted EPS 的 Q4 欄為 `—`。
5. IS section 尾註出現「Q4 EPS 不還原…」句，且只出現一次。
6. 既有 Q1/Q2/Q3 欄的數字沒變（只有欄位集合與註變）。

- [ ] **Step 4: 美股 zero-diff gate**

挑一個既有美股 ticker（用實際存在的 Financials.md）：

```bash
ls /Users/mensch5566/Obsidian/Khouse/Semiconductors/*/03_Working/Topics/Trackers/Financials.md | head -5
# 挑一個美股（英文資料夾名，如 GLW/LITE/AAOI），例：
cd /Users/mensch5566/.claude/skills/compose-financials/scripts
python3 -m compose_financials.cli GLW
cd /Users/mensch5566/Obsidian
git diff "Khouse/Semiconductors/GLW/03_Working/Topics/Trackers/Financials.md"
```
Expected: diff **只有** frontmatter `updated:` 一行（PNG 為 matplotlib 重繪、不列入 byte gate，照 v2 spec 慣例）。有任何其他 diff = 迴歸，停下調查。

- [ ] **Step 5: 全 suite 最後一次 + 收尾 commit**

```bash
cd /Users/mensch5566/CC_Switch_Config/skills/compose-financials && python3 -m pytest tests/ -q
cd /Users/mensch5566/CC_Switch_Config && git status --short   # 應為乾淨（Task 3-5 已各自 commit）
```

- [ ] **Step 6: spec 狀態更新**

把 spec 頭部 `Status: argued-converged（…待 user 核可）` 改為 `Status: implemented（2026-07-08）`：

```bash
cd /Users/mensch5566/AI_Agent
# 編輯 docs/superpowers/specs/2026-07-08-compose-tw-q4-single-quarter-design.md 的 Status 行
git add docs/superpowers/specs/2026-07-08-compose-tw-q4-single-quarter-design.md
git commit -m "docs(spec): compose TW Q4 marked implemented"
```

---

## Self-Review 紀錄

- **Spec coverage**：§4.1（Task 3）、§4.2（Task 1+3）、§4.3（Task 2 kind 測試 + Task 6 實跑驗證）、§4.4（Task 4）、§5 文件三處（Task 5；loaders docstring 在 Task 3）、§6 測試 1-7（Task 2/4/6）、§7 gate（Task 6）、§9 warning/timestamp（Task 3）。無缺口。
- **Placeholder scan**：無 TBD/TODO；每個 code step 附完整程式碼。
- **Type consistency**：`_rec(source, statement, version, uni, period, value, unit, kind)` 簽名與 loaders.py 現行一致；`SIGN_FLIP_TO_POSITIVE_OUTFLOW` 名稱 Task 1/3 一致；fixture `derived_metrics` 欄位對 loaders 讀取欄位（period/period_kind/statement/version/uni_account/value/unit）一致；整合測試斷言的 `Q4 FY25` 與 `_col_label` 輸出格式一致。
