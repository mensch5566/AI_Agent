"""Phase 6.1 — unit tests for _shared/preservation.preserve_audited_rows.

The skill-end behavior is covered by existing test_xbrl_extract_preservation /
test_extract_8k_preservation / test_phase4_supplement_preservation. These
tests target the shared helper directly so future regressions in the helper
surface immediately without skipping through a parse-skill wrapper.

Run: uv run --with pytest python3 -m pytest scripts/tests/test_phase6_preservation_helper.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "Tools" / "research-tools"))

from _shared.audit_metadata import (  # noqa: E402
    DuplicateIdentityError,
    build_preservation_identity,
)
from _shared.preservation import (  # noqa: E402
    PreservationResult,
    preserve_audited_rows,
    row_has_audit,
    row_has_classification,
    values_match,
)


# ── basic helpers ────────────────────────────────────────────────────────────

def test_values_match_inclusive_tolerance():
    assert values_match(100.0, 100.0 + 1e-6) is True   # exact boundary
    assert values_match(100.0, 100.0 + 1e-3) is False  # outside


def test_values_match_handles_none():
    assert values_match(None, None) is True
    assert values_match(None, 100.0) is False


def test_row_has_audit_canonical_and_legacy():
    assert row_has_audit({"audit_source": "MANUAL_AUDIT_FROM_OFFICIAL_FILING"}) is True
    assert row_has_audit({"audit_source": "MANUAL_AUDIT_FROM_PDF"}) is True   # legacy
    assert row_has_audit({"audit_source_raw": "MANUAL_AUDIT_FROM_PDF"}) is True
    assert row_has_audit({"audit_source": "AGENT_CLASSIFIED"}) is False       # classification


def test_row_has_classification_canonical_and_legacy():
    assert row_has_classification({"classification_source": "AGENT_CLASSIFIED"}) is True
    assert row_has_classification({"classification_source": "MANUAL_RECLASSIFIED"}) is True
    # Legacy: pre-v4 wrote it into audit_source
    assert row_has_classification({"audit_source": "AGENT_CLASSIFIED"}) is True
    assert row_has_classification({"audit_source": "MANUAL_AUDIT_FROM_PDF"}) is False


# ── preserve_audited_rows matrix ────────────────────────────────────────────

def _ident(row):
    """Tiny identity function for these tests."""
    return (row.get("period"), row.get("uni_account"), row.get("source_account"))


def test_no_existing_audit_returns_input_unchanged():
    existing = [{"period": "Q1", "uni_account": "rev", "value": 100.0}]
    new = [{"period": "Q1", "uni_account": "rev", "value": 110.0}]
    result = preserve_audited_rows(existing, new, _ident)
    assert isinstance(result, PreservationResult)
    assert result.merged_rows is new
    assert new[0]["value"] == 110.0  # caller's new value, untouched


def test_match_copies_audit_no_event():
    existing = [{
        "period": "Q1", "uni_account": "rev", "value": 100.0,
        "audit_source": "MANUAL_AUDIT_FROM_OFFICIAL_FILING",
        "audit_source_raw": "MANUAL_AUDIT_FROM_OFFICIAL_FILING",
        "audit_note": "x",
    }]
    new = [{"period": "Q1", "uni_account": "rev", "value": 100.0}]
    result = preserve_audited_rows(existing, new, _ident)
    assert result.n_match == 1
    assert new[0]["audit_source"] == "MANUAL_AUDIT_FROM_OFFICIAL_FILING"
    assert new[0]["audit_note"] == "x"
    assert "preservation_event" not in new[0]


def test_added_back_carries_old_row_with_audit_event():
    existing = [{
        "period": "Q1", "uni_account": "rev", "value": 100.0,
        "audit_source": "MANUAL_AUDIT_FROM_OFFICIAL_FILING",
    }]
    new = []
    result = preserve_audited_rows(existing, new, _ident)
    assert result.n_added_back == 1
    assert len(new) == 1
    assert new[0]["value"] == 100.0
    assert new[0]["preservation_event"] == "REEXTRACT_PRESERVED_PRIOR_AUDIT"


def test_added_back_classification_only_uses_classification_event():
    existing = [{
        "period": "Q1", "uni_account": "rev", "value": 10.0,
        "classification_source": "AGENT_CLASSIFIED",
    }]
    new = []
    result = preserve_audited_rows(existing, new, _ident)
    assert new[0]["preservation_event"] == "REEXTRACT_PRESERVED_PRIOR_CLASSIFICATION"


def test_added_back_canonicalizes_legacy_agent_classified():
    """Phase 2 F14 baked into the helper: ADDED_BACK on legacy
    AGENT_CLASSIFIED-in-audit_source canonicalizes the field."""
    existing = [{
        "period": "Q1", "uni_account": "rev", "value": 10.0,
        "audit_source": "AGENT_CLASSIFIED",
        "long_tail_metadata": {"rolls_up_to": "x"},
    }]
    new = []
    preserve_audited_rows(existing, new, _ident)
    row = new[0]
    assert row.get("audit_source") is None
    assert row["classification_source"] == "AGENT_CLASSIFIED"
    assert row["long_tail_metadata"]["legacy_audit_source_raw"] == "AGENT_CLASSIFIED"


def test_conflict_default_keeps_audit_writes_conflict_entry():
    existing = [{
        "period": "Q1", "uni_account": "rev", "value": 100.0,
        "audit_source": "MANUAL_AUDIT_FROM_OFFICIAL_FILING",
    }]
    new = [{"period": "Q1", "uni_account": "rev", "value": 999.0}]
    result = preserve_audited_rows(existing, new, _ident)
    assert result.n_conflict == 1
    assert len(result.conflicts_for_json) == 1   # audit conflict → fail-closed entry
    assert new[0]["value"] == 100.0
    assert new[0]["preservation_event"] == "REEXTRACT_PRESERVED_PRIOR_AUDIT"
    assert new[0]["new_extract_value_rejected"] == 999.0


def test_conflict_classification_only_does_not_write_conflict_entry():
    """P4-F1 baked into helper: classification-only conflict stays on row
    but does NOT enter conflicts_for_json fail-closed list."""
    existing = [{
        "period": "Q1", "uni_account": "rev", "value": 100.0,
        "classification_source": "AGENT_CLASSIFIED",
    }]
    new = [{"period": "Q1", "uni_account": "rev", "value": 999.0}]
    result = preserve_audited_rows(existing, new, _ident)
    assert result.n_conflict == 1
    assert result.conflicts_for_json == []
    assert new[0]["value"] == 100.0
    assert new[0]["preservation_event"] == "REEXTRACT_PRESERVED_PRIOR_CLASSIFICATION"


def test_accept_new_clears_audit_keeps_classification():
    existing = [{
        "period": "Q1", "uni_account": "rev", "value": 100.0,
        "audit_source": "MANUAL_AUDIT_FROM_OFFICIAL_FILING",
        "audit_note": "x",
    }]
    new = [{"period": "Q1", "uni_account": "rev", "value": 999.0}]
    result = preserve_audited_rows(existing, new, _ident, accept_new_values=True)
    assert result.n_accept_new == 1
    assert result.conflicts_for_json == []
    assert new[0]["value"] == 999.0
    assert "audit_source" not in new[0]
    assert new[0]["accepted_new_value_replaces_audit"]["prior_audit_value"] == 100.0


def test_duplicate_identity_in_existing_audit_fails_closed():
    existing = [
        {"period": "Q1", "uni_account": "rev", "source_account": "x", "value": 100.0,
         "audit_source": "MANUAL_AUDIT_FROM_OFFICIAL_FILING"},
        {"period": "Q1", "uni_account": "rev", "source_account": "x", "value": 200.0,
         "audit_source": "MANUAL_AUDIT_FROM_OFFICIAL_FILING"},
    ]
    with pytest.raises(DuplicateIdentityError, match="duplicate audit"):
        preserve_audited_rows(existing, [], _ident)


def test_duplicate_identity_in_new_fails_closed():
    existing = [{"period": "Q1", "uni_account": "rev", "source_account": "x", "value": 100.0,
                 "audit_source": "MANUAL_AUDIT_FROM_OFFICIAL_FILING"}]
    new = [
        {"period": "Q1", "uni_account": "rev", "source_account": "x", "value": 100.0},
        {"period": "Q1", "uni_account": "rev", "source_account": "x", "value": 200.0},
    ]
    with pytest.raises(DuplicateIdentityError, match="duplicate identity"):
        preserve_audited_rows(existing, new, _ident)


# ── integration: build_preservation_identity from audit_metadata ────────────

def test_works_with_real_build_preservation_identity():
    existing = [{
        "period": "Q1_FY2026", "uni_account": "revenue",
        "source_account": "Revenues", "unit": "USD_millions", "type": "GAAP",
        "value": 100.0, "audit_source": "MANUAL_AUDIT_FROM_OFFICIAL_FILING",
    }]
    new = [{
        "period": "Q1_FY2026", "uni_account": "revenue",
        "source_account": "Revenues", "unit": "USD_millions", "type": "GAAP",
        "value": 100.0,
    }]
    identity_fn = lambda r: build_preservation_identity("income_statement", r)
    result = preserve_audited_rows(existing, new, identity_fn)
    assert result.n_match == 1
    assert new[0]["audit_source"] == "MANUAL_AUDIT_FROM_OFFICIAL_FILING"
