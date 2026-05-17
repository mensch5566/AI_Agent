"""Identity rule sources for derive-base.

Two rule sources (design §3.2):
  1. calc-linkbase rules (GAAP only): parent + children + weights, grouped
     by (role_uri, parent_qname). Built from {TICKER}_gaap_edges_cal.json.
  2. Static allowlist (small, hand-coded): used for Non-GAAP sparse identity
     and as a GAAP fallback when calc edges are absent.

Both produce Candidate rows via apply_identity_rules() (Task 8).
"""
from __future__ import annotations
from collections import defaultdict


def calc_rules_from_edges(edges: list[dict]) -> dict[tuple, list[dict]]:
    """Group calc edges by (role_uri, parent_qname).

    Each value is a list of child dicts with at least:
      {"child_qname": str, "weight": int, "source": str | None}
    """
    out: dict[tuple, list[dict]] = defaultdict(list)
    for e in edges:
        if e.get("edge_type") != "calc":
            continue
        parent = e.get("parent_qname")
        role = e.get("role_uri")
        child = e.get("child_qname")
        if not (parent and role and child):
            continue
        out[(role, parent)].append({
            "child_qname": child,
            "weight": int(e.get("weight") or 0),
            "source": e.get("source"),
        })
    return dict(out)
