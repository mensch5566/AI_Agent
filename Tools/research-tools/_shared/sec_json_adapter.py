"""SEC ParseSkill JSON -> DB-ready row adapter.

Spec: tmp/financials-viewer-redesign-plan.md §18.3 (v5) + §20 (v5.1).

Three input streams:
    parse-10QK-gaap     -> AAOI_gaap_facts.json + AAOI_gaap_edges_{cal,pre}.json
                          + AAOI_sign_flip_concepts.json
    parse-8k-nongaap    -> AAOI_nongaap.json
    parse-SEC-supplement-> AAOI_supplement_facts_v3.json + AAOI_supplement_edges_v3.json

Output: NormalizedBatch dataclass with rows ready for upsert + validation
report (rejected rows, dedupe stats, value conflicts).

JSON variability ends in this module. Upsert script / API / Viewer should
never see raw JSON quirks.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from . import cell_id as _id
from .audit_metadata import (
    AUDIT_PROVENANCE_KEYS,
    CLASSIFICATION_KEYS,
    MANUAL_CLASSIFICATION_SOURCES,
    PRESERVATION_EVENT_KEYS,
    PRESERVATION_EVENTS,
    is_manual_audit_source,
    is_manual_classification_source,
    normalize_audit_source,
)
from .dimensional_aliases import build_axis_key, build_member_key
from .period_kind import infer_period_kind, normalize_supplement_period_kind
from .presentation_resolver import (
    AmbiguityError,
    NeedsNlmOrder,
    _local,
    resolve_label_ordinal,
    resolve_label_ordinal_any,
    resolve_via_uni,
)
from .source_account_class import classify_source_account
from .unit_canonicalize import (
    PCT_UNITS,
    UnitNormalizationError,
    canonicalize_unit,
    normalize_pct_value,
)

# ---- Non-GAAP RATIO routing (per docs/sec-financials-v2-schema.md §4.1) ----

RATIO_UNI_ACCOUNTS = {
    "gross_margin_pct",
    "operating_margin_pct",
    "net_margin_pct",
    "ebitda_margin_pct",
    "adjusted_ebitda_margin_pct",
    "effective_tax_rate",
}

_EPS_UNI_ACCOUNTS = {"eps_basic", "eps_diluted"}


def route_statement_nongaap(array_name: str, uni_account: str, raw_unit: str) -> str:
    """Decide statement for a Non-GAAP row (income_statement vs RATIO).

    Allowlist + unit-guard safety net per §20.2.
    """
    if array_name == "balance_sheet":
        return "BS"
    if array_name == "cash_flow_statement":
        return "CF"
    if array_name != "income_statement":
        raise ValueError(f"Unknown non-GAAP array: {array_name!r}")
    if uni_account in RATIO_UNI_ACCOUNTS:
        return "RATIO"
    if uni_account.endswith("_ratio") or uni_account.endswith("_rate"):
        return "RATIO"
    if raw_unit in PCT_UNITS and (uni_account.endswith("_pct") or "margin" in uni_account):
        return "RATIO"
    return "IS"


# ---- Period end map ----------------------------------------------------------

_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def build_period_end_map(metadata: dict) -> dict[str, str]:
    """Build period -> period_end (ISO date) map from GAAP metadata.filings.

    Tolerant of two shapes:
      - metadata["filings"]  (parse-10QK-gaap top-level)
      - metadata["metadata"]["filings"]  (if wrapped)
    Adds synthetic FYxxxx entry whose period_end := Q4_FYxxxx.period_end when
    only Q4 entry is present (10-K filing is Q4 entry).
    """
    filings = metadata.get("filings") or metadata.get("metadata", {}).get("filings", {})
    pe: dict[str, str] = {}
    for period, info in filings.items():
        if not isinstance(info, dict):
            continue
        end = info.get("period_end")
        if end and _ISO_DATE_RE.match(end):
            pe[period] = end
    # Synthesize FYxxxx from Q4_FYxxxx
    for q4 in [k for k in pe if k.startswith("Q4_FY")]:
        fy = q4.replace("Q4_", "")
        pe.setdefault(fy, pe[q4])
    return pe


def is_iso_date(s: str | None) -> bool:
    return bool(s) and bool(_ISO_DATE_RE.match(s))


# ---- Output dataclasses -----------------------------------------------------


@dataclass
class FactRow:
    cell_id: str
    ticker: str
    period: str
    period_end: str
    period_kind: str
    statement: str
    version: str
    uni_account: str
    source_account: str
    xbrl_tag: str | None
    value: float
    weight: int
    unit: str
    status: str
    ordinal: int | None
    long_tail_metadata: dict | None
    provenance: dict
    # PDF-faithful display metadata (Task 8 / spec G4 prep). Resolved by
    # attach_display_metadata() AFTER the per-source adapt functions run.
    #   display_label    — PDF line label (null → frontend falls back to source_account)
    #   display_eligible — False for a synthetic SUM-of-multiple-PDF-lines core:
    #                       it builds NO Statement-view row (its component
    #                       long-tail rows are the PDF lines). NOT a DB column —
    #                       stripped before upsert (see row_to_dict).
    display_label: str | None = None
    display_eligible: bool = True


@dataclass
class DimensionalRow:
    cell_id: str
    ticker: str
    period: str
    period_end: str
    period_kind: str
    axis: str
    axis_qname: str | None
    axis_key: str
    member: str
    member_qname: str | None
    member_key: str
    source_account: str
    source_account_qname: str | None
    source_doc: str | None
    uni_account: str
    value: float
    unit: str
    decimals: int | None
    other_dimensions: list[dict] | None
    provenance: dict


@dataclass
class EdgeRow:
    edge_id: str
    ticker: str
    period: str
    edge_type: str
    role_uri: str
    parent_qname: str | None
    child_qname: str
    weight: int | None
    ordinal: float | None
    preferred_label: str | None


@dataclass
class CompanyRow:
    ticker: str
    company_name: str
    exchange: str
    cik: str
    currency: str
    fiscal_year_end_month: int
    filings: dict
    sign_flip_concepts: list[str]


@dataclass
class NormalizedBatch:
    ticker: str
    company: CompanyRow | None = None
    facts: list[FactRow] = field(default_factory=list)
    dimensional: list[DimensionalRow] = field(default_factory=list)
    edges: list[EdgeRow] = field(default_factory=list)
    rejected: list[dict] = field(default_factory=list)
    dedupe_stats: dict = field(default_factory=dict)
    value_conflicts: list[dict] = field(default_factory=list)


# ---- Adapter functions ------------------------------------------------------


def adapt_company(metadata: dict, sign_flip_concepts: list[str] | None = None) -> CompanyRow:
    return CompanyRow(
        ticker=metadata["ticker"].upper(),
        company_name=metadata.get("company") or metadata["ticker"],
        exchange=metadata.get("exchange") or "NASDAQ",
        cik=str(metadata.get("cik") or "").lstrip("0").zfill(10) if metadata.get("cik") else "",
        currency=metadata.get("currency") or "USD",
        fiscal_year_end_month=int(metadata.get("fiscal_year_end_month") or 12),
        filings=metadata.get("filings") or {},
        sign_flip_concepts=sign_flip_concepts or [],
    )


def _carry_audit_metadata_to_provenance(row: dict, provenance: dict[str, Any]) -> None:
    """Copy v4 audit metadata channels from a parse-skill row into the
    FactRow.provenance dict that downstream (derive-base / upsert / API)
    reads.

    Schema v4 §7.1 canonical contract:
      - `audit_source` → normalized via legacy enum map; **only written if
        the value is in MANUAL_AUDIT_SOURCES** (allowlist-guarded, P3-F1
        fix). Non-audit strings like `AGENT_CLASSIFIED` / `NotebookLM_PDF_read`
        never leak into `provenance.audit_source`.
      - `audit_source_raw` → preserves the row's original audit_source value
        ONLY when the canonical value is in the audit allowlist (forensic).
      - audit_note / audited_at / audited_by / audit_evidence carried as-is,
        BUT only if a valid `audit_source` was also written (P3-F2 fix:
        orphan audit metadata raises ValueError → row goes to rejected list).
      - classification_source / classification_note / classified_at /
        long_tail_metadata carried (independent channel).
      - **Legacy promotion** (P3-F1): if row has `audit_source="AGENT_CLASSIFIED"`
        and no `classification_source`, promote it to classification channel.
      - preservation_event keys carried (downstream may need to inspect)

    Raises:
        ValueError: row carries audit metadata fields (audit_note / audited_at /
            audited_by / audit_evidence) but the `audit_source` is invalid /
            absent / not a promotable classification — half-set audit
            metadata can't be silently accepted (P3-F2).
    """
    raw_audit_source = row.get("audit_source")
    raw_audit_source_raw = row.get("audit_source_raw")
    # Canonical normalization
    canonical = normalize_audit_source(raw_audit_source or raw_audit_source_raw)
    # P3-F1: allowlist-guard audit channel writes. Only canonical values in
    # MANUAL_AUDIT_SOURCES get written to provenance.audit_source.
    audit_channel_written = False
    if is_manual_audit_source(canonical):
        provenance["audit_source"] = canonical
        provenance["audit_source_raw"] = (
            raw_audit_source_raw if raw_audit_source_raw is not None
            else raw_audit_source
        )
        audit_channel_written = True

    audit_detail_keys = ("audit_note", "audited_at", "audited_by", "audit_evidence")
    has_audit_detail = any(row.get(k) is not None for k in audit_detail_keys)
    is_promotable_classification = (
        raw_audit_source in MANUAL_CLASSIFICATION_SOURCES
        or raw_audit_source_raw in MANUAL_CLASSIFICATION_SOURCES
    )
    audit_source_present = (raw_audit_source is not None
                            or raw_audit_source_raw is not None)

    # P3-F2a: invalid audit_source enum fail-closed REGARDLESS of audit_detail.
    # If row has any audit_source value at all, it must be in MANUAL_AUDIT_SOURCES
    # or be a promotable classification enum. Unknown / malformed strings reject.
    if (audit_source_present and not audit_channel_written
            and not is_promotable_classification):
        raise ValueError(
            f"invalid audit_source: {raw_audit_source!r} (raw={raw_audit_source_raw!r}) "
            f"is not in MANUAL_AUDIT_SOURCES allowlist nor a promotable "
            f"classification enum. Schema §3.1 is strict allowlist."
        )

    # P3-F2 (original): orphan audit metadata without any audit_source at all.
    # E.g. audit_note set but no audit_source field → malformed.
    if has_audit_detail and not audit_channel_written and not is_promotable_classification:
        raise ValueError(
            f"orphan audit metadata: audit_note/audited_at/audited_by/audit_evidence "
            f"present but audit_source={raw_audit_source!r} (raw={raw_audit_source_raw!r}) "
            f"is not in MANUAL_AUDIT_SOURCES allowlist. "
            f"Either supply a valid audit_source enum or remove the detail fields."
        )

    # P3-F2b: classification row carrying audit-channel detail fields is a
    # channel violation. audit_note is audit provenance, not classification
    # reasoning — for the latter, source side should write `classification_note`.
    if is_promotable_classification and has_audit_detail:
        offending = [k for k in audit_detail_keys if row.get(k) is not None]
        raise ValueError(
            f"channel violation: row with classification source "
            f"({raw_audit_source or raw_audit_source_raw!r}) carries audit-channel "
            f"fields {offending}. Use `classification_note` instead, or supply "
            f"a valid manual audit_source enum."
        )

    # Carry audit detail keys verbatim — only when audit_channel_written
    # (P3-F2: don't ship orphan note/evidence without a valid source).
    if audit_channel_written:
        for key in audit_detail_keys:
            v = row.get(key)
            if v is not None:
                provenance[key] = v
    # Classification channel — P3-F3: strict allowlist on classification_source.
    raw_cls_source = row.get("classification_source")
    if raw_cls_source is not None and not is_manual_classification_source(raw_cls_source):
        raise ValueError(
            f"invalid classification_source: {raw_cls_source!r} is not in "
            f"MANUAL_CLASSIFICATION_SOURCES allowlist. Schema §3.2."
        )
    # Carry classification fields
    for key in CLASSIFICATION_KEYS:
        v = row.get(key)
        if v is not None:
            provenance[key] = v
    # P3-F1: legacy promotion — pre-v4 parsers wrote AGENT_CLASSIFIED into
    # audit_source field. Promote to classification_source if no canonical
    # classification_source set. Do NOT write into audit_source/raw (that
    # would re-pollute the v4 contract).
    if not provenance.get("classification_source"):
        for legacy_field in (raw_audit_source, raw_audit_source_raw):
            if legacy_field in MANUAL_CLASSIFICATION_SOURCES:
                provenance["classification_source"] = legacy_field
                break

    # P3-F3 classification orphan: classification_note / classified_at without
    # classification_source is malformed. (long_tail_metadata can stand alone
    # for backward compat with legacy long-tail rows.)
    cls_detail_keys = ("classification_note", "classified_at")
    has_cls_detail = any(row.get(k) is not None for k in cls_detail_keys)
    if has_cls_detail and not provenance.get("classification_source"):
        raise ValueError(
            f"orphan classification metadata: classification_note/classified_at "
            f"present but no valid classification_source. Schema §3.2."
        )

    # Preservation event channel — P3-F3: strict allowlist on preservation_event.
    raw_event = row.get("preservation_event")
    if raw_event is not None and raw_event not in PRESERVATION_EVENTS:
        raise ValueError(
            f"invalid preservation_event: {raw_event!r} is not in "
            f"PRESERVATION_EVENTS allowlist. Schema §3.3."
        )
    for key in PRESERVATION_EVENT_KEYS:
        v = row.get(key)
        if v is not None:
            provenance[key] = v


def adapt_gaap_facts(gaap_json: dict, pe_map: dict[str, str]) -> tuple[list[FactRow], list[dict]]:
    """parse-10QK-gaap facts -> FactRow list."""
    ticker = gaap_json["metadata"]["ticker"].upper()
    accession = {p: info.get("accession_number") for p, info in (gaap_json["metadata"].get("filings") or {}).items()}
    form = {p: info.get("form") for p, info in (gaap_json["metadata"].get("filings") or {}).items()}

    rows: list[FactRow] = []
    rejected: list[dict] = []
    for idx, f in enumerate(gaap_json["facts"]):
        try:
            row = _adapt_one_gaap_fact(ticker, f, pe_map, accession, form)
            rows.append(row)
        except (UnitNormalizationError, ValueError, KeyError) as e:
            rejected.append({
                "source": "gaap_facts",
                "idx": idx,
                "row": f,
                "reason": str(e),
            })
    return rows, rejected


def _adapt_one_gaap_fact(
    ticker: str, f: dict, pe_map: dict[str, str], accession: dict, form: dict
) -> FactRow:
    period = f["period"]
    statement = f["statement"]
    raw_unit = f["unit"]
    uni_account = f["uni_account"]
    source_account = f.get("source_account") or ""
    weight = int(f.get("weight") or 1)

    # period_end
    pe = f.get("period_end")
    if not pe or not pe.strip():
        pe = pe_map.get(period)
    if not pe or not is_iso_date(pe):
        raise ValueError(f"missing/invalid period_end for period={period}")

    # period_kind
    period_kind = infer_period_kind(statement, period)

    # unit
    canon_unit, scale = canonicalize_unit(
        raw_unit,
        decimals=f.get("decimals"),
        eps_context=(uni_account in _EPS_UNI_ACCOUNTS),
    )
    value = float(f["value"]) * scale
    if canon_unit == "Pure":
        value = normalize_pct_value(value, canon_unit)

    # GAAP: source_account IS the XBRL tag (per §18.3.1)
    # Exception: synthesized rows where source_account is None or contains
    # 'SUM(' / 'None' marker -> xbrl_tag is null
    xbrl_tag: str | None
    if not source_account or source_account in ("None",) or source_account.startswith("SUM("):
        xbrl_tag = None
    else:
        xbrl_tag = source_account

    provenance: dict[str, Any] = {
        "source_filing": form.get(period),
        "accession_number": accession.get(period),
    }
    # Phase 3.1: audit metadata v4 — read raw row, dual-write canonical +
    # raw, carry full v4 channel set (audit / classification / preservation
    # event). Reading downstream MUST use `provenance.audit_source` for
    # canonical decisions; `audit_source_raw` is forensic only.
    _carry_audit_metadata_to_provenance(f, provenance)

    cid = _id.facts_cell_id(
        ticker=ticker,
        period=period,
        period_kind=period_kind,
        version="GAAP",
        statement=statement,
        uni_account=uni_account,
        source_account=source_account or "",
        xbrl_tag=xbrl_tag,
    )

    return FactRow(
        cell_id=cid,
        ticker=ticker,
        period=period,
        period_end=pe,
        period_kind=period_kind,
        statement=statement,
        version="GAAP",
        uni_account=uni_account,
        source_account=source_account or "",
        xbrl_tag=xbrl_tag,
        value=value,
        weight=weight,
        unit=canon_unit,
        status="SOURCE_OF_TRUTH",
        ordinal=f.get("ordinal"),
        long_tail_metadata=f.get("long_tail_metadata"),
        provenance=provenance,
    )


# ---- Task 8: PDF-faithful display metadata resolution -----------------------
#
# After the per-source adapt functions build the FactRow list, this layer
# resolves a `display_label` + `ordinal` + `provenance` ordinal lineage per
# DISPLAY-ELIGIBLE fact (spec §13-§16, G2/G3/G4/G6/G7). Parse skills stay
# untouched — all resolution lives here at the upsert boundary.
#
# Routing (spec G6, classifier order null → synthetic → preserved_pdf_label →
# tag_like):
#   tag_like / preserved_pdf_label → resolve_label_ordinal(local, ...)
#     (for preserved_pdf_label the source_account IS the PDF text → fall back to
#      it as the display_label when the resolver yields no label)
#   synthetic / null              → resolve_via_uni(uni_account, ...)
#   on NeedsNlmOrder / AmbiguityError → look up the cell's ordinal in the
#     AUDITED NLM artifact (keyed by cell_id); set ordinal + ordinal_source="nlm"
#     when present, else leave ordinal=None (next task's coverage gate catches it).
#
# Display-ineligibility (spec G7): a synthetic source_account that SUMS MULTIPLE
# PDF lines (SUM(D&A components), SUM(S&M+G&A)) is display_eligible=False → it
# builds NO statement row (its component long-tail rows are the PDF lines). The
# core SUM stays in storage for EBITDA/analytics; it just never becomes a
# Statement-view prototype, and a derived single-quarter cell must not pull it
# back via shared uni_account.


def _local_name(source_account: str) -> str:
    """Bare local name from a tag-like source_account (strip any prefix:)."""
    return source_account.rsplit(":", 1)[-1]


def _set_xbrl_ordinal_provenance(
    row: "FactRow", ordinal, network_role: str | None
) -> None:
    """Stamp ordinal + XBRL-sourced ordinal provenance on a FactRow.

    XBRL ordinals carry source_doc/period = the fact's own filing (the network
    role is the deterministic prototype), per spec §14.
    """
    row.ordinal = ordinal
    row.provenance["ordinal_source"] = "xbrl"
    row.provenance["ordinal_source_doc"] = row.provenance.get("source_filing")
    row.provenance["ordinal_source_period"] = row.period
    row.provenance["ordinal_match_method"] = "xbrl_presentation"
    if network_role is not None:
        row.provenance["ordinal_source_network"] = network_role


def _try_audited_nlm_ordinal(row: "FactRow", audited_for_stmt: dict | None) -> None:
    """Fall back to the AUDITED NLM ordering artifact for this statement.

    `audited_for_stmt` shape (built by the upsert script from
    nlm_statement_order.read_audited_order + artifact metadata):
        {
          "cell_id_to_ordinal": {cell_id: ordinal, ...},   # audited only
          "source_doc": str, "period": str, "artifact_hash": str,
        }
    If the row's cell_id has an audited ordinal → set ordinal +
    ordinal_source="nlm" provenance. Else leave ordinal=None (coverage gate next
    task). NEVER feeds a pending_audit artifact (the reader already gated that).
    """
    if not audited_for_stmt:
        return
    mapping = audited_for_stmt.get("cell_id_to_ordinal") or {}
    ordinal = mapping.get(row.cell_id)
    if ordinal is None:
        return
    row.ordinal = ordinal
    row.provenance["ordinal_source"] = "nlm"
    row.provenance["ordinal_source_doc"] = audited_for_stmt.get("source_doc")
    row.provenance["ordinal_source_period"] = audited_for_stmt.get("period")
    row.provenance["ordinal_match_method"] = "nlm_audited_order"
    if audited_for_stmt.get("artifact_hash") is not None:
        row.provenance["ordinal_artifact_hash"] = audited_for_stmt["artifact_hash"]


def attach_display_metadata(
    facts: list["FactRow"],
    *,
    statement: str,
    edges: list[dict],
    labels: dict,
    network_role: str | None,
    accepted_concepts: set | None = None,
    audited_orders: dict | None = None,
) -> None:
    """Resolve display_label + ordinal + provenance for one statement's facts.

    Mutates each FactRow in place. Call once per statement (IS/BS/CF) with that
    statement's selected presentation network role, its edges_pre, and labels.json.
    Facts whose `.statement` != `statement` are skipped (caller groups by
    statement, but the guard keeps this safe if mixed).

    `accepted_concepts` = the UNION of bare concept local names across ALL face
    networks matching `statement` (presentation_resolver.accepted_face_concepts).
    Used for the narrow note-level exclusion below.

    `audited_orders` maps statement → audited-order dict (see
    _try_audited_nlm_ordinal). Used as the fallback when the XBRL resolver can't
    resolve an ordinal (NeedsNlmOrder / AmbiguityError) or the network is absent.

    Resolution (spec G2/G3/G6/G7 + T14 Issue2):
      - classify source_account → 4 classes.
      - synthetic SUM-of-multiple-PDF-lines → display_eligible=False, no row (G7).
      - tag_like / preserved_pdf_label → resolve_label_ordinal_any across ALL
        matching face networks (10-K full ∪ 10-Q condensed). preserved_pdf_label
        falls back to source_account as the display_label.
      - synthetic (non-multi) / null → resolve_via_uni(uni_account, ...).
      - NeedsNlmOrder / AmbiguityError → audited NLM ordinal (else ordinal=None).
      - NARROW note-level exclusion (T14 Issue2): a STILL-unresolved `tag_like`
        GAAP fact whose concept is NOT in the (non-empty) accepted face set is a
        note-level sub-component → display_eligible=False with a durable
        provenance reason. NEVER applied to preserved_pdf_label / null /
        synthetic, nor when there is no face network (accepted empty) — those
        keep failing the coverage gate (fail-loud; need NLM / manual).
    """
    audited_for_stmt = (audited_orders or {}).get(statement)

    for row in facts:
        if row.statement != statement:
            continue

        cls = classify_source_account(row.source_account or None)

        # --- Display-ineligibility: synthetic SUM of multiple PDF lines ----- #
        # These never build a Statement-view row (G7); component long-tail rows
        # are the PDF lines. Keep in storage for EBITDA/analytics; no label/ordinal.
        if cls == "synthetic" and _is_sum_of_multiple(row.source_account):
            row.display_eligible = False
            row.display_label = None
            row.ordinal = None
            continue

        if cls in ("tag_like", "preserved_pdf_label"):
            # Resolve across ALL matching face networks (full ∪ condensed), not a
            # single selected one (T14 Issue2). resolve_label_ordinal_any already
            # skips AmbiguityError networks internally.
            label, ordinal = resolve_label_ordinal_any(
                _local_name(row.source_account), edges, labels, statement
            )

            if cls == "preserved_pdf_label":
                # source_account IS the PDF text → use it as the display label
                # when the resolver produced none.
                row.display_label = label or row.source_account
            else:
                row.display_label = label

            if ordinal is not None and network_role is not None:
                _set_xbrl_ordinal_provenance(row, ordinal, network_role)
            else:
                _try_audited_nlm_ordinal(row, audited_for_stmt)
                # NARROW note-level exclusion (T14 Issue2): only tag_like, only
                # when a face network exists and this concrete concept is NOT on
                # it. preserved_pdf_label is excluded by the cls guard below.
                _maybe_exclude_note_level(row, cls, accepted_concepts)
            continue

        # cls in ("synthetic" (single-line), "null") → resolve via uni→canonical
        try:
            label, ordinal = resolve_via_uni(
                row.uni_account, statement, network_role, edges, labels
            )
            row.display_label = label
            if ordinal is not None and network_role is not None:
                _set_xbrl_ordinal_provenance(row, ordinal, network_role)
            else:
                _try_audited_nlm_ordinal(row, audited_for_stmt)
        except (NeedsNlmOrder, AmbiguityError):
            # Canonical concept absent from this filing's network/labels → fall
            # to the audited NLM order. Never render SUM(...) / invent a label.
            _try_audited_nlm_ordinal(row, audited_for_stmt)


def _maybe_exclude_note_level(
    row: "FactRow", cls: str, accepted_concepts: set | None
) -> None:
    """Narrow note-level auto-exclusion (T14 Issue2, Codex-mandated).

    Applies ONLY when ALL of:
      - the fact is still unresolved (``row.ordinal is None``),
      - its class is ``tag_like`` (a concrete XBRL concept — NEVER
        preserved_pdf_label / null / synthetic, which legitimately need
        NLM/manual and must keep failing the coverage gate, fail-loud),
      - a face network IS present for this statement
        (``accepted_concepts`` non-empty), AND
      - the concept (``_local(source_account)``) is NOT in ``accepted_concepts``
        (the UNION of ALL matching face networks — 10-K full ∪ 10-Q condensed).

    Then the fact is a note-level sub-component that rolls up into a face
    aggregate: mark it display-INELIGIBLE (no face row, dropped from coverage)
    and write a durable provenance reason so a human can audit the call. Existing
    provenance keys are preserved.
    """
    if row.ordinal is not None:
        return
    if cls != "tag_like":
        return
    if not accepted_concepts:  # None or empty → no face network → fail-loud
        return
    if _local(row.source_account or "") in accepted_concepts:
        return
    row.display_eligible = False
    row.display_label = None
    row.ordinal = None
    if row.provenance is None:
        row.provenance = {}
    row.provenance["display_exclusion_reason"] = "note_level_not_in_face_network"


def _is_sum_of_multiple(source_account: str | None) -> bool:
    """True for a synthetic SUM that aggregates MULTIPLE PDF lines.

    These are the display-ineligible cores per spec G7: SUM(D&A components),
    SUM(S&M+G&A). Detection mirrors the synthetic markers in
    source_account_class.classify_source_account — any synthetic SUM(...) /
    components) / +G&A) marker means multiple components were summed.
    """
    if not source_account:
        return False
    return (
        source_account.startswith("SUM(")
        or "components)" in source_account
        or "+G&A)" in source_account
    )


# ---- Metric-only rows (sec_financial_metrics) — no statement ordinal --------
#
# Derived single-quarter cells (derived_q2 / derived_q3 / derived_q4) and
# absolute-value metrics (ebitda, free_cash_flow) live in sec_financial_metrics,
# NOT in sec_financial_facts. They attach to fact-prototype rows on the FRONTEND
# by uni_account; the adapter MUST NOT assign them a Statement-view display
# ordinal (spec §16). All three derived quarters behave identically.

_DERIVED_SINGLE_QUARTER_PKINDS = frozenset({"derived_q2", "derived_q3", "derived_q4"})


def metric_row_carries_statement_ordinal(metric_row: dict) -> bool:
    """Whether a sec_financial_metrics row should carry a Statement display ordinal.

    Always False: metric rows (derived_q2/q3/q4 single-quarter values, ebitda,
    free_cash_flow) are not facts. They attach by uni_account on the frontend, so
    the adapter never assigns them a statement display ordinal (spec §16). Kept as
    an explicit predicate so the contract is testable and the derived_q2/q3/q4
    set is provably handled identically.
    """
    return False


_NONGAAP_ARRAY_TO_STMT = {
    "income_statement": "IS",
    "balance_sheet": "BS",
    "cash_flow_statement": "CF",
}


def adapt_nongaap_facts(
    nongaap_json: dict, pe_map: dict[str, str], accession_8k: dict | None = None
) -> tuple[list[FactRow], list[dict]]:
    """parse-8k-nongaap rows -> FactRow list (version=NON_GAAP)."""
    ticker = nongaap_json["metadata"]["ticker"].upper()
    accession_8k = accession_8k or {}

    rows: list[FactRow] = []
    rejected: list[dict] = []
    for array_name in ("income_statement", "balance_sheet", "cash_flow_statement"):
        for idx, r in enumerate(nongaap_json.get(array_name, [])):
            try:
                row = _adapt_one_nongaap_fact(ticker, array_name, r, pe_map, accession_8k)
                rows.append(row)
            except (UnitNormalizationError, ValueError, KeyError) as e:
                rejected.append({
                    "source": f"nongaap.{array_name}",
                    "idx": idx,
                    "row": r,
                    "reason": str(e),
                })
    return rows, rejected


def _adapt_one_nongaap_fact(
    ticker: str, array_name: str, r: dict, pe_map: dict[str, str], accession_8k: dict
) -> FactRow:
    period = r["period"]
    uni_account = r["uni_account"]
    raw_unit = r["unit"]

    # Statement routing (RATIO allowlist + safety net)
    statement = route_statement_nongaap(array_name, uni_account, raw_unit)

    # period_end (Non-GAAP JSON usually lacks it)
    pe = r.get("period_end")
    if not pe or not pe.strip():
        pe = pe_map.get(period)
    if not pe or not is_iso_date(pe):
        raise ValueError(f"missing/invalid period_end for period={period}")

    # period_kind
    period_kind = infer_period_kind(statement, period)

    # unit (Non-GAAP EPS uses bare "USD" -> per_share via eps_context)
    canon_unit, scale = canonicalize_unit(
        raw_unit,
        decimals=r.get("decimals"),
        eps_context=(uni_account in _EPS_UNI_ACCOUNTS),
    )
    value = float(r["value"]) * scale
    if canon_unit == "Pure":
        value = normalize_pct_value(value, canon_unit)

    source_account = r.get("source_account") or ""

    provenance: dict[str, Any] = {
        "source_filing": "8-K",
        "accession_number": accession_8k.get(period),
        # Phase 3.2: provenance.data_source replaces legacy
        # `audit_source: "NotebookLM_PDF_read"`. That string was NEVER a v4
        # manual audit source (not in MANUAL_AUDIT_SOURCES) — using
        # `audit_source` for it would let `is_manual_audit_source` return
        # False but still pollute the field semantics. Move to its own
        # parser-extraction lineage field.
        "data_source": "NotebookLM_PDF_read",
    }
    # Phase 3.2: carry v4 audit metadata (canonical + raw) from row if present.
    # Manual audits written by parse-8k-nongaap.apply_audit will populate
    # these via stamp_audit_provenance; plain extracted rows have nothing.
    _carry_audit_metadata_to_provenance(r, provenance)

    cid = _id.facts_cell_id(
        ticker=ticker,
        period=period,
        period_kind=period_kind,
        version="NON_GAAP",
        statement=statement,
        uni_account=uni_account,
        source_account=source_account,
        xbrl_tag=None,
    )

    return FactRow(
        cell_id=cid,
        ticker=ticker,
        period=period,
        period_end=pe,
        period_kind=period_kind,
        statement=statement,
        version="NON_GAAP",
        uni_account=uni_account,
        source_account=source_account,
        xbrl_tag=None,
        value=value,
        weight=int(r.get("weight") or 1),
        unit=canon_unit,
        status="SOURCE_OF_TRUTH",
        ordinal=None,
        long_tail_metadata=None,
        provenance=provenance,
    )


def adapt_supplement_facts(
    supplement_json: dict, accession_map: dict[str, str] | None = None
) -> tuple[list[DimensionalRow], list[dict], dict, list[dict]]:
    """parse-SEC-supplement facts -> DimensionalRow list + dedupe report.

    Returns (rows, rejected, dedupe_stats, value_conflicts).

    Multi-source dedupe (§20.4):
      - same (ticker, period, period_kind, axis_key, member_key, uni_account,
        canonical_json(other_dimensions)) with same value -> one row,
        provenance.sources[] preserves raw labels.
      - same key, different value -> entire batch fails (caller should write
        validation_conflicts.md and abort upsert).
    """
    ticker = supplement_json["metadata"]["ticker"].upper()
    accession_map = accession_map or {}

    # Pass 1: normalize all rows
    normalized: list[tuple[DimensionalRow, dict, str]] = []  # (row, raw, dedupe_key)
    rejected: list[dict] = []
    for idx, f in enumerate(supplement_json["facts"]):
        try:
            row, raw_meta, dk = _adapt_one_supplement_fact(ticker, f, accession_map)
            normalized.append((row, raw_meta, dk))
        except (UnitNormalizationError, ValueError, KeyError) as e:
            rejected.append({
                "source": "supplement",
                "idx": idx,
                "row": f,
                "reason": str(e),
            })

    # Pass 2: dedupe by key.
    # Same key with same value -> collapse, preserve multi-source provenance.
    # Same key, different value but different precision (decimals) -> prefer
    # most-precise row (most negative decimals attribute), drop redundant
    # rounded duplicates silently with stats accounting.
    # Same key, different value, same precision -> real conflict (fail batch).
    groups: dict[str, list[tuple[DimensionalRow, dict]]] = defaultdict(list)
    for row, raw_meta, dk in normalized:
        groups[dk].append((row, raw_meta))

    final_rows: list[DimensionalRow] = []
    value_conflicts: list[dict] = []
    dedupe_count = 0
    precision_dedupe_count = 0

    def _v4_metadata_present(row: DimensionalRow) -> bool:
        """True if row's provenance carries any v4 audit/classification/
        preservation channel (independent of `sources[]`/`source_filing`/etc.)."""
        p = row.provenance
        return (
            p.get("audit_source") is not None
            or p.get("audit_source_raw") is not None
            or p.get("classification_source") is not None
            or p.get("preservation_event") is not None
        )

    def _merge_v4_channels(chosen_row: DimensionalRow,
                            other_rows: list[DimensionalRow],
                            dk: str) -> None:
        """P5-F8: ensure any v4 audit/classification/preservation metadata on
        non-chosen duplicates survives dedupe. If chosen already has v4 data,
        any other member with conflicting v4 data fails the batch (we won't
        silently pick one)."""
        chosen_prov = chosen_row.provenance
        for other in other_rows:
            for key in (
                "audit_source", "audit_source_raw", "audit_note",
                "audited_at", "audited_by", "audit_evidence",
                "classification_source", "classification_note",
                "classified_at", "long_tail_metadata",
                "preservation_event", "preserved_from_audit", "preserved_at",
            ):
                v = other.provenance.get(key)
                if v is None:
                    continue
                existing = chosen_prov.get(key)
                if existing is None:
                    chosen_prov[key] = v
                elif existing != v:
                    raise ValueError(
                        f"supplement dedupe: conflicting v4 metadata for "
                        f"key={dk!r}, field={key!r}: chosen={existing!r} "
                        f"vs other={v!r}. Resolve manually before re-running."
                    )

    for dk, members in groups.items():
        if len(members) == 1:
            row, raw_meta = members[0]
            row.provenance["sources"] = [_source_entry(raw_meta, accession_map)]
            final_rows.append(row)
            continue

        values = {m[0].value for m in members}
        if len(values) == 1:
            # P5-F8: if multiple members exist and any carries v4 metadata,
            # prefer that one as the chosen row so its provenance is the
            # natural target for merge. Falls back to members[0] otherwise.
            preferred_idx = next(
                (i for i, m in enumerate(members) if _v4_metadata_present(m[0])),
                0,
            )
            chosen_pair = members[preferred_idx]
            chosen = chosen_pair[0]
            other_rows = [m[0] for i, m in enumerate(members) if i != preferred_idx]
            try:
                _merge_v4_channels(chosen, other_rows, dk)
            except ValueError as e:
                rejected.append({
                    "source": "supplement",
                    "row": {"dedupe_key": dk},
                    "reason": str(e),
                })
                continue
            chosen.provenance["sources"] = [
                _source_entry(m[1], accession_map) for m in members
            ]
            final_rows.append(chosen)
            dedupe_count += len(members) - 1
            continue

        # Different values: try precision-based resolution.
        # XBRL decimals semantics: more-negative decimals = COARSER rounding
        # bucket (less precise). e.g. decimals=-3 (precise to $1K) is MORE
        # precise than decimals=-5 (precise to $100K).
        # So we want the HIGHEST decimals (closest to 0 / least negative).
        # decimals=None treated as least precise (sorted last).
        def _prec_key(item):
            d = item[0].decimals
            # Sort: highest decimals first (more precise). None goes to end.
            return (-d if d is not None else 99999)
        sorted_members = sorted(members, key=_prec_key)
        precisions = [m[0].decimals for m in sorted_members]
        if precisions[0] != precisions[-1]:
            # P5-F10: precision-dedupe means values differ (this branch is
            # only reached when len(values) > 1). Audit provenance is value
            # evidence — it CANNOT be merged across different numeric values.
            # Classification could in theory be value-independent, but to
            # keep the channel boundary clean and follow GPT's
            # recommendation #3, we reject any v4 metadata on dropped rows,
            # regardless of what the chosen row carries.
            dropped_with_v4 = [
                m[0] for m in sorted_members[1:] if _v4_metadata_present(m[0])
            ]
            if dropped_with_v4:
                rejected.append({
                    "source": "supplement",
                    "row": {"dedupe_key": dk},
                    "reason": (
                        f"precision dedupe would silently drop v4 metadata "
                        f"(audit/classification/preservation) from a "
                        f"less-precise duplicate with a different numeric "
                        f"value. Cannot merge value-bound provenance across "
                        f"different values. Resolve manually."
                    ),
                })
                continue
            chosen = sorted_members[0][0]
            # No v4 metadata on dropped rows; chosen's own v4 metadata (if
            # any) stays untouched. Nothing to merge.
            chosen.provenance["sources"] = [_source_entry(sorted_members[0][1], accession_map)]
            chosen.provenance["precision_dedupe"] = {
                "kept_decimals": precisions[0],
                "dropped_decimals": precisions[1:],
            }
            final_rows.append(chosen)
            precision_dedupe_count += len(members) - 1
            continue

        # Same precision, different values -> real conflict
        value_conflicts.append({
            "dedupe_key": dk,
            "values": [
                {"value": m[0].value, "decimals": m[0].decimals,
                 "source_doc": m[1].get("source_doc"),
                 "raw_member": m[1].get("source_account")}
                for m in members
            ],
        })

    dedupe_stats = {
        "input_rows": len(normalized),
        "output_rows": len(final_rows),
        "collapsed_same_value": dedupe_count,
        "collapsed_precision_dedupe": precision_dedupe_count,
        "conflict_groups": len(value_conflicts),
    }
    return final_rows, rejected, dedupe_stats, value_conflicts


def _source_entry(raw_meta: dict, accession_map: dict[str, str]) -> dict:
    period = raw_meta.get("period")
    return {
        "source_filing": raw_meta.get("source_filing")
            or _infer_filing_from_doc(raw_meta.get("source_doc")),
        "accession_number": accession_map.get(period),
        "source_doc": raw_meta.get("source_doc"),
        "raw_member_label": raw_meta.get("source_account"),
    }


def _infer_filing_from_doc(source_doc: str | None) -> str | None:
    if not source_doc:
        return None
    if "8k" in source_doc.lower() or "8-k" in source_doc.lower():
        return "8-K"
    if "10q" in source_doc.lower() or "10-q" in source_doc.lower():
        return "10-Q"
    if "10k" in source_doc.lower() or "10-k" in source_doc.lower():
        return "10-K"
    if "instance" in source_doc.lower():
        return "10-K/Q"  # XBRL instance — caller should refine with period
    return None


def _adapt_one_supplement_fact(
    ticker: str, f: dict, accession_map: dict
) -> tuple[DimensionalRow, dict, str]:
    period = f["period"]
    pe = f.get("period_end")
    if not is_iso_date(pe):
        raise ValueError(f"supplement period_end missing/invalid: {pe!r}")

    raw_kind = f.get("period_kind")
    if not raw_kind:
        raise ValueError("supplement row missing period_kind")
    period_kind = normalize_supplement_period_kind(raw_kind)

    axis = f["axis"]
    axis_qname = f.get("axis_qname")
    member = f.get("source_account") or ""
    member_qname = f.get("source_account_qname")
    uni_account = f["uni_account"]
    raw_unit = f["unit"]

    canon_unit, scale = canonicalize_unit(
        raw_unit,
        decimals=int(f["decimals"]) if f.get("decimals") not in (None, "") else None,
    )
    value = float(f["value"]) * scale
    if canon_unit == "Pure":
        value = normalize_pct_value(value, canon_unit)

    axis_key = build_axis_key(axis, axis_qname)
    member_key = build_member_key(member, member_qname)
    other_dims = f.get("other_dimensions") or None

    cid = _id.dimensional_cell_id(
        ticker=ticker,
        period=period,
        period_kind=period_kind,
        axis_key=axis_key,
        member_key=member_key,
        uni_account=uni_account,
        other_dimensions=other_dims,
    )

    # P5-F1: supplement provenance carries v4 audit metadata through the
    # adapter, same as GAAP / Non-GAAP. The downstream dedupe pass later
    # appends `sources[]`; the audit channel writes must happen first so
    # they survive collapse.
    provenance: dict[str, Any] = {}
    _carry_audit_metadata_to_provenance(f, provenance)

    row = DimensionalRow(
        cell_id=cid,
        ticker=ticker,
        period=period,
        period_end=pe,
        period_kind=period_kind,
        axis=axis,
        axis_qname=axis_qname,
        axis_key=axis_key,
        member=member,
        member_qname=member_qname,
        member_key=member_key,
        source_account=member,
        source_account_qname=member_qname,
        source_doc=f.get("source_doc"),
        uni_account=uni_account,
        value=value,
        unit=canon_unit,
        decimals=int(f["decimals"]) if f.get("decimals") not in (None, "") else None,
        other_dimensions=other_dims,
        provenance=provenance,
    )

    dedupe_key = "|".join([
        ticker, period, period_kind, axis_key, member_key, uni_account,
        _id.canonical_json(other_dims),
    ])
    raw_meta = {
        "period": period,
        "source_doc": f.get("source_doc"),
        "source_account": member,
        "source_filing": None,  # _source_entry will infer
    }
    return row, raw_meta, dedupe_key


def adapt_edges(edges_json: dict, ticker: str, edge_type: str) -> list[EdgeRow]:
    """parse-10QK-gaap calc/pre edges OR parse-SEC-supplement def edges -> EdgeRow.

    Silently dedupes by edge_id (parse-SEC-supplement def_linkbase can emit
    identical rows when the same dimensional relationship is declared in
    multiple linkbase files — same parent/child/role/ordinal/label).
    """
    seen_ids: set[str] = set()
    rows: list[EdgeRow] = []
    for e in edges_json.get("edges", []):
        period = e.get("period") or ""
        role_uri = e.get("role_uri") or ""
        parent_qname = e.get("parent_qname") or e.get("parent")
        child_qname = e.get("child_qname") or e.get("child") or ""
        ordinal = float(e["order"]) if "order" in e and e["order"] is not None else None
        preferred_label = e.get("preferred_label")
        cid = _id.edge_id(
            ticker=ticker,
            period=period,
            edge_type=edge_type,
            role_uri=role_uri,
            parent_qname=parent_qname,
            child_qname=child_qname,
            preferred_label=preferred_label,
            ordinal=ordinal,
        )
        if cid in seen_ids:
            continue  # silent dedupe of identical edges
        seen_ids.add(cid)
        rows.append(EdgeRow(
            edge_id=cid,
            ticker=ticker,
            period=period,
            edge_type=edge_type,
            role_uri=role_uri,
            parent_qname=parent_qname,
            child_qname=child_qname,
            weight=int(e["weight"]) if "weight" in e and e["weight"] is not None else None,
            ordinal=ordinal,
            preferred_label=preferred_label,
        ))
    return rows
