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


def _local_name(qname_or_tag: str | None) -> str:
    """Strip any 'prefix:' from an XBRL identifier so calc child_qname
    (`us-gaap:GrossProfit`) and FactRow.xbrl_tag (`GrossProfit`) match.
    Returns "" for None/empty."""
    if not qname_or_tag:
        return ""
    return qname_or_tag.rsplit(":", 1)[-1]


def calc_rules_from_edges(edges: list[dict]) -> dict[tuple, list[dict]]:
    """Group calc edges by (period, role_uri, parent_qname).

    Each value is a list of unique child dicts (deduped by child_qname+weight):
      {"child_qname": str, "weight": int, "source": str | None}

    Period is included in the key because the same (role_uri, parent, child)
    edge appears once per filing period in production cal files; collapsing
    across period would replicate children N times and over-derive the parent
    by Nx if identity ever fired. Period-aware grouping also lets us handle
    company taxonomies that legitimately change between filings.

    Real XBRL calc edges carry parent_qname/role_uri/child_qname. Long-tail
    roll-up edges injected by build_separated.py use bare parent/child fields
    (no qname, no role_uri) and are filtered out by the qname presence check.
    """
    grouped: dict[tuple, list[dict]] = defaultdict(list)
    for e in edges:
        # Missing edge_type means production cal file (already type-implicit by
        # filename); only reject when edge_type is explicitly non-calc.
        edge_type = e.get("edge_type")
        if edge_type is not None and edge_type != "calc":
            continue
        parent = e.get("parent_qname")
        role = e.get("role_uri")
        child = e.get("child_qname")
        if not (parent and role and child):
            continue
        period = e.get("period")  # may be None for fixtures; deduped later
        grouped[(period, role, parent)].append({
            "child_qname": child,
            "weight": int(e.get("weight") or 0),
            "source": e.get("source"),
        })
    # Dedupe children within each rule by (child_qname, weight).
    out: dict[tuple, list[dict]] = {}
    for key, children in grouped.items():
        seen: set[tuple] = set()
        unique: list[dict] = []
        for c in children:
            k = (c["child_qname"], c["weight"])
            if k in seen:
                continue
            seen.add(k)
            unique.append(c)
        out[key] = unique
    return out


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
    # Index facts by (period, statement, version, unit, local_tag).
    # Use _local_name() so calc child_qname (us-gaap:GrossProfit) matches
    # FactRow.xbrl_tag (GrossProfit) regardless of namespace prefix.
    fact_idx: dict[tuple, object] = {}
    seen_uni: set[tuple] = set()
    for f in facts:
        if f.version != "GAAP":
            continue
        key = (f.period, f.statement, f.version, f.unit, _local_name(f.xbrl_tag))
        fact_idx.setdefault(key, f)
        seen_uni.add((f.period, f.statement, f.version, f.uni_account))

    out: list[Candidate] = []
    # Build a (period, statement, version, unit) → child tag → fact lookup
    facts_by_pctx: dict[tuple, dict[str, object]] = defaultdict(dict)
    for (period, stmt, ver, unit, tag), f in fact_idx.items():
        facts_by_pctx[(period, stmt, ver, unit)][tag] = f

    for rule_key, children in calc_rules.items():
        # Support both period-aware (period, role, parent) and legacy
        # (role, parent) keys so old test fixtures keep working.
        if len(rule_key) == 3:
            rule_period, role_uri, parent_qname = rule_key
        else:
            rule_period = None
            role_uri, parent_qname = rule_key
        parent_uni = qname_to_uni.get(parent_qname)
        if not parent_uni:
            continue
        for (period, stmt, ver, unit), tag_map in facts_by_pctx.items():
            # Period-aware rules only fire against matching-period facts.
            if rule_period is not None and rule_period != period:
                continue
            # All children present?
            child_facts = []
            ok = True
            for ch in children:
                cf = tag_map.get(_local_name(ch["child_qname"]))
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


def build_qname_to_uni(inline_json: dict) -> dict[str, str]:
    """Read source_account values from the inline {TICKER}_gaap.json long-format
    rows and build a qname → uni_account lookup.

    parse-10QK-gaap stores `source_account` as the bare XBRL local name (e.g.
    `GrossProfit`); calc edges store qname with `us-gaap:` prefix. We assume
    us-gaap namespace; ticker extensions (rare in three-statement core) are
    skipped — the rule simply won't fire for them.
    """
    m: dict[str, str] = {}
    for stmt_key in ("income_statement", "balance_sheet", "cash_flow_statement"):
        for row in inline_json.get(stmt_key, []):
            uni = row.get("uni_account")
            tag = row.get("source_account")
            if not (uni and tag):
                continue
            if ":" in tag:
                m[tag] = uni
            else:
                m[f"us-gaap:{tag}"] = uni
    return m


