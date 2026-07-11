# parse-twse-ixbrl BS Grouping Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop parse-twse-ixbrl from double-representing the current-bond (`2320`) inside `other_current_liabilities` and from bundling 預收股本 (`3140`) inside `common_stock`, by mapping each TWSE grouping tag to a distinct uni_account and reconciling the canonical key with an explicit-priority, fail-loud, computation-free post-pass.

**Architecture:** The extractor keeps first-occurrence-wins, so two tags cannot target one key. Map the narrow/component tags to the canonical keys (`2399`→`other_current_liabilities`, `3110`→`common_stock`) and the subtotal tags to disclosure keys (`2300`→`other_current_liabilities_subtotal`, `3100`→`issued_capital_total`, `3140`→`advance_stock_receipts`). A new `_reconcile_grouping` pass promotes a subtotal to the canonical key ONLY when the narrow tag is absent AND no separately-extracted guard component is present; otherwise it leaves the canonical key empty and writes an audit warning. It only moves existing tag tuples — never computes.

**Tech Stack:** Python 3.13 stdlib + pytest (parse skill); the derive engines + Supabase upsert are downstream consumers unchanged by this plan.

## Global Constraints

- **parse never computes**: every change is tag-mapping or moving an existing tag's tuple. Guards may COMPARE (validation) but must NEVER emit `2300 − 2320` or any arithmetic value. (spec §0, §4, §7)
- **totals byte-identical**: `total_current_liabilities`, `total_equity`, `total_liabilities`, `total_liabilities_and_equity`, `total_assets` etc. are separate as-reported tags — their values MUST be identical before/after. (spec §4)
- **TW/US same-semantic → same uni_account key**: `common_stock` = par/ordinary (US excludes stock-subscribed) → TW `3110 普通股股本`, NOT `3100 IssuedCapital` (bundles 預收). (spec §2, B-2 adopted)
- **fail-loud over silent double-count**: when a subtotal fallback would re-introduce double-count (guard component present), leave the canonical key EMPTY + audit warning. (spec §1, §2, argue DEFECT)
- **canonical SSOT** = `~/CC_Switch_Config/skills/parse-twse-ixbrl/`; edit there, run tests there, then `cd ~/CC_Switch_Config && bash scripts/sync-to-local.sh`.
- **B-2 equity mapping (adopted)**: `3110 OrdinaryShare`→`common_stock`; `3140 AdvanceReceiptsForShareCapital`→`advance_stock_receipts`; `3100 IssuedCapital`→`issued_capital_total`.
- **production impact**: 6274/2308 already upserted with the double-counted sub-items; 台燿 29 wiki periods render the broad OCL — both must be corrected (spec §5, §6). Per-ticker upsert needs USER authorization.

---

## File Structure

- `~/CC_Switch_Config/skills/parse-twse-ixbrl/parse_ixbrl.py` — XBRL_MAP entries + new `_reconcile_grouping` + its call site in `parse_period_facts` and `parse_ixbrl_annual_facts`. (the ONE engine file)
- `~/CC_Switch_Config/skills/parse-twse-ixbrl/tests/test_parse_pure.py` — new grouping/reconcile tests.
- `~/CC_Switch_Config/skills/parse-tw-crosscheck/scripts/cross_check_twse.py` — `CODE_TO_KEY` + `label_to_key` (via ticker configs) additions.
- `~/CC_Switch_Config/skills/parse-tw-crosscheck/scripts/tests/test_cross_check_twse.py` — code-map tests.
- `~/AI_Agent/Tools/research-tools/parse-twse-ixbrl/batch_parse.py` — LEGACY (not the active pipeline); deprecation note only, NOT a half-fix.
- `~/AI_Agent/CLAUDE.md` — correct the stale `batch_parse.py` pipeline reference.
- `~/AI_Agent/docs/financials-view-schema.md` — register `advance_stock_receipts`, `issued_capital_total`, `other_current_liabilities_subtotal`; note `common_stock` TW/US definition.
- `~/AI_Agent/scripts/upsert_twse_financials.py` — display_label/ordinal for the 3 new BS keys (if it carries a display map).
- Vault Skill_Output (re-parse/derive outputs) + Supabase + 台燿 wiki pages — regenerated in rollout tasks, not committed.

---

## Task 0: Engine — grouping map split + fail-loud reconcile pass (TDD)

**Files:**
- Modify: `~/CC_Switch_Config/skills/parse-twse-ixbrl/parse_ixbrl.py` (XBRL_MAP L105/L107/L119 area; add `_reconcile_grouping`; call in `parse_period_facts` ~L305 after first `_parse_content`, and in `parse_ixbrl_annual_facts`)
- Test: `~/CC_Switch_Config/skills/parse-twse-ixbrl/tests/test_parse_pure.py`

**Interfaces:**
- Produces: `_reconcile_grouping(results: dict[str, tuple], period: str="") -> None` — mutates `results` in place. `results` shape is `{metric: (value, statement, sort_order, xbrl_concept)}` (the `_parse_content` return). New uni_accounts emitted into facts: `other_current_liabilities` (now from 2399), `other_current_liabilities_subtotal`, `issued_capital_total`, `advance_stock_receipts`; `common_stock` now from 3110.

**Environment:** run tests with `cd ~/CC_Switch_Config/skills/parse-twse-ixbrl && uv run --with pytest python3 -m pytest tests/ -q`. Current baseline must be green first (record the count).

- [ ] **Step 1: Confirm `_sort_order_to_statement` bands + baseline green**

Run:
```bash
cd ~/CC_Switch_Config/skills/parse-twse-ixbrl
sed -n '/def _sort_order_to_statement/,/return "cash_flow/p' parse_ixbrl.py
uv run --with pytest python3 -m pytest tests/ -q 2>&1 | tail -3
```
Expected: bands show `1000–1999 balance_sheet_assets`, `2000–2999 balance_sheet_liabilities`, `3000–3999 balance_sheet_equity` (confirm exact upper/lower); baseline all pass. Record which sort_orders land in `balance_sheet_liabilities` (2xxx) and `balance_sheet_equity` (3xxx) — the new keys must use numbers in those bands: `other_current_liabilities`=2195 (unchanged), `other_current_liabilities_subtotal`=2196, `issued_capital_total`=3105, `advance_stock_receipts`=3115, `common_stock`=3110 (unchanged).

- [ ] **Step 2: Write the failing reconcile tests**

Add to `tests/test_parse_pure.py` (a pure unit test of the new function — no fixture file needed):
```python
from parse_ixbrl import _reconcile_grouping

def _t(v, stmt="balance_sheet_liabilities", so=2196, c="x"):
    return (v, stmt, so, c)

def test_reconcile_ocl_narrow_present_keeps_narrow():
    # 2399 filed → other_current_liabilities already set → subtotal ignored, no promote
    r = {"other_current_liabilities": _t(949137, so=2195),
         "other_current_liabilities_subtotal": _t(3173625),
         "current_portion_of_long_term_debt": _t(2224488)}
    _reconcile_grouping(r, "Q1_FY2026")
    assert r["other_current_liabilities"][0] == 949137  # unchanged

def test_reconcile_ocl_absent_no_guard_promotes_subtotal():
    # no 2399, no 2320 → subtotal == narrow → promote (健策-style)
    r = {"other_current_liabilities_subtotal": _t(22269)}
    _reconcile_grouping(r, "Q1_FY2026")
    assert r["other_current_liabilities"][0] == 22269

def test_reconcile_ocl_absent_with_guard_leaves_empty_and_audits(capsys):
    # no 2399 but 2320 present → promoting subtotal would double-count → leave empty
    r = {"other_current_liabilities_subtotal": _t(3173625),
         "current_portion_of_long_term_debt": _t(2224488)}
    _reconcile_grouping(r, "Q1_FY2026")
    assert "other_current_liabilities" not in r
    assert "grouping" in capsys.readouterr().err  # audit warning to stderr

def test_reconcile_common_stock_narrow_present_keeps_narrow():
    r = {"common_stock": _t(1367511, "balance_sheet_equity", 3110),
         "issued_capital_total": _t(1380872, "balance_sheet_equity", 3105),
         "advance_stock_receipts": _t(13361, "balance_sheet_equity", 3115)}
    _reconcile_grouping(r, "Q1_FY2023")
    assert r["common_stock"][0] == 1367511

def test_reconcile_common_stock_absent_no_advance_promotes_issued_total():
    r = {"issued_capital_total": _t(1222652, "balance_sheet_equity", 3105)}
    _reconcile_grouping(r, "Q1_FY2021")
    assert r["common_stock"][0] == 1222652

def test_reconcile_no_arithmetic_emitted():
    # never derive: subtotal(3173625) minus guard(2224488) must NOT appear
    r = {"other_current_liabilities_subtotal": _t(3173625),
         "current_portion_of_long_term_debt": _t(2224488)}
    _reconcile_grouping(r, "Q1_FY2026")
    vals = [t[0] for t in r.values()]
    assert 949137 not in vals  # 3173625-2224488 must not be computed
```

- [ ] **Step 3: Run to verify they fail**

Run: `uv run --with pytest python3 -m pytest tests/test_parse_pure.py -q -k reconcile`
Expected: FAIL — `ImportError: cannot import name '_reconcile_grouping'`.

- [ ] **Step 4: Change the XBRL_MAP entries**

In `parse_ixbrl.py` XBRL_MAP:
- Change `'ifrs-full:OtherCurrentLiabilities'` target from `('other_current_liabilities', 'BS', 2195)` → `('other_current_liabilities_subtotal', 'BS', 2196)`.
- Add `'tifrs-bsci-ci:OtherCurrentLiabilitiesOthers': ('other_current_liabilities', 'BS', 2195),`.
- Change `'ifrs-full:IssuedCapital'` from `('common_stock', 'BS', 3110)` → `('issued_capital_total', 'BS', 3105)`.
- Add `'tifrs-bsci-ci:OrdinaryShare': ('common_stock', 'BS', 3110),`.
- Add `'tifrs-bsci-ci:AdvanceReceiptsForShareCapital': ('advance_stock_receipts', 'BS', 3115),`.
(`'tifrs-bsci-ci:LongtermLiabilitiesCurrentPortion' → current_portion_of_long_term_debt` at L107 stays.)

- [ ] **Step 5: Add `_reconcile_grouping` and call it**

Add near the other helpers (before `parse_period_facts`):
```python
# TWSE 標準表 grouping：小計 concept 的成分被另外對映到 canonical key。為避免小計與
# 成分雙計，小計對映到「揭露 key」，canonical key 由此 pass 依 priority 決定：優先用
# 已對映的殘差/純成分 tag；殘差缺席且無 guard 成分時才提升小計（小計==殘差）；有 guard
# 成分則留空 + audit。純 tag 選擇/提升，絕不做算術（spec §1/§2/§4）。
_GROUPING_RECONCILE = [
    # (canonical_key, subtotal_key, guard_keys, code)
    ("other_current_liabilities", "other_current_liabilities_subtotal",
     ("current_portion_of_long_term_debt",), "2300"),
    ("common_stock", "issued_capital_total",
     ("advance_stock_receipts",), "3100"),
]

def _reconcile_grouping(results, period=""):
    """results: {metric: (value, statement, sort_order, xbrl_concept)}, mutated in place."""
    for canon, subtotal, guards, code in _GROUPING_RECONCILE:
        if canon in results:
            continue                      # narrow/component tag filed → done
        if subtotal not in results:
            continue                      # genuinely absent
        if any(g in results for g in guards):
            print(f"⚠️  grouping {code}: {canon} 缺殘差 tag 但成分 {guards} 在 → "
                  f"{canon} 留空避免雙計 (period={period})", file=sys.stderr)
            continue
        results[canon] = results[subtotal]  # promote existing tag tuple (no arithmetic)
```
In `parse_period_facts`, right after `ytd_facts = _parse_content(content, as_of, ytd)` add:
```python
    _reconcile_grouping(ytd_facts, period)
```
Do the SAME in `parse_ixbrl_annual_facts` after its `_parse_content(...)` call (find its results var and add `_reconcile_grouping(<results>, period)`).

- [ ] **Step 6: Run reconcile tests + full suite**

Run: `uv run --with pytest python3 -m pytest tests/ -q`
Expected: the 6 reconcile tests PASS; existing tests still green EXCEPT any that assert the old `common_stock`/`other_current_liabilities` mapping — if an existing fixture test (e.g. `test_renamed_keys_and_no_old_names`, or a 3081/聯亞 landmark) now sees `common_stock` from 3110 or OCL from 2399, update its expected value to the narrow/correct one and note why. Do NOT weaken; pin the new correct value. Report every test touched.

- [ ] **Step 7: Real-data smoke on the 5 tickers (no commit yet)**

Run a one-off: re-parse 緯穎 Q1_FY2026 + 健策 Q1_FY2023 in-process and assert `other_current_liabilities==949137` (緯穎), `other_current_liabilities_subtotal==3173625`, `common_stock==1367511` (健策), `advance_stock_receipts==13361`, `issued_capital_total==1380872`, and that `total_current_liabilities`/`total_equity` are unchanged vs the pre-fix facts JSON. Paste the values.

- [ ] **Step 8: sync-to-local + commit**

```bash
cd ~/CC_Switch_Config && bash scripts/sync-to-local.sh
git add skills/parse-twse-ixbrl/parse_ixbrl.py skills/parse-twse-ixbrl/tests/test_parse_pure.py
git commit -m "fix(parse-twse-ixbrl): split BS grouping tags + fail-loud reconcile (2399/2300, 3110/3100/3140)"
```

---

## Task 1: Legacy batch_parse.py — deprecate, do NOT half-fix

**Files:**
- Modify: `~/AI_Agent/Tools/research-tools/parse-twse-ixbrl/batch_parse.py` (header note only)
- Modify: `~/AI_Agent/CLAUDE.md` (stale pipeline reference)

**Interfaces:** none (documentation only).

- [ ] **Step 1: Confirm batch_parse.py is not the active pipeline**

Run:
```bash
grep -rn "batch_parse" ~/.claude/skills/parse-twse-ixbrl/run.sh ~/.claude/skills/parse-twse-ixbrl/*.py 2>/dev/null || echo "NOT referenced by active skill"
```
Expected: not referenced — the active path is `run.sh → parse_ixbrl.py`. If it IS referenced/imported by the active skill, STOP: this becomes a full port of Task 0's change instead of a doc note (escalate).

- [ ] **Step 2: Add a deprecation banner to batch_parse.py**

At the top of `~/AI_Agent/Tools/research-tools/parse-twse-ixbrl/batch_parse.py`, add a comment:
```python
# DEPRECATED (2026-07-11): superseded by the parse-twse-ixbrl SKILL
# (~/.claude/skills/parse-twse-ixbrl/, run.sh → parse_ixbrl.py). This legacy
# copy's XBRL_MAP still maps 2300→other_current_liabilities and 3100→common_stock
# (the pre-grouping-fix behaviour) and is intentionally NOT half-patched — a
# map-only change here without the reconcile pass would drop other_current_liabilities.
# Do NOT run this for production facts; use the skill.
```
Do NOT change its XBRL_MAP.

- [ ] **Step 3: Fix the stale CLAUDE.md reference**

In `~/AI_Agent/CLAUDE.md` (the 台股 XBRL 管道 section, ~L18-24 referencing `batch_parse.py`), replace the `batch_parse.py` step with the current skill invocation (`run.sh fetch`/`run.sh parse` via parse-twse-ixbrl). Keep it one line; don't restructure the section.

- [ ] **Step 4: Commit**

```bash
cd ~/AI_Agent
git add Tools/research-tools/parse-twse-ixbrl/batch_parse.py CLAUDE.md
git commit -m "docs: mark legacy batch_parse.py deprecated + fix CLAUDE.md TW parse pipeline ref"
```

---

## Task 2: Cross-check code/label map additions (TDD)

**Files:**
- Modify: `~/CC_Switch_Config/skills/parse-tw-crosscheck/scripts/cross_check_twse.py` (`CODE_TO_KEY` L51-~100)
- Modify: `~/CC_Switch_Config/skills/parse-tw-crosscheck/ticker_configs/{6669,3653,6274,2308,3081}.json` (`label_to_key`)
- Test: `~/CC_Switch_Config/skills/parse-tw-crosscheck/scripts/tests/test_cross_check_twse.py`

**Interfaces:**
- Consumes: statement-aware `compare_period` (already shipped this session).
- Produces: `CODE_TO_KEY` with `2399`/`3140`/`3100` added and `2300` no longer → `other_current_liabilities`.

- [ ] **Step 1: Write failing code-map tests**

Add to `test_cross_check_twse.py`:
```python
def test_code_map_2399_is_other_current_liabilities():
    assert cc.CODE_TO_KEY.get("2399") == "other_current_liabilities"

def test_code_map_2300_not_ocl_after_fix():
    # subtotal code must not map to the canonical narrow key
    assert cc.CODE_TO_KEY.get("2300") != "other_current_liabilities"

def test_code_map_equity_grouping():
    assert cc.CODE_TO_KEY.get("3140") == "advance_stock_receipts"
    assert cc.CODE_TO_KEY.get("3100") == "issued_capital_total"
    assert cc.CODE_TO_KEY.get("3110") == "common_stock"
```

- [ ] **Step 2: Run to verify fail**

Run: `cd ~/CC_Switch_Config/skills/parse-tw-crosscheck/scripts && uv run --with pytest python3 -m pytest tests/ -q -k "code_map"`
Expected: FAIL (2399/3140/3100 absent; 2300 still → other_current_liabilities).

- [ ] **Step 3: Edit CODE_TO_KEY**

In `cross_check_twse.py` `CODE_TO_KEY`: change `"2300": "other_current_liabilities",` → `"2300": "other_current_liabilities_subtotal",`; add `"2399": "other_current_liabilities",`; in the equity block add `"3100": "issued_capital_total",` and `"3140": "advance_stock_receipts",` (`"3110": "common_stock"` stays).

- [ ] **Step 4: Add label_to_key entries to the 5 TW configs**

For each `ticker_configs/{T}.json` `label_to_key`, add: `"其他流動負債－其他": "other_current_liabilities"`, `"預收股本": "advance_stock_receipts"`, `"股本合計": "issued_capital_total"`, `"普通股股本": "common_stock"`. Leave `"其他流動負債": "other_current_liabilities"` (audited-face PDFs print the residual under this label; §3.4) — the statement-aware + code-first logic disambiguates when codes exist.

- [ ] **Step 5: Run tests + full suite**

Run: `uv run --with pytest python3 -m pytest tests/ -q`
Expected: PASS (code-map tests + the 30 existing incl. statement-aware).

- [ ] **Step 6: sync-to-local + commit**

```bash
cd ~/CC_Switch_Config && bash scripts/sync-to-local.sh
git add skills/parse-tw-crosscheck/scripts/cross_check_twse.py skills/parse-tw-crosscheck/scripts/tests/test_cross_check_twse.py skills/parse-tw-crosscheck/ticker_configs/*.json
git commit -m "feat(parse-tw-crosscheck): code/label map for 2399/2300 + equity 3110/3100/3140 grouping"
```

---

## Task 3: Re-parse 5 TW tickers + verification gates

**Files:** vault Skill_Output per ticker (regenerated). Back up first.

- [ ] **Step 1: Back up current facts + derive outputs**

For 6669/3653/6274/2308/3081: copy `{T}_twse_facts.json` + latest `derive-base`/`derive-analytics` run to `~/AI_Agent/tmp/twse-bs/baseline/`.

- [ ] **Step 2: Re-parse all 5**

`cd ~/.claude/skills/parse-twse-ixbrl` and for each ticker run `bash run.sh parse <T> --dir <ticker XML dir> --out <Skill_Output>/parse-twse-ixbrl/<T>_twse_facts.json`. Capture stderr — collect every `⚠️ grouping` audit line (expected: none for cr tickers where 2399 is filed; any line means a period lacks 2399 while 2320 present → record it).

- [ ] **Step 3: GATE — totals byte-identical**

Diff new vs baseline facts for every `total_*` key across all periods/tickers. MUST be 0 changes. Any total change → STOP (regression).

- [ ] **Step 4: GATE — full-history grouping identity (compare-only, no output)**

For every ticker/period, assert (comparison, not stored): where 2399 & 2320 present, `subtotal(2300) == other_current_liabilities(2399) + current_portion_of_long_term_debt(2320)`; where 3110 & 3140 present, `issued_capital_total(3100) == common_stock(3110) + advance_stock_receipts(3140)`. List any period where it fails (means an un-extracted grouping component exists → audit note, not a blocker for the residual value).

- [ ] **Step 5: Re-derive + GATE — derived full diff**

Re-run derive-base + derive-analytics for all 5. Diff ALL derived outputs (esp. debt_to_equity, net_debt_to_ebitda, ROIC, ratios) new vs baseline. Expected: 0 change (no derived metric consumes the affected sub-account keys). Any change → investigate before proceeding.

- [ ] **Step 6: Present the gate report** (ticker × totals-changed(0) × derived-changed(0) × audit-lines × sample sub-account before/after). This is the gate before cross-check + production.

---

## Task 4: Re-run cross-check + NLM-side resolution

- [ ] **Step 1: Re-run compare for 緯穎 + 健策** (reuse the existing raw NLM run folder). Expected: 緯穎 `other_current_liabilities` ×10 → resolved; 健策 `common_stock` ×10 → resolved (NLM 普通股股本 1,367,511 == new parse).
- [ ] **Step 2: Re-query 健策 Q2_FY2022** via NLM (that period's raw response was sparse/corrupted) → overwrite its `raw_nlm_responses_twse/Q2_FY2022.json` → re-compare.
- [ ] **Step 3: PDF-verify the residual small diffs** (緯穎 Q4_FY2021 operating_income 200; 健策 Q4_FY2021 eps_diluted 9.41 vs 8.23; 健策 dividends_paid ×5; the ~30 tiny totals/OCR diffs). For each, open the source PDF page; mark NLM_ERROR (parse authoritative) or a real parse issue (escalate). Write the audit `.md`.
- [ ] **Step 4: Converge** — both tickers 0 unexplained MISMATCH; audit `.md` accounts for every remaining item.

---

## Task 5: Production re-upsert (per-ticker USER authorization)

- [ ] **Step 1: Dry-run diff per ticker** — `upsert_twse_financials.py <T>` (no `--apply`) for 6274/2308/6669/3653/3081; show the row delta (OCL value change for 6274/2308; new `advance_stock_receipts`/`issued_capital_total`/`other_current_liabilities_subtotal` rows; common_stock change where 預收≠0).
- [ ] **Step 2: STOP — request per-ticker authorization** before any `--apply`. Call out that 6274/2308 are CHANGING already-live values (台燿 OCL 324,038→56,407-class; 台達電 OCL 9.6B-class).
- [ ] **Step 3: On authorization, `--apply` per ticker.**
- [ ] **Step 4: Post-upsert DB verify** — the affected keys hold the new values; totals unchanged.

---

## Task 6: 台燿 wiki 29-period OCL re-render

- [ ] **Step 1: Confirm the delta** — 台燿 BS pages currently render `other_current_liabilities` = broad 2300 (e.g. 2026Q1 324,038); post-fix = 56,407; equity unaffected (預收=0 all periods).
- [ ] **Step 2: Re-render** the 29 台燿 wiki source pages via the mops-10k deterministic renderer `update_page` (Block C reads the re-parsed analytics/facts). Coordinate with / hand off to the wiki-ingest session; do NOT hand-edit pages.
- [ ] **Step 3: Spot-check** 2-3 台燿 wiki pages show the residual OCL + no double-count.

---

## Task 7: Key registration + docs + finish

- [ ] **Step 1: Register the 3 new keys** in `docs/financials-view-schema.md` (`advance_stock_receipts`, `issued_capital_total`, `other_current_liabilities_subtotal`) with 代碼 3140/3100/2300 + tags; add a note that `common_stock` = TW 3110 par / US par (definitions aligned), and 預收 lives in `advance_stock_receipts`.
- [ ] **Step 2: upsert display map** — add display_label/ordinal for the 3 new keys in `upsert_twse_financials.py` if it carries a BS display/label map (grep for an existing BS key like `other_current_liabilities` to find the map; if none, note "data-driven, no map" and skip).
- [ ] **Step 3: wiki-ingest Block C contract** — register the new keys in `wiki-ingest-mops-10k` Block C key list so future ingests render them (hand-off note if owned by the wiki session).
- [ ] **Step 4: skill.md CHANGELOG + Known Limitations** — parse-twse-ixbrl: the grouping split, the fail-loud reconcile, the 2300-identity audit caveat.
- [ ] **Step 5: STATUS.md + memory** — grouping fix shipped, B-2 adopted, 5 tickers re-parsed/re-upserted, 台燿 wiki re-rendered.
- [ ] **Step 6: Final full test run** both skills' suites green; sync-to-local; commit; STOP for push authorization.

---

## Self-Review

**1. Spec coverage:**
- §0.1 OCL grouping → T0 (map+reconcile) + T2 (cross-check) + T3 (re-parse) + T5 (upsert) + T6 (wiki). ✅
- §0.2 equity grouping / B-2 → T0 (3110/3100/3140) + T2 + T3 + T5. ✅
- §0.3 face-presentation homonym → T2 Step 4 (label kept) + T4 (NLM audit). ✅
- §1 fail-loud fallback + priority parse mechanism (argue DEFECT) → T0 Step 5 (`_reconcile_grouping` guard) + Step 2 audit test. ✅
- §1/§4 no-arithmetic → T0 Step 2 `test_reconcile_no_arithmetic_emitted`. ✅
- §2 B-2 + issued_capital_total decided → T0/T2/T7. ✅
- §3 cross-check CODE_TO_KEY/label additions + statement-aware (shipped) → T2 + T4. ✅
- §4 totals byte-identical → T3 Step 3 GATE. ✅
- §5.0 batch_parse mirror (argue DEFECT) → T1 (deprecate, not half-fix — reasoned deviation from "update every mirror" because a map-only edit would break it). ✅
- §5.3 full-history identity + derived diff gates → T3 Steps 4-5. ✅
- §5.6 台燿 wiki re-render (argue DEFECT) → T6. ✅
- §5.7 key registration (argue DEFECT) → T7. ✅
- §5 per-ticker authorized upsert → T5 Step 2 STOP. ✅
- NLM-side (Q2_FY2022 re-query, small diffs) → T4. ✅

**2. Placeholder scan:** T0/T2 carry full code + exact map edits; T3-T7 use commands + explicit gates (re-parse/upsert/render are not TDD-able — correct). No "TBD"/"similar to". ✅

**3. Type consistency:** `_reconcile_grouping(results, period="")` signature identical across T0 Steps 2/5 and Interfaces; `results` tuple shape `(value, statement, sort_order, xbrl_concept)` matches `_parse_content`'s real return; key names (`other_current_liabilities_subtotal`, `issued_capital_total`, `advance_stock_receipts`) identical in parse map (T0), CODE_TO_KEY (T2), view-schema (T7). ✅
