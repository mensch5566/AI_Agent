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
