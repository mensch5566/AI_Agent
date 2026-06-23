# parse-10QK-gaap same-line double-tag single-emission — converged design (Argue 2026-06-14)

Argue `lite-stbcd` (architect=Claude Opus vs skeptic=Codex GPT-5.5, 5 rounds, **status=consensus**,
score 91.43, 11/11 claims accepted by BOTH seats). Transcript: `~/.config/argue/lite-stbcd-{result.json,summary.md}`.

## Problem
LITE (Lumentum) tags ONE balance-sheet face line — NLM-verified label **"Current portion of
long-term debt"** — under TWO XBRL concepts, `us-gaap:ShortTermBorrowings` AND
`us-gaap:LongTermDebtCurrent`, with IDENTICAL values in 6 periods. With
`short_term_borrowings=[ShortTermBorrowings,…]` and `current_debt=[DebtCurrent, LongTermDebtCurrent]`
both core, a re-parse double-counts current liabilities (footing overshoots `LiabilitiesCurrent`).

## Rule (narrow, registry-bounded, decidable from concepts+values only)
A curated registry `SAME_LINE_DOUBLE_TAG_PAIRS` of `{concept_a (suppressed), suppressed_uni_account,
concept_b (winner), winner_uni_account, rolls_up_to, rule_id}`, seeded:
`ShortTermBorrowings → short_term_borrowings` (suppressed) / `LongTermDebtCurrent → current_debt` (winner).

`apply_same_line_single_emission(bs_liabilities, bs_tag_by_period)` runs AFTER per-metric fact
selection and BEFORE core-row emission. A period collapses **only** when, for a registry pair:
1. the suppressed metric's selected value for that period came from `concept_a`, AND
2. the winner metric's selected value came from `concept_b`, AND
3. both are present, AND
4. the values are **EXACTLY equal** (no tolerance; covers 0.0==0.0).

On collapse: remove the suppressed period from its core metric (footing counts the winner once);
preserve the suppressed fact in `bs_long_tail` with `single_emission_suppressed=true`,
`footing_excluded=true`, `suppression_rule_id`, `rolls_up_to=winner` (audit lineage only).

Guarantees:
- Precedence is hard-coded per registry pair — NEVER inferred from face labels / concept specificity
  at runtime (parse has no face label).
- Single-tag periods (only one concept present) are structurally untouched (trigger needs BOTH).
- Genuinely-distinct two-line filers (both present, DIFFERENT values) keep BOTH core rows (fail-safe;
  parse cannot merge without face-label evidence).
- Unregistered concept pairs / unrelated equal values are NOT collapsed.
- 0.0==0.0 collapses but the winner `current_debt=0` row still emits.
- New double-tag structures require a new registry row + tests — never "any two equal core values".

## Verification (LITE re-parse)
6 DUP periods → `current_debt` keeps value (LongTermDebtCurrent), `short_term_borrowings` core
suppressed, `ShortTermBorrowings` preserved in `bs_long_tail` (metadata in gaap.json source).
Early genuine "Short-term debt" periods (FY2023 ~420M) untouched. cal sum sanity 312✅/0❌;
current-liab footing overshoot = 0; `debt_to_equity` Q1_FY2026 = 4.15 counts current_debt once.
TDD: `test_face_debt_map.py` (8 single-emission cases; 20 total green; full suite 78).

## Out-of-scope note — RESOLVED (original diagnosis was wrong)
LITE's long_term_debt was empty for Q4_FY2023 / Q1-Q3_FY2024 (face label "Convertible notes,
non-current", $2,500.0–2,502.4M). Initially suspected a filer extension concept, but companyfacts
DOES expose it under the STANDARD `us-gaap:ConvertibleDebtNoncurrent` — it was just missing from
the `long_term_debt` candidate list. Fixed by appending `ConvertibleDebtNoncurrent` as a
lower-priority fallback candidate (after the standard LTD concepts). LITE long_term_debt now
27/27 periods. Lesson: a changed BS face *label* does not imply a changed *concept* — check the
full companyfacts concept set before concluding "extension, unreachable".

## build_separated note
`build_separated.py` strips `long_tail_metadata` from facts (converts `rolls_up_to` to cal edges),
so the rich single-emission metadata survives in `{T}_gaap.json` (xbrl_extract source) but not in
`{T}_gaap_facts.json`; the suppressed VALUE + rolls_up_to edge are preserved there.
