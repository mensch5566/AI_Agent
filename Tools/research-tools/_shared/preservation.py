"""Shared preservation matrix helper — schema v4 §5 behavior, identity-fn pluggable.

Used by:
  - parse-10QK-gaap/scripts/xbrl_extract.py
  - parse-8k-nongaap/scripts/extract_8k_nongaap.py
  - parse-SEC-supplement/scripts/extract_supplement_v3.py

Each skill supplies its own `identity_fn` (from `_shared.audit_metadata`,
either `build_preservation_identity` for GAAP/8K or `build_supplement_identity`
for supplement) and a `statement` label. The matrix logic (MATCH /
ADDED_BACK / CONFLICT / ACCEPT_NEW with audit vs classification-only branches,
legacy AGENT_CLASSIFIED canonicalization, duplicate fail-closed) is identical.

Supplement-specific `audit_conflicts_unresolved` fail-closed file is NOT
written here — caller passes `conflicts_for_json` from the return value to
the supplement-specific `write_supplement_conflict_json()` helper.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .audit_metadata import (
    DuplicateIdentityError,
    clear_audit_provenance,
    copy_audit_provenance,
    copy_classification_metadata,
    is_manual_audit_source,
    is_manual_classification_source,
    set_preservation_event,
)

IdentityFn = Callable[[dict[str, Any]], tuple]


def values_match(a: Any, b: Any, tol: float = 1e-6) -> bool:
    """Schema §5 MATCH: abs(diff) <= tol. P4-F4 fixed `<` → `<=` per spec."""
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    try:
        return abs(float(a) - float(b)) <= tol
    except (TypeError, ValueError):
        return a == b


def row_has_audit(row: dict[str, Any]) -> bool:
    """True if row carries manual audit provenance (canonical or legacy raw)."""
    return (
        is_manual_audit_source(row.get("audit_source"))
        or is_manual_audit_source(row.get("audit_source_raw"))
    )


def row_has_classification(row: dict[str, Any]) -> bool:
    """True if row carries classification metadata.

    Includes legacy detection: pre-v4 apply_audit wrote AGENT_CLASSIFIED into
    the audit_source field. Phase 2 F14 / P3-F1 canonicalize on ADDED_BACK
    so the field eventually disappears from the row.
    """
    if is_manual_classification_source(row.get("classification_source")):
        return True
    return row.get("audit_source") == "AGENT_CLASSIFIED"


@dataclass
class PreservationResult:
    """Return shape for `preserve_audited_rows`."""
    merged_rows:        list[dict[str, Any]]
    preserved_log:      list[dict[str, Any]] = field(default_factory=list)
    conflicts_for_json: list[dict[str, Any]] = field(default_factory=list)
    n_match:            int = 0
    n_added_back:       int = 0
    n_conflict:         int = 0
    n_accept_new:       int = 0


def _canonicalize_added_back_legacy_classification(carried: dict[str, Any]) -> None:
    """Phase 2 F14: ADDED_BACK on a legacy AGENT_CLASSIFIED-in-audit_source row
    canonicalizes to classification_source; preserves the raw value under
    long_tail_metadata.legacy_audit_source_raw so the field eventually
    disappears as rows naturally refresh."""
    if (carried.get("audit_source") == "AGENT_CLASSIFIED"
            and not carried.get("classification_source")):
        carried["classification_source"] = "AGENT_CLASSIFIED"
        ltm = carried.get("long_tail_metadata") or {}
        if isinstance(ltm, dict):
            ltm.setdefault("legacy_audit_source_raw", "AGENT_CLASSIFIED")
            carried["long_tail_metadata"] = ltm
        carried.pop("audit_source", None)


def preserve_audited_rows(
    existing_rows:    list[dict[str, Any]],
    new_rows:         list[dict[str, Any]],
    identity_fn:      IdentityFn,
    *,
    accept_new_values: bool = False,
    statement_label:   str  = "",
) -> PreservationResult:
    """Preserve audit / classification metadata across re-extracts.

    Schema v4 §5 behavior matrix:
      - MATCH       (new found, values equal):       copy provenance + classification, no event
      - ADDED_BACK  (new dropped this row):          carry old, set event
      - CONFLICT    (values differ, no --accept):    restore old_val, copy meta,
                                                     set event, write new_extract_value_rejected.
                                                     If has_audit, also append to
                                                     conflicts_for_json (supplement-only output).
      - ACCEPT_NEW  (values differ + --accept):      clear audit, copy classification,
                                                     write accepted_new_value_replaces_audit
                                                     (audit branch only)

    Identity is provided by `identity_fn(row) -> tuple`. Duplicate identity
    in either existing audit-bearing rows OR new rows raises DuplicateIdentityError.

    Mutates `new_rows` in place (appends ADDED_BACK rows; updates matched rows).
    Returns PreservationResult; `merged_rows` is the same list reference.
    """
    # 1. Track existing audit/classification rows
    tracked: dict[tuple, tuple[dict, bool, bool]] = {}
    tracked_dups: list[tuple] = []
    for r in existing_rows:
        ha = row_has_audit(r)
        hc = row_has_classification(r)
        if not (ha or hc):
            continue
        ident = identity_fn(r)
        if ident in tracked:
            tracked_dups.append(ident)
            continue
        tracked[ident] = (r, ha, hc)
    if tracked_dups:
        label = f" ({statement_label})" if statement_label else ""
        raise DuplicateIdentityError(
            f"existing rows{label} have {len(tracked_dups)} duplicate "
            f"audit/classification identity tuples — cannot safely preserve. "
            f"First: {tracked_dups[0]!r}"
        )
    if not tracked:
        return PreservationResult(merged_rows=new_rows)

    # 2. Index new rows by identity (fail-closed on duplicate)
    new_index: dict[tuple, tuple[int, dict]] = {}
    new_dups: list[tuple] = []
    for i, r in enumerate(new_rows):
        ident = identity_fn(r)
        if ident in new_index:
            new_dups.append(ident)
            continue
        new_index[ident] = (i, r)
    if new_dups:
        label = f" ({statement_label})" if statement_label else ""
        raise DuplicateIdentityError(
            f"new rows{label} have {len(new_dups)} duplicate identity tuples — "
            f"fail-closed (would otherwise mis-attribute audit metadata). "
            f"First: {new_dups[0]!r}"
        )

    # 3. Apply matrix
    result = PreservationResult(merged_rows=new_rows)
    for ident, (old_row, has_audit, has_classification) in tracked.items():
        old_val = old_row.get("value")
        entry = new_index.get(ident)

        if entry is None:
            # ADDED_BACK
            carried = {**old_row}
            for k in ("preserved_from_audit", "preserved_at", "preservation_event"):
                carried.pop(k, None)
            _canonicalize_added_back_legacy_classification(carried)
            event = (
                "REEXTRACT_PRESERVED_PRIOR_AUDIT" if has_audit
                else "REEXTRACT_PRESERVED_PRIOR_CLASSIFICATION"
            )
            set_preservation_event(carried, event)
            new_rows.append(carried)
            result.n_added_back += 1
            result.preserved_log.append({
                "kind":   "ADDED_BACK",
                "period": old_row.get("period"),
                "uni":    old_row.get("uni_account"),
                "value":  old_val,
            })
            continue

        _, new_row = entry
        new_val = new_row.get("value")

        if values_match(old_val, new_val):
            # MATCH
            if has_audit:
                copy_audit_provenance(new_row, old_row)
            if has_classification:
                copy_classification_metadata(new_row, old_row)
            result.n_match += 1
            result.preserved_log.append({
                "kind":   "MATCH",
                "period": old_row.get("period"),
                "uni":    old_row.get("uni_account"),
                "value":  old_val,
            })
            continue

        # CONFLICT or ACCEPT_NEW
        conflict_entry = {
            "period":              old_row.get("period"),
            "uni_account":         old_row.get("uni_account"),
            "source_account":      old_row.get("source_account"),
            "unit":                old_row.get("unit"),
            "prior_audit_value":   old_val,
            "new_extracted_value": new_val,
            "has_audit":           has_audit,
            "has_classification":  has_classification,
        }
        if accept_new_values:
            # ACCEPT_NEW
            if has_audit:
                clear_audit_provenance(new_row)
            if has_classification:
                copy_classification_metadata(new_row, old_row)
            if has_audit:
                new_row["accepted_new_value_replaces_audit"] = {
                    "prior_audit_value":   old_val,
                    "new_extracted_value": new_val,
                }
            result.n_accept_new += 1
            result.preserved_log.append({**conflict_entry, "kind": "ACCEPT_NEW"})
        else:
            # CONFLICT (keep audit/classification, restore value)
            new_row["value"] = old_val
            if has_audit:
                copy_audit_provenance(new_row, old_row)
            if has_classification:
                copy_classification_metadata(new_row, old_row)
            event = (
                "REEXTRACT_PRESERVED_PRIOR_AUDIT" if has_audit
                else "REEXTRACT_PRESERVED_PRIOR_CLASSIFICATION"
            )
            set_preservation_event(new_row, event)
            new_row["new_extract_value_rejected"] = new_val
            # P4-F1: schema §5 only AUDIT conflicts go to fail-closed JSON
            if has_audit:
                result.conflicts_for_json.append(conflict_entry)
            result.n_conflict += 1
            result.preserved_log.append({**conflict_entry, "kind": "CONFLICT"})

    return result
