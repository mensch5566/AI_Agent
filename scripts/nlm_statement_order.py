"""NLM ordering artifact — matcher + schema + reader (spec G1, G7, G8).

Where a statement has NO XBRL presentation network (e.g. AAOI BS/CF), row
ORDER comes from a human-audited NLM artifact: a list of PDF lines captured
top-to-bottom from the filing. This module is the pure-Python half of that
flow — it binds each PDF line to a fact ``cell_id`` so the frontend can order
rows. It does NOT query NLM (that is the next task) and never touches the
network.

Safety properties:
  - G8 uniqueness: at the ``uni_account`` fallback tier, NEVER guess when more
    than one display-eligible fact remains — emit ``ambiguous_uni_account``.
  - G1/G7: NEVER feed a ``pending_audit`` artifact's order into production —
    ``read_audited_order`` returns ``{}`` unless ``status == "audited"``.

The downstream adapter (Task 8) calls ``read_audited_order`` on a
``NeedsNlmOrder`` statement; the producer (Task 7) builds the artifact.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

# Match-method labels, in priority order (first that yields a UNIQUE fact wins).
METHOD_EXACT_DISPLAY = "exact_display_label"
METHOD_NORMALIZED_DISPLAY = "normalized_display_label"
METHOD_SOURCE_ACCOUNT = "source_account"
METHOD_UNI_ACCOUNT = "uni_account"

REASON_AMBIGUOUS_UNI = "ambiguous_uni_account"
REASON_NO_FACT = "no_fact_for_pdf_line"

# Confidence per match method: high-precision label/source matches are 1.0;
# the uni_account fallback tier is intrinsically weaker (display_label and
# source_account both failed), so it gets a reduced confidence. Unmatched
# lines carry no confidence (None).
CONFIDENCE_HIGH = 1.0
CONFIDENCE_UNI = 0.5
_HIGH_CONFIDENCE_METHODS = {
    METHOD_EXACT_DISPLAY,
    METHOD_NORMALIZED_DISPLAY,
    METHOD_SOURCE_ACCOUNT,
}

VALID_STATUSES = {"pending_audit", "audited"}
VALID_STATEMENTS = {"IS", "BS", "CF"}

_ARTIFACT_TOP_KEYS = (
    "source_doc",
    "accession",
    "period",
    "form",
    "page_or_section",
    "statement",
    "status",
    "signer",
    "lines",
)

# Punctuation stripped during normalization (keep alphanumerics + spaces).
_PUNCT_RE = re.compile(r"[^\w\s]", flags=re.UNICODE)
_WS_RE = re.compile(r"\s+")


def _normalize(text: Any) -> Optional[str]:
    """Lowercase, strip punctuation, collapse whitespace.

    Returns ``None`` for non-string / empty input so it never spuriously
    matches another ``None``-derived value.
    """
    if not isinstance(text, str):
        return None
    no_punct = _PUNCT_RE.sub(" ", text)
    collapsed = _WS_RE.sub(" ", no_punct).strip().lower()
    return collapsed or None


def _result(
    cell_id: Optional[str],
    method: Optional[str],
    reason: Optional[str],
) -> Dict[str, Optional[str]]:
    return {
        "matched_cell_id": cell_id,
        "match_method": method,
        "unmatched_reason": reason,
    }


def match_pdf_line_to_fact(
    pdf_line: Dict[str, Any],
    facts: List[Dict[str, Any]],
    display_eligible: bool = True,
) -> Dict[str, Optional[str]]:
    """Bind a single PDF line to a fact ``cell_id``.

    Match priority — the first tier that yields exactly ONE candidate wins:
      1. exact ``pdf_label == fact['display_label']``       → exact_display_label
      2. normalized equality of pdf_label vs display_label  → normalized_display_label
      3. exact ``pdf_label == fact['source_account']``      → source_account
      4. ``uni_account`` tier — only when exactly ONE display-eligible fact
         remains. If >1 candidate here → matched_cell_id=None,
         unmatched_reason="ambiguous_uni_account" (spec G8).

    No tier matches → unmatched_reason="no_fact_for_pdf_line".

    ``display_eligible`` is a caller contract flag: the caller pre-filters
    ``facts`` to display-eligible facts. When False, nothing is eligible.
    """
    if not display_eligible or not facts:
        return _result(None, None, REASON_NO_FACT)

    pdf_label = pdf_line.get("pdf_label")

    # --- Tier 1: exact display_label -------------------------------------- #
    if isinstance(pdf_label, str):
        tier1 = [f for f in facts if f.get("display_label") == pdf_label]
        if len(tier1) == 1:
            return _result(tier1[0]["cell_id"], METHOD_EXACT_DISPLAY, None)

    # --- Tier 2: normalized display_label --------------------------------- #
    norm_pdf = _normalize(pdf_label)
    if norm_pdf is not None:
        tier2 = [f for f in facts if _normalize(f.get("display_label")) == norm_pdf]
        if len(tier2) == 1:
            return _result(tier2[0]["cell_id"], METHOD_NORMALIZED_DISPLAY, None)

    # --- Tier 3: exact source_account ------------------------------------- #
    if isinstance(pdf_label, str):
        tier3 = [f for f in facts if f.get("source_account") == pdf_label]
        if len(tier3) == 1:
            return _result(tier3[0]["cell_id"], METHOD_SOURCE_ACCOUNT, None)

    # --- Tier 4: uni_account fallback (uniqueness gate, spec G8) ----------- #
    # Only reachable when no higher tier produced a unique match. Candidates
    # are facts whose normalized ``uni_account`` matches the normalized
    # pdf_label. We refuse to guess (spec G8) when more than one remains; if
    # exactly one, we bind it; if none, the pdf_line corresponds to no fact.
    if norm_pdf is not None:
        tier4 = [f for f in facts if _normalize(f.get("uni_account")) == norm_pdf]
        if len(tier4) == 1:
            return _result(tier4[0]["cell_id"], METHOD_UNI_ACCOUNT, None)
        if len(tier4) > 1:
            return _result(None, None, REASON_AMBIGUOUS_UNI)

    return _result(None, None, REASON_NO_FACT)


def bidirectional_unmatched(
    pdf_lines: List[Dict[str, Any]],
    facts: List[Dict[str, Any]],
) -> Dict[str, List[Any]]:
    """Report unmatched lines and unmatched facts in both directions.

    Returns:
      - ``pdf_without_fact``: PDF lines that matched no fact (full line dicts).
      - ``fact_without_pdf_line``: display-eligible fact ``cell_id``s that no
        PDF line matched.

    ``facts`` is assumed to be the display-eligible set (same contract as the
    matcher's pre-filtered input).
    """
    pdf_without_fact: List[Any] = []
    matched_cell_ids: set = set()

    for line in pdf_lines:
        res = match_pdf_line_to_fact(line, facts, display_eligible=True)
        cid = res["matched_cell_id"]
        if cid is None:
            pdf_without_fact.append(line)
        else:
            matched_cell_ids.add(cid)

    fact_without_pdf_line = [
        f["cell_id"] for f in facts if f.get("cell_id") not in matched_cell_ids
    ]

    return {
        "pdf_without_fact": pdf_without_fact,
        "fact_without_pdf_line": fact_without_pdf_line,
    }


def validate_artifact(artifact: Dict[str, Any]) -> List[str]:
    """Validate an ordering artifact against the schema.

    Returns a list of human-readable error strings (empty == valid).

    Schema:
      {source_doc, accession, period, form, page_or_section, statement,
       status, signer,
       lines: [{ordinal, pdf_label, matched_cell_id, match_method,
                confidence, unmatched_reason}]}

    Enforced (minimum):
      - all top-level keys present
      - status ∈ {pending_audit, audited}
      - statement ∈ {IS, BS, CF}
      - each line has numeric ``ordinal`` + string ``pdf_label``
    """
    errors: List[str] = []

    if not isinstance(artifact, dict):
        return ["artifact must be a dict"]

    for key in _ARTIFACT_TOP_KEYS:
        if key not in artifact:
            errors.append(f"missing top-level key: {key}")

    status = artifact.get("status")
    if status not in VALID_STATUSES:
        errors.append(
            f"status must be one of {sorted(VALID_STATUSES)}, got: {status!r}"
        )

    statement = artifact.get("statement")
    if statement not in VALID_STATEMENTS:
        errors.append(
            f"statement must be one of {sorted(VALID_STATEMENTS)}, got: {statement!r}"
        )

    lines = artifact.get("lines")
    if "lines" in artifact and not isinstance(lines, list):
        errors.append("lines must be a list")
    elif isinstance(lines, list):
        for i, line in enumerate(lines):
            if not isinstance(line, dict):
                errors.append(f"line[{i}] must be a dict")
                continue
            ordinal = line.get("ordinal")
            # bool is a subclass of int — reject it as an ordinal.
            if not isinstance(ordinal, (int, float)) or isinstance(ordinal, bool):
                errors.append(f"line[{i}] ordinal must be a number, got: {ordinal!r}")
            if not isinstance(line.get("pdf_label"), str):
                errors.append(f"line[{i}] pdf_label must be a string")

    return errors


def read_audited_order(artifact: Dict[str, Any]) -> Dict[str, int]:
    """Build ``{cell_id: ordinal}`` from an AUDITED artifact only.

    Safety (G1/G7): a ``pending_audit`` (or any non-``audited``) artifact
    returns ``{}`` — unaudited order MUST never feed production. Only lines
    with a non-null ``matched_cell_id`` contribute.
    """
    if artifact.get("status") != "audited":
        return {}

    order: Dict[str, int] = {}
    for line in artifact.get("lines", []):
        cell_id = line.get("matched_cell_id")
        if cell_id is not None:
            order[cell_id] = line.get("ordinal")
    return order


def _confidence_for(method: Optional[str]) -> Optional[float]:
    """Map a match_method to a confidence score (None when unmatched)."""
    if method in _HIGH_CONFIDENCE_METHODS:
        return CONFIDENCE_HIGH
    if method == METHOD_UNI_ACCOUNT:
        return CONFIDENCE_UNI
    return None


def produce_nlm_order(
    ticker: str,
    statement: str,
    facts: List[Dict[str, Any]],
    nlm_query_fn: Callable[[str, str], List[Dict[str, Any]]],
    out_dir: str,
    *,
    source_doc: str,
    accession: str,
    period: str,
    form: str,
    page_or_section: str,
) -> Tuple[Dict[str, Any], Dict[str, List[Any]]]:
    """Build a ``pending_audit`` NLM ordering artifact (spec G1/G7/G8).

    This is the runtime entry point. The NLM query is INJECTED via
    ``nlm_query_fn`` — a callable ``(ticker, statement) -> [pdf_line, ...]``
    returning PDF lines top-to-bottom, each ``{"pdf_label": str,
    "page_or_section": str (optional)}``. At runtime the caller injects a
    function that wraps the NLM MCP query; tests inject a stub. This producer
    NEVER imports an MCP client and never touches the network / Supabase.

    Steps:
      1. ``lines_raw = nlm_query_fn(ticker, statement)``.
      2. For each raw line, assign 1-based ``ordinal`` and bind it to a fact
         via ``match_pdf_line_to_fact(... display_eligible=True)``. Confidence
         is 1.0 for label/source matches, 0.5 for the uni_account tier, None
         when unmatched.
      3. Assemble the artifact with ``status="pending_audit"`` and
         ``signer=None`` — an unaudited artifact MUST never feed production.
      4. ``validate_artifact`` must pass (else ``ValueError``).
      5. Write to ``{out_dir}/{TICKER}_{STATEMENT}_nlm_order.json`` (pretty
         JSON) and RETURN ``(artifact, bidirectional_unmatched(...))``.

    Returns ``(artifact, unmatched_report)``.
    """
    lines_raw = nlm_query_fn(ticker, statement)

    artifact_lines: List[Dict[str, Any]] = []
    for idx, raw in enumerate(lines_raw, start=1):
        match = match_pdf_line_to_fact(raw, facts, display_eligible=True)
        method = match["match_method"]
        artifact_lines.append(
            {
                "ordinal": idx,
                "pdf_label": raw.get("pdf_label"),
                "matched_cell_id": match["matched_cell_id"],
                "match_method": method,
                "confidence": _confidence_for(method),
                "unmatched_reason": match["unmatched_reason"],
            }
        )

    artifact: Dict[str, Any] = {
        "source_doc": source_doc,
        "accession": accession,
        "period": period,
        "form": form,
        "page_or_section": page_or_section,
        "statement": statement,
        "status": "pending_audit",
        "signer": None,
        "lines": artifact_lines,
    }

    errors = validate_artifact(artifact)
    if errors:
        raise ValueError(
            "produce_nlm_order built an invalid artifact: " + "; ".join(errors)
        )

    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{ticker.upper()}_{statement.upper()}_nlm_order.json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(artifact, fh, indent=2, ensure_ascii=False)

    unmatched = bidirectional_unmatched(lines_raw, facts)

    n_pdf = len(unmatched["pdf_without_fact"])
    n_fact = len(unmatched["fact_without_pdf_line"])
    print(
        f"[produce_nlm_order] {ticker.upper()} {statement.upper()} → {out_path} "
        f"(pending_audit, {len(artifact_lines)} lines; "
        f"unmatched: {n_pdf} pdf-without-fact, {n_fact} fact-without-pdf-line)"
    )

    return artifact, unmatched
