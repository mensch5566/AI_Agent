"""Resolve PDF-faithful display label + presentation order from XBRL labels.json +
edges_pre, at the upsert layer (parse skill untouched). Spec §13.2, G3."""
import re

_KW = {"IS": ("operations", "income"), "BS": ("balancesheet", "financialposition"), "CF": ("cashflow",)}
_EXCLUDE = ("parenthetical", "details", "note", "reconciliation")

def _norm(role):
    return re.sub(r"[-_]", "", role.split("/role/")[-1].lower())

def select_network(edges, statement, facts_concepts=None):
    """Pick the primary presentation network role_uri for `statement`.
    Latest-network primary; keyword set case/hyphen/underscore-insensitive;
    exclude parenthetical/details/note/reconciliation networks; tie-break by the
    network whose child set overlaps most with the ticker's facts (facts_concepts),
    then by size. Returns None when no matching network exists (e.g. AAOI BS/CF)."""
    roles = {}
    for e in edges:
        r = e.get("role_uri", "")
        n = _norm(r)
        if any(x in n for x in _EXCLUDE):
            continue
        if any(k in n for k in _KW[statement]):
            roles.setdefault(r, set()).add(e["child_qname"].split(":")[-1])
    if not roles:
        return None
    def score(item):
        role, childs = item
        ov = len(childs & facts_concepts) if facts_concepts else 0
        return (ov, len(childs))
    return max(roles.items(), key=score)[0]


# Standard XBRL label roles used in the PDF-faithful fallback chain (spec §13.2).
_STD_LABEL = "http://www.xbrl.org/2003/role/label"
_TERSE_LABEL = "http://www.xbrl.org/2003/role/terseLabel"
_TOTAL_LABEL = "http://www.xbrl.org/2003/role/totalLabel"


class AmbiguityError(Exception):
    """Raised when a bare local name resolves to more than one distinct full
    child_qname within the selected network (e.g. us-gaap:GrossProfit AND
    intc:GrossProfit). Fail-closed (spec G3): NEVER silently pick one — route to
    manual / NLM handling instead."""


def _local(qname):
    """Strip any ``prefix:`` — return the text after the last ':'. Handles both
    ``us-gaap:GrossProfit`` and a bare ``GrossProfit``."""
    return qname.rsplit(":", 1)[-1]


def resolve_label_ordinal(concept_local, network_role, edges, labels):
    """Resolve PDF-faithful (display_label, ordinal) for a bare local concept
    name within the selected presentation network. Spec §13.2, G3.

    - Only edges where ``edge['role_uri'] == network_role`` are considered.
    - Match edges whose ``child_qname`` local name equals ``concept_local``.
    - Fail-closed (G3): if matched edges reference more than one DISTINCT full
      ``child_qname``, raise :class:`AmbiguityError` — never silently pick one.
    - 0 matches → return ``(None, None)`` so the caller can fall back.
    - ``ordinal`` = the matched edge's ``order``.
    - ``display_label``: from ``labels[full_qname]`` pick the text whose role ==
      the edge's ``preferred_label``; fallback chain when that role is absent:
      terseLabel → totalLabel → standard label → None.
    """
    matched = [e for e in edges
               if e.get("role_uri") == network_role
               and _local(e["child_qname"]) == concept_local]
    if not matched:
        return (None, None)

    distinct = {e["child_qname"] for e in matched}
    if len(distinct) > 1:
        raise AmbiguityError(
            f"local name {concept_local!r} maps to {len(distinct)} distinct "
            f"qnames in network {network_role!r}: {sorted(distinct)}")

    edge = matched[0]
    full_qname = edge["child_qname"]
    ordinal = edge.get("order")

    texts = {lab["role"]: lab["text"] for lab in labels.get(full_qname, [])}
    preferred = edge.get("preferred_label")
    for role in (preferred, _TERSE_LABEL, _TOTAL_LABEL, _STD_LABEL):
        if role and role in texts:
            return (texts[role], ordinal)
    return (None, ordinal)
