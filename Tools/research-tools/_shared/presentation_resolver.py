"""Resolve PDF-faithful display label + presentation order from XBRL labels.json +
edges_pre, at the upsert layer (parse skill untouched). Spec §13.2, G3."""
import re

_KW = {"IS": ("operations", "income"), "BS": ("balancesheet", "financialposition"), "CF": ("cashflow",)}
_EXCLUDE = ("parenthetical", "details", "note", "reconciliation")

def _norm(role):
    return re.sub(r"[-_]", "", role.split("/role/")[-1].lower())

def _face_network_childsets(edges, statement):
    """Map role_uri -> set of bare child local names, for every presentation
    network matching `statement`'s keyword set and not in the exclude list.
    Shared helper behind matching_face_networks / select_network /
    accepted_face_concepts so they agree on exactly which networks count as
    "face" networks for the statement."""
    roles = {}
    for e in edges:
        r = e.get("role_uri", "")
        n = _norm(r)
        if any(x in n for x in _EXCLUDE):
            continue
        if any(k in n for k in _KW[statement]):
            roles.setdefault(r, set()).add(_local(e["child_qname"]))
    return roles


def matching_face_networks(edges, statement):
    """All role_uris that match `statement`'s face-network keyword set and are
    not excluded (parenthetical/details/note/reconciliation), in a deterministic
    order.

    A filer can legitimately have more than one face network for the same
    statement (e.g. a 10-K full statement network + a 10-Q condensed network).
    Returns the empty list when none match (e.g. AAOI BS/CF). Order: primary
    (select_network's pick) first, then the rest sorted by role_uri for
    determinism."""
    roles = _face_network_childsets(edges, statement)
    if not roles:
        return []
    primary = select_network(edges, statement)
    rest = sorted(r for r in roles if r != primary)
    return [primary] + rest


def select_network(edges, statement, facts_concepts=None):
    """Pick the primary presentation network role_uri for `statement`.
    Latest-network primary; keyword set case/hyphen/underscore-insensitive;
    exclude parenthetical/details/note/reconciliation networks; tie-break by the
    network whose child set overlaps most with the ticker's facts (facts_concepts),
    then by size, then PREFER the non-condensed role (a 10-K full statement beats
    a 10-Q condensed statement when otherwise tied). Returns None when no matching
    network exists (e.g. AAOI BS/CF)."""
    roles = _face_network_childsets(edges, statement)
    if not roles:
        return None
    def score(item):
        role, childs = item
        ov = len(childs & facts_concepts) if facts_concepts else 0
        # Tie-break: after overlap + size, prefer the role whose normalized name
        # does NOT contain "condensed" (10-K full beats 10-Q condensed).
        not_condensed = 0 if "condensed" in _norm(role) else 1
        return (ov, len(childs), not_condensed)
    return max(roles.items(), key=score)[0]


def compute_global_ordinals(edges, statement):
    """Global PDF-order ordinal per concept, via pre-order DFS over the MERGED
    presentation tree of ALL face networks matching `statement` (T15 fix).

    XBRL presentation ``order`` is sibling-relative within one parent abstract, so
    it COLLIDES across groups (Revenue, Operating-Expenses, EPS all restart at 1).
    A statement row sorted on raw ``order`` therefore scrambles. This flattens the
    tree depth-first — each parent's children in ``order``, recursing — to a single
    global sequence matching the statement's top-to-bottom PDF layout.

    Arcs from EVERY matching face network (10-K full ∪ 10-Q condensed ∪ prior
    periods, whose role names differ only by case/era) are MERGED and de-duped, so
    a concept disclosed in only one period's network still lands in its correct
    slot relative to the others (e.g. LITE income_before_taxes, present only in the
    full network, slots between non-operating income and income tax).

    Returns ``{bare_local_name: 1-based int}``. A concept on no face tree is absent
    (caller falls back to NLM/manual). First DFS visit wins on a duplicate local
    name; the empty dict is returned when no face network matches (AAOI BS/CF).
    """
    arcs = set()
    for e in edges:
        n = _norm(e.get("role_uri", ""))
        if any(x in n for x in _EXCLUDE):
            continue
        if not any(k in n for k in _KW[statement]):
            continue
        order = e.get("order")
        arcs.add((e.get("parent_qname"), e["child_qname"],
                  float(order) if order is not None else 0.0))
    if not arcs:
        return {}

    children = {}
    childset = set()
    for parent, child, order in arcs:
        children.setdefault(parent, []).append((order, child))
        childset.add(child)
    # Roots = parents that are never themselves a child (incl. a None parent).
    roots = sorted((p for p in children if p not in childset), key=lambda p: str(p))

    out = {}
    counter = [0]
    visited = set()

    def visit(node):
        for _order, child in sorted(children.get(node, []), key=lambda oc: (oc[0], oc[1])):
            if child in visited:
                continue
            visited.add(child)
            counter[0] += 1
            out.setdefault(_local(child), counter[0])
            visit(child)

    for r in roots:
        visit(r)
    return out


def accepted_face_concepts(edges, statement):
    """Set of bare local concept names that appear on ANY matching face network
    for `statement` — the UNION across all `matching_face_networks`.

    This is the exclusion basis for note-level auto-exclusion (T14 Issue2): a
    GAAP fact whose concept is NOT in this union does not appear on any face
    statement and is a note-level sub-component. The union (not a single
    network) ensures we never drop a line that is only present in the other
    (e.g. condensed) network. Empty set when no face network exists."""
    roles = _face_network_childsets(edges, statement)
    out = set()
    for childs in roles.values():
        out |= childs
    return out


def resolve_label_ordinal_any(concept_local, edges, labels, statement, facts_concepts=None,
                              prefer_period=None):
    """Resolve (display_label, ordinal, negated) for a bare local concept across
    ALL matching face networks for `statement` (T14 Issue2).

    ``prefer_period`` ('start'|'end'|None) is forwarded to ``resolve_label_ordinal``
    for CF cash movement-analysis arc selection (see that function).

    Tries the primary network (select_network) first, then the remaining
    `matching_face_networks` in order, returning the FIRST non-None ordinal hit
    (carrying that network's label AND that network's negated flag — all three
    come from the SAME matched edge, in lockstep, never resolved separately). A
    concept present only in the condensed network — or only in the full network
    when condensed is primary — still resolves. AmbiguityError in one network
    skips that network (does not crash); another clean network can still resolve
    it. Returns ``(None, None, False)`` when no matching network resolves the
    concept."""
    for role in matching_face_networks(edges, statement):
        try:
            label, ordinal, negated = resolve_label_ordinal(
                concept_local, role, edges, labels, prefer_period=prefer_period)
        except AmbiguityError:
            continue
        if ordinal is not None:
            return (label, ordinal, negated)
    return (None, None, False)


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


def _edge_negated(edge) -> bool:
    """PDF-faithful sign flag for ONE matched presentation arc (spec §13.2).

    True iff the arc's ``preferred_label`` role, normalized via :func:`_norm`
    (part after ``/role/``, lowercased, dashes/underscores stripped), begins with
    ``"negated"`` — covering negatedLabel, negatedTerseLabel, negatedTotalLabel,
    negatedNetLabel, negatedPeriodStart/EndLabel. No preferred_label → False.

    When True the PDF renders ``-storedValue`` (TRUE negation, not -abs): a stored
    -26 with a negated role displays as +26.
    """
    preferred = edge.get("preferred_label")
    if not preferred:
        return False
    return _norm(preferred).startswith("negated")


def resolve_label_ordinal(concept_local, network_role, edges, labels,
                          prefer_period=None):
    """Resolve PDF-faithful (display_label, ordinal, negated) for a bare local
    concept name within the selected presentation network. Spec §13.2, G3.

    ``prefer_period`` ('start' | 'end' | None): for a concept that appears in BOTH a
    periodStartLabel and a periodEndLabel arc (CF cash reconciliation / movement
    analysis, EFM §7.7), select the arc whose preferred_label role matches — the
    stored ending-balance fact uses 'end' so it renders "…at end of period" instead
    of matched[0] (= periodStart). Falls back to matched[0] when no arc matches the
    preference (keeps existing behavior for every non-dual concept).

    - Only edges where ``edge['role_uri'] == network_role`` are considered.
    - Match edges whose ``child_qname`` local name equals ``concept_local``.
    - Fail-closed (G3): if matched edges reference more than one DISTINCT full
      ``child_qname``, raise :class:`AmbiguityError` — never silently pick one.
    - 0 matches → return ``(None, None, False)`` so the caller can fall back.
    - ``ordinal`` = the matched edge's ``order``.
    - ``negated`` = the matched edge's PDF-faithful sign flag (:func:`_edge_negated`
      — preferred_label role normalized startswith "negated"). Comes from the SAME
      matched edge as label + ordinal, so display sign, label and order stay in
      lockstep.
    - ``display_label``: from ``labels[full_qname]`` pick the text whose role ==
      the edge's ``preferred_label``; fallback chain when that role is absent:
      terseLabel → totalLabel → standard label → None.
    """
    matched = [e for e in edges
               if e.get("role_uri") == network_role
               and _local(e["child_qname"]) == concept_local]
    if not matched:
        return (None, None, False)

    distinct = {e["child_qname"] for e in matched}
    if len(distinct) > 1:
        raise AmbiguityError(
            f"local name {concept_local!r} maps to {len(distinct)} distinct "
            f"qnames in network {network_role!r}: {sorted(distinct)}")

    edge = matched[0]
    if prefer_period in ("start", "end"):
        want = "periodstartlabel" if prefer_period == "start" else "periodendlabel"
        preferred_edge = next(
            (e for e in matched if _norm(e.get("preferred_label") or "") == want),
            None)
        if preferred_edge is not None:
            edge = preferred_edge
    full_qname = edge["child_qname"]
    ordinal = edge.get("order")
    negated = _edge_negated(edge)

    texts = {lab["role"]: lab["text"] for lab in labels.get(full_qname, [])}
    preferred = edge.get("preferred_label")
    for role in (preferred, _TERSE_LABEL, _TOTAL_LABEL, _STD_LABEL):
        if role and role in texts:
            return (texts[role], ordinal, negated)
    return (None, ordinal, negated)


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
    # T14 item1: income_before_taxes is a CORE face line that some filers (LITE)
    # store with a PDF-text source_account (preserved_pdf_label) rather than the
    # tag. Mapping its uni_account → the canonical concept lets the preserved
    # branch borrow the face ordinal without NLM (resolve_via_uni_any). NOTE:
    # this is LITE's concept variant; a filer using a different us-gaap variant
    # (…MinorityInterest…) won't match and falls through to NLM (safe — never a
    # wrong ordinal). Promote this value to a tuple of accepted variants if a
    # second variant is ever observed.
    "income_before_taxes":
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
}


def resolve_via_uni(uni_account, statement, network_role, edges, labels):
    """Resolve PDF-faithful (display_label, ordinal, negated) for a synthetic/null-
    source fact by mapping its ``uni_account`` to its canonical XBRL concept and
    resolving THAT within the selected presentation network. Spec G2, G7. The
    ``negated`` flag comes from the matched canonical edge (delegated to
    :func:`resolve_label_ordinal`).

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


def resolve_via_uni_any(uni_account, edges, labels, statement):
    """Multi-network sibling of :func:`resolve_via_uni` for the preserved_pdf_label
    ORDINAL-borrow path (T14 item1).

    Maps ``uni_account`` → its canonical XBRL concept (CANONICAL_CONCEPT) and
    resolves ``(label, ordinal, negated)`` for THAT concept across ALL matching
    face networks (:func:`resolve_label_ordinal_any` — 10-K full ∪ 10-Q condensed).

    Deliberately LAXER than :func:`resolve_via_uni`: it does NOT require the
    canonical concept to key into ``labels``. The only caller is a
    preserved_pdf_label fact, which already owns its display label (the
    period-exact PDF text) and needs ONLY the face ordinal. The canonical
    concept must still actually appear on a face network for an ordinal to come
    back — otherwise returns ``(None, None)`` (never invents an order).

    Raises :class:`NeedsNlmOrder` when ``uni_account`` has no canonical mapping
    (e.g. a long-tail bucket) → caller routes to NLM, unchanged.
    """
    canonical = CANONICAL_CONCEPT.get(uni_account)
    if canonical is None:
        raise NeedsNlmOrder(
            f"no known canonical concept for uni_account {uni_account!r}")
    return resolve_label_ordinal_any(canonical, edges, labels, statement)
