"""Tests for _shared/audit_metadata.py — schema v4 contract.

Run: uv run --with pytest python3 -m pytest scripts/tests/test_audit_metadata.py -v
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "Tools" / "research-tools"))

from _shared.audit_metadata import (  # noqa: E402
    AUDIT_PROVENANCE_KEYS,
    CLASSIFICATION_KEYS,
    LEGACY_AUDIT_SOURCE_MAP,
    MANUAL_AUDIT_SOURCES,
    MANUAL_CLASSIFICATION_SOURCES,
    PRESERVATION_EVENT_KEYS,
    PRESERVATION_EVENTS,
    clear_audit_provenance,
    copy_audit_provenance,
    copy_classification_metadata,
    is_manual_audit_source,
    is_manual_classification_source,
    normalize_audit_source,
    row_has_audited_value,
    set_preservation_event,
    stamp_audit_provenance,
    stamp_classification,
)


# ── §3.1 audit_source allowlist ──────────────────────────────────────────────

def test_canonical_audit_sources_in_allowlist():
    assert "MANUAL_AUDIT_FROM_OFFICIAL_FILING" in MANUAL_AUDIT_SOURCES
    assert "MANUAL_RESTATEMENT_FROM_AMENDED_FILING" in MANUAL_AUDIT_SOURCES


def test_legacy_audit_sources_in_allowlist():
    assert "MANUAL_AUDIT_FROM_PDF" in MANUAL_AUDIT_SOURCES
    assert "MANUAL_AUDIT_FROM_8K_PDF" in MANUAL_AUDIT_SOURCES


def test_normalize_legacy_to_canonical():
    assert normalize_audit_source("MANUAL_AUDIT_FROM_PDF") == "MANUAL_AUDIT_FROM_OFFICIAL_FILING"
    assert normalize_audit_source("MANUAL_AUDIT_FROM_8K_PDF") == "MANUAL_AUDIT_FROM_OFFICIAL_FILING"


def test_normalize_canonical_passthrough():
    assert normalize_audit_source("MANUAL_AUDIT_FROM_OFFICIAL_FILING") == "MANUAL_AUDIT_FROM_OFFICIAL_FILING"


def test_normalize_none_returns_none():
    assert normalize_audit_source(None) is None


def test_normalize_unknown_passthrough():
    assert normalize_audit_source("UNKNOWN_VALUE") == "UNKNOWN_VALUE"


def test_is_manual_audit_source_canonical():
    assert is_manual_audit_source("MANUAL_AUDIT_FROM_OFFICIAL_FILING") is True


def test_is_manual_audit_source_legacy():
    assert is_manual_audit_source("MANUAL_AUDIT_FROM_PDF") is True
    assert is_manual_audit_source("MANUAL_AUDIT_FROM_8K_PDF") is True


def test_is_manual_audit_source_negative():
    assert is_manual_audit_source(None) is False
    assert is_manual_audit_source("") is False
    assert is_manual_audit_source("AGENT_CLASSIFIED") is False  # classification not audit


# ── §3.2 classification_source ───────────────────────────────────────────────

def test_is_manual_classification_source():
    assert is_manual_classification_source("AGENT_CLASSIFIED") is True
    assert is_manual_classification_source("MANUAL_RECLASSIFIED") is True
    assert is_manual_classification_source(None) is False
    assert is_manual_classification_source("MANUAL_AUDIT_FROM_OFFICIAL_FILING") is False


# ── §3.3 preservation events ─────────────────────────────────────────────────

def test_preservation_events_allowlist():
    assert "REEXTRACT_PRESERVED_PRIOR_AUDIT" in PRESERVATION_EVENTS
    assert "REEXTRACT_PRESERVED_PRIOR_CLASSIFICATION" in PRESERVATION_EVENTS


# ── §4 copy helpers ──────────────────────────────────────────────────────────

def test_copy_audit_provenance_copies_all_keys():
    src = {
        "audit_source":      "MANUAL_AUDIT_FROM_OFFICIAL_FILING",
        "audit_source_raw":  "MANUAL_AUDIT_FROM_OFFICIAL_FILING",
        "audit_note":        "10-Q Note 15",
        "audited_at":        "2026-05-21T11:00:00Z",
        "audited_by":        "user@example.com",
        "audit_evidence":    {"source_doc": "lite-Q1.htm"},
        "value":             100,
    }
    dst = {"value": 200}
    copy_audit_provenance(dst, src)
    for k in AUDIT_PROVENANCE_KEYS:
        assert dst[k] == src[k]
    assert dst["value"] == 200  # untouched


def test_copy_audit_provenance_skips_none():
    src = {"audit_source": "MANUAL_AUDIT_FROM_PDF", "audit_note": None}
    dst = {}
    copy_audit_provenance(dst, src)
    assert dst["audit_source"] == "MANUAL_AUDIT_FROM_PDF"
    assert "audit_note" not in dst


def test_copy_audit_provenance_does_not_copy_classification():
    src = {
        "audit_source":          "MANUAL_AUDIT_FROM_OFFICIAL_FILING",
        "classification_source": "AGENT_CLASSIFIED",
    }
    dst = {}
    copy_audit_provenance(dst, src)
    assert "classification_source" not in dst


def test_copy_audit_provenance_does_not_copy_preservation_event():
    src = {
        "audit_source":         "MANUAL_AUDIT_FROM_OFFICIAL_FILING",
        "preserved_from_audit": True,
        "preservation_event":   "REEXTRACT_PRESERVED_PRIOR_AUDIT",
    }
    dst = {}
    copy_audit_provenance(dst, src)
    assert "preserved_from_audit" not in dst
    assert "preservation_event" not in dst


def test_copy_classification_metadata():
    src = {
        "classification_source": "AGENT_CLASSIFIED",
        "classification_note":   "long-tail bucket",
        "classified_at":         "2026-05-21T11:00:00Z",
        "long_tail_metadata":    {"rolls_up_to": "operating_expense"},
    }
    dst = {}
    copy_classification_metadata(dst, src)
    for k in CLASSIFICATION_KEYS:
        assert dst[k] == src[k]


def test_copy_classification_does_not_copy_audit():
    src = {
        "audit_source":          "MANUAL_AUDIT_FROM_OFFICIAL_FILING",
        "classification_source": "AGENT_CLASSIFIED",
    }
    dst = {}
    copy_classification_metadata(dst, src)
    assert "audit_source" not in dst
    assert dst["classification_source"] == "AGENT_CLASSIFIED"


# ── §4 set_preservation_event ────────────────────────────────────────────────

def test_set_preservation_event_audit():
    dst = {}
    set_preservation_event(dst, "REEXTRACT_PRESERVED_PRIOR_AUDIT")
    assert dst["preserved_from_audit"] is True
    assert dst["preservation_event"] == "REEXTRACT_PRESERVED_PRIOR_AUDIT"
    assert "preserved_at" in dst
    # validate ISO-like timestamp
    datetime.fromisoformat(dst["preserved_at"].replace("Z", "+00:00"))


def test_set_preservation_event_classification():
    dst = {}
    set_preservation_event(dst, "REEXTRACT_PRESERVED_PRIOR_CLASSIFICATION")
    assert dst["preserved_from_audit"] is False
    assert dst["preservation_event"] == "REEXTRACT_PRESERVED_PRIOR_CLASSIFICATION"


def test_set_preservation_event_rejects_unknown():
    with pytest.raises(ValueError, match="unknown preservation_event"):
        set_preservation_event({}, "BOGUS_EVENT")


def test_set_preservation_event_uses_fresh_timestamp_not_old():
    dst = {"preserved_at": "2020-01-01T00:00:00Z"}
    set_preservation_event(dst, "REEXTRACT_PRESERVED_PRIOR_AUDIT")
    assert dst["preserved_at"] != "2020-01-01T00:00:00Z"


# ── §4 clear_audit_provenance ────────────────────────────────────────────────

def test_clear_audit_provenance_removes_all_audit_and_event_keys():
    dst = {
        "audit_source":         "MANUAL_AUDIT_FROM_OFFICIAL_FILING",
        "audit_source_raw":     "MANUAL_AUDIT_FROM_OFFICIAL_FILING",
        "audit_note":           "x",
        "audited_at":           "2026-05-21T11:00:00Z",
        "audited_by":           "u",
        "audit_evidence":       {},
        "preserved_from_audit": True,
        "preserved_at":         "2026-05-21T11:00:00Z",
        "preservation_event":   "REEXTRACT_PRESERVED_PRIOR_AUDIT",
        "value":                100,  # untouched
    }
    clear_audit_provenance(dst)
    for k in AUDIT_PROVENANCE_KEYS + PRESERVATION_EVENT_KEYS:
        assert k not in dst
    assert dst["value"] == 100


def test_clear_audit_provenance_does_not_remove_classification():
    dst = {
        "audit_source":          "MANUAL_AUDIT_FROM_OFFICIAL_FILING",
        "classification_source": "AGENT_CLASSIFIED",
    }
    clear_audit_provenance(dst)
    assert dst["classification_source"] == "AGENT_CLASSIFIED"


# ── stamp helpers (dual-write canonical + raw) ──────────────────────────────

def test_stamp_audit_provenance_canonical():
    dst = {}
    stamp_audit_provenance(
        dst,
        audit_source="MANUAL_AUDIT_FROM_OFFICIAL_FILING",
        audit_note="10-Q Note 15",
        audit_evidence={"source_doc": "x.htm"},
    )
    assert dst["audit_source"] == "MANUAL_AUDIT_FROM_OFFICIAL_FILING"
    assert dst["audit_source_raw"] == "MANUAL_AUDIT_FROM_OFFICIAL_FILING"
    assert dst["audit_note"] == "10-Q Note 15"
    assert "audited_at" in dst


def test_stamp_audit_provenance_legacy_normalizes_canonical_keeps_raw():
    dst = {}
    stamp_audit_provenance(
        dst,
        audit_source="MANUAL_AUDIT_FROM_PDF",
        audit_evidence={"source_doc": "x.htm"},
    )
    assert dst["audit_source"] == "MANUAL_AUDIT_FROM_OFFICIAL_FILING"  # normalized
    assert dst["audit_source_raw"] == "MANUAL_AUDIT_FROM_PDF"          # raw preserved


def test_stamp_audit_provenance_rejects_unknown():
    with pytest.raises(ValueError, match="unknown audit_source"):
        stamp_audit_provenance({}, audit_source="BOGUS")


def test_stamp_audit_provenance_restatement_requires_accession():
    with pytest.raises(ValueError, match="accession_number"):
        stamp_audit_provenance(
            {},
            audit_source="MANUAL_RESTATEMENT_FROM_AMENDED_FILING",
            audit_evidence={"source_doc": "x.htm"},  # missing accession_number
        )


def test_stamp_audit_provenance_restatement_with_accession_ok():
    dst = {}
    stamp_audit_provenance(
        dst,
        audit_source="MANUAL_RESTATEMENT_FROM_AMENDED_FILING",
        audit_evidence={"accession_number": "0001234567-25-000001"},
    )
    assert dst["audit_source"] == "MANUAL_RESTATEMENT_FROM_AMENDED_FILING"


def test_stamp_audit_provenance_audit_note_length_limit():
    with pytest.raises(ValueError, match="500"):
        stamp_audit_provenance(
            {},
            audit_source="MANUAL_AUDIT_FROM_OFFICIAL_FILING",
            audit_note="x" * 501,
            audit_evidence={"source_doc": "x.htm"},
        )


def test_stamp_classification():
    dst = {}
    stamp_classification(
        dst,
        classification_source="AGENT_CLASSIFIED",
        long_tail_metadata={"rolls_up_to": "operating_expense"},
    )
    assert dst["classification_source"] == "AGENT_CLASSIFIED"
    assert dst["long_tail_metadata"] == {"rolls_up_to": "operating_expense"}
    assert "classified_at" in dst


def test_stamp_classification_rejects_unknown():
    with pytest.raises(ValueError, match="unknown classification_source"):
        stamp_classification({}, classification_source="BOGUS")


# ── row_has_audited_value predicate ──────────────────────────────────────────

def test_row_has_audited_value_canonical():
    assert row_has_audited_value({"audit_source": "MANUAL_AUDIT_FROM_OFFICIAL_FILING"}) is True


def test_row_has_audited_value_legacy_raw_only():
    """Legacy DB rows may only have audit_source_raw set."""
    assert row_has_audited_value({"audit_source_raw": "MANUAL_AUDIT_FROM_PDF"}) is True


def test_row_has_audited_value_empty():
    assert row_has_audited_value({}) is False
    assert row_has_audited_value(None) is False


def test_row_has_audited_value_classification_only_is_false():
    """A row with only classification (no audit) should return False."""
    assert row_has_audited_value({"classification_source": "AGENT_CLASSIFIED"}) is False


# ── round-trip: stamp → copy → preserve ──────────────────────────────────────

def test_round_trip_stamp_copy_preserve():
    """Realistic re-extract preservation flow."""
    old_row = {}
    stamp_audit_provenance(
        old_row,
        audit_source="MANUAL_AUDIT_FROM_OFFICIAL_FILING",
        audit_note="LITE Q4_FY2024 IBT from PDF",
        audit_evidence={"source_doc": "lite-10K.htm"},
    )

    new_row = {"value": 999, "uni_account": "income_before_tax"}
    # re-extract CONFLICT scenario: keep audit, mark preserved
    copy_audit_provenance(new_row, old_row)
    set_preservation_event(new_row, "REEXTRACT_PRESERVED_PRIOR_AUDIT")

    assert new_row["audit_source"] == "MANUAL_AUDIT_FROM_OFFICIAL_FILING"
    assert new_row["preserved_from_audit"] is True
    assert new_row["preservation_event"] == "REEXTRACT_PRESERVED_PRIOR_AUDIT"
    assert row_has_audited_value(new_row) is True
