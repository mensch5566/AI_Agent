# Derive 市場無關化(A 案)Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 台股 TWSE facts 收斂進美股 derive engine(單一 code path),parse 命名對齊美股 canonical,退役 twse-derive。

**Architecture:** 新 `_shared/twse_json_adapter.py` 把台股 `facts_by_period` 轉成美股 `FactRow` list;rules engine(rules_q4/q2q3/identity/ratios/crossperiod)邏輯不改、只把 5 個 USD 寫死點參數化;parse-twse-ixbrl 的 uni_account rename 到美股名。Spec:`docs/superpowers/specs/2026-07-02-derive-market-agnostic-design.md`(v2.1,Argue 共識版)。

**Tech Stack:** Python 標準庫(parse/adapter/engine 全無第三方依賴)、pytest。

## Global Constraints

- **Canonical SSOT**:skill code 改 `~/CC_Switch_Config/skills/`,改完 `cd ~/CC_Switch_Config && bash scripts/sync-to-local.sh`;`_shared/` 改 `~/AI_Agent/Tools/research-tools/_shared/`(engine 經 `AI_AGENT_ROOT` 直接 import 它,無鏡像)。兩 repo 都要 commit。
- **權威引擎 = live**:`~/CC_Switch_Config/skills/derive-base/scripts/`、`~/CC_Switch_Config/skills/derive-analytics/scripts/`。**禁止**拿 `~/AI_Agent/tmp/derive-*`(過期 prototype)當任何 diff/回歸基準。
- **美股零回歸(鐵律 5)**:全程不得改變美股輸出(排除 run metadata 的 deep-equal;Task 1 抓基準、Task 9 驗證)。
- **parse 永不運算**:rename / 家族重貼標 / xbrl_concept 填入都是「揭露驅動的重命名」,不得出現任何加減。
- **fail-closed**:缺 input → 跳過規則;`--market` 未知值 → argparse choices 直接擋。
- **測試位置**:parse 測試在 `~/CC_Switch_Config/skills/parse-twse-ixbrl/tests/`;cross-check 測試在 `~/CC_Switch_Config/skills/parse-tw-crosscheck/scripts/tests/`;adapter + engine 參數化測試在 `~/AI_Agent/scripts/tests/`。跑法一律 `python3 -m pytest <path> -v`。
- **前端不動**:app/ 內讀 Supabase 舊台股(2454)資料的 legacy 命名(`operating_revenue`/`basic_eps`)是 DB 層舊資料的事,Phase E 輪才處理;本輪 grep 清理範圍不含 app/。
- **hardcode 盤點(spec §5,已完成,live grep 證據)**:
  1. `derive-base/scripts/rules_q4.py:47-50` `_ADDITIVE_Q4_UNITS`(rules_q2q3 經 `from rules_q4 import _is_denied` 共用)
  2. `derive-base/scripts/rules_q4.py:191` `_EPS_UNIT = "USD_per_share"` — **即是 Q4 EPS 的 market gate**:台股 EPS unit=`TWD_per_share` 永不命中 → 不改 code,只加測試鎖(Task 7)
  3. `derive-base/scripts/tolerance.py:13-19` `ABS_TOL_BY_UNIT`
  4. `derive-base/scripts/validation_nlm.py:26-36` — 只在 `discover_cross_check_run`(找 `parse-sec-cross-check/` 目錄)命中時執行;台股 run 在 `parse-tw-crosscheck/` → 天然跳過,不改,Task 8 加註釋
  5. `derive-analytics/scripts/rules_ratios.py:130-131` `_USD_SCALE`/`_SHARE_SCALE`;`:413-429` per-share 分支(`out_unit = "USD_per_share"`)
  6. `derive-base/scripts/io_loader.py:36-58` + `derive-analytics/scripts/io_loader.py:31-66` 路徑寫死 `SEC Filings`/`parse-10QK-gaap`
  7. `derive_base.py:65` 硬要求 `gaap_inline`;`derive_base.py:106-130` cc 驗證(US-only,見 4)
  8. 註解/docstring 的 USD 字樣:僅 `rules_identity.apply_static_allowlist` 的 `extras["formula"]`(`" - ".join`)是「生成產物依賴」→ Task 7 處理;其餘純說明不改(spec §5 盤點紀律)

---

### Task 1: 美股零回歸基準抓取(改 code 前)

**Files:**
- Create: `/private/tmp/claude-501/-Users-mensch5566-AI-Agent/cec654d3-2750-4739-af9d-18d2863d7f2e/scratchpad/us_baseline/`(基準輸出)
- Create: `/private/tmp/claude-501/-Users-mensch5566-AI-Agent/cec654d3-2750-4739-af9d-18d2863d7f2e/scratchpad/gate3_compare.py`

**Interfaces:**
- Produces: `us_baseline/{TICKER}_derived.json` + `{TICKER}_analytics.json` ×5 ticker;`gate3_compare.py <baseline_dir> <new_dir>`(exit 0 = 語義等值)— Task 9 消費。

- [ ] **Step 1: 跑 5 檔美股 derive 並收基準**

```bash
SCRATCH=/private/tmp/claude-501/-Users-mensch5566-AI-Agent/cec654d3-2750-4739-af9d-18d2863d7f2e/scratchpad
mkdir -p "$SCRATCH/us_baseline"
for T in MU LITE INTC SNDK AAOI; do
  python3 ~/CC_Switch_Config/skills/derive-base/scripts/derive_base.py --ticker $T
  python3 ~/CC_Switch_Config/skills/derive-analytics/scripts/derive_analytics.py --ticker $T
  DB=$(ls -td ~/Obsidian/Khouse/Semiconductors/$T/01_Source/SEC\ Filings/Skill_Output/derive-base/*/ | head -1)
  DA=$(ls -td ~/Obsidian/Khouse/Semiconductors/$T/01_Source/SEC\ Filings/Skill_Output/derive-analytics/*/ | head -1)
  cp "$DB/${T}_derived.json" "$SCRATCH/us_baseline/"
  cp "$DA/${T}_analytics.json" "$SCRATCH/us_baseline/"
done
ls "$SCRATCH/us_baseline"   # 應有 10 檔
```

- [ ] **Step 2: 寫 gate3_compare.py(排除 run metadata 的 deep-equal)**

```python
#!/usr/bin/env python3
"""Gate 3: US zero-regression — compare derived/analytics arrays, ignoring run metadata."""
import json, sys
from pathlib import Path

VOLATILE_META = {"run_timestamp", "input_files", "stats"}  # stats 含計數,值陣列才是合約

def canon(doc: dict) -> dict:
    meta = {k: v for k, v in doc.get("metadata", {}).items() if k not in VOLATILE_META}
    arr_key = "derived_metrics" if "derived_metrics" in doc else "analytics_metrics"
    rows = sorted(doc.get(arr_key, []), key=lambda r: r.get("cell_id", ""))
    return {"metadata": meta, arr_key: rows}

def main(baseline_dir: str, new_dir: str) -> int:
    fails = 0
    for bp in sorted(Path(baseline_dir).glob("*.json")):
        np = Path(new_dir) / bp.name
        if not np.exists():
            print(f"❌ missing new output: {np}"); fails += 1; continue
        a, b = canon(json.loads(bp.read_text())), canon(json.loads(np.read_text()))
        if a != b:
            print(f"❌ DIFF: {bp.name}"); fails += 1
        else:
            print(f"✅ {bp.name}")
    return 1 if fails else 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
```

- [ ] **Step 3: 自我驗證 — 基準對自己比必須全綠**

Run: `python3 $SCRATCH/gate3_compare.py $SCRATCH/us_baseline $SCRATCH/us_baseline`
Expected: 10 行 ✅,exit 0

*(scratchpad 不進 git,無 commit)*

---

### Task 2: Pin twse-derive(原子擋掉,防 rename 後誤跑)

**Files:**
- Modify: `~/CC_Switch_Config/skills/twse-derive/derive_twse.py`(main() 開頭)
- Test: `~/AI_Agent/scripts/tests/test_twse_derive_pinned.py`

**Interfaces:**
- Produces: `derive_twse.py main()` 一進來就 `SystemExit(3)`,訊息指向 spec。

- [ ] **Step 1: 寫失敗測試**

```python
# ~/AI_Agent/scripts/tests/test_twse_derive_pinned.py
"""twse-derive is PINNED during the derive-A migration: it reads pre-rename
TW uni_account keys and would silently misread renamed facts (spec §7/§10)."""
import subprocess, sys

SCRIPT = "/Users/mensch5566/CC_Switch_Config/skills/twse-derive/derive_twse.py"

def test_twse_derive_exits_3_with_pointer():
    r = subprocess.run([sys.executable, SCRIPT, "3081"],
                       capture_output=True, text=True)
    assert r.returncode == 3
    assert "derive-market-agnostic" in (r.stderr + r.stdout)
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python3 -m pytest ~/AI_Agent/scripts/tests/test_twse_derive_pinned.py -v`
Expected: FAIL(現在會正常執行,returncode != 3)

- [ ] **Step 3: 在 derive_twse.py main() 第一行加 hard pin**

```python
def main(argv=None):
    import sys as _sys
    print(
        "⛔ twse-derive is RETIRED-PENDING (pinned 2026-07-02): TW facts keys were "
        "renamed to US canonical names; this script reads the OLD names and would "
        "silently misread them.\n"
        "→ use derive-base/derive-analytics --market tw instead.\n"
        "→ spec: docs/superpowers/specs/2026-07-02-derive-market-agnostic-design.md",
        file=_sys.stderr,
    )
    raise SystemExit(3)
    # --- original body below is intentionally unreachable until Task 11 deletes the skill ---
```

- [ ] **Step 4: 跑測試確認通過**

Run: `python3 -m pytest ~/AI_Agent/scripts/tests/test_twse_derive_pinned.py -v`
Expected: PASS

- [ ] **Step 5: Commit(兩 repo)**

```bash
cd ~/CC_Switch_Config && git add skills/twse-derive/derive_twse.py && git commit -m "chore(twse-derive): pin with hard exit 3 - reads pre-rename TW keys (derive-A spec sec7/sec10)"
cd ~/AI_Agent && git add scripts/tests/test_twse_derive_pinned.py && git commit -m "test: lock twse-derive pin (exit 3 + spec pointer)"
```

---

### Task 3: parse-twse-ixbrl rename + NI/Equity 家族 + xbrl_concept 填入(TDD)

**Files:**
- Modify: `~/CC_Switch_Config/skills/parse-twse-ixbrl/parse_ixbrl.py`
- Modify: `~/CC_Switch_Config/skills/parse-twse-ixbrl/tests/test_parse_pure.py`

**Interfaces:**
- Produces: `{T}_twse_facts.json` 的 facts key 用下表新名;每 fact `xbrl_concept` = 來源 concept qname(非 null);cr 報表輸出 `net_income`(歸母)/`net_income_nci`/`net_income_total_pre_nci` 與 `total_equity`(歸母)/`minority_interest_bs`/`total_equity_incl_nci`。Task 4/5/6 全部依賴此命名。

**RENAME 全表(spec §3;此表為 Task 3/4/5 的單一來源)**:

| 舊名 | 新名 | | 舊名 | 新名 |
|---|---|---|---|---|
| operating_revenue | revenue | | cash_and_equivalents | cash_and_cash_equivalents |
| cost_of_revenue | cost_of_goods_sold | | ppe_net | property_plant_equipment_net |
| r_and_d_expenses | research_and_development | | capital_surplus | additional_paid_in_capital |
| operating_expenses | total_operating_expenses | | long_term_debt_current | current_portion_of_long_term_debt |
| basic_eps | eps_basic | | non_controlling_interests | minority_interest_bs |
| diluted_eps | eps_diluted | | operating_cash_flow | net_cash_from_operating |
| capex | capital_expenditures | | investing_cash_flow | net_cash_from_investing |
| | | | financing_cash_flow | net_cash_from_financing |

家族重貼標(揭露驅動,零計算;僅當歸母行揭露時觸發 → ir 自然不動):
- NI:`net_income`(ProfitLoss 總額)→ `net_income_total_pre_nci`;`net_income_parent` → `net_income`(含 `__q` 變體)
- Equity:`total_equity`(Equity 總額)→ `total_equity_incl_nci`;`equity_attributable_to_parent` → `total_equity`

保留台股名(美股 core 無對應,不硬湊):selling_expenses、general_admin_expenses、expected_credit_loss、other_income、other_gains_losses、non_operating_income_expense、equity_method_income、income_before_taxes(已同名)、oci_*、total_comprehensive_income*、legal_reserve、long_term_payables、depreciation_expense、amortization_expense(→ 餵 Task 7 的 D&A identity)、beginning_cash/ending_cash/net_change_in_cash/fx_effect/dividends_paid、contract_liabilities_current、其餘 BS 明細。

- [ ] **Step 1: 改測試斷言為新名 + 新增家族/concept 測試(先紅)**

`test_parse_pure.py` 既有斷言改名:`operating_revenue`→`revenue`(值 904389 不變)、`operating_cash_flow`→`net_cash_from_operating`、`"operating_revenue" in first["facts"]`→`"revenue" in ...`。新增:

```python
def test_renamed_keys_and_no_old_names():
    out = parse_period_facts(LANDMARK_Q1, "Q1_FY2026")
    f = out["facts"]
    assert f["revenue"]["value"] == 904389
    assert "eps_basic" in f and "eps_diluted" in f
    assert f["cash_and_cash_equivalents"]["statement"] == "balance_sheet_assets"
    assert "net_cash_from_operating" in f and "capital_expenditures" in f
    OLD = {"operating_revenue", "cost_of_revenue", "r_and_d_expenses", "basic_eps",
           "diluted_eps", "capex", "cash_and_equivalents", "ppe_net", "capital_surplus",
           "operating_cash_flow", "investing_cash_flow", "financing_cash_flow",
           "operating_expenses", "long_term_debt_current", "non_controlling_interests"}
    assert not (OLD & set(f)), OLD & set(f)


def test_xbrl_concept_populated():
    out = parse_period_facts(LANDMARK_Q1, "Q1_FY2026")
    f = out["facts"]
    assert f["revenue"]["xbrl_concept"] == "ifrs-full:Revenue"
    assert f["total_assets"]["xbrl_concept"] == "ifrs-full:Assets"
    # 每一筆都要有(audit-trail 承諾, spec §3)
    assert all(v.get("xbrl_concept") for v in f.values())


def test_ir_ni_equity_family_untouched():
    # 聯亞 ir:無歸母/NCI 揭露 → net_income / total_equity 原位,不出現家族鍵
    out = parse_period_facts(LANDMARK_Q1, "Q1_FY2026")
    f = out["facts"]
    assert "net_income" in f and "total_equity" in f
    assert "net_income_total_pre_nci" not in f
    assert "total_equity_incl_nci" not in f


def test_cr_ni_equity_family_relabel():
    # 台達電 cr:同時揭露總額+歸母+NCI → 家族重貼標(值不動,純改 key)
    import glob, os
    hits = glob.glob(os.path.expanduser(
        "~/Obsidian/Khouse/**/tifrs-fr1-m1-ci-cr-2308-2026Q1.html"), recursive=True)
    assert hits, "台達電 FY26Q1 cr 檔案不在本地"
    out = parse_period_facts(hits[0], "Q1_FY2026")
    f = out["facts"]
    for k in ("net_income", "net_income_nci", "net_income_total_pre_nci",
              "total_equity", "minority_interest_bs", "total_equity_incl_nci"):
        assert k in f, k
    # 歸母 < 總額(NCI 為正時);至少驗 identity 不被 parse 竄改:總額 = 揭露值原樣
    assert f["net_income"]["sort_order"] == 8610          # 歸母行的原 sort
    assert f["net_income_total_pre_nci"]["sort_order"] == 8200
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python3 -m pytest ~/CC_Switch_Config/skills/parse-twse-ixbrl/tests/ -v`
Expected: 新測試 FAIL(KeyError `revenue` 等);既有測試也因改名 FAIL

- [ ] **Step 3: 實作 — XBRL_MAP 值改名 + SCALE_EXEMPT + concept 傳遞 + 家族 pass**

(a) `XBRL_MAP` 中把 RENAME 表的**值**改掉(key/sort_order 不動),例:

```python
    'ifrs-full:Revenue':                    ('revenue',                    'IS', 4000),
    'tifrs-bsci-ci:OperatingCosts':         ('cost_of_goods_sold',         'IS', 5000),
    'ifrs-full:ResearchAndDevelopmentExpense': ('research_and_development', 'IS', 6300),
    'ifrs-full:OperatingExpense':           ('total_operating_expenses',   'IS', 6800),
    'ifrs-full:BasicEarningsLossPerShare':  ('eps_basic',                  'IS', 9710),
    # ...(RENAME 表全套;net_income / net_income_parent 兩個 concept 的值先「不」改,
    #     家族 pass 統一處理)...
    'ifrs-full:NoncontrollingInterests':    ('minority_interest_bs',       'BS', 3700),
```

並新增台達電可能揭露的長期借款 concept(spec §3 debt 家族):

```python
    'ifrs-full:LongtermBorrowings':         ('long_term_debt',             'BS', 2540),
```

(b) `SCALE_EXEMPT_METRICS = {'eps_basic', 'eps_diluted'}`(line 189)。

(c) `_parse_content` 回傳加 concept:`results[metric_name] = (value, stmt, sort_order, xbrl_name)`;兩個 caller(`parse_period_facts` 的 ytd 與 `__q` 迴圈、`parse_ixbrl_annual_facts` 的下游)解包改 4-tuple,fact dict 寫 `"xbrl_concept": xbrl_name`。

(d) 家族 pass — `parse_period_facts` 組完 facts(含 `__q`)後呼叫:

```python
def _normalize_cr_families(facts: dict) -> None:
    """cr 合併報表家族正規化(揭露驅動重貼標,零計算;spec §3 NI/Equity 家族)。
    有歸母揭露 → 總額行讓位:ProfitLoss→net_income_total_pre_nci、歸母→net_income;
    Equity→total_equity_incl_nci、歸母權益→total_equity。ir 無歸母行 → 不動。"""
    for suffix in ("", "__q"):
        parent, total = f"net_income_parent{suffix}", f"net_income{suffix}"
        if parent in facts and total in facts:
            facts[f"net_income_total_pre_nci{suffix}"] = facts.pop(total)
            facts[total] = facts.pop(parent)
    if "equity_attributable_to_parent" in facts and "total_equity" in facts:
        facts["total_equity_incl_nci"] = facts.pop("total_equity")
        facts["total_equity"] = facts.pop("equity_attributable_to_parent")
```

- [ ] **Step 4: 跑測試確認通過**

Run: `python3 -m pytest ~/CC_Switch_Config/skills/parse-twse-ixbrl/tests/ -v`
Expected: 全 PASS

- [ ] **Step 5: Commit**

```bash
cd ~/CC_Switch_Config && git add skills/parse-twse-ixbrl && git commit -m "feat(parse-twse-ixbrl): rename uni_account to US canonical + cr NI/Equity family relabel + populate xbrl_concept (derive-A spec sec3)"
```

---

### Task 4: re-parse 3081/2308 + Gate 1 無值變 diff

**Files:**
- Create: `$SCRATCH/gate1_diff.py`
- Regenerate: `~/Obsidian/Khouse/Semiconductors/聯亞/01_Source/MOPS Filings/Skill_Output/parse-twse-ixbrl/3081_twse_facts.json` + 台達電 `2308_twse_facts.json`(先備份)

**Interfaces:**
- Consumes: Task 3 的 RENAME 表 + `_normalize_cr_families` 語義。
- Produces: rename 後 facts 檔(Task 6/10 輸入);Gate 1 報告(0 值差)。

- [ ] **Step 1: 備份舊 facts + re-parse**

```bash
VAULT=~/Obsidian/Khouse/Semiconductors
cp "$VAULT/聯亞/01_Source/MOPS Filings/Skill_Output/parse-twse-ixbrl/3081_twse_facts.json" \
   "$SCRATCH/3081_twse_facts.OLD.json"
cp "$VAULT"/台達電*/01_Source/MOPS\ Filings/Skill_Output/parse-twse-ixbrl/2308_twse_facts.json \
   "$SCRATCH/2308_twse_facts.OLD.json"
python3 ~/CC_Switch_Config/skills/parse-twse-ixbrl/parse_ixbrl.py 3081
python3 ~/CC_Switch_Config/skills/parse-twse-ixbrl/parse_ixbrl.py 2308
```

- [ ] **Step 2: 寫 gate1_diff.py(舊檔 key 對翻後與新檔全等;xbrl_concept null→值 為唯一例外)**

```python
#!/usr/bin/env python3
"""Gate 1: rename 無值變 — old facts (key-translated) must deep-equal new facts."""
import json, sys

RENAME = {
    "operating_revenue": "revenue", "cost_of_revenue": "cost_of_goods_sold",
    "r_and_d_expenses": "research_and_development", "operating_expenses": "total_operating_expenses",
    "basic_eps": "eps_basic", "diluted_eps": "eps_diluted",
    "cash_and_equivalents": "cash_and_cash_equivalents", "ppe_net": "property_plant_equipment_net",
    "capital_surplus": "additional_paid_in_capital",
    "long_term_debt_current": "current_portion_of_long_term_debt",
    "non_controlling_interests": "minority_interest_bs",
    "operating_cash_flow": "net_cash_from_operating",
    "investing_cash_flow": "net_cash_from_investing",
    "financing_cash_flow": "net_cash_from_financing", "capex": "capital_expenditures",
}

def translate_period(facts: dict) -> dict:
    out = {}
    for k, v in facts.items():
        base, suf = (k[:-3], "__q") if k.endswith("__q") else (k, "")
        out[RENAME.get(base, base) + suf] = dict(v)
    # 家族 pass(與 parse_ixbrl._normalize_cr_families 同語義)
    for suf in ("", "__q"):
        p, t = f"net_income_parent{suf}", f"net_income{suf}"
        if p in out and t in out:
            out[f"net_income_total_pre_nci{suf}"] = out.pop(t)
            out[t] = out.pop(p)
    if "equity_attributable_to_parent" in out and "total_equity" in out:
        out["total_equity_incl_nci"] = out.pop("total_equity")
        out["total_equity"] = out.pop("equity_attributable_to_parent")
    return out

def main(old_path: str, new_path: str) -> int:
    old, new = json.loads(open(old_path).read()), json.loads(open(new_path).read())
    fails = 0
    assert old["periods"] == new["periods"], "period set changed!"
    for p in old["periods"]:
        of = translate_period(old["facts_by_period"][p]["facts"])
        nf = new["facts_by_period"][p]["facts"]
        if set(of) != set(nf):
            print(f"❌ {p} key set: only-old={set(of)-set(nf)} only-new={set(nf)-set(of)}"); fails += 1; continue
        for k in of:
            for field in ("value", "statement", "sort_order", "period_kind"):
                if of[k][field] != nf[k][field]:
                    print(f"❌ {p}/{k}.{field}: {of[k][field]} -> {nf[k][field]}"); fails += 1
            # 唯一允許差異:xbrl_concept null → 非空字串(spec §3 增補)
            if of[k].get("xbrl_concept") is not None and of[k]["xbrl_concept"] != nf[k].get("xbrl_concept"):
                print(f"❌ {p}/{k}.xbrl_concept changed"); fails += 1
            if not nf[k].get("xbrl_concept"):
                print(f"❌ {p}/{k}.xbrl_concept still empty"); fails += 1
    print("✅ Gate 1 PASS" if not fails else f"❌ Gate 1 FAIL ({fails})")
    return 1 if fails else 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
```

- [ ] **Step 3: 兩檔跑 Gate 1**

```bash
python3 $SCRATCH/gate1_diff.py "$SCRATCH/3081_twse_facts.OLD.json" \
  "$VAULT/聯亞/01_Source/MOPS Filings/Skill_Output/parse-twse-ixbrl/3081_twse_facts.json"
python3 $SCRATCH/gate1_diff.py "$SCRATCH/2308_twse_facts.OLD.json" \
  "$VAULT"/台達電*/01_Source/MOPS\ Filings/Skill_Output/parse-twse-ixbrl/2308_twse_facts.json
```
Expected: 兩次都 `✅ Gate 1 PASS`,exit 0。任何 ❌ → 停,回 Task 3 查 parse。

---

### Task 5: parse-tw-crosscheck 連動 + repo 舊名 grep 清零

**Files:**
- Modify: `~/CC_Switch_Config/skills/parse-tw-crosscheck/scripts/cross_check_twse.py`(`CODE_TO_KEY` 值域、`EPS_KEYS`)
- Modify: `~/CC_Switch_Config/skills/parse-tw-crosscheck/ticker_configs/{3081,2308}.json`(`label_to_key` 值域)
- Modify: `~/CC_Switch_Config/skills/parse-tw-crosscheck/scripts/tests/test_cross_check_twse.py`

**Interfaces:**
- Consumes: Task 3 RENAME 表。
- Produces: cross-check 認得新名;`EPS_KEYS = {"eps_basic","eps_diluted","eps_basic__q","eps_diluted__q"}`。

- [ ] **Step 1: 加防回歸測試(先紅)**

```python
# 加進 test_cross_check_twse.py
OLD_NAMES = {"operating_revenue", "cost_of_revenue", "r_and_d_expenses", "basic_eps",
             "diluted_eps", "capex", "cash_and_equivalents", "ppe_net", "capital_surplus",
             "operating_cash_flow", "investing_cash_flow", "financing_cash_flow",
             "operating_expenses", "long_term_debt_current", "non_controlling_interests",
             "net_income_parent", "equity_attributable_to_parent"}

def test_code_to_key_uses_canonical_names():
    import cross_check_twse as cc
    vals = {v[:-3] if v.endswith("__q") else v for v in cc.CODE_TO_KEY.values()}
    assert not (vals & OLD_NAMES), vals & OLD_NAMES

def test_eps_keys_canonical():
    import cross_check_twse as cc
    assert cc.EPS_KEYS == {"eps_basic", "eps_diluted", "eps_basic__q", "eps_diluted__q"}

def test_ticker_configs_use_canonical_names():
    import json
    from pathlib import Path
    cfg_dir = Path(__file__).resolve().parents[2] / "ticker_configs"
    for t in ("3081", "2308"):
        l2k = json.loads((cfg_dir / f"{t}.json").read_text())["label_to_key"]
        vals = {v[:-3] if v.endswith("__q") else v for v in l2k.values()}
        assert not (vals & OLD_NAMES), (t, vals & OLD_NAMES)
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python3 -m pytest ~/CC_Switch_Config/skills/parse-tw-crosscheck/scripts/tests/ -v`
Expected: 3 個新測試 FAIL

- [ ] **Step 3: 實作 — 依 RENAME 表機械翻值**

- `cross_check_twse.py`:`CODE_TO_KEY` 每個 value 套 RENAME(手改,git diff 逐行複查);cr 專屬碼對映家族鍵:總額淨利碼(8600/6000 系)→ `net_income_total_pre_nci`、8610 → `net_income`、8620 → `net_income_nci`;權益總計碼 → `total_equity_incl_nci`、歸母權益碼 → `total_equity`、NCI 權益碼 → `minority_interest_bs`。`EPS_KEYS` 改新名。既有測試中的舊名斷言同步改。
- `ticker_configs/{3081,2308}.json`:一次性遷移腳本(跑完即棄,git diff 複查):

```bash
python3 - <<'EOF'
import json
from pathlib import Path
RENAME = { }  # ← 貼 Task 4 gate1_diff.py 的同一張 RENAME dict
FAMILY = {"net_income_parent": "net_income", "net_income": "net_income_total_pre_nci",
          "equity_attributable_to_parent": "total_equity", "total_equity": "total_equity_incl_nci"}
for t in ("3081", "2308"):
    p = Path.home() / f"CC_Switch_Config/skills/parse-tw-crosscheck/ticker_configs/{t}.json"
    cfg = json.loads(p.read_text())
    l2k = cfg["label_to_key"]
    fam = FAMILY if t == "2308" else {}   # 家族重貼標僅 cr(台達電)
    for label, key in list(l2k.items()):
        base, suf = (key[:-3], "__q") if key.endswith("__q") else (key, "")
        base = fam.get(base, RENAME.get(base, base))
        l2k[label] = base + suf
    p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2))
    print("done", t)
EOF
```

**注意**:3081(ir)不套 FAMILY;2308(cr)FAMILY 的順序依 dict 遍歷會撞——先把 `net_income`(總額 label)翻成 `net_income_total_pre_nci`、`net_income_parent` 翻成 `net_income`,兩條規則對「原值」查表(上面 code 對原 key 一次查表,無先後污染 ✓)。

- [ ] **Step 4: 跑全部 cross-check 測試**

Run: `python3 -m pytest ~/CC_Switch_Config/skills/parse-tw-crosscheck/scripts/tests/ -v`
Expected: 全 PASS(既有 22 + 新 3)

- [ ] **Step 5: pipeline 範圍舊名 grep 清零**

```bash
grep -rnE "operating_revenue|cost_of_revenue|r_and_d_expenses|basic_eps|diluted_eps|cash_and_equivalents|ppe_net|\bcapex\b|operating_cash_flow|investing_cash_flow|financing_cash_flow" \
  ~/CC_Switch_Config/skills/parse-twse-ixbrl \
  ~/CC_Switch_Config/skills/parse-tw-crosscheck \
  --include="*.py" --include="*.json" | grep -v "OLD_NAMES\|RENAME\|gate1\|CHANGELOG\|test_.*old"
```
Expected: 無輸出(twse-derive 已 pin 不在範圍;app/ 依 Global Constraints 排除)。scratchpad 的 `twse_sweep.py` 不含科目名,免改。

- [ ] **Step 6: Commit**

```bash
cd ~/CC_Switch_Config && git add skills/parse-tw-crosscheck && git commit -m "feat(parse-tw-crosscheck): CODE_TO_KEY/EPS_KEYS/ticker_configs to US canonical names (derive-A)"
```

---

### Task 6: `twse_json_adapter.py`(TDD;結構橋接核心)

**Files:**
- Create: `~/AI_Agent/Tools/research-tools/_shared/twse_json_adapter.py`
- Test: `~/AI_Agent/scripts/tests/test_twse_json_adapter.py`

**Interfaces:**
- Consumes: `_shared.sec_json_adapter.FactRow/CompanyRow`、`_shared.period_kind.infer_period_kind`、`_shared.cell_id.facts_cell_id`、Task 4 的新名 facts JSON。
- Produces: `adapt_twse_facts(facts_json: dict) -> list[FactRow]`、`adapt_company_twse(facts_json: dict) -> CompanyRow`、`reconcile_disclosed_quarters(facts_json: dict, tol: float = 0.0) -> list[dict]`。Task 8 的 `load_facts_tw` 與 Task 10 的 Gate 2 消費。

- [ ] **Step 1: 寫 fixture 失敗測試**

```python
# ~/AI_Agent/scripts/tests/test_twse_json_adapter.py
"""TWSE facts → FactRow adapter (derive-A spec §4). Fixture-driven, covers the
eight conversion rules + __q reconciliation + Argue-mandated guards."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "Tools" / "research-tools"))
from _shared.twse_json_adapter import (
    adapt_company_twse, adapt_twse_facts, reconcile_disclosed_quarters,
)


def _fx(period, facts, period_end="2025-06-30", cat="ir"):
    return {"ticker": "3081", "report_category": cat, "unit": "TWD_thousands",
            "periods": [period],
            "facts_by_period": {period: {"period_end": period_end,
                                         "report_category": cat, "facts": facts}}}


def _fact(value, stmt, sort, kind, concept="ifrs-full:X"):
    return {"value": value, "statement": stmt, "sort_order": sort,
            "period_kind": kind, "xbrl_concept": concept}


def _one(rows, uni, period=None):
    hits = [r for r in rows if r.uni_account == uni and (period is None or r.period == period)]
    assert len(hits) == 1, (uni, period, [(r.uni_account, r.period) for r in rows])
    return hits[0]


def test_company_row_twd():
    c = adapt_company_twse(_fx("Q1_FY2025", {}))
    assert c.currency == "TWD" and c.exchange == "TWSE" and c.fiscal_year_end_month == 12


def test_q1_ytd_is_single_quarter():
    rows = adapt_twse_facts(_fx("Q1_FY2025",
        {"revenue": _fact(100.0, "income_statement", 4000, "ytd")}, "2025-03-31"))
    r = _one(rows, "revenue")
    assert r.period == "Q1_FY2025" and r.period_kind == "quarter_duration"
    assert r.unit == "TWD_thousands" and r.status == "SOURCE_OF_TRUTH"
    assert r.version == "GAAP" and r.statement == "IS" and r.weight == 1


def test_q2_ytd_relabels_6m_and_dq_promotes():
    rows = adapt_twse_facts(_fx("Q2_FY2025", {
        "revenue":     _fact(220.0, "income_statement", 4000, "ytd"),
        "revenue__q":  _fact(120.0, "income_statement", 4000, "quarter"),
    }))
    ytd = _one(rows, "revenue", "6M_FY2025")
    assert ytd.period_kind == "ytd_duration"
    dq = _one(rows, "revenue", "Q2_FY2025")
    assert dq.period_kind == "quarter_duration" and dq.status == "SOURCE_OF_TRUTH"
    assert dq.provenance["disclosed_single_quarter"] is True


def test_annual_is_cf_fy_but_bs_q4():
    rows = adapt_twse_facts(_fx("Q4_FY2024", {
        "revenue":      _fact(500.0, "income_statement", 4000, "ytd"),
        "net_cash_from_operating": _fact(80.0, "cash_flow_operating", 8010, "ytd"),
        "total_assets": _fact(999.0, "balance_sheet_assets", 1900, "instant"),
    }, "2024-12-31"))
    assert _one(rows, "revenue").period == "FY2024"
    assert _one(rows, "revenue").period_kind == "fy_annual_duration"
    assert _one(rows, "net_cash_from_operating").period == "FY2024"
    bs = _one(rows, "total_assets")
    assert bs.period == "Q4_FY2024" and bs.period_kind == "instant_period_end"  # Argue: 年末 BS=Q4_FY


def test_quarterly_bs_keeps_q_label():
    rows = adapt_twse_facts(_fx("Q2_FY2025",
        {"total_assets": _fact(900.0, "balance_sheet_assets", 1900, "instant")}))
    assert _one(rows, "total_assets").period == "Q2_FY2025"


def test_eps_unit_twd_per_share():
    rows = adapt_twse_facts(_fx("Q1_FY2025",
        {"eps_basic": _fact(1.23, "income_statement", 9710, "ytd")}, "2025-03-31"))
    assert _one(rows, "eps_basic").unit == "TWD_per_share"


def test_capex_sign_flips_to_positive_outflow():
    # Argue 關鍵刀:台股揭 -502002(帶號流出);共用 FCF 規則 coef=-1 期望正支出
    rows = adapt_twse_facts(_fx("Q1_FY2025",
        {"capital_expenditures": _fact(-502002.0, "cash_flow_investing", 8021, "ytd")},
        "2025-03-31"))
    assert _one(rows, "capital_expenditures").value == 502002.0


def test_net_flows_keep_signed_values():
    rows = adapt_twse_facts(_fx("Q1_FY2025",
        {"net_cash_from_investing": _fact(-511174.0, "cash_flow_investing", 8020, "ytd")},
        "2025-03-31"))
    assert _one(rows, "net_cash_from_investing").value == -511174.0


def test_cash_balances_excluded_net_change_kept():
    # Argue 關鍵刀:balance 進了重建流會被 FY−9M 硬算
    rows = adapt_twse_facts(_fx("Q1_FY2025", {
        "beginning_cash":     _fact(2048546.0, "cash_flow_summary", 8045, "ytd"),
        "ending_cash":        _fact(1907355.0, "cash_flow_summary", 8050, "ytd"),
        "net_change_in_cash": _fact(-141191.0, "cash_flow_summary", 8040, "ytd"),
    }, "2025-03-31"))
    unis = {r.uni_account for r in rows}
    assert unis == {"net_change_in_cash"}


def test_provenance_and_concept_carried():
    rows = adapt_twse_facts(_fx("Q1_FY2025",
        {"revenue": _fact(100.0, "income_statement", 4000, "ytd", "ifrs-full:Revenue")},
        "2025-03-31"))
    r = _one(rows, "revenue")
    assert r.source_account == "ifrs-full:Revenue" and r.xbrl_tag == "ifrs-full:Revenue"
    assert r.provenance["market"] == "TW"
    assert r.provenance["substatement"] == "income_statement"
    assert r.period_end == "2025-03-31" and r.cell_id


def test_unexpected_top_unit_fails_closed():
    bad = _fx("Q1_FY2025", {})
    bad["unit"] = "TWD_millions"
    try:
        adapt_twse_facts(bad)
        assert False, "should raise"
    except ValueError:
        pass


def test_reconcile_disclosed_quarters():
    fx = {"ticker": "3081", "report_category": "ir", "unit": "TWD_thousands",
          "periods": ["Q1_FY2025", "Q2_FY2025"],
          "facts_by_period": {
              "Q1_FY2025": {"period_end": "2025-03-31", "report_category": "ir",
                  "facts": {"revenue": _fact(100.0, "income_statement", 4000, "ytd")}},
              "Q2_FY2025": {"period_end": "2025-06-30", "report_category": "ir",
                  "facts": {"revenue":    _fact(220.0, "income_statement", 4000, "ytd"),
                            "revenue__q": _fact(120.0, "income_statement", 4000, "quarter"),
                            "eps_basic":    _fact(2.0, "income_statement", 9710, "ytd"),
                            "eps_basic__q": _fact(1.1, "income_statement", 9710, "quarter")}}}}
    rep = reconcile_disclosed_quarters(fx)
    rev = [r for r in rep if r["uni_account"] == "revenue"][0]
    assert rev["status"] == "MATCH" and rev["ytd_diff"] == 120.0
    eps = [r for r in rep if r["uni_account"] == "eps_basic"][0]
    assert eps["status"] == "SKIPPED_NON_ADDITIVE"   # per-share 不做 ytd 差對帳


def test_reconcile_flags_mismatch():
    fx = {"ticker": "3081", "report_category": "ir", "unit": "TWD_thousands",
          "periods": ["Q1_FY2025", "Q2_FY2025"],
          "facts_by_period": {
              "Q1_FY2025": {"period_end": "2025-03-31", "report_category": "ir",
                  "facts": {"revenue": _fact(100.0, "income_statement", 4000, "ytd")}},
              "Q2_FY2025": {"period_end": "2025-06-30", "report_category": "ir",
                  "facts": {"revenue":    _fact(220.0, "income_statement", 4000, "ytd"),
                            "revenue__q": _fact(119.0, "income_statement", 4000, "quarter")}}}}
    rev = [r for r in reconcile_disclosed_quarters(fx) if r["uni_account"] == "revenue"][0]
    assert rev["status"] == "MISMATCH" and rev["diff"] == -1.0
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python3 -m pytest ~/AI_Agent/scripts/tests/test_twse_json_adapter.py -v`
Expected: FAIL(ModuleNotFoundError: twse_json_adapter)

- [ ] **Step 3: 實作 adapter**

```python
# ~/AI_Agent/Tools/research-tools/_shared/twse_json_adapter.py
"""TWSE parse facts → FactRow adapter(市場無關 derive 的台股入口)。

鏡像 sec_json_adapter:derive engine 只認 FactRow,本模組把
parse-twse-ixbrl 的 {TICKER}_twse_facts.json(facts_by_period keyed-dict)
攤平成 FactRow list。Spec:
docs/superpowers/specs/2026-07-02-derive-market-agnostic-design.md §4。

轉換規則(spec §4 表):
  2a  IS/CF duration:Q1 ytd→Q1_FY(單季);Q2/Q3 ytd→6M/9M_FY;年報→FY
  2b  BS instant:恆為 Q{n}_FY —— 年報期末 BS = Q4_FY(rules_crossperiod
      的年度比率用 Q4_FY label 查期末餘額;標成 FY 會整組靜默跳過)
  3   __q 揭露單季 → Q{n}_FY quarter_duration,SOURCE_OF_TRUTH(揭露值優先;
      engine rules_q2q3/rules_q4 看到單季已存在即跳過重建)
  4   unit:每 row TWD_thousands;EPS row TWD_per_share
  7   符號:capital_expenditures 翻成正支出(共用 FCF 規則 coef=-1 的 SEC 慣例);
      淨流量(investing/financing/operating/fx/net_change)維持帶號
  8   beginning_cash/ending_cash 為餘額非流量,排除於 fact 流(rules_q4 選
      重建對象只看 statement+unit,餘額會被 FY−9M 硬算)
"""
from __future__ import annotations

from . import cell_id as _id
from .period_kind import infer_period_kind
from .sec_json_adapter import CompanyRow, FactRow

_STMT_MAP = {
    "income_statement": "IS",
    "balance_sheet_assets": "BS",
    "balance_sheet_liabilities": "BS",
    "balance_sheet_equity": "BS",
    "cash_flow_operating": "CF",
    "cash_flow_investing": "CF",
    "cash_flow_financing": "CF",
    "cash_flow_summary": "CF",
}
_EPS_UNIS = {"eps_basic", "eps_diluted"}
# CF 現金「餘額」(非流量)— 不得進入重建 fact 流(spec §4 規則 8)。
_CASH_BALANCE_KEYS = {"beginning_cash", "ending_cash"}
# 台股 CF 帶號加總慣例 → 共用引擎期望「正的支出」的科目(spec §4 規則 7)。
_SIGN_FLIP_TO_POSITIVE_OUTFLOW = {"capital_expenditures"}


def adapt_company_twse(facts_json: dict) -> CompanyRow:
    t = str(facts_json["ticker"])
    return CompanyRow(ticker=t, company_name=t, exchange="TWSE", cik="",
                      currency="TWD", fiscal_year_end_month=12,
                      filings={}, sign_flip_concepts=[])


def _period_label(period: str, stmt: str, is_q_variant: bool) -> str:
    q, fy = period.split("_FY")
    qn = int(q[1])
    if stmt == "BS":
        return period            # 2b:年末 BS = Q4_FY{Y},季 BS = Q{n}_FY{Y}
    if is_q_variant or qn == 1:
        return period            # 3 / 2a:揭露單季、Q1 ytd 即單季
    if qn == 4:
        return f"FY{fy}"         # 2a:年報 IS/CF 累計
    return f"{qn * 3}M_FY{fy}"   # 2a:6M / 9M


def adapt_twse_facts(facts_json: dict) -> list[FactRow]:
    ticker = str(facts_json["ticker"])
    top_unit = facts_json.get("unit")
    if top_unit != "TWD_thousands":
        raise ValueError(f"unexpected TWSE facts unit: {top_unit!r} (fail-closed)")
    rows: list[FactRow] = []
    for period, pdata in facts_json.get("facts_by_period", {}).items():
        period_end = pdata.get("period_end")
        cat = pdata.get("report_category")
        for key, fact in pdata.get("facts", {}).items():
            is_q = key.endswith("__q")
            base = key[:-3] if is_q else key
            if base in _CASH_BALANCE_KEYS:
                continue
            stmt = _STMT_MAP[fact["statement"]]
            label = _period_label(period, stmt, is_q)
            unit = "TWD_per_share" if base in _EPS_UNIS else "TWD_thousands"
            value = float(fact["value"])
            if base in _SIGN_FLIP_TO_POSITIVE_OUTFLOW:
                value = -value
            period_kind = infer_period_kind(stmt, label)
            concept = fact.get("xbrl_concept") or ""
            provenance = {
                "source_filing": "TWSE_iXBRL",
                "market": "TW",
                "report_category": cat,
                "substatement": fact["statement"],
                "disclosed_single_quarter": is_q,
            }
            cid = _id.facts_cell_id(
                ticker=ticker, period=label, period_kind=period_kind,
                version="GAAP", statement=stmt, uni_account=base,
                source_account=concept, xbrl_tag=concept or None,
            )
            rows.append(FactRow(
                cell_id=cid, ticker=ticker, period=label, period_end=period_end,
                period_kind=period_kind, statement=stmt, version="GAAP",
                uni_account=base, source_account=concept, xbrl_tag=concept or None,
                value=value, weight=1, unit=unit, status="SOURCE_OF_TRUTH",
                ordinal=None, long_tail_metadata=None, provenance=provenance,
            ))
    return rows


def reconcile_disclosed_quarters(facts_json: dict, tol: float = 0.0) -> list[dict]:
    """spec §4 __q 對帳:__q 升格後 engine 跳過重建 → conflicts 統計抓不到
    「揭露單季 vs YTD 差」;此函式補上該檢查。per-share(EPS)非加性,跳過。"""
    fbp = facts_json.get("facts_by_period", {})
    out: list[dict] = []
    for period, pdata in fbp.items():
        q, fy = period.split("_FY")
        qn = int(q[1])
        prior_facts = fbp.get(f"Q{qn - 1}_FY{fy}", {}).get("facts", {})
        for key, fact in pdata.get("facts", {}).items():
            if not key.endswith("__q"):
                continue
            base = key[:-3]
            if base in _EPS_UNIS:
                out.append({"period": period, "uni_account": base,
                            "status": "SKIPPED_NON_ADDITIVE",
                            "disclosed_q": fact["value"]})
                continue
            cur = pdata["facts"].get(base)
            prev = prior_facts.get(base)
            if cur is None or prev is None:
                out.append({"period": period, "uni_account": base,
                            "status": "MISSING_YTD_INPUT",
                            "disclosed_q": fact["value"]})
                continue
            expected = cur["value"] - prev["value"]
            diff = fact["value"] - expected
            out.append({"period": period, "uni_account": base,
                        "status": "MATCH" if abs(diff) <= tol else "MISMATCH",
                        "disclosed_q": fact["value"], "ytd_diff": expected,
                        "diff": diff})
    return out
```

- [ ] **Step 4: 跑測試確認通過**

Run: `python3 -m pytest ~/AI_Agent/scripts/tests/test_twse_json_adapter.py -v`
Expected: 全 PASS

- [ ] **Step 5: Commit**

```bash
cd ~/AI_Agent && git add Tools/research-tools/_shared/twse_json_adapter.py scripts/tests/test_twse_json_adapter.py \
  && git commit -m "feat(_shared): twse_json_adapter - TWSE facts to FactRow (period relabel, __q promote, sign-normalize capex, cash-balance exclusion, __q reconciliation)"
```

---

### Task 7: engine 參數化(TDD;美股行為凍結)

**Files:**
- Modify: `~/CC_Switch_Config/skills/derive-base/scripts/rules_q4.py:47-50`
- Modify: `~/CC_Switch_Config/skills/derive-base/scripts/tolerance.py:13-19`
- Modify: `~/CC_Switch_Config/skills/derive-base/scripts/rules_identity.py`(allowlist 6-tuple op + D&A 規則)
- Modify: `~/CC_Switch_Config/skills/derive-analytics/scripts/rules_ratios.py:130-131, 424, 429`
- Test: `~/AI_Agent/scripts/tests/test_derive_tw_params.py`

**Interfaces:**
- Consumes: Task 6 的 FactRow(TWD 單位)。
- Produces: engine 接受 `TWD_thousands` additive;`IDENTITY_DA_DEP_PLUS_AMORT` 規則(inputs=`depreciation_expense`+`amortization_expense`,美股無此二 key → 結構性不觸發);per-share 輸出單位隨幣別。

- [ ] **Step 1: 寫失敗測試**

```python
# ~/AI_Agent/scripts/tests/test_derive_tw_params.py
"""Engine parameterization for TWD (derive-A spec §5). US behavior frozen by
Gate 3 (Task 9); these tests lock the TW-side semantics unit-level."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "Tools" / "research-tools"))
sys.path.insert(0, "/Users/mensch5566/CC_Switch_Config/skills/derive-base/scripts")
sys.path.insert(0, "/Users/mensch5566/CC_Switch_Config/skills/derive-analytics/scripts")

from _shared.sec_json_adapter import FactRow


def _row(uni, period, value, *, stmt="IS", unit="TWD_thousands", kind="quarter_duration",
         pe="2025-03-31", version="GAAP"):
    return FactRow(cell_id=f"t::{uni}::{period}", ticker="3081", period=period,
                   period_end=pe, period_kind=kind, statement=stmt, version=version,
                   uni_account=uni, source_account="ifrs-full:X", xbrl_tag="ifrs-full:X",
                   value=value, weight=1, unit=unit, status="SOURCE_OF_TRUTH",
                   ordinal=None, long_tail_metadata=None, provenance={})


def test_q4_reconstruction_accepts_twd():
    from rules_q4 import q4_candidates
    facts = [
        _row("revenue", "FY2024", 500.0, kind="fy_annual_duration", pe="2024-12-31"),
        _row("revenue", "9M_FY2024", 380.0, kind="ytd_duration", pe="2024-09-30"),
    ]
    cands = q4_candidates(facts)
    assert len(cands) == 1
    assert cands[0].value == 120.0 and cands[0].unit == "TWD_thousands"
    assert cands[0].rule_id == "Q4_FY_MINUS_9M"


def test_q4_eps_approx_never_fires_for_twd_per_share():
    # spec §5 row 4:_EPS_UNIT="USD_per_share" 即是 market gate — TW 留空是紀律
    from rules_q4 import q4_eps_approx_candidates
    facts = [
        _row("eps_basic", "FY2024", 4.66, unit="TWD_per_share", kind="fy_annual_duration", pe="2024-12-31"),
        _row("eps_basic", "Q1_FY2024", 1.0, unit="TWD_per_share"),
        _row("eps_basic", "Q2_FY2024", 1.2, unit="TWD_per_share"),
        _row("eps_basic", "Q3_FY2024", 1.3, unit="TWD_per_share"),
    ]
    assert q4_eps_approx_candidates(facts) == []


def test_tolerance_has_twd_entries():
    from tolerance import ABS_TOL_BY_UNIT
    assert ABS_TOL_BY_UNIT["TWD_thousands"] == 1.0
    assert ABS_TOL_BY_UNIT["TWD_per_share"] == 0.01


def test_da_identity_from_split_components():
    from rules_identity import apply_static_allowlist
    facts = [
        _row("depreciation_expense", "Q1_FY2025", 30.0, stmt="CF"),
        _row("amortization_expense", "Q1_FY2025", 12.0, stmt="CF"),
    ]
    cands = apply_static_allowlist(facts, "GAAP")
    da = [c for c in cands if c.uni_account == "depreciation_and_amortization"]
    assert len(da) == 1
    assert da[0].value == 42.0 and da[0].statement == "CF"
    assert da[0].rule_id == "IDENTITY_DA_DEP_PLUS_AMORT"
    assert da[0].extras["formula"] == "depreciation_expense + amortization_expense"


def test_da_identity_skips_when_da_direct():
    from rules_identity import apply_static_allowlist
    facts = [
        _row("depreciation_expense", "Q1_FY2025", 30.0, stmt="CF"),
        _row("amortization_expense", "Q1_FY2025", 12.0, stmt="CF"),
        _row("depreciation_and_amortization", "Q1_FY2025", 42.0, stmt="CF"),
    ]
    cands = apply_static_allowlist(facts, "GAAP")
    assert not [c for c in cands if c.uni_account == "depreciation_and_amortization"]


def test_existing_allowlist_formula_unchanged():
    # Gate 3 前哨:5-tuple 舊規則的 formula 字串必須維持 " - ".join
    from rules_identity import apply_static_allowlist
    facts = [
        _row("revenue", "Q1_FY2025", 100.0),
        _row("cost_of_goods_sold", "Q1_FY2025", 60.0),
    ]
    gp = [c for c in apply_static_allowlist(facts, "GAAP")
          if c.uni_account == "gross_profit"]
    assert gp and gp[0].extras["formula"] == "revenue - cost_of_goods_sold"


def test_money_scale_accepts_twd():
    import rules_ratios as rr
    assert rr._MONEY_SCALE["TWD_thousands"] == 1e3
    assert rr._MONEY_SCALE["USD_millions"] == 1e6   # US 原值不動
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python3 -m pytest ~/AI_Agent/scripts/tests/test_derive_tw_params.py -v`
Expected: FAIL(TWD 不在 allowlist、無 _MONEY_SCALE、無 D&A 規則)

- [ ] **Step 3: 實作四處修改**

(a) `rules_q4.py:47-50`:

```python
_ADDITIVE_Q4_UNITS = frozenset({
    "USD_thousands",
    "USD_millions",
    "TWD_thousands",   # derive-A: TWSE additive money (spec §5.1)
})
```

(b) `tolerance.py` `ABS_TOL_BY_UNIT` 加兩行:

```python
    "TWD_thousands":     1.0,
    "TWD_per_share":     0.01,
```

(c) `rules_identity.py`:allowlist 支援可選第 6 欄 formula op(舊 5-tuple 行為不變),並加 D&A 規則:

```python
# STATIC_ALLOWLIST_GAAP 末尾追加:
    # derive-A(spec §5.5):D&A = 折舊 + 攤銷。台股 CF 分列揭露
    # depreciation_expense / amortization_expense;美股 facts 無此二 key
    # → 此規則對美股結構性不觸發(Gate 3 另行凍結驗證)。若該期已直接
    # 揭露 depreciation_and_amortization,上方 direct-skip 讓位揭露值。
    ("depreciation_and_amortization", ("depreciation_expense", "amortization_expense"),
        lambda v: v["depreciation_expense"] + v["amortization_expense"],
        "IDENTITY_DA_DEP_PLUS_AMORT", 4, " + "),
```

`apply_static_allowlist` 迴圈解包改成:

```python
    for entry in allowlist:
        output_uni, requires, fn, rule_id, priority = entry[:5]
        formula_op = entry[5] if len(entry) > 5 else " - "
```

且 `extras={"formula": " - ".join(requires)}` 改為 `extras={"formula": formula_op.join(requires)}`。

(d) `rules_ratios.py`:

```python
# line 130-131 →
_MONEY_SCALE = {"USD_millions": 1e6, "USD_thousands": 1e3, "USD": 1.0,
                "TWD_thousands": 1e3}   # derive-A: currency-aware (spec §5.2)
_USD_SCALE = _MONEY_SCALE   # back-compat alias(既有引用/測試不破)
_SHARE_SCALE = {"millions_shares": 1e6, "thousands_shares": 1e3, "shares": 1.0}
```

line 424 `eq_scale = _USD_SCALE.get(...)` → `eq_scale = _MONEY_SCALE.get(...)`;
line 429 `out_unit = "USD_per_share"` → 隨幣別:

```python
                    out_unit = next(iter(num_units)).split("_")[0] + "_per_share"
```

(美股 num_units={"USD_millions"} → "USD_per_share",原行為不變;BVPS 台股缺股數本就不觸發。)

- [ ] **Step 4: 跑新測試 + 兩 skill 既有測試**

Run: `python3 -m pytest ~/AI_Agent/scripts/tests/test_derive_tw_params.py ~/AI_Agent/scripts/tests/ -v -k "derive or ratio or adapter"`
Expected: 全 PASS

- [ ] **Step 5: Commit**

```bash
cd ~/CC_Switch_Config && git add skills/derive-base skills/derive-analytics \
  && git commit -m "feat(derive): parameterize engine for TWD - additive allowlist, tolerance, _MONEY_SCALE, currency per-share unit, IDENTITY_DA_DEP_PLUS_AMORT (derive-A spec sec5)"
cd ~/AI_Agent && git add scripts/tests/test_derive_tw_params.py && git commit -m "test: TW engine parameterization locks (TWD allowlist, no TW Q4 EPS, DA identity)"
```

---

### Task 8: `--market tw` 接線(io_loader + 兩支 CLI)

**Files:**
- Modify: `~/CC_Switch_Config/skills/derive-base/scripts/io_loader.py`
- Modify: `~/CC_Switch_Config/skills/derive-base/scripts/derive_base.py:54-76`
- Modify: `~/CC_Switch_Config/skills/derive-analytics/scripts/io_loader.py`
- Modify: `~/CC_Switch_Config/skills/derive-analytics/scripts/derive_analytics.py:51-66`
- Test: `~/AI_Agent/scripts/tests/test_derive_market_tw_wiring.py`

**Interfaces:**
- Consumes: Task 6 `adapt_twse_facts`。
- Produces: `derive_base.py --ticker 3081 --market tw` 端到端可跑,輸出 `.../MOPS Filings/Skill_Output/derive-base/<ts>/3081_derived.json`;analytics 同型。`--market us`(default)路徑一個字不變。

- [ ] **Step 1: 寫失敗測試(discover/load 層,不打真 CLI)**

```python
# ~/AI_Agent/scripts/tests/test_derive_market_tw_wiring.py
"""--market tw source discovery + loading (derive-A spec §5.6)."""
import json, sys
from pathlib import Path

sys.path.insert(0, "/Users/mensch5566/CC_Switch_Config/skills/derive-base/scripts")
import io_loader as db_io


def _mk_tw_vault(tmp_path: Path) -> Path:
    d = tmp_path / "Khouse/Semiconductors/聯亞/01_Source/MOPS Filings/Skill_Output/parse-twse-ixbrl"
    d.mkdir(parents=True)
    (d / "3081_twse_facts.json").write_text(json.dumps({
        "ticker": "3081", "report_category": "ir", "unit": "TWD_thousands",
        "periods": ["Q1_FY2025"],
        "facts_by_period": {"Q1_FY2025": {"period_end": "2025-03-31", "report_category": "ir",
            "facts": {"revenue": {"value": 100.0, "statement": "income_statement",
                                  "sort_order": 4000, "period_kind": "ytd",
                                  "xbrl_concept": "ifrs-full:Revenue"}}}}}))
    return tmp_path


def test_discover_sources_tw_globs_chinese_folder(tmp_path):
    vault = _mk_tw_vault(tmp_path)
    srcs = db_io.discover_sources_tw(vault, "3081")
    assert srcs["twse_facts"] is not None and srcs["twse_facts"].exists()


def test_load_facts_tw_returns_factrows(tmp_path):
    vault = _mk_tw_vault(tmp_path)
    rows = db_io.load_facts_tw(db_io.discover_sources_tw(vault, "3081"))
    assert len(rows) == 1 and rows[0].unit == "TWD_thousands"
    assert rows[0].period == "Q1_FY2025"


def test_output_dir_tw_lands_beside_facts(tmp_path):
    vault = _mk_tw_vault(tmp_path)
    srcs = db_io.discover_sources_tw(vault, "3081")
    od = db_io.output_dir_tw(srcs, "2026-07-02-1200")
    assert od.name == "2026-07-02-1200" and od.parent.name == "derive-base"
    assert od.parent.parent.name == "Skill_Output"


def test_missing_facts_fails_closed(tmp_path):
    srcs = db_io.discover_sources_tw(tmp_path, "9999")
    try:
        db_io.load_facts_tw(srcs)
        assert False, "should raise"
    except FileNotFoundError:
        pass
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python3 -m pytest ~/AI_Agent/scripts/tests/test_derive_market_tw_wiring.py -v`
Expected: FAIL(no attribute discover_sources_tw)

- [ ] **Step 3: 實作 derive-base 側**

`io_loader.py` 末尾加:

```python
# ---- derive-A: --market tw sources(spec §5.6)---------------------------
# 台股資料夾用中文公司名(聯亞/台達電…),以 ticker 檔名 glob 定位。

def discover_sources_tw(vault_base: Path, ticker: str) -> dict[str, Path | None]:
    hits = sorted(vault_base.glob(
        "Khouse/Semiconductors/*/01_Source/MOPS Filings/Skill_Output/"
        f"parse-twse-ixbrl/{ticker}_twse_facts.json"))
    return {"twse_facts": hits[0] if hits else None}


def load_facts_tw(sources: dict[str, Path | None]) -> list[FactRow]:
    from _shared.twse_json_adapter import adapt_twse_facts
    p = sources.get("twse_facts")
    if p is None or not p.exists():
        raise FileNotFoundError(f"twse_facts json missing for --market tw: {p}")
    return adapt_twse_facts(json.loads(p.read_text()))


def output_dir_tw(sources: dict[str, Path | None], run_stamp: str) -> Path:
    skill_out = sources["twse_facts"].parent.parent    # .../Skill_Output
    d = skill_out / "derive-base" / run_stamp
    d.mkdir(parents=True, exist_ok=True)
    return d
```

`derive_base.py main()` 改(市場分支;us 路徑一字不動):

```python
    ap.add_argument("--ticker", required=True)
    ap.add_argument("--market", choices=("us", "tw"), default="us",
                    help="us = SEC pipeline (default) / tw = TWSE pipeline")
    ...
    ticker = args.ticker.upper()
    vault = Path(args.vault).expanduser()

    if args.market == "tw":
        srcs = discover_sources_tw(vault, args.ticker)
        facts = load_facts_tw(srcs)
        edges = []                       # 台股無 calc linkbase(spec §5 輸入差異)
        calc_rules = calc_rules_from_edges(edges)
        qname_to_uni = {}
    else:
        srcs = discover_sources(vault, ticker)
        if srcs["gaap_inline"] is None or not srcs["gaap_inline"].exists():
            print(f"❌ {ticker} inline gaap.json not found under {vault}", file=sys.stderr)
            return 2
        facts = load_facts(srcs)
        edges = load_calc_edges(srcs)
        calc_rules = calc_rules_from_edges(edges)
        inline = json.loads(srcs["gaap_inline"].read_text())
        qname_to_uni = build_qname_to_uni(inline)
```

之後 `od = output_dir(vault, ticker, run_stamp)` 改成:

```python
    od = (output_dir_tw(srcs, run_stamp) if args.market == "tw"
          else output_dir(vault, ticker, run_stamp))
```

NLM 驗證段(line 106 起)加 gate:`cc_run = None if args.market == "tw" else discover_cross_check_run(vault, ticker)`(台股 cross-check 目錄名不同,本就找不到;顯式化)。ticker 變數:tw 用 `args.ticker`(數字)貫穿。

- [ ] **Step 4: 實作 derive-analytics 側(同型)**

`derive-analytics/scripts/io_loader.py` 加(derived rows 轉換抽成 helper 供兩市場共用):

```python
def _derived_rows_to_facts(derived_doc: dict) -> list:
    rows = []
    for r in derived_doc.get("derived_metrics", []):
        try:
            rows.append(FactRow(
                cell_id=r.get("cell_id", ""), ticker=r["ticker"], period=r["period"],
                period_end=r["period_end"], period_kind=r["period_kind"],
                statement=r["statement"], version=r["version"],
                uni_account=r["uni_account"], source_account="(derived)", xbrl_tag=None,
                value=float(r["value"]), weight=1, unit=r["unit"],
                status=r.get("status", "DERIVED_FROM_DISCLOSED"),
                ordinal=None, long_tail_metadata=None,
                provenance=r.get("provenance", {}),
            ))
        except (KeyError, TypeError, ValueError):
            continue
    return rows


def discover_sources_tw(vault_base: Path, ticker: str) -> dict[str, Path | None]:
    hits = sorted(vault_base.glob(
        "Khouse/Semiconductors/*/01_Source/MOPS Filings/Skill_Output/"
        f"parse-twse-ixbrl/{ticker}_twse_facts.json"))
    out: dict[str, Path | None] = {"twse_facts": hits[0] if hits else None,
                                   "derive_base": None}
    if hits:
        derive_dir = hits[0].parent.parent / "derive-base"
        if derive_dir.exists():
            runs = sorted([d for d in derive_dir.iterdir()
                           if d.is_dir() and d.name[:4].isdigit()], reverse=True)
            if runs:
                cand = runs[0] / f"{ticker}_derived.json"
                out["derive_base"] = cand if cand.exists() else None
    return out


def load_facts_tw(sources: dict[str, Path | None]) -> list:
    from _shared.twse_json_adapter import adapt_twse_facts
    p = sources.get("twse_facts")
    if p is None or not p.exists():
        raise FileNotFoundError(f"twse_facts json missing for --market tw: {p}")
    rows = adapt_twse_facts(json.loads(p.read_text()))
    if sources.get("derive_base") is not None:
        rows.extend(_derived_rows_to_facts(json.loads(sources["derive_base"].read_text())))
    return rows


def output_dir_tw(sources: dict[str, Path | None], run_stamp: str) -> Path:
    skill_out = sources["twse_facts"].parent.parent
    d = skill_out / "derive-analytics" / run_stamp
    d.mkdir(parents=True, exist_ok=True)
    return d
```

既有 `load_facts` 的 derive_base 轉換迴圈改呼叫 `_derived_rows_to_facts`(純重構,Gate 3 保護)。`derive_analytics.py main()` 加同樣的 `--market` 分支(discover/load/output_dir 三處),其餘不動。

- [ ] **Step 5: 跑接線測試 + adapter/param 測試**

Run: `python3 -m pytest ~/AI_Agent/scripts/tests/test_derive_market_tw_wiring.py ~/AI_Agent/scripts/tests/test_twse_json_adapter.py ~/AI_Agent/scripts/tests/test_derive_tw_params.py -v`
Expected: 全 PASS

- [ ] **Step 6: Commit**

```bash
cd ~/CC_Switch_Config && git add skills/derive-base skills/derive-analytics \
  && git commit -m "feat(derive): --market tw wiring - TW source discovery via glob, adapter loading, MOPS output dirs; us path unchanged (derive-A spec sec5.6)"
cd ~/AI_Agent && git add scripts/tests/test_derive_market_tw_wiring.py && git commit -m "test: --market tw discovery/load/output wiring"
```

---

### Task 9: Gate 3 — 美股零回歸驗證

**Files:**
- Uses: Task 1 的 `us_baseline/` + `gate3_compare.py`

- [ ] **Step 1: 重跑 5 檔美股 + 收新輸出**

```bash
mkdir -p "$SCRATCH/us_after"
for T in MU LITE INTC SNDK AAOI; do
  python3 ~/CC_Switch_Config/skills/derive-base/scripts/derive_base.py --ticker $T
  python3 ~/CC_Switch_Config/skills/derive-analytics/scripts/derive_analytics.py --ticker $T
  DB=$(ls -td ~/Obsidian/Khouse/Semiconductors/$T/01_Source/SEC\ Filings/Skill_Output/derive-base/*/ | head -1)
  DA=$(ls -td ~/Obsidian/Khouse/Semiconductors/$T/01_Source/SEC\ Filings/Skill_Output/derive-analytics/*/ | head -1)
  cp "$DB/${T}_derived.json" "$SCRATCH/us_after/"; cp "$DA/${T}_analytics.json" "$SCRATCH/us_after/"
done
```

- [ ] **Step 2: 比對**

Run: `python3 $SCRATCH/gate3_compare.py $SCRATCH/us_baseline $SCRATCH/us_after`
Expected: 10 行 ✅,exit 0。**任何 DIFF → 停**:先查 `IDENTITY_DA_DEP_PLUS_AMORT` 是否對美股觸發(不應該;若觸發改成 TW-only gate 再回 Task 7),再查 formula 字串(5-tuple op 預設 `" - "` 是否保住)。

---

### Task 10: 台股端到端 + Gate 2 交叉驗證報告

**Files:**
- Create: `$SCRATCH/gate2_report.py`
- Output: `$SCRATCH/gate2_{3081,2308}.md`(人工 audit 表)

**Interfaces:**
- Consumes: Task 8 CLI、Task 6 `reconcile_disclosed_quarters`、舊 `twse-derive` 輸出 `3081_twse_metrics.json`(歷史對照檔,唯讀)。

- [ ] **Step 1: 跑台股兩檔 derive**

```bash
python3 ~/CC_Switch_Config/skills/derive-base/scripts/derive_base.py --ticker 3081 --market tw
python3 ~/CC_Switch_Config/skills/derive-analytics/scripts/derive_analytics.py --ticker 3081 --market tw
python3 ~/CC_Switch_Config/skills/derive-base/scripts/derive_base.py --ticker 2308 --market tw
python3 ~/CC_Switch_Config/skills/derive-analytics/scripts/derive_analytics.py --ticker 2308 --market tw
```
Expected: 各產出 `.../MOPS Filings/Skill_Output/derive-{base,analytics}/<ts>/{T}_{derived,analytics}.json`,無 traceback。

- [ ] **Step 2: 寫 gate2_report.py**

```python
#!/usr/bin/env python3
"""Gate 2(spec §6):新舊 derive 交叉驗證 + Argue 追加檢查。
用法:gate2_report.py <ticker> <twse_facts.json> <derived.json> <analytics.json> [<old_twse_metrics.json>] <out.md>
"""
import json, sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / "AI_Agent/Tools/research-tools"))
from _shared.twse_json_adapter import reconcile_disclosed_quarters

# 直接可比:新 uni_account → 舊 twse-derive metric 名(spec §6 Gate 2 重分類版)
COMPARABLE = {"gross_margin_pct": "gross_margin", "operating_margin_pct": "operating_margin",
              "net_margin_pct": "net_margin", "effective_tax_rate": "effective_tax_rate",
              "current_ratio": "current_ratio"}
# 口徑不同(記錄不 fail):interest_coverage / roe / roa / debt_to_equity
NON_COMPARABLE = {"interest_coverage", "roe", "roa", "debt_to_equity"}

def main(argv):
    ticker, facts_p, derived_p, analytics_p = argv[0], argv[1], argv[2], argv[3]
    old_p, out_p = (argv[4], argv[5]) if len(argv) == 6 else (None, argv[4])
    facts = json.loads(Path(facts_p).read_text())
    derived = json.loads(Path(derived_p).read_text())["derived_metrics"]
    analytics = json.loads(Path(analytics_p).read_text())["analytics_metrics"]
    lines = [f"# Gate 2 — {ticker}", ""]
    fails = 0

    # (1) 無現金餘額重建 + 無台股 Q4 EPS(Argue 追加)
    bad_cash = [r for r in derived if r["uni_account"] in ("beginning_cash", "ending_cash")]
    bad_eps = [r for r in derived if r["uni_account"] in ("eps_basic", "eps_diluted")
               and r["period_kind"] == "derived_q4"]
    lines.append(f"- derived cash-balance rows: {len(bad_cash)} (must be 0)")
    lines.append(f"- derived TW Q4 EPS rows: {len(bad_eps)} (must be 0)")
    fails += len(bad_cash) + len(bad_eps)

    # (2) __q 對帳(engine conflicts 抓不到,spec §4)
    rec = reconcile_disclosed_quarters(facts)
    mism = [r for r in rec if r["status"] == "MISMATCH"]
    lines.append(f"- __q vs ytd-diff: {sum(r['status']=='MATCH' for r in rec)} MATCH / "
                 f"{len(mism)} MISMATCH / "
                 f"{sum(r['status']=='SKIPPED_NON_ADDITIVE' for r in rec)} EPS-skipped")
    for r in mism:
        lines.append(f"  - AUDIT: {r['period']} {r['uni_account']} disclosed={r['disclosed_q']} "
                     f"ytd_diff={r['ytd_diff']} diff={r['diff']}")

    # (3) capex 符號 raw 檢核(spec §6:FCF 可比的前置)
    capex_raw = [(p, d["facts"]["capital_expenditures"]["value"])
                 for p, d in facts["facts_by_period"].items()
                 if "capital_expenditures" in d["facts"]]
    pos_raw = [x for x in capex_raw if x[1] > 0]
    lines.append(f"- raw TW capex sign: {len(capex_raw)} rows, disclosed-positive={len(pos_raw)} (expect 0)")

    # (4) 新舊比率交叉驗證
    if old_p:
        old = json.loads(Path(old_p).read_text())["metrics_by_period"]
        new_by = {}
        for r in analytics:
            if r["period_kind"] == "quarter_duration" or r["period_kind"].startswith("derived_"):
                new_by[(r["period"], r["uni_account"])] = r["value"]
        lines.append("\n## 直接可比(tol=1e-9)\n\n| period | metric | old | new | ok |\n|---|---|---|---|---|")
        for period, met in sorted(old.items()):
            for new_uni, old_name in COMPARABLE.items():
                if old_name not in met:
                    continue
                ov = met[old_name]["value"]
                nv = new_by.get((period, new_uni))
                if nv is None:
                    lines.append(f"| {period} | {new_uni} | {ov:.6f} | (missing) | ⚠️ |")
                    continue
                ok = abs(ov - nv) < 1e-9
                fails += 0 if ok else 1
                lines.append(f"| {period} | {new_uni} | {ov:.6f} | {nv:.6f} | {'✅' if ok else '❌'} |")
        lines.append("\n## 口徑不同(記錄,不 fail): " + ", ".join(sorted(NON_COMPARABLE)))
    lines.append(f"\n**RESULT: {'PASS' if fails == 0 else f'FAIL ({fails})'}**")
    Path(out_p).write_text("\n".join(lines))
    print(f"→ {out_p}  fails={fails}")
    return 1 if fails else 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

**COMPARABLE 對帳注意**:舊 twse-derive 的 margin 是「單季值」算的(它自己重建單季);新 engine 的 quarter_duration/derived_q* 同口徑 → 逐 (period, metric) 對。舊檔 3081 路徑:`.../Skill_Output/twse-derive/3081_twse_metrics.json`。2308 無舊檔(twse-derive 沒跑過)→ 4 參數呼叫,只跑檢查 (1)-(3)。

- [ ] **Step 3: 跑 Gate 2**

```bash
V31="$VAULT/聯亞/01_Source/MOPS Filings/Skill_Output"
DB31=$(ls -td "$V31/derive-base"/*/ | head -1); DA31=$(ls -td "$V31/derive-analytics"/*/ | head -1)
python3 $SCRATCH/gate2_report.py 3081 "$V31/parse-twse-ixbrl/3081_twse_facts.json" \
  "$DB31/3081_derived.json" "$DA31/3081_analytics.json" \
  "$V31/twse-derive/3081_twse_metrics.json" "$SCRATCH/gate2_3081.md"
# 2308(無舊 metrics 對照)
V23=$(dirname "$(ls -d "$VAULT"/台達電*/01_Source/MOPS\ Filings/Skill_Output/parse-twse-ixbrl)")
DB23=$(ls -td "$V23/derive-base"/*/ | head -1); DA23=$(ls -td "$V23/derive-analytics"/*/ | head -1)
python3 $SCRATCH/gate2_report.py 2308 "$V23/parse-twse-ixbrl/2308_twse_facts.json" \
  "$DB23/2308_derived.json" "$DA23/2308_analytics.json" "$SCRATCH/gate2_2308.md"
```
Expected: 兩份 `RESULT: PASS`。MISMATCH 行(如官方重編)→ 人工 audit 判讀後記錄於報告,不自動蓋值。

- [ ] **Step 4: 抽查「新有舊無」指標(spec §6)**

quick_ratio / FCF / QoQ/YoY 各抽 2 期,人工用 facts JSON 手算核對(計算過程貼進 `$SCRATCH/gate2_spotcheck.md`)。Expected: 全對。

---

### Task 11: twse-derive 退役 + docs + 收尾

**Files:**
- Delete: `~/CC_Switch_Config/skills/twse-derive/`
- Modify: `~/CC_Switch_Config/cc-switch/skills-manifest.json`(移除 twse-derive entry)
- Modify: `~/CC_Switch_Config/skills/derive-base/SKILL.md` + `derive-analytics/SKILL.md`(CHANGELOG + `--market tw` 用法)
- Modify: `~/CC_Switch_Config/skills/parse-twse-ixbrl/skill.md 或 SKILL.md`(CHANGELOG:rename + concept)
- Modify: `~/AI_Agent/docs/STATUS.md`(台股 derive 統一 + twse-derive 退役)
- Delete: `~/AI_Agent/scripts/tests/test_twse_derive_pinned.py`(skill 已刪,pin 測試失去對象)

- [ ] **Step 1: Gate 2/3 全綠後刪 skill + manifest 除名**

```bash
cd ~/CC_Switch_Config
git rm -r skills/twse-derive
# skills-manifest.json:刪除 {"id": "twse-derive", ...} 那個 entry(手改)
bash scripts/sync-to-local.sh
rm ~/AI_Agent/scripts/tests/test_twse_derive_pinned.py
```

驗證:`ls ~/.cc-switch/skills/ | grep twse-derive` → 無;`python3 -m pytest ~/AI_Agent/scripts/tests/ -v` 全綠。
舊輸出 `Skill_Output/twse-derive/3081_twse_metrics.json` **保留**(歷史對照,spec §7)。

- [ ] **Step 2: docs 更新**

- 兩份 derive SKILL.md:CHANGELOG 加 derive-A 條目(TWD 參數化、D&A identity、`--market tw`、台股輸出位置);用法段加 tw 範例。
- parse-twse-ixbrl skill 文件:CHANGELOG 加 rename 全表 + cr 家族 + xbrl_concept。
- `docs/STATUS.md`:台股 derive 併入共用引擎、twse-derive 退役、Gate 1/2/3 結果一行摘要。

- [ ] **Step 3: 最終全測試 + Commit(兩 repo)+ memory**

```bash
python3 -m pytest ~/AI_Agent/scripts/tests/ ~/CC_Switch_Config/skills/parse-twse-ixbrl/tests/ \
  ~/CC_Switch_Config/skills/parse-tw-crosscheck/scripts/tests/ -v
cd ~/CC_Switch_Config && git add -A && git commit -m "feat(derive-A): retire twse-derive - TW now runs shared derive engine via --market tw; docs + manifest"
cd ~/AI_Agent && git add -A && git commit -m "docs(derive-A): STATUS + retire pin test; Gate 1/2/3 all green"
```

更新 memory `project_financials_skill_naming_refactor.md`(derive-A 完成狀態)+ save_memory 一筆完工摘要。

---

## Self-Review 紀錄

- **Spec coverage**:§0→T1/T9(live 基準)、§3→T3/T4/T5、§4→T6、§5→T7/T8、§6→T4(G1)/T9(G3)/T10(G2)、§7/§10 pin→T2、退役→T11、§8 測試→各 task Step 1。SG&A/compose/Phase E/前端 = Non-goals,無 task ✓。
- **Placeholder scan**:無 TBD;所有 code 步驟含完整 code ✓(Task 5 Step 3 的 RENAME dict 明確指向 Task 4 同一張表,避免兩處漂移)。
- **Type consistency**:`adapt_twse_facts`/`load_facts_tw`/`discover_sources_tw`/`output_dir_tw`/`reconcile_disclosed_quarters` 名稱在 T6/T8/T10 一致;`IDENTITY_DA_DEP_PLUS_AMORT` 在 T7 測試與實作一致;RENAME 表 T3=T4=T5 同表 ✓。
