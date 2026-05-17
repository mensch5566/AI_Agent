"""Bounded 3-pass derive engine + candidate resolution.

Pipeline (design §4):
  Pass 1 identity_on_direct: identity rules on direct facts only
  Pass 2 GAAP_Q4:            Q4 reconstruction (FY-9M / FY-Q1Q2Q3)
  Pass 3 identity_on_q4:     identity rules on Q4 (period_kind=derived_q4) keys

Each pass produces Candidate[]; resolve_candidates picks one per semantic key,
or skips with a conflict report when hard tolerance breached.
"""
from __future__ import annotations
from collections import defaultdict

from tolerance import diff_classification
from derive_types import Candidate, DerivedMetricRow


SemanticKey = tuple  # (ticker, period, period_kind, statement, version, uni_account)


def _key(c: Candidate) -> SemanticKey:
    return (c.ticker, c.period, c.period_kind, c.statement, c.version, c.uni_account)


def resolve_candidates(candidates: list[Candidate]) -> tuple[list[Candidate], list[dict]]:
    """Group candidates by semantic key; pick best or skip on hard conflict.

    Returns (winners, conflicts).
      winners:   Candidate[]  — at most one per key
      conflicts: dict[]       — for keys skipped due to hard-band disagreement
    """
    by_key: dict[SemanticKey, list[Candidate]] = defaultdict(list)
    for c in candidates:
        by_key[_key(c)].append(c)

    winners: list[Candidate] = []
    conflicts: list[dict] = []
    for k, cs in by_key.items():
        cs_sorted = sorted(cs, key=lambda x: (x.rule_priority, x.chain_depth))
        preferred = cs_sorted[0]
        # Compare every other candidate's value against the preferred.
        hard_break = False
        for other in cs_sorted[1:]:
            cls = diff_classification(preferred.value, other.value, preferred.unit)
            if cls["level"] == "hard":
                hard_break = True
                conflicts.append({
                    "ticker": k[0], "period": k[1], "period_kind": k[2],
                    "statement": k[3], "version": k[4], "uni_account": k[5],
                    "preferred_rule": preferred.rule_id, "preferred_value": preferred.value,
                    "preferred_chain_depth": preferred.chain_depth,
                    "other_rule":     other.rule_id,     "other_value":     other.value,
                    "other_chain_depth": other.chain_depth,
                    "abs_diff": cls["abs"], "rel_pct": cls["rel_pct"],
                    "unit": preferred.unit,
                })
                break
        if not hard_break:
            winners.append(preferred)
    return winners, conflicts


from rules_q4 import q4_candidates
from rules_identity import apply_identity_rules, apply_static_allowlist


def _materialize_facts_with_winners(facts: list, winners: list[Candidate]) -> list:
    """Append Pass 1 / Pass 2 winners as facts for the next pass.

    We use the same FactRow shape so identity rules can iterate uniformly.
    """
    from _shared.sec_json_adapter import FactRow
    out = list(facts)
    for w in winners:
        out.append(FactRow(
            cell_id=f"derived::{w.rule_id}::{w.period}::{w.uni_account}",
            ticker=w.ticker, period=w.period, period_end=w.period_end,
            period_kind=w.period_kind, statement=w.statement, version=w.version,
            uni_account=w.uni_account, source_account="derived",
            xbrl_tag=None, value=w.value, weight=1, unit=w.unit,
            status="DERIVED_FROM_DISCLOSED", ordinal=None,
            long_tail_metadata=None,
            provenance={"rule_id": w.rule_id, "chain_depth": w.chain_depth},
        ))
    return out


def run_engine(
    *, facts: list, calc_rules: dict, qname_to_uni: dict,
) -> dict:
    """Bounded 3-pass driver. Returns {winners, conflicts, stats}."""
    # Pass 1 — identity on direct (GAAP calc + GAAP allowlist + Non-GAAP allowlist)
    p1: list[Candidate] = []
    p1 += apply_identity_rules(facts, calc_rules, qname_to_uni)
    p1 += apply_static_allowlist(facts, version="GAAP")
    p1 += apply_static_allowlist(facts, version="NON_GAAP")
    p1_winners, p1_conflicts = resolve_candidates(p1)

    facts_after_p1 = _materialize_facts_with_winners(facts, p1_winners)

    # Pass 2 — GAAP Q4 reconstruction
    p2: list[Candidate] = q4_candidates(facts_after_p1)
    p2_winners, p2_conflicts = resolve_candidates(p2)

    facts_after_p2 = _materialize_facts_with_winners(facts_after_p1, p2_winners)

    # Pass 3 — identity on Q4 keys
    # Only run identity rules; only emit Candidates whose period is derived_q4
    p3_raw: list[Candidate] = []
    p3_raw += apply_identity_rules(facts_after_p2, calc_rules, qname_to_uni)
    p3_raw += apply_static_allowlist(facts_after_p2, version="GAAP")
    p3 = [c for c in p3_raw if c.period_kind == "derived_q4"]
    # bump chain_depth to reflect we built on Pass 2 outputs
    for c in p3:
        c.chain_depth = 3
        c.chained = True
    p3_winners, p3_conflicts = resolve_candidates(p3)

    return {
        "winners": p1_winners + p2_winners + p3_winners,
        "conflicts": p1_conflicts + p2_conflicts + p3_conflicts,
        "stats": {
            "pass1_count": len(p1_winners),
            "pass2_count": len(p2_winners),
            "pass3_count": len(p3_winners),
            "conflicts":   len(p1_conflicts) + len(p2_conflicts) + len(p3_conflicts),
        },
    }
