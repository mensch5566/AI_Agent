# parse-twse-ixbrl 台股 SSOT 資料管道 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把台股 iXBRL 從「parse+derive 合一」重構成美股式分層管道：純 parse（零運算）→ NLM cross-check → twse-derive（單季+比率）→ upsert(`twse_financial_*`)，前端延後。

**Architecture:** 沿用隔壁已建 `fetch_ixbrl.py` + `XBRL_MAP` + `_parse_content`（純抽取核心）。把 derive 邏輯（CF 單季相減、Q4 還原、ratios、Q4 EPS）全部移出 parse 到獨立 `twse-derive` skill。新增 `twse_cross_check`（NLM 雙源）與 `upsert_twse`。canonical SSOT = `~/CC_Switch_Config/skills/`，改完 `cd ~/CC_Switch_Config && bash scripts/sync-to-local.sh`。

**Tech Stack:** Python3 標準庫（無 lxml/requests/supabase 於 parse）；upsert 用 supabase client（同美股 `scripts/upsert_sec_financials.py` 模式）；測試 pytest/unittest；NLM 走 notebooklm-mcp。

**測試標的：** 聯亞 3081（個體 ir，無 NCI）+ 台達電 2308（合併 cr，有 NCI）。

---

## 鐵律（每個 task 都遵守）

- **parse 零運算**：parse 只輸出 iXBRL **直接揭露**的 fact（含 IS 單季「本季」context、IS「本期累計」YTD、BS 期末 instant、CF YTD）。**禁止**：CF 單季相減、Q4=FY−9M、任何 ratio、Q4 EPS 反推。
- TWSE nuance：**IS 單季是揭露的（本季 column 有獨立 context）→ parse 可出**；CF 只揭 YTD（單季需相減=derive）；Q4 無獨立申報（FY−9M=derive）。
- **Q4 EPS 留空**（加權股數非加性）。
- footing = 唯讀驗證閘，**不寫值**。
- 每筆 fact 帶 `report_category`（ir/cr）、`unit=TWD_thousands`、`period_kind`。
- 改 canonical 後 sync。commit 頻繁。**production 寫入(`--apply`)需 user 授權**。

---

## File Structure

```
~/CC_Switch_Config/skills/parse-twse-ixbrl/        # 純 parse（重構）
  fetch_ixbrl.py          # 沿用（下載，不動）
  parse_ixbrl.py          # 重構 → 純 parse：XBRL_MAP + _parse_content + 多期 facts 輸出；移除 derive
  footing_check.py        # 新增：唯讀自洽驗證
  tests/test_parse_pure.py
  tests/test_footing.py

~/CC_Switch_Config/skills/twse-derive/             # 新 skill（fork 美股 derive 精神）
  derive_twse.py          # 單季還原(CF 相減/Q4=FY−9M) + ratios；Q4 EPS 留空
  tests/test_derive_twse.py

~/CC_Switch_Config/skills/parse-tw-crosscheck/        # 新 skill（NLM 雙源）
  cross_check_twse.py     # parse facts vs NLM tolerance=0；mirror parse-sec-cross-check
  ticker_configs/3081.json, 2308.json
  tests/test_cross_check_twse.py

AI_Agent/
  supabase/migrations/2026XXXX_twse_financial_tables.sql   # 新表
  scripts/upsert_twse_financials.py                        # 新 upsert（mirror upsert_sec_financials.py）
  scripts/tests/test_upsert_twse.py
```

輸出 JSON 落地（per ticker vault）：
`Khouse/Semiconductors/{TICKER}/01_Source/MOPS Filings/Skill_Output/parse-twse-ixbrl/{TICKER}_twse_facts.json`
`.../twse-derive/{TICKER}_twse_metrics.json`

---

## Phase A — parse 重構為純抽取（零運算）

### Task A1: 抽出純 parse 的 facts 輸出契約（測試先行）

**Files:**
- Modify: `~/CC_Switch_Config/skills/parse-twse-ixbrl/parse_ixbrl.py`
- Test: `~/CC_Switch_Config/skills/parse-twse-ixbrl/tests/test_parse_pure.py`

- [ ] **Step 1: 寫失敗測試** — parse 單一 iXBRL 檔，輸出純揭露 facts（無 derive），每 fact 帶 unit/period_kind/report_category，且**不含任何 ratio key**。

```python
# tests/test_parse_pure.py
import os, json
from parse_ixbrl import parse_period_facts   # 新 API（pure）

LANDMARK_Q1 = os.path.expanduser(
    "~/Obsidian/Khouse/Semiconductors/聯亞/01_Source/MOPS Filings/XML/"
    "tifrs-fr1-m1-ci-ir-3081-2026Q1.html")

def test_pure_parse_emits_disclosed_only():
    out = parse_period_facts(LANDMARK_Q1, period="Q1_FY2026")
    assert out["report_category"] == "ir"
    assert out["unit"] == "TWD_thousands"
    f = out["facts"]
    # 揭露值在（Revenue 已驗證 904,389 千元）
    assert f["operating_revenue"]["value"] == 904389
    assert f["operating_revenue"]["period_kind"] in ("quarter", "ytd")
    # 禁止任何 derive/ratio 出現在 parse 輸出
    for k in f:
        assert not k.endswith("_pct") and not k.endswith("_ratio") and k not in ("roe","roa","fcf")
    assert "metrics" not in out   # parse 不出 metrics
```

- [ ] **Step 2: 跑測試確認 FAIL**
Run: `cd ~/CC_Switch_Config/skills/parse-twse-ixbrl && python3 -m pytest tests/test_parse_pure.py -v`
Expected: FAIL（`parse_period_facts` 未定義 / 仍含 metrics）

- [ ] **Step 3: 實作 `parse_period_facts`（純）** — 複用既有 `_parse_content`，但：(a) 每期同時抽「本季 IS context」+「本期累計 YTD context」+「BS 期末 instant」+「CF YTD」；(b) 各 fact 標 `period_kind`（quarter / ytd / instant）；(c) 標 `report_category`（`report_type_of`）；(d) **不呼叫** `_subtract_ytd` / `_derive_q4_eps_from_annual` / ratios。輸出 `{ticker, report_category, period, period_end, unit:"TWD_thousands", facts:{metric:{value,statement,sort_order,period_kind,xbrl_concept}}}`。

```python
def parse_period_facts(file_path: str, period: str) -> dict:
    import re
    m = re.match(r'Q(\d)_FY(\d{4})', period); q, year = int(m.group(1)), m.group(2)
    end_month = q*3; end_day = ['31','30','30','31'][q-1]
    as_of = f"AsOf{year}{end_month:02d}{end_day}"
    ytd   = f"From{year}0101To{year}{end_month:02d}{end_day}"
    qstart_month = (q-1)*3+1
    q_ctx = f"From{year}{qstart_month:02d}01To{year}{end_month:02d}{end_day}"  # 本季
    content = open(file_path, encoding='utf-8', errors='ignore').read()
    facts = {}
    # YTD（IS+CF）+ BS instant
    for metric, v in _parse_content(content, as_of, ytd).items():
        facts[metric] = {"value": v[0], "statement": v[1], "sort_order": v[2],
                         "period_kind": "instant" if v[1].startswith("balance_sheet") else "ytd",
                         "xbrl_concept": None}
    # 本季 IS（揭露的單季 column；僅 IS，覆蓋同 metric 加 _quarter 變體保留兩者）
    for metric, v in _parse_content(content, as_of, q_ctx).items():
        if v[1] == "income_statement" and q != 1:   # Q1 本季==YTD，不重複
            facts[f"{metric}__q"] = {"value": v[0], "statement": v[1], "sort_order": v[2],
                                     "period_kind": "quarter", "xbrl_concept": None}
    return {"ticker": _ticker_of(file_path), "report_category": report_type_of(file_path),
            "period": period, "period_end": f"{year}-{end_month:02d}-{end_day}",
            "unit": "TWD_thousands", "facts": facts}
```

- [ ] **Step 4: 跑測試確認 PASS**
Run: `python3 -m pytest tests/test_parse_pure.py -v` → PASS

- [ ] **Step 5: Commit**
```bash
cd ~/CC_Switch_Config && git add skills/parse-twse-ixbrl && git commit -m "refactor(twse-parse): pure parse_period_facts, no derive"
```

### Task A2: 移除 parse 內所有 derive（刪 DERIVED_METRICS / _subtract_ytd / Q4 EPS / parse_ixbrl_full 的相減）

**Files:** Modify `parse_ixbrl.py`; Test `tests/test_parse_pure.py`

- [ ] **Step 1: 寫失敗測試** — 確認 module 不再 export derive 函式、Q3 檔輸出的 CF 是 YTD（非單季相減）。
```python
def test_cf_is_ytd_not_subtracted():
    q3 = os.path.expanduser(".../tifrs-fr1-m1-ci-ir-3081-2025Q3.html")
    out = parse_period_facts(q3, "Q3_FY2025")
    # CF 是 9M YTD（直接揭露），parse 不相減
    assert out["facts"]["operating_cash_flow"]["period_kind"] == "ytd"

def test_no_derive_symbols_exported():
    import parse_ixbrl as p
    assert not hasattr(p, "DERIVED_METRICS")
    assert not hasattr(p, "_derive_q4_eps_from_annual")
```
- [ ] **Step 2: 跑確認 FAIL**（symbols 還在）
- [ ] **Step 3: 刪除** `DERIVED_METRICS`、`_subtract_ytd`、`_drop_statements`(若僅 derive 用)、`_derive_q4_eps_from_annual`、`parse_ixbrl_full` 的 Q2/Q3/Q4 相減分支與 ratio 計算；保留 `XBRL_MAP` / `_parse_content` / `find_local_xbrl_files` / `report_type_of`。`run.sh parse` 改呼叫 `parse_period_facts` 對每期、合併成 `{TICKER}_twse_facts.json`（多期）。
- [ ] **Step 4: 跑確認 PASS** + 既有 fetch 流程不受影響
- [ ] **Step 5: Commit** `refactor(twse-parse): strip derive (ratios/Q4/CF-subtraction) out of parse`

### Task A3: 多期合併輸出 `{TICKER}_twse_facts.json` + sync

**Files:** Modify `parse_ixbrl.py` (main/run), `run.sh`; Test `tests/test_parse_pure.py`

- [ ] **Step 1: 失敗測試** — `parse 3081` 掃本地全期 → 輸出含 `periods` list + 每期 facts + metadata(report_category 一致)。
- [ ] **Step 2: FAIL**
- [ ] **Step 3: 實作** 多期聚合 writer（落地 `Skill_Output/parse-twse-ixbrl/3081_twse_facts.json`）。
- [ ] **Step 4: PASS**；實跑 `./run.sh parse 3081 --out .../3081_twse_facts.json` + `./run.sh parse 2308 ...`，肉眼檢查量級（台達電季營收 ~1,000 億級）。
- [ ] **Step 5: Commit** + `cd ~/CC_Switch_Config && bash scripts/sync-to-local.sh`

---

## Phase B — footing_check（唯讀驗證）

### Task B1: footing 斷言（report_category-aware）

**Files:** Create `~/CC_Switch_Config/skills/parse-twse-ixbrl/footing_check.py`; Test `tests/test_footing.py`

- [ ] **Step 1: 失敗測試** — 對 parse facts 驗 BS/IS/CF identity，0 容差（±1 千元 soft-warn）。
```python
def test_bs_foots_individual_no_nci():
    facts = parse_period_facts(LANDMARK_Q1, "Q1_FY2026")["facts"]
    rep = check_footing(facts, report_category="ir")
    # 個體：A = L + Equity（無 NCI）
    assert rep["balance_sheet"]["ok"] is True

def test_bs_foots_consolidated_total_equity_no_extra_nci():
    facts = parse_period_facts(DELTA_Q1, "Q1_FY2026")["facts"]
    rep = check_footing(facts, report_category="cr")
    # 合併：A = L + Equity(total，已含 NCI)，不另加 NCI
    assert rep["balance_sheet"]["ok"] is True
```
- [ ] **Step 2: FAIL**
- [ ] **Step 3: 實作 `check_footing`** — BS: `total_assets == total_liabilities + total_equity`（total_equity 用 ifrs-full:Equity，已含 NCI；兩 report_category 同式）；IS: `gross_profit − operating_expenses == operating_income`（用揭露 OperatingExpense，不 re-sum）；CF: `CFO+CFI+CFF+FX == net_change` 且 `beginning+net_change == ending`。回 `{stmt:{ok,diff}}`；diff>1千元 ❌、≤1 soft-warn。**唯讀,不改 facts**。
- [ ] **Step 4: PASS**（兩 ticker）
- [ ] **Step 5: Commit** `feat(twse-parse): read-only footing_check (A=L+Equity, no +NCI)`

### Task B2: scale fail-loud robustness

- [ ] **Step 1: 失敗測試** — 餵一個 scale≠3 的合成 fact → parse raise/skip-loud（不靜默當千元）。
- [ ] **Step 2: FAIL** **Step 3:** `_parse_content` 讀 `scale` 屬性,statement-eligible TWD fact 若 scale≠3 → 記 anomaly + fail-loud。 **Step 4:** PASS **Step 5:** commit + sync

---

## Phase C — twse-derive（fork，獨立 skill）

### Task C1: 單季還原（CF 相減 + Q4=FY−9M），Q4 EPS 留空

**Files:** Create `~/CC_Switch_Config/skills/twse-derive/derive_twse.py`; Test `tests/test_derive_twse.py`

- [ ] **Step 1: 失敗測試**
```python
def test_q3_single_quarter_cf_is_9m_minus_6m():
    # 讀 parse facts（YTD）→ Q3 單季 CF = 9M − 6M
    out = derive_twse("3081", facts_dir=FIXT)
    assert out["Q3_FY2025"]["operating_cash_flow"]["status"] == "DERIVED_FROM_DISCLOSED"

def test_q4_eps_left_blank():
    out = derive_twse("3081", facts_dir=FIXT)
    assert "basic_eps" not in out["Q4_FY2025"]   # Q4 EPS 不反推
```
- [ ] **Step 2: FAIL** **Step 3:** 實作 `derive_twse`：讀 `{T}_twse_facts.json`；CF 單季=YTD 相減前一季 YTD（telescoping，同 concept+unit guard）；Q4 IS/CF=FY−9M YTD；ratios（移植 `DERIVED_METRICS` 清單）；**Q4 EPS/WASO 不輸出**。輸出 `{T}_twse_metrics.json`(對齊 twse_financial_metrics)。 **Step 4:** PASS **Step 5:** commit + sync

### Task C2: ratios（margins/ROE/ROA/current/D-E/FCF）

- [ ] **Step 1: 失敗測試**（gross_margin_pct == gross_profit/operating_revenue，台達電某期已知量級）。 **Step 2:** FAIL **Step 3:** 移植 ratio rules（小數存,標 formula）。 **Step 4:** PASS **Step 5:** commit + sync

---

## Phase D — NLM cross-check（parse-tw-crosscheck skill）

### Task D1: ticker_configs + per-period NLM query producer

**Files:** Create `~/CC_Switch_Config/skills/parse-tw-crosscheck/ticker_configs/{3081,2308}.json`, `cross_check_twse.py`; Test `tests/test_cross_check_twse.py`

- [ ] **Step 1: 失敗測試** — config schema（notebook id + period_sources + label_to_key）+ compare 函式 tolerance=0。
- [ ] **Step 2: FAIL** **Step 3:** 建 config（聯亞/台達電 NotebookLM notebook + 各期 MOPS PDF source_id；需先確認該 ticker 有 NLM notebook，無則停下反問 user）。`cross_check_twse(ticker, period)`：NLM query 該期 PDF → compare vs `{T}_twse_facts.json`,tolerance=0,sign-flip 容許,unmapped→audit queue。 **Step 4:** PASS（unit 測試用 fixture）**Step 5:** commit + sync

### Task D2: 跑 3081 + 2308 實際 cross-check + 人工 audit

- [ ] **Step 1:** 對每期 NLM query 存 raw → cross_check → 報 ✅/❌/⚠️。 **Step 2:** ❌ 逐項查（parse 抽錯 vs NLM 讀錯）。 **Step 3:** audit 回寫（比照美股 apply_audit）。 **Step 4:** 收斂 0 ❌。 **Step 5:** commit

---

## Phase E — twse_financial_* 表 + upsert

### Task E1: migration（建表）

**Files:** Create `AI_Agent/supabase/migrations/2026XXXX_twse_financial_tables.sql`

- [ ] **Step 1: 失敗測試** — apply migration（local supabase）後表存在 + 欄位齊。
- [ ] **Step 2: FAIL** **Step 3:** 建 `twse_financial_companies`(ticker,company_name,exchange='TWSE',currency='TWD',fiscal_year_end_month=12,**無 cik**)、`twse_financial_facts`(period/period_kind/statement/uni_account/source_account/value/weight/unit/display_label/ordinal/report_category)、`twse_financial_metrics`(derive,statement含 RATIO)。 **Step 4:** PASS **Step 5:** commit（**不 apply production,待授權**）

### Task E2: upsert_twse_financials.py（mirror 美股 upsert，dry-run gate）

**Files:** Create `AI_Agent/scripts/upsert_twse_financials.py`; Test `scripts/tests/test_upsert_twse.py`

- [ ] **Step 1: 失敗測試** — dry-run 讀 facts+metrics → coverage/footing gate report，預設不寫。
- [ ] **Step 2: FAIL** **Step 3:** 實作（mirror `upsert_sec_financials.py`：load facts+metrics、gate、`--apply` 才寫、report_category 進 row）。 **Step 4:** PASS（dry-run）**Step 5:** commit

### Task E3: 3081 + 2308 dry-run → 授權後 --apply

- [ ] **Step 1:** `python3 scripts/upsert_twse_financials.py 3081`（dry-run）→ gate PASS。 **Step 2:** 同 2308。 **Step 3:** 報 diff 給 user。 **Step 4:** **user 授權後** `--apply`。 **Step 5:** 驗 production row count + footing。

---

## Self-Review

- **Spec coverage**：parse 純化(A1-A3)✓、footing(B)✓、derive fork+Q4 EPS 留空(C)✓、NLM cross-check(D)✓、twse_financial_* + upsert(E)✓、scale fail-loud(B2)✓、A=L+Equity 不加 NCI(B1)✓、report_category first-class(A1/E1)✓、前端延後(不在本plan)✓。
- **Placeholder scan**：D1/E 的 NLM notebook id 與 migration 流水號需執行時確認(D1 已寫「無 notebook 則停下反問」、E1 檔名 2026XXXX 執行時補日期)——非邏輯 placeholder。
- **Type consistency**：`parse_period_facts` 輸出 schema 在 A1 定義、B/C/D/E 一致引用；`check_footing(facts, report_category)`、`derive_twse(ticker)`、`cross_check_twse(ticker, period)` 簽名跨 task 一致。
- **時間序列基準轉換**(spec §13)：report_category per-period 已在 facts，upsert 與 derive YoY 的斷點處理列為 twse-derive 後續(本 plan 聯亞全個體、台達電全合併,不觸發；標 follow-up)。
