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
