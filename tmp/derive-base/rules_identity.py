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
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from _shared.sec_json_adapter import FactRow  # noqa: F401


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


from derive_types import Candidate, input_dict_from_fact


# (output, requires, formula_fn, rule_id, rule_priority)
# formula_fn receives a dict {uni_account: fact_value} and returns float.
STATIC_ALLOWLIST_GAAP = [
    # output, requires, fn, rule_id, priority
    ("gross_profit",              ("revenue", "cost_of_goods_sold"),
        lambda v: v["revenue"] - v["cost_of_goods_sold"],
        "STATIC_ALLOWLIST", 4),
    ("cost_of_goods_sold",        ("revenue", "gross_profit"),
        lambda v: v["revenue"] - v["gross_profit"],
        "STATIC_ALLOWLIST", 4),
    ("total_operating_expenses",  ("gross_profit", "operating_income"),
        lambda v: v["gross_profit"] - v["operating_income"],
        "STATIC_ALLOWLIST", 4),
    ("operating_income",          ("gross_profit", "total_operating_expenses"),
        lambda v: v["gross_profit"] - v["total_operating_expenses"],
        "STATIC_ALLOWLIST", 4),
]

STATIC_ALLOWLIST_NONGAAP = [
    ("cost_of_goods_sold",        ("revenue", "gross_profit"),
        lambda v: v["revenue"] - v["gross_profit"],
        "NG_ALLOWLIST", 5),
    ("gross_profit",              ("revenue", "cost_of_goods_sold"),
        lambda v: v["revenue"] - v["cost_of_goods_sold"],
        "NG_ALLOWLIST", 5),
    ("total_operating_expenses",  ("gross_profit", "operating_income"),
        lambda v: v["gross_profit"] - v["operating_income"],
        "NG_ALLOWLIST", 5),
    ("operating_income",          ("gross_profit", "total_operating_expenses"),
        lambda v: v["gross_profit"] - v["total_operating_expenses"],
        "NG_ALLOWLIST", 5),
]


def apply_static_allowlist(facts: list["FactRow"], version: str) -> list[Candidate]:
    """Apply static identity allowlist rules for sparse GAAP fallback and Non-GAAP.

    For each (period, statement, version, unit), try each allowlist rule.
    Skips if output uni_account already direct.
    Skips if any required input is missing.
    """
    allowlist = STATIC_ALLOWLIST_GAAP if version == "GAAP" else STATIC_ALLOWLIST_NONGAAP

    # Group: (period, statement, version, unit) → uni_account → fact
    grouped: dict[tuple, dict[str, object]] = defaultdict(dict)
    for f in facts:
        if f.version != version:
            continue
        grouped[(f.period, f.statement, f.version, f.unit)][f.uni_account] = f

    out: list[Candidate] = []
    for (period, stmt, ver, unit), uni_map in grouped.items():
        for output_uni, requires, fn, rule_id, priority in allowlist:
            if output_uni in uni_map:
                continue  # parent already direct
            if not all(r in uni_map for r in requires):
                continue
            try:
                value = fn({r: uni_map[r].value for r in requires})
            except Exception:
                continue
            template = uni_map[requires[0]]
            out.append(Candidate(
                ticker=template.ticker, period=period, period_kind=template.period_kind,
                period_start=None, period_end=template.period_end,
                statement=stmt, version=ver, uni_account=output_uni,
                value=value, unit=unit,
                rule_id=rule_id, rule_priority=priority,
                chain_depth=1, chained=False,
                inputs=[input_dict_from_fact(uni_map[r]) for r in requires],
                extras={"formula": " - ".join(requires)},
            ))
    return out


def apply_identity_rules(
    facts: list["FactRow"],
    calc_rules: dict[tuple, list[dict]],
    qname_to_uni: dict[str, str],
) -> list[Candidate]:
    """For each (period, statement, version, unit), try each calc rule.

    Emits a Candidate per (period × rule × derivable parent).
    Skips if any required child is missing.
    Skips if parent uni_account already exists for that period.
    """
    # Index facts by (period, statement, version, unit, xbrl_tag)
    fact_idx: dict[tuple, object] = {}
    seen_uni: set[tuple] = set()
    for f in facts:
        if f.version != "GAAP":
            continue
        key = (f.period, f.statement, f.version, f.unit, f.xbrl_tag)
        fact_idx.setdefault(key, f)
        seen_uni.add((f.period, f.statement, f.version, f.uni_account))

    out: list[Candidate] = []
    # Build a (period, statement, version, unit) → child tag → fact lookup
    facts_by_pctx: dict[tuple, dict[str, object]] = defaultdict(dict)
    for (period, stmt, ver, unit, tag), f in fact_idx.items():
        facts_by_pctx[(period, stmt, ver, unit)][tag] = f

    for (role_uri, parent_qname), children in calc_rules.items():
        parent_uni = qname_to_uni.get(parent_qname)
        if not parent_uni:
            continue
        for (period, stmt, ver, unit), tag_map in facts_by_pctx.items():
            # All children present?
            child_facts = []
            ok = True
            for ch in children:
                cf = tag_map.get(ch["child_qname"])
                if cf is None:
                    ok = False
                    break
                child_facts.append((cf, ch["weight"]))
            if not ok:
                continue
            if (period, stmt, ver, parent_uni) in seen_uni:
                continue
            value = sum(cf.value * w for cf, w in child_facts)
            # period_end: take from any child (they share the period)
            period_end = child_facts[0][0].period_end
            period_start = None
            ticker = child_facts[0][0].ticker
            inputs = [input_dict_from_fact(cf) for cf, _ in child_facts]
            formula = " + ".join(
                f"{w:+d} * {qname_to_uni.get(ch['child_qname'], ch['child_qname'])}"
                for ch, (_, w) in zip(children, child_facts)
            )
            out.append(Candidate(
                ticker=ticker, period=period, period_kind=child_facts[0][0].period_kind,
                period_start=period_start, period_end=period_end,
                statement=stmt, version=ver, uni_account=parent_uni,
                value=value, unit=unit,
                rule_id="CALC_LINKBASE", rule_priority=3,
                chain_depth=1, chained=False,
                inputs=inputs,
                extras={"role_uri": role_uri, "parent_qname": parent_qname, "formula": formula},
            ))
    return out


