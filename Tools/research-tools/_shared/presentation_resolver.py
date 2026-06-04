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


class NeedsNlmOrder(Exception):
    """Raised when a synthetic (``SUM(...)``) or null-source fact can't have its
    canonical concept resolved in this filing's presentation network/labels —
    either no known canonical mapping for the ``uni_account``, or the canonical
    concept is not actually disclosed (absent from the selected network OR from
    the labels map). Fail-closed safety property (spec G7): NEVER invent a label
    or render ``SUM(...)``; route to the NLM ordering artifact / manual handling
    instead."""


# uni_account → bare canonical us-gaap local name. Minimal seed map (spec G2):
# the primary candidate per the parse skill's IS/BS/CF tag maps. Hardcoded here
# on purpose — do NOT import from the parse skill.
CANONICAL_CONCEPT = {
    "net_income": "NetIncomeLoss",
    "shares_basic_millions": "WeightedAverageNumberOfSharesOutstandingBasic",
    "shares_diluted_millions": "WeightedAverageNumberOfDilutedSharesOutstanding",
    "depreciation_and_amortization": "DepreciationAndAmortization",
    "selling_general_administrative": "SellingGeneralAndAdministrativeExpense",
}


def resolve_via_uni(uni_account, statement, network_role, edges, labels):
    """Resolve PDF-faithful (display_label, ordinal) for a synthetic/null-source
    fact by mapping its ``uni_account`` to its canonical XBRL concept and
    resolving THAT within the selected presentation network. Spec G2, G7.

    - ``canonical = CANONICAL_CONCEPT.get(uni_account)``; if no mapping →
      raise :class:`NeedsNlmOrder`.
    - The canonical concept must BE DISCLOSED: present as an edge in the SELECTED
      network (``role_uri == network_role`` with ``child_qname`` local == canonical)
      AND ``f"us-gaap:{canonical}"`` must key into ``labels``. If either is
      missing → raise :class:`NeedsNlmOrder` (never invent a label / render SUM).
    - Otherwise delegate to :func:`resolve_label_ordinal` on the canonical local.
    """
    canonical = CANONICAL_CONCEPT.get(uni_account)
    if canonical is None:
        raise NeedsNlmOrder(
            f"no known canonical concept for uni_account {uni_account!r}")

    in_network = any(
        e.get("role_uri") == network_role
        and _local(e["child_qname"]) == canonical
        for e in edges)
    if not in_network or f"us-gaap:{canonical}" not in labels:
        raise NeedsNlmOrder(
            f"canonical concept {canonical!r} for uni_account {uni_account!r} "
            f"is not disclosed in network {network_role!r} / labels map")

    return resolve_label_ordinal(canonical, network_role, edges, labels)
