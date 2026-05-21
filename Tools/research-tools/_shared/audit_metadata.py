"""Audit metadata schema v4 — shared helpers for parse skills.

Canonical contract: docs/audit-metadata-schema.md

Three semantic channels per row:
  1. Audit provenance — value evidence (manual correction)
  2. Classification — long-tail bucket assignment
  3. Preservation event — what happened during this re-extract

Helpers here are the ONLY way parse / adapter / upsert / derive-base
code should read/write these fields. Do not string-compare audit_source
directly — go through is_manual_audit_source().
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


# ─────────────────────────────────────────────────────────────────────────────
# §3.1 audit_source allowlist + legacy normalization
# ─────────────────────────────────────────────────────────────────────────────

MANUAL_AUDIT_SOURCES = frozenset({
    # Canonical (v4)
    "MANUAL_AUDIT_FROM_OFFICIAL_FILING",
    "MANUAL_RESTATEMENT_FROM_AMENDED_FILING",
    # Legacy (accepted, will normalize to canonical on write)
    "MANUAL_AUDIT_FROM_PDF",
    "MANUAL_AUDIT_FROM_8K_PDF",
})

LEGACY_AUDIT_SOURCE_MAP = {
    "MANUAL_AUDIT_FROM_PDF":    "MANUAL_AUDIT_FROM_OFFICIAL_FILING",
    "MANUAL_AUDIT_FROM_8K_PDF": "MANUAL_AUDIT_FROM_OFFICIAL_FILING",
}


def normalize_audit_source(raw: str | None) -> str | None:
    """Map legacy enum to canonical. Unknown values pass through unchanged."""
    if raw is None:
        return None
    return LEGACY_AUDIT_SOURCE_MAP.get(raw, raw)


def is_manual_audit_source(audit_source: str | None) -> bool:
    """True iff this row's value came from a manual audit source.
    Accepts either raw legacy or canonical normalized value."""
    return audit_source in MANUAL_AUDIT_SOURCES


# ─────────────────────────────────────────────────────────────────────────────
# §3.2 classification_source allowlist
# ─────────────────────────────────────────────────────────────────────────────

MANUAL_CLASSIFICATION_SOURCES = frozenset({
    "AGENT_CLASSIFIED",
    "MANUAL_RECLASSIFIED",
})


def is_manual_classification_source(classification_source: str | None) -> bool:
    return classification_source in MANUAL_CLASSIFICATION_SOURCES


# ─────────────────────────────────────────────────────────────────────────────
# §3.3 preservation_event allowlist
# ─────────────────────────────────────────────────────────────────────────────

PRESERVATION_EVENTS = frozenset({
    "REEXTRACT_PRESERVED_PRIOR_AUDIT",
    "REEXTRACT_PRESERVED_PRIOR_CLASSIFICATION",
})


# ─────────────────────────────────────────────────────────────────────────────
# §4 helper key constants + copy/set helpers
# ─────────────────────────────────────────────────────────────────────────────

AUDIT_PROVENANCE_KEYS = (
    "audit_source",
    "audit_source_raw",
    "audit_note",
    "audited_at",
    "audited_by",
    "audit_evidence",
)

CLASSIFICATION_KEYS = (
    "classification_source",
    "classification_note",
    "classified_at",
    "long_tail_metadata",
)

PRESERVATION_EVENT_KEYS = (
    "preserved_from_audit",
    "preserved_at",
    "preservation_event",
)


def copy_audit_provenance(dst: dict[str, Any], src: dict[str, Any]) -> None:
    """Copy value-source audit metadata from src to dst.
    Does NOT touch preservation event keys — those are re-set per event."""
    for key in AUDIT_PROVENANCE_KEYS:
        if key in src and src[key] is not None:
            dst[key] = src[key]


def copy_classification_metadata(dst: dict[str, Any], src: dict[str, Any]) -> None:
    """Copy classification metadata (long-tail bucket assignment).
    Independent from audit provenance."""
    for key in CLASSIFICATION_KEYS:
        if key in src and src[key] is not None:
            dst[key] = src[key]


def set_preservation_event(
    dst: dict[str, Any],
    event: str,
    *,
    now_iso: str | None = None,
) -> None:
    """Mark this row as preserved during current re-extract.
    Always uses fresh timestamp, not carried-over from old row."""
    if event not in PRESERVATION_EVENTS:
        raise ValueError(f"unknown preservation_event: {event}")
    dst["preserved_from_audit"] = (event == "REEXTRACT_PRESERVED_PRIOR_AUDIT")
    dst["preserved_at"] = now_iso or datetime.now(timezone.utc).isoformat()
    dst["preservation_event"] = event


def clear_audit_provenance(dst: dict[str, Any]) -> None:
    """Remove all audit provenance + preservation event keys.
    Used by --accept-new-values on re-extract CONFLICT."""
    for key in AUDIT_PROVENANCE_KEYS + PRESERVATION_EVENT_KEYS:
        dst.pop(key, None)


# ─────────────────────────────────────────────────────────────────────────────
# Write-time helpers (canonical dual-write: normalized + raw)
# ─────────────────────────────────────────────────────────────────────────────

def stamp_audit_provenance(
    dst: dict[str, Any],
    *,
    audit_source: str,
    audit_note: str | None = None,
    audited_at: str | None = None,
    audited_by: str | None = None,
    audit_evidence: dict[str, Any] | None = None,
) -> None:
    """Write canonical audit provenance to row.

    Dual-writes:
      - audit_source     ← canonical (normalized)
      - audit_source_raw ← caller's raw value (preserved for forensic)

    Raises ValueError if audit_source isn't a recognized enum.
    Raises ValueError if MANUAL_RESTATEMENT but accession_number missing
    in audit_evidence (per §2.2).
    """
    if audit_source not in MANUAL_AUDIT_SOURCES:
        raise ValueError(f"unknown audit_source: {audit_source}")
    canonical = normalize_audit_source(audit_source)
    # Schema §2.2: audit_evidence required for both OFFICIAL_FILING and
    # RESTATEMENT. Must carry at minimum source_doc or page_or_section.
    if canonical in (
        "MANUAL_AUDIT_FROM_OFFICIAL_FILING",
        "MANUAL_RESTATEMENT_FROM_AMENDED_FILING",
    ):
        if not audit_evidence:
            raise ValueError(
                f"{canonical} requires non-empty audit_evidence "
                "(at minimum source_doc or page_or_section)"
            )
        has_locator = bool(
            audit_evidence.get("source_doc")
            or audit_evidence.get("page_or_section")
        )
        if not has_locator:
            raise ValueError(
                f"{canonical} audit_evidence must include source_doc "
                "or page_or_section"
            )
    if canonical == "MANUAL_RESTATEMENT_FROM_AMENDED_FILING":
        if not audit_evidence.get("accession_number"):
            raise ValueError(
                "MANUAL_RESTATEMENT_FROM_AMENDED_FILING requires "
                "audit_evidence.accession_number"
            )
    dst["audit_source"] = canonical
    dst["audit_source_raw"] = audit_source
    if audit_note is not None:
        if len(audit_note) > 500:
            raise ValueError(f"audit_note exceeds 500 chars ({len(audit_note)})")
        dst["audit_note"] = audit_note
    dst["audited_at"] = audited_at or datetime.now(timezone.utc).isoformat()
    if audited_by is not None:
        dst["audited_by"] = audited_by
    if audit_evidence is not None:
        dst["audit_evidence"] = audit_evidence


def stamp_classification(
    dst: dict[str, Any],
    *,
    classification_source: str,
    classification_note: str | None = None,
    classified_at: str | None = None,
    long_tail_metadata: dict[str, Any] | None = None,
) -> None:
    """Write classification metadata to row."""
    if classification_source not in MANUAL_CLASSIFICATION_SOURCES:
        raise ValueError(f"unknown classification_source: {classification_source}")
    dst["classification_source"] = classification_source
    if classification_note is not None:
        dst["classification_note"] = classification_note
    dst["classified_at"] = classified_at or datetime.now(timezone.utc).isoformat()
    if long_tail_metadata is not None:
        dst["long_tail_metadata"] = long_tail_metadata


# ─────────────────────────────────────────────────────────────────────────────
# Read-time predicate (works on both raw row dict and provenance subdict)
# ─────────────────────────────────────────────────────────────────────────────

def row_has_audited_value(row_or_provenance: dict[str, Any] | None) -> bool:
    """Return True if this row's value is backed by manual audit.
    Accepts either a full row dict or a `provenance` subdict.
    Checks both canonical and raw fields (so legacy rows still detected)."""
    if not row_or_provenance:
        return False
    return (
        is_manual_audit_source(row_or_provenance.get("audit_source"))
        or is_manual_audit_source(row_or_provenance.get("audit_source_raw"))
    )


# ─────────────────────────────────────────────────────────────────────────────
# Preservation identity (schema §6) — deterministic key for matching old/new
# rows during re-extract. Long-tail rows share uni_account but differ on
# source_account / unit / type, so single-key match would mis-bucket them.
# ─────────────────────────────────────────────────────────────────────────────

# Fields used to build identity tuple for GAAP / 8K row preservation.
# `statement` is supplied by caller (not on row); rest come from row.
PRESERVATION_IDENTITY_FIELDS = (
    "period",
    "uni_account",
    "source_account",
    "unit",
    "type",
)


def build_preservation_identity(statement: str, row: dict[str, Any]) -> tuple:
    """Build deterministic identity tuple for preservation matching.

    Returns: (statement, period, uni_account, source_account, unit, type)

    Schema §6 specifies a richer tuple including period_kind / xbrl_tag, but
    those aren't independent fields on current GAAP/8K rows (period_kind is
    inferred from period string; xbrl_tag is what source_account stores for
    SEC rows). The fields here are what's actually present and deterministic.

    Callers MUST detect duplicates and fail-closed; legacy rows missing
    `unit` or `type` are tolerated only when they don't collide on identity.
    """
    return (
        statement,
        row.get("period"),
        row.get("uni_account"),
        row.get("source_account"),
        row.get("unit"),
        row.get("type"),
    )


class DuplicateIdentityError(RuntimeError):
    """Raised when two rows resolve to the same preservation identity tuple.
    Means the fallback identity isn't unique — pipeline must add discriminator
    or stop. Never silently overwrite (last-write-wins) on audit-bearing data."""
