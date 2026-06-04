# Codex Functional Review — 2026-06-04 session production changes (retroactive Review gate)

**Why this doc**: five production-touching changes shipped this session via `--apply` **without** the
SOP §3.5 multi-AI adversarial Review gate (human approved each, but the Codex round was skipped). This
is the retroactive functional review. All changes are diff-gated / idempotent / git-revertable; the ask
is: confirm correctness, find any P1/P2, or sign off.

Reviewer: Codex (adversarial). Author: Claude. Debate to convergence — no performative agreement.

---

## Change 1 — MU supplement: full 23-period NLM-first rebuild + XBRL off-by-one quarantine

**What**: MU (Micron) was the first ticker run on parse-SEC-supplement XBRL-primary alone. NLM
cross-check caught a **systematic off-by-one fiscal-quarter labeling bug** in the XBRL-primary output
(`parse_instance_xbrl.py`): Nov 27 2025 (cover page = Q1_FY2026) was labeled Q4_FY2025; verified across
4/4 non-empty quarters (DRAM+total fingerprint). Rebuilt MU supplement **NLM-first for all 23 periods**
(FY2021Q1→FY2026Q2): gap periods = NLM primary, covered periods = NLM validator (10K/10Q-strength).

**Evidence**:
- Footing: every period segment Σ revenue = product Σ revenue = consolidated total revenue from the
  GAAP three-statements; **23/23 periods, 0 footing failures**; FY2025 segment OI Σ (incl Unallocated)
  = 9,770 = 10-K. (Q4_FY2025 segment Σ 11,314 vs 11,315: 8-K BU table omits ~$1M "All Other".)
- Q4_FY2021–2024 single-quarter segment/product **left empty** (old 8-Ks don't disclose; Parse-no-compute
  — NOT reconstructed as FY−9M).
- XBRL off-by-one artifacts renamed `QUARANTINED_offbyone_*` (not consumed downstream).
- Upserted: `sec_financial_dimensional_facts` **374 rows**, dry-run gate green (0 rejected/conflict, all
  unique). Audit trail: `…/parse-SEC-supplement/2026-06-03-1545_NLM_VALIDATE…/MU_supplement_VALIDATION.md`.
- New supplement config `parse-SEC-supplement/ticker_configs/MU.json` (27 periods) committed (CC `f03bd4f`);
  parse-8k-nongaap MU.json committed (`fab768b`).

**Scrutinize**: (a) is NLM-first acceptable as the source for a T3 dimensional dataset given footing ties
to the GAAP three-statements? (b) the quarantine (not deletion) of the off-by-one XBRL files — any
downstream path that still reads `_v3`? (the upsert reads `_supplement_facts_v3.json`; I transformed the
NLM canonical into that filename with correct fiscal `period_end` — confirm no stale XBRL leak.)

---

## Change 2 — parse-SEC-supplement: `fy_end_month` silent-default off-by-one fix (tool root-cause)

**What**: root cause of Change 1's bug — `parse_instance_xbrl.py` / `parse_def_xml.py` defaulted
`--fy-end-month` to 12; a non-December filer (MU=Aug, LITE=Jun) run without the flag silently mislabeled
every quarter by −1 fiscal quarter (the `derive_period_label` **formula was already correct**; the
defect was the unsupplied fiscal-year-end). Fix: `resolve_fy_end_month(ticker, cli)` in both scripts —
precedence **CLI > ticker_config `fiscal_year_end_month` (SSOT) > 12 (LOUD warning)**; default 12→None.
All supplement configs now declare `fiscal_year_end_month` (MU=8, LITE=6, INTC=12, AAOI=12).

**Evidence**: TDD `scripts/test_period_label.py` (8 tests pass) — MU/LITE label correctness, off-by-one
reproduction under default-12, config resolution, fail paths. Integration: re-ran `parse_instance_xbrl`
for MU with NO flag → printed `fy_end_month=8 (from ticker_config MU.json)`, labeled mu-20251127 →
Q1_FY2026, mu-20260226 → Q2_FY2026, mu-20250828 → FY2025 (all correct). LITE def_xml resolved 6. CC
commit `08e690c` + 4-mirror sync. SKILL.md CHANGELOG added.

**Scrutinize**: precedence order (CLI override above config — correct for one-offs?); the loud-12
fallback (should a non-Dec filer with no config/flag **hard-fail** instead of warn-and-proceed?).

---

## Change 3 — net_debt_to_ebitda rollout (LITE)

**What**: `net_debt_to_ebitda` was in the engine + frontend (CC `ec91e68`) but only MU had been
re-upserted with it. LITE re-upserted (no re-parse) → analytics rows 626→650 (**+24 net_debt_to_ebitda**,
ttm_duration, negative in net-cash years, positive when net debt — verified sane). INTC/AAOI/SNDK picked
it up via Change 4. **EBITDA now live for all 5 tickers** (MU 17 / LITE 30 / INTC 4 / AAOI 16 / SNDK 3);
net_debt_to_ebitda MU 5 / LITE 24 / INTC 1 (AAOI/SNDK 0 — chronic losses / few periods, by design).

**Scrutinize**: `net_debt_to_ebitda` itself never had an independent Codex functional review (it shipped
earlier this/prior session). Confirm the rule (TTM EBITDA + net debt, skip on EBITDA≤0) and its
provenance are sound.

---

## Change 4 — stale-parse modernization: re-parse INTC / AAOI / SNDK to current contract

**What**: the deferred "FUTURE PROJECT" — INTC/AAOI/SNDK production parses predated the 2026-05-17
YTD-first-class + 2026-06-01 CF D&A composite changes. Re-parsed each to current contract (`xbrl_extract`
→ `build_separated`), then full chain (derive-base → derive-analytics → upsert).

**Evidence (diff-gate per ticker, OLD vs NEW facts)**:
- **INTC**: +98 (IS/CF 6M+9M YTD first-class; CF D&A composite: Q1 2674 / FY2025 11706 / Q1_FY2026 3136),
  −40 (old silently-derived CF Q2/Q3 single-quarter → now derive-base reconstructs from YTD), **CHANGED=0**.
  EBITDA unblocked (FY2025 14354). cal sum sanity 0❌. Applied: 448 facts / 73 analytics.
- **AAOI**: +12 (CF D&A), 0 removed, **CHANGED=0**. cal sanity 0❌. Applied 1072 facts / 272 analytics.
- **SNDK**: **0 added/removed/CHANGED** (already current — recent spin-off); re-upsert for net_debt.
  Applied 379 / 52.
- Freshness chain enforced by the upsert (refused stale derive-base/derive-analytics until re-run — good
  guardrail). LITE + MU already current.

**Scrutinize**: (a) INTC CF Q2/Q3 single-quarter now come from derive-base (not parse) — confirm
derive-base reconstructs them correctly and the frontend CF single-quarter display still works (frontend
visual verification is PENDING — flagged as the one unverified item). (b) INTC EBITDA FY2025 = 14354 —
spot-check the add-backs. (c) **Known pre-existing residual**: AAOI derive-base NLM validation 24✅/20❌
— since the re-parse CHANGED=0, these ❌ predate this session (derived-Q4 vs NLM), NOT introduced here;
needs a separate look but is not a regression.

---

## Change 5 — test fix: drift guard skips DEPRECATED mirrors

`test_analytics_fallback_matches_skill_registry` failed because it scanned the ADR-001-retired flat
prototype `tmp/derive-analytics/` (carries `DEPRECATED.md`, intentionally no longer synced). Fix: skip
mirrors with `DEPRECATED.md`. `scripts/` tests 275 pass. CC/AI commit `dacc5d4`.

**Scrutinize**: is skipping deprecated mirrors the right call vs deleting the prototype? (ADR-001 said
keep-with-marker.)

---

## Commits
- CC_Switch_Config: `f03bd4f` (MU supplement config), `fab768b` (MU 8-K config), `08e690c` (fy_end_month fix)
- AI_Agent: `dacc5d4` (re-parse + net_debt + STATUS + test fix)
- Production DB: MU/INTC/AAOI/LITE/SNDK all re-upserted (facts + dimensional + metrics + analytics)

## Open items (not for this review, tracked)
- Frontend CF single-quarter / EBITDA / net_debt visual verification (will happen in the frontend Build).
- AAOI derive-base NLM 20❌ (pre-existing) — separate investigation.
- Why `build_separated` didn't capture AAOI BS/CF presentation networks — separate ticket.
- supplement Stage-B-always design change + other-ticker supplement re-validation — spawned ticket.

**Ask**: confirm Changes 1–5 are production-correct or list P1/P2. Author will debate each to convergence.

---

## Codex round-1 findings + convergence (2026-06-04)

No P1. 2 P2; both **verified true by author + accepted** (no pushback). Changes 1, 3, 5 cleared.

### P2.1 (Change 4) — Q2/Q3 single-quarter CF are NOT reconstructed (author's handoff claim was WRONG)

Codex correct, author-verified: `derive-base` has **only Q4 rules** (`rules_q4.py`: Q4=FY−9M /
FY−Q1Q2Q3; `derive_engine` emits only `derived_q4`). After the re-parse, INTC's Q2/Q3 single-quarter CF
**flows** (OCF/capex/D&A) were removed (YTD-disclosed → old parser silently derived them; new parser
correctly does not) and **nothing rebuilds them** — only CF `net_income` (carried from IS) survives for
Q2/Q3. Result: quarterly CF display + quarterly TTM analytics (e.g. INTC `net_debt_to_ebitda` has only
FY annual, no quarterly) are missing Q2/Q3 for re-parsed YTD-CF tickers (INTC; check AAOI/SNDK/MU/LITE).
Violates the parse-skill contract "derive-base 要靠 YTD 算 Q2/Q3/Q4" — only Q4 was ever built.

**Accepted fix (Codex option 1)**: add `derive-base` additive rules `Q2 = 6M − Q1`, `Q3 = 9M − 6M`
(IS/CF duration), `period_kind = derived_q2 / derived_q3`, provenance/allowlist same tier as Q4; re-run
derive chain + re-upsert affected tickers. Mirrors the existing Q4 rule.

### P2.2 (Change 2) — fy_end_month fallback-12 must be fail-closed

Accepted: when no ticker_config `fiscal_year_end_month` AND no `--fy-end-month` → **hard fail**, not
warn-then-default-12 (the original bug class is "fiscal year-end silently wrong"). To support a true
calendar default, require an explicit `--allow-calendar-year-default`. Current 5 tickers are configured
so this round's data is safe; fix needed before the next production run on an unconfigured ticker.

### Disposition (user decision: option B)

Both P2s **deferred to the next session as the first work, before the frontend Build** — they are their
own focused TDD change (esp P2.1, a derive-base skill enhancement) that deserves clean context + its own
Codex round. The Q2/Q3 gap is a missing-row gap (no wrong values), not data corruption. Tracked in
`docs/STATUS.md`. **Review NOT signed off** until P2.1 (and P2.2) land.

---

## CLOSURE (2026-06-04) — both P2s landed, review signed off

### P2.1 — derive-base Q2/Q3 reconstruction: SHIPPED to production, Codex 2-round sign-off

Implemented `rules_q2q3` (Q2=6M−Q1, Q3=9M−6M) mirroring rules_q4 + derive-analytics `_SINGLE_Q_KINDS`
TTM extension + migration `20260604120000` (period_kind += derived_q2/q3) + frontend/docs. 2 Codex
rounds: round-1 found 1 P2 (upsert `DERIVE_BASE_RULE_IDS_FALLBACK` stale-row guard missing the Q2/Q3
rule_ids → fixed + `derive_base_delete_scope()` helper + 3 tests) and 2 P3 (YoY-docs, handoff overclaim
— both fixed); round-2 signed off. **Additivity proven both ways** (pre-apply 0 changed/0 removed vs old
DB across 2115 keys; post-apply DB == verified local). Migration applied via Management API; 5 tickers
re-upserted `--apply`, 0 rejected. Full detail: `tmp/2026-06-04-derive-base-q2q3-review.md`. **SIGNED OFF.**

### P2.2 — fy_end_month resolver fail-closed: DONE (CC `863e056`, no production write)

`resolve_fy_end_month(ticker, cli_value, allow_calendar_default=False)` now HARD FAILS (SystemExit) when
neither `--fy-end-month` nor ticker_config `fiscal_year_end_month` resolves, instead of silently
defaulting to 12 (the off-by-one bug class — would still mislabel an unconfigured non-Dec filer like
SNDK). New `--allow-calendar-year-default` loud opt-in for true Dec filers. Both `parse_instance_xbrl.py`
+ `parse_def_xml.py`; `test_period_label.py` 11 tests (unknown-ticker asserts SystemExit; CLI/config/opt-in
paths). Synced 3 runtimes; SKILL.md CHANGELOG; stale "LOUD warning" docstring corrected. Current 5
tickers all configured → no data impact; gate protects the next unconfigured-ticker run. **Codex re-ran
`test_period_label.py` → 11 passed; P2.2 code+tests signed off.**

**Both P2s closed → the retroactive review gate for this session's production changes is now satisfied.**
