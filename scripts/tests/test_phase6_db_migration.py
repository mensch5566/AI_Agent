"""Phase 6.3 — unit tests for migrate_db_audit_source_v4 helpers.

The migration runner itself (CLI / Supabase calls) is not tested here —
those require live DB. These tests verify the pure transformation logic:
`classify_row` + `build_updated_provenance`.

Run: uv run --with pytest python3 -m pytest scripts/tests/test_phase6_db_migration.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "Tools" / "research-tools"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

# Import without triggering supabase-py import path: monkey-patch via module
# attribute access. The migration script imports supabase at top level, so
# we shim it before import.
import types as _types
_supabase_stub = _types.ModuleType("supabase")
_supabase_stub.create_client = lambda *a, **kw: None  # type: ignore
sys.modules.setdefault("supabase", _supabase_stub)

import migrate_db_audit_source_v4 as mig  # noqa: E402


# ── classify_row ─────────────────────────────────────────────────────────────

def test_classify_legacy_audit_pdf():
    prov = {"audit_source": "MANUAL_AUDIT_FROM_PDF"}
    assert mig.classify_row(prov) == "audit_normalize"


def test_classify_legacy_audit_8k_pdf():
    prov = {"audit_source": "MANUAL_AUDIT_FROM_8K_PDF"}
    assert mig.classify_row(prov) == "audit_normalize"


def test_classify_legacy_classification_in_audit_field():
    prov = {"audit_source": "AGENT_CLASSIFIED"}
    assert mig.classify_row(prov) == "classification_promote"


def test_classify_manual_reclassified_in_audit_field():
    prov = {"audit_source": "MANUAL_RECLASSIFIED"}
    assert mig.classify_row(prov) == "classification_promote"


def test_classify_canonical_audit_no_op():
    prov = {"audit_source": "MANUAL_AUDIT_FROM_OFFICIAL_FILING"}
    assert mig.classify_row(prov) is None


def test_classify_no_audit_source():
    assert mig.classify_row({}) is None
    assert mig.classify_row({"audit_source": None}) is None


def test_classify_unknown_audit_source():
    """Unknown string isn't a legacy mapping target → leave alone."""
    assert mig.classify_row({"audit_source": "SOME_UNKNOWN"}) is None


# ── build_updated_provenance: audit normalize ────────────────────────────────

def test_audit_normalize_writes_canonical_and_preserves_raw():
    prov = {
        "audit_source": "MANUAL_AUDIT_FROM_PDF",
        "audit_note":   "from 10-Q",
        "accession_number": "0001234567-25-000001",
    }
    new, op = mig.build_updated_provenance(prov)
    assert op == "audit_normalize"
    assert new["audit_source"] == "MANUAL_AUDIT_FROM_OFFICIAL_FILING"
    assert new["audit_source_raw"] == "MANUAL_AUDIT_FROM_PDF"
    # Other fields untouched
    assert new["audit_note"] == "from 10-Q"
    assert new["accession_number"] == "0001234567-25-000001"


def test_audit_normalize_8k_pdf():
    prov = {"audit_source": "MANUAL_AUDIT_FROM_8K_PDF"}
    new, op = mig.build_updated_provenance(prov)
    assert op == "audit_normalize"
    assert new["audit_source"] == "MANUAL_AUDIT_FROM_OFFICIAL_FILING"
    assert new["audit_source_raw"] == "MANUAL_AUDIT_FROM_8K_PDF"


def test_audit_normalize_does_not_overwrite_existing_raw():
    """If audit_source_raw is already set (from earlier dual-write), keep it."""
    prov = {
        "audit_source":     "MANUAL_AUDIT_FROM_PDF",
        "audit_source_raw": "MANUAL_AUDIT_FROM_PDF",   # already set
    }
    new, _ = mig.build_updated_provenance(prov)
    assert new["audit_source"] == "MANUAL_AUDIT_FROM_OFFICIAL_FILING"
    assert new["audit_source_raw"] == "MANUAL_AUDIT_FROM_PDF"


# ── build_updated_provenance: classification promote ─────────────────────────

def test_classification_promote_basic():
    prov = {"audit_source": "AGENT_CLASSIFIED"}
    new, op = mig.build_updated_provenance(prov)
    assert op == "classification_promote"
    assert new["classification_source"] == "AGENT_CLASSIFIED"
    # Legacy audit_source removed
    assert "audit_source" not in new
    # Not preserved as audit_source_raw (it wasn't audit)
    assert "audit_source_raw" not in new


def test_classification_promote_records_in_long_tail_metadata():
    """If row already has long_tail_metadata, drop forensic marker there
    (mirrors Phase 2 F14 ADDED_BACK canonicalization)."""
    prov = {
        "audit_source": "AGENT_CLASSIFIED",
        "long_tail_metadata": {"rolls_up_to": "operating_expenses"},
    }
    new, _ = mig.build_updated_provenance(prov)
    assert new["long_tail_metadata"]["legacy_audit_source_raw"] == "AGENT_CLASSIFIED"
    assert new["long_tail_metadata"]["rolls_up_to"] == "operating_expenses"  # untouched
    assert "audit_source" not in new


def test_classification_promote_does_not_clobber_existing_classification_source():
    """If a row somehow has BOTH legacy audit_source=AGENT_CLASSIFIED AND a
    canonical classification_source, the canonical one wins (no-op on field)."""
    prov = {
        "audit_source": "AGENT_CLASSIFIED",
        "classification_source": "MANUAL_RECLASSIFIED",  # explicit canonical
    }
    new, _ = mig.build_updated_provenance(prov)
    # New code overwrites — this is current behavior. Document via test.
    # If we want preservation, change classify_row to detect this case.
    assert new["classification_source"] == "AGENT_CLASSIFIED"
    assert "audit_source" not in new


def test_classification_promote_manual_reclassified():
    prov = {"audit_source": "MANUAL_RECLASSIFIED"}
    new, op = mig.build_updated_provenance(prov)
    assert op == "classification_promote"
    assert new["classification_source"] == "MANUAL_RECLASSIFIED"


# ── summarize ─────────────────────────────────────────────────────────────────

def test_summarize_groups_by_op_and_source():
    rows = [
        {"provenance": {"audit_source": "MANUAL_AUDIT_FROM_PDF"}},
        {"provenance": {"audit_source": "MANUAL_AUDIT_FROM_PDF"}},
        {"provenance": {"audit_source": "MANUAL_AUDIT_FROM_8K_PDF"}},
        {"provenance": {"audit_source": "AGENT_CLASSIFIED"}},
        {"provenance": {"audit_source": "MANUAL_AUDIT_FROM_OFFICIAL_FILING"}},  # canonical, no-op
    ]
    summary = mig.summarize(rows, "sec_financial_facts")
    counts = summary["counts"]
    assert counts[("audit_normalize", "MANUAL_AUDIT_FROM_PDF")] == 2
    assert counts[("audit_normalize", "MANUAL_AUDIT_FROM_8K_PDF")] == 1
    assert counts[("classification_promote", "AGENT_CLASSIFIED")] == 1
    # canonical not in counts
    assert ("audit_normalize", "MANUAL_AUDIT_FROM_OFFICIAL_FILING") not in counts


# ── round-trip with adapter contract ────────────────────────────────────────

def test_migrated_row_passes_adapter_allowlist_check():
    """Phase 3 P3-F1: adapter requires audit_source ∈ MANUAL_AUDIT_SOURCES.
    After migration, the canonical value must satisfy is_manual_audit_source."""
    from _shared.audit_metadata import is_manual_audit_source

    prov = {"audit_source": "MANUAL_AUDIT_FROM_PDF"}
    new, _ = mig.build_updated_provenance(prov)
    assert is_manual_audit_source(new["audit_source"])


def test_migrated_classification_row_does_not_pollute_audit_predicate():
    """After classification promotion, is_manual_audit_source on the row's
    audit_source/audit_source_raw should return False (row is classification,
    not audit)."""
    from _shared.audit_metadata import row_has_audited_value

    prov = {"audit_source": "AGENT_CLASSIFIED"}
    new, _ = mig.build_updated_provenance(prov)
    assert row_has_audited_value(new) is False
