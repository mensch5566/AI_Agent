# derive-analytics Rate-of-Change Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Change derive-analytics growth metrics from growth-rate `(cur−prior)/prior` (prior>0 guard) to rate-of-change `(cur−prior)/|prior|` (prior==0 guard only), and expand the growth family from 5 to ~22 universal IS 科目 (台美聯集), backend data only.

**Architecture:** Single deterministic touch in `_growth_candidate` (formula + guard), one EPS-class guard generalization in `_emit_growth`, a GROWTH_METRICS registry expansion, and two upsert-fallback rule_id lists. The generator derives all rule_ids; the engine emits only for uni_accounts a ticker's facts actually carry. No frontend, no schema migration, no derive-base change.

**Tech Stack:** Python 3.13 stdlib, pytest. Canonical SSOT = `~/CC_Switch_Config/skills/derive-analytics/`; run `bash ~/CC_Switch_Config/scripts/sync-to-local.sh` after edits. Supabase upsert via `~/AI_Agent/scripts/upsert_{sec,twse}_financials.py`.

## Global Constraints

- Canonical SSOT = `~/CC_Switch_Config/skills/derive-analytics/`; edit there, then `cd ~/CC_Switch_Config && bash scripts/sync-to-local.sh`.
- Tests run from the skill root: `cd ~/CC_Switch_Config/skills/derive-analytics && python3 -m pytest tests/ -q` (fallback `uv run --with pytest python3 -m pytest`).
- **Formula = rate of change**: `value = (cv − pv) / abs(pv)`; skip ONLY when `cv is None or pv is None or pv == 0`.
- **Invariant is NUMERIC value equivalence, NOT byte-identity**: existing positive-base growth rows keep the same `value` (abs(pv)==pv for pv>0); their `formula` string DOES change; provenance/updated_at/cell_id churn on re-upsert (snapshot delete+reinsert).
- **台美 parity 鐵律**: same-semantic IS lines use ONE canonical `uni_account` key + same formula across markets; genuinely different-semantic lines (台 selling_expenses vs 美 selling_general_administrative) keep distinct keys. The registry key MUST byte-match the spelling in the actual parse-output facts.
- **絕不動**: ROE/ROA/ROIC (incl. ROIC's NOPAT pretax/rate guard at rules_crossperiod L568/571), effective_tax_rate, DSO/DIO/DPO/CCC, asset_turnover, interest_coverage, net_debt_to_ebitda, all margins/BS ratios/bvps/fcf/ebitda — their `value` must be identical before/after.
- **EPS non-additive guard applies to ALL EPS metrics** (eps_diluted AND eps_basic): skip growth if either endpoint is a `derived_q4` EPS.
- Frontend `constants.ts` NOT touched. No Supabase migration (no rule_id CHECK exists — verified).
- Spec: `docs/superpowers/specs/2026-07-10-derive-analytics-rate-of-change-design.md` (v2, post-argue).

---

## File Structure

- `~/CC_Switch_Config/skills/derive-analytics/scripts/rules_crossperiod.py` — `_growth_candidate` (formula+guard), `_emit_growth` (EPS guard), `GROWTH_METRICS` (registry), comments.
- `~/CC_Switch_Config/skills/derive-analytics/tests/test_growth_qoq.py` — count assertion + new rate-of-change + expanded-metric tests.
- `~/CC_Switch_Config/skills/derive-analytics/tests/test_properties.py` — yoy property test (semantics change).
- `~/AI_Agent/scripts/upsert_sec_financials.py` + `upsert_twse_financials.py` — `DERIVE_ANALYTICS_RULE_IDS_FALLBACK`.
- `~/AI_Agent/docs/financials-view-schema.md` — canonical-key doc alignment (T0).
- Derived JSON outputs (vault Skill_Output) — regenerated in T5, not committed.

---

## Task 0: Canonical uni_account key reconciliation (DEFECT #1)

**Files:**
- Modify: `~/AI_Agent/docs/financials-view-schema.md` (doc alignment)
- Create: `~/AI_Agent/tmp/roc-plan/growth_metrics.txt` (the authoritative list, consumed by Task 3)

**Interfaces:**
- Produces: the exact `GROWTH_METRICS` Python list (facts-verified spellings) written to `growth_metrics.txt`, one uni_account per line.

- [ ] **Step 1: Enumerate IS uni_accounts actually present in every upserted ticker's facts**

Run:
```bash
mkdir -p ~/AI_Agent/tmp/roc-plan
python3 - <<'PY'
import json, glob, os
BASE_US="/Users/mensch5566/Obsidian/Khouse/Semiconductors/{t}/01_Source/SEC Filings/Skill_Output/parse-10QK-gaap/{t}_gaap_facts.json"
BASE_TW="/Users/mensch5566/Obsidian/Khouse/Semiconductors/{name}/01_Source/MOPS Filings/Skill_Output/parse-twse-ixbrl/{t}_twse_facts.json"
US=["INTC","AAOI","SNDK","LITE","MU","GLW"]
TW={"3081":"聯亞","2308":"台達電","6274":"台燿"}
seen=set()
for t in US:
    f=BASE_US.format(t=t)
    if not os.path.exists(f): print("MISSING",f); continue
    d=json.load(open(f)); rows=d.get("facts",d if isinstance(d,list) else [])
    seen|={r["uni_account"] for r in rows if r.get("statement")=="IS"}
for t,name in TW.items():
    f=BASE_TW.format(name=name,t=t)
    if not os.path.exists(f): print("MISSING",f); continue
    d=json.load(open(f))
    for node in d["facts_by_period"].values():
        seen|={k for k,v in node["facts"].items() if v.get("statement")=="income_statement"}
# Tier B semantic set (canonical spellings = whatever appears in `seen`)
TIER_B_CANDIDATES=[
 "revenue","gross_profit","operating_income","net_income","eps_diluted",       # existing 5
 "cost_of_goods_sold","income_before_taxes","income_tax_expense","eps_basic",   # main P&L
 "selling_expenses","general_admin_expenses","research_and_development",
 "expected_credit_loss","total_operating_expenses",                            # TW opex
 "selling_general_administrative",                                             # US opex
 "interest_income","interest_expense",
 "other_gains_losses","non_operating_income_expense",                          # TW non-op
 "other_nonoperating_income_expense",                                          # US non-op
 "net_income_total_pre_nci","net_income_nci",                                  # NI family
]
final=[k for k in TIER_B_CANDIDATES if k in seen or k.endswith("__q") is False and k in {x.replace("__q","") for x in seen}]
# keep only those actually present as a base key (strip __q variants when matching)
base_seen={x[:-3] if x.endswith("__q") else x for x in seen}
final=[k for k in TIER_B_CANDIDATES if k in base_seen]
missing=[k for k in TIER_B_CANDIDATES if k not in base_seen]
open("/Users/mensch5566/AI_Agent/tmp/roc-plan/growth_metrics.txt","w").write("\n".join(final)+"\n")
print("FINAL GROWTH_METRICS (",len(final),"):"); [print(" ",k) for k in final]
print("NOT FOUND in any ticker's facts (dropped):",missing)
PY
```
Expected: prints the finalized list (~18-22 keys) + any candidates not present in any facts (those are dropped from the registry — the engine couldn't emit them anyway). Record the count.

- [ ] **Step 2: Confirm each finalized key's spelling matches the schema doc; fix doc where it diverges**

Run:
```bash
for k in $(cat ~/AI_Agent/tmp/roc-plan/growth_metrics.txt); do
  grep -q "\`$k\`" "/Users/mensch5566/AI_Agent/docs/financials-view-schema.md" && echo "OK  $k" || echo "DOC-MISS $k"
done
```
For each `DOC-MISS`, check whether the doc uses a DIFFERENT spelling for the same line (e.g. `selling_general_admin_expenses` vs facts' `selling_general_administrative`; `operating_expenses` vs facts' `total_operating_expenses`). Where it does, edit `financials-view-schema.md` to the facts spelling (facts are authoritative — production facts already use it; re-spelling facts is out of scope). Add a one-line note in the doc: `<!-- 2026-07-10: aligned to parse-output spelling for growth registry -->`.

- [ ] **Step 3: Commit the doc alignment**

```bash
cd ~/AI_Agent
git add docs/financials-view-schema.md
git commit -m "docs(view-schema): align IS growth-metric uni_account spellings to parse output (rate-of-change T0)"
```

---

## Task 1: Rate-of-change formula in `_growth_candidate` (TDD)

**Files:**
- Modify: `~/CC_Switch_Config/skills/derive-analytics/scripts/rules_crossperiod.py:418-449` (`_growth_candidate`)
- Test: `~/CC_Switch_Config/skills/derive-analytics/tests/test_properties.py:122-151`

**Interfaces:**
- Consumes: `_growth_candidate(src_uni, out_uni, rule_id, cur, prior, period, period_kind, basis)`, `_yoy_candidate(src_uni, cur, prior, period, period_kind)` (test helper).
- Produces: same signatures; `value = (cv − pv)/abs(pv)`; returns None only when `cv is None or pv is None or pv == 0`.

- [ ] **Step 1: Rewrite the property test to the new semantics**

Replace the block at `test_properties.py` L122-148 (the `test_yoy_skip_and_value` parametrized test + its comment) with:

```python
# EL2→ROC _growth_candidate: value=(cur-prior)/abs(prior); skip ONLY prior==0.
@pytest.mark.parametrize("cv,pv,expected", [
    (150.0, 100.0, 0.5),        # positive base unchanged: (150-100)/100
    (-100.0, 100.0, -2.0),      # positive base, turned negative (unchanged from old)
    (100.0, -100.0, 2.0),       # NEW: loss→profit = +200% (rate of change)
    (-50.0, -100.0, 0.5),       # NEW: loss shrank = +50% (improvement)
    (-200.0, -100.0, -1.0),     # NEW: loss grew = -100% (deterioration)
    (0.0, -100.0, 1.0),         # NEW: to zero from loss = +100%
])
def test_growth_value_rate_of_change(cv, pv, expected):
    cur = _FactStub(value=cv); prior = _FactStub(value=pv)
    c = _yoy_candidate("revenue", cur, prior, "Q1_FY2024", "quarter_duration")
    assert c is not None
    assert abs(c.value - expected) < 1e-9

def test_growth_skip_only_on_zero_base():
    cur = _FactStub(value=5.0)
    assert _yoy_candidate("revenue", cur, _FactStub(value=0.0),
                          "Q1_FY2024", "quarter_duration") is None   # div-by-zero
```

(Keep `test_yoy_skip_on_missing_prior` at L150 unchanged — missing prior still → None.)

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd ~/CC_Switch_Config/skills/derive-analytics && python3 -m pytest tests/test_properties.py -q -k "growth_value or skip_only_on_zero"`
Expected: FAIL — old code returns None for negative pv (the `-100.0` base cases) and uses `/pv` not `/abs(pv)`.

- [ ] **Step 3: Apply the formula change**

In `rules_crossperiod.py` `_growth_candidate`, change the guard line (currently `if cv is None or pv is None or pv <= 0:`) to:

```python
    if cv is None or pv is None or pv == 0:
        return None
```

and the value + formula lines (currently `value=(cv - pv) / pv` and `formula=f"({src_uni}@{cur.period} - {src_uni}@{prior.period}) / {src_uni}@{prior.period}"`) to:

```python
        value=(cv - pv) / abs(pv), unit="Pure", rule_id=rule_id, inputs=inputs,
        formula=f"({src_uni}@{cur.period} - {src_uni}@{prior.period}) / abs({src_uni}@{prior.period})",
```

Also update the docstring line `"""(current − prior) / prior, prior > 0 required (spec §8.D). period_start is` →
`"""(current − prior) / abs(prior); skip only prior==0 (spec 2026-07-10 rate-of-change). period_start is`.

- [ ] **Step 4: Run the test to verify it passes + whole suite**

Run: `python3 -m pytest tests/ -q`
Expected: PASS (the 6 rate-of-change cases + zero-skip; all other tests still green — the positive-base cases 0.5 / −2.0 prove existing values unchanged).

- [ ] **Step 5: Sync + commit**

```bash
cd ~/CC_Switch_Config && bash scripts/sync-to-local.sh
git add skills/derive-analytics/scripts/rules_crossperiod.py skills/derive-analytics/tests/test_properties.py
git commit -m "feat(derive-analytics): growth→rate-of-change (cur-prior)/abs(prior), skip only prior==0 (TDD)"
```

---

## Task 2: Generalize EPS-class Q4 guard (DEFECT #2/#3, TDD)

**Files:**
- Modify: `~/CC_Switch_Config/skills/derive-analytics/scripts/rules_crossperiod.py:480` (`_emit_growth`)
- Test: `~/CC_Switch_Config/skills/derive-analytics/tests/test_growth_qoq.py`

**Interfaces:**
- Consumes: `_emit_growth(flow_q, flow_fy, out)`, `_eps_q4_approx(fact)`.
- Produces: `_emit_growth` skips growth for `uni in ("eps_diluted", "eps_basic")` when either endpoint is `derived_q4`.

- [ ] **Step 1: Write the failing test (append to test_growth_qoq.py)**

```python
def test_eps_basic_q4approx_skipped_like_diluted():
    """eps_basic is also non-additive: a derived_q4 endpoint must skip its growth."""
    from rules_crossperiod import _emit_growth
    @dataclass
    class F:
        ticker="T"; version="GAAP"; unit="USD/sh"; period=""; period_end=""
        value=0.0; cell_id=""; period_kind="derived_q4"
    # eps_basic present in the registry (Task 3 adds it) — this test also guards
    # that once added, its derived_q4 endpoint is skipped.
    cur = F(period="Q4_FY2025", period_kind="derived_q4", value=1.0)
    prior = F(period="Q4_FY2024", period_kind="quarter_duration", value=0.9)
    flow_q = {("GAAP","eps_basic",(2025,4)): cur, ("GAAP","eps_basic",(2024,4)): prior}
    out=[]
    _emit_growth(flow_q, {}, out)
    assert not any(r.uni_account.startswith("eps_basic") for r in out), \
        "derived_q4 eps_basic must not seed a growth row"
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd ~/CC_Switch_Config/skills/derive-analytics && python3 -m pytest tests/test_growth_qoq.py -q -k eps_basic_q4approx`
Expected: FAIL — `is_eps = uni == "eps_diluted"` excludes eps_basic (and eps_basic not yet in registry → also KeyError-free but no skip). (If it errors on eps_basic not in `_GROWTH_OUT`, that's fine — the assert still must hold; note the test passes trivially only once Task 3 adds eps_basic, so run this test again in Task 3 Step 4.)

- [ ] **Step 3: Generalize the guard**

In `_emit_growth`, change `is_eps = uni == "eps_diluted"` to:

```python
        is_eps = uni in ("eps_diluted", "eps_basic")
```

Update the docstring `EPS guard: for BOTH bases of eps_diluted, skip if EITHER endpoint is a` →
`EPS guard: for BOTH bases of ANY EPS metric (eps_diluted/eps_basic — non-additive), skip if EITHER endpoint is a`.

- [ ] **Step 4: Run test + whole suite**

Run: `python3 -m pytest tests/ -q`
Expected: PASS.

- [ ] **Step 5: Sync + commit**

```bash
cd ~/CC_Switch_Config && bash scripts/sync-to-local.sh
git add skills/derive-analytics/scripts/rules_crossperiod.py skills/derive-analytics/tests/test_growth_qoq.py
git commit -m "fix(derive-analytics): EPS-class Q4-approx guard covers eps_basic too (DEFECT #2/#3)"
```

---

## Task 3: Expand GROWTH_METRICS 5 → Tier B (TDD)

**Files:**
- Modify: `~/CC_Switch_Config/skills/derive-analytics/scripts/rules_crossperiod.py:137` (GROWTH_METRICS) + comment L134-136
- Test: `~/CC_Switch_Config/skills/derive-analytics/tests/test_growth_qoq.py:50-53`

**Interfaces:**
- Consumes: the finalized list from `~/AI_Agent/tmp/roc-plan/growth_metrics.txt` (Task 0).
- Produces: `GROWTH_METRICS` = that list; `GROWTH_RULES` count = 2 × len(list); existing 5 metrics' rule_ids byte-identical.

- [ ] **Step 1: Update the count test to the T0 count**

Read `~/AI_Agent/tmp/roc-plan/growth_metrics.txt`; let N = its line count. In `test_growth_qoq.py`, change `test_growth_rules_generates_expected_10_pairs` (L50-53): rename to `test_growth_rules_generates_expected_pairs` and set:

```python
def test_growth_rules_generates_expected_pairs():
    pairs = {(uni, rid) for (_, _, uni, rid) in GROWTH_RULES}
    assert len(GROWTH_RULES) == 2 * len(GROWTH_METRICS)   # each metric × {qoq, yoy}
    # existing 5 metrics' 10 rule_ids must remain present, byte-identical
    for m in ("revenue","gross_profit","operating_income","net_income","eps_diluted"):
        assert (f"{m}_yoy", f"RATIO_{m.upper()}_YOY") in pairs
        assert (f"{m}_qoq", f"RATIO_{m.upper()}_QOQ") in pairs
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd ~/CC_Switch_Config/skills/derive-analytics && python3 -m pytest tests/test_growth_qoq.py -q -k expected_pairs`
Expected: FAIL — GROWTH_METRICS still 5, len(GROWTH_RULES)=10 but the existing-5 assertions pass; the `2*len` holds trivially. (This test mainly locks the existing-5 invariant + the count relation; it will pass once GROWTH_METRICS is the new list AND stay consistent.) If it already passes, proceed — the load-bearing check is Step 4's byte-identity of the existing 5.

- [ ] **Step 3: Set GROWTH_METRICS to the finalized list**

Replace `rules_crossperiod.py:137` `GROWTH_METRICS = [...]` with the exact list from `growth_metrics.txt`, existing 5 FIRST (order-independent for correctness, but keep revenue/gross_profit/operating_income/net_income/eps_diluted first for readability). Example (verify against T0 output — do NOT hand-type; paste from the file):

```python
GROWTH_METRICS = [
    "revenue", "gross_profit", "operating_income", "net_income", "eps_diluted",
    "cost_of_goods_sold", "income_before_taxes", "income_tax_expense", "eps_basic",
    "selling_expenses", "general_admin_expenses", "research_and_development",
    "expected_credit_loss", "total_operating_expenses", "selling_general_administrative",
    "interest_income", "interest_expense", "other_gains_losses",
    "non_operating_income_expense", "other_nonoperating_income_expense",
    "net_income_total_pre_nci", "net_income_nci",
]
```

Also fix the stale comment at L134-136 (`the 3 pre-existing production uni_accounts/rule_ids` → `the 5 pre-existing production growth metrics (10 rule_ids)`); update the docstring in `test_growth_qoq.py` header similarly.

- [ ] **Step 4: Run tests (incl. the Task 2 eps_basic test now meaningful)**

Run: `python3 -m pytest tests/ -q`
Expected: PASS (count test, existing-5 byte-identity, eps_basic Q4 skip from Task 2).

- [ ] **Step 5: Sanity — generator produces all rule_ids, no dupes**

Run:
```bash
cd ~/CC_Switch_Config/skills/derive-analytics/scripts && python3 -c "
import rules_crossperiod as r
ids=[rid for *_,rid in r.GROWTH_RULES]
print('rule_ids:',len(ids),'unique:',len(set(ids)))
assert len(ids)==len(set(ids))
print('sample new:', [x for x in ids if 'COST_OF_GOODS' in x or 'SELLING' in x][:4])
"
```
Expected: `rule_ids: 44 unique: 44` (or 2×N), sample shows new ids like `RATIO_COST_OF_GOODS_SOLD_YOY`.

- [ ] **Step 6: Sync + commit**

```bash
cd ~/CC_Switch_Config && bash scripts/sync-to-local.sh
git add skills/derive-analytics/scripts/rules_crossperiod.py skills/derive-analytics/tests/test_growth_qoq.py
git commit -m "feat(derive-analytics): expand GROWTH_METRICS 5→Tier B (台美聯集 IS 科目)"
```

---

## Task 4: Register new rule_ids in both upsert fallbacks

**Files:**
- Modify: `~/AI_Agent/scripts/upsert_sec_financials.py` (DERIVE_ANALYTICS_RULE_IDS_FALLBACK ~L90-130)
- Modify: `~/AI_Agent/scripts/upsert_twse_financials.py` (DERIVE_ANALYTICS_RULE_IDS_FALLBACK ~L92-127)

**Interfaces:**
- Consumes: `rules_crossperiod.GROWTH_RULES` rule_ids (Task 3).
- Produces: both fallbacks contain every growth rule_id.

- [ ] **Step 1: Generate the authoritative growth rule_id list**

Run:
```bash
cd ~/CC_Switch_Config/skills/derive-analytics/scripts && python3 -c "
import rules_crossperiod as r
for rid in sorted(rid for *_,rid in r.GROWTH_RULES): print('    \"%s\",' % rid)
" > ~/AI_Agent/tmp/roc-plan/growth_rule_ids.txt
cat ~/AI_Agent/tmp/roc-plan/growth_rule_ids.txt | wc -l
```
Expected: 44 lines (or 2×N).

- [ ] **Step 2: Replace the growth block in `upsert_sec_financials.py`**

In `DERIVE_ANALYTICS_RULE_IDS_FALLBACK`, replace the 10 existing growth entries (L120-130, `RATIO_REVENUE_YOY` … `RATIO_EPS_DILUTED_QOQ`) with the full block from `growth_rule_ids.txt`. Keep all non-growth entries untouched.

- [ ] **Step 3: Same for `upsert_twse_financials.py`** (L118-127).

- [ ] **Step 4: Verify both fallbacks == registry (no drift)**

Run:
```bash
python3 - <<'PY'
import sys; sys.path.insert(0,"/Users/mensch5566/CC_Switch_Config/skills/derive-analytics/scripts")
import rules_crossperiod as r
reg=set(rid for *_,rid in r.GROWTH_RULES)
for f in ["/Users/mensch5566/AI_Agent/scripts/upsert_sec_financials.py",
          "/Users/mensch5566/AI_Agent/scripts/upsert_twse_financials.py"]:
    txt=open(f).read()
    missing=[rid for rid in reg if f'"{rid}"' not in txt]
    print(f.split('/')[-1], "missing growth rule_ids:", missing or "NONE ✓")
PY
```
Expected: both `NONE ✓`.

- [ ] **Step 5: Run upsert scripts' own tests (fallback drift guard)**

Run: `cd ~/AI_Agent && python3 -m pytest scripts/tests/test_upsert_derived.py -q` (fallback: `uv run --with pytest ...`).
Expected: PASS (this suite previously enforced fallback==registry; earlier this session it was aligned to 34 — now it must match the new count).

- [ ] **Step 6: Commit**

```bash
cd ~/AI_Agent
git add scripts/upsert_sec_financials.py scripts/upsert_twse_financials.py
git commit -m "chore(upsert): register Tier-B growth rate-of-change rule_ids in both fallbacks"
```

---

## Task 5: Re-run derive-analytics + numeric invariant verify (local, no production)

**Files:**
- Read/Write: vault `Skill_Output/derive-analytics/` per ticker (new run folder; old kept for diff).

- [ ] **Step 1: Back up current analytics outputs for byte-diff baseline**

For each ticker, copy the latest `{T}_analytics.json` to `~/AI_Agent/tmp/roc-plan/baseline/{T}_analytics_pre.json`.

- [ ] **Step 2: Re-run derive-analytics for all 9 tickers**

Run the skill's runner (`derive_analytics.py`) `--market us` for INTC/AAOI/SNDK/LITE/MU/GLW and `--market tw` for 3081/2308/6274, per its SKILL.md invocation. Record each new run-folder path.

- [ ] **Step 3: Numeric invariant diff (value-only, exclude formula/provenance/updated_at)**

Run a comparison script: for each ticker, load pre + new analytics; for every (uni_account, period, period_kind, version) present in BOTH, assert `value` bit-identical; report NEW keys (should be only growth rate-of-change rows — negative-base fills for existing 5 + the 17 new metrics); report any value change on a non-growth metric (MUST be empty).
Expected per ticker: 0 value-changes on shared keys; new keys ⊆ growth family; 台燿's 4 known negative-base fills appear (Q2_FY2023 net_income/eps_diluted_qoq, Q1_FY2024 net_income/eps_diluted_yoy).

- [ ] **Step 4: Present the diff report to the user** (a table: ticker | value-changes(must be 0) | new growth rows count | sample new). This is the gate before any production write.

---

## Task 6: Downstream smoke test (compose + wiki-ingest)

- [ ] **Step 1: Run compose-financials on one US + one TW ticker** (e.g. GLW + 6274) against the new analytics; diff the composed `Financials.md` growth section vs the prior version.
Expected: either the new growth rows appear intentionally, OR compose whitelists keys and they don't leak. Confirm no raw `RATIO_*` id renders. If a leak is found, STOP and report — compose needs a whitelist fix (separate task, out of this plan's engine scope).

- [ ] **Step 2: Run wiki-ingest-mops-10k on 6274** (staging, not promote) against the new analytics; confirm the derived block doesn't dump the 17 new rows as raw/unlabeled. Report findings.

---

## Task 7: Per-ticker authorized re-upsert (PRODUCTION — user auth)

- [ ] **Step 1: Dry-run diff per ticker** — `upsert_{sec,twse}_financials.py {T}` without `--apply`; show the row delta (additions = new growth rows; snapshot re-writes of existing rows with identical value).
- [ ] **Step 2: STOP — request explicit per-ticker authorization** before any `--apply`.
- [ ] **Step 3: On authorization, `--apply` per ticker.**
- [ ] **Step 4: Post-upsert DB-level numeric verify** — query `sec_financial_metrics` for the growth rule_ids; confirm existing positive-base values match the pre-upsert values (numeric-only; ignore updated_at/cell_id/provenance churn); confirm new rows present.

---

## Task 8: Docs + finish

- [ ] **Step 1: Update `derive-analytics/SKILL.md`** — growth family is rate-of-change; list the Tier-B metrics; note EPS-class guard.
- [ ] **Step 2: Cross-note the old growth spec** (`2026-06-02-derive-analytics-el2-expansion-design.md` §8.D) as superseded by the 2026-07-10 rate-of-change spec.
- [ ] **Step 3: Update `docs/STATUS.md`** + write a memory (rate-of-change shipped; 變動率 semantics; negative-base now filled; display-layer polarity still TODO).
- [ ] **Step 4: Final full test run** both repos' relevant suites green; sync-to-local; commit; STOP for push authorization.

---

## Self-Review

**1. Spec coverage:**
- §1 formula → Task 1. §1 near-zero (emit-as-is) → Task 1 covers `pv==0`-only guard; §8 risk documented (no code cap — correct). ✅
- §2.1 canonical key reconcile (DEFECT #1) → Task 0. ✅
- §2.2 Tier B expansion → Task 3 (list from Task 0). ✅
- §2b EPS-class guard + name-branch audit (DEFECT #2/#3) → Task 2 (+ audit confirmed single branch in spec). ✅
- §3 絕不動 + tax-guard fix (DEFECT #4) → Task 5 invariant verify enforces non-growth zero value-change; the tax-guard is a spec-doc fix already applied (no code touch). ✅
- §4 numeric invariant (DEFECT #5) → Task 5 Step 3 + Task 7 Step 4 (value-only, exclude formula/provenance). ✅
- §5 touch points → Tasks 1-4 (engine/guard/registry/fallbacks) + stale comment (Task 3 Step 3) + tests (Tasks 1-3). ✅
- §6 rollout → Tasks 5-8. §6 downstream smoke → Task 6. ✅
- §7 out-of-scope (frontend) → not touched; §7 frontend-visible-change noted → Task 6/7 verify. ✅
- §8 zero-delete → owned-scope behavior, no code (Task 5/7 note). ✅

**2. Placeholder scan:** Task 0/5/6/7 use commands + criteria rather than fabricated unit tests (correct — reconciliation/re-run/production-upsert are not TDD-able); Tasks 1-4 carry full code. No "TBD"/"similar to Task N". ✅

**3. Type consistency:** `_growth_candidate`/`_yoy_candidate`/`_emit_growth`/`_eps_q4_approx`/`GROWTH_METRICS`/`GROWTH_RULES`/`_GROWTH_OUT` names match the real code (verified via Read). `_FactStub` (test_properties) + `_FactStub`-like `F` (test_growth_qoq) are per-file test doubles. Rule_id format `RATIO_{M}_{B}` consistent with generator. ✅
