"""Phase 4 regression tests — parse-SEC-supplement v3 preservation matrix.

Covers schema §5 (re-extract behavior) + §6.2 (dimensional identity) +
supplement-specific conflict.json fail-closed.

Run: uv run --with pytest python3 -m pytest scripts/tests/test_phase4_supplement_preservation.py -v
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "Tools" / "research-tools"))
sys.path.insert(
    0,
    "/Users/mensch5566/CC_Switch_Config/skills/parse-SEC-supplement/scripts",
)


def _write_existing(tmp_path, facts):
    p = tmp_path / "LITE_supplement_facts_v3.json"
    p.write_text(json.dumps({"metadata": {"ticker": "LITE"}, "facts": facts}))
    return p


def _mk(period="Q1_FY2026", axis="business_segment",
        axis_qname="us-gaap:StatementBusinessSegmentsAxis",
        source_account="CCG", source_account_qname="us-gaap:ConsumerCCGMember",
        uni_account="revenue", value=100.0, unit="USD_millions",
        period_kind="single_quarter", other_dimensions=None, **extras):
    row = {
        "period":               period,
        "period_kind":          period_kind,
        "axis":                 axis,
        "axis_qname":           axis_qname,
        "source_account":       source_account,
        "source_account_qname": source_account_qname,
        "uni_account":          uni_account,
        "value":                value,
        "unit":                 unit,
        "other_dimensions":     other_dimensions or [],
        "type":                 "GAAP_SEGMENT",
    }
    row.update(extras)
    return row


# ─────────────────────────────────────────────────────────────────────────────
# Phase 4.1: build_supplement_identity
# ─────────────────────────────────────────────────────────────────────────────

def test_identity_tuple_uses_qname_when_present():
    from _shared.audit_metadata import build_supplement_identity
    row = _mk()
    ident = build_supplement_identity(row)
    # (period, period_kind, axis_key, member_key, uni, other_dims_canonical, unit)
    assert ident == (
        "Q1_FY2026",
        "single_quarter",
        "us-gaap:StatementBusinessSegmentsAxis",
        "us-gaap:ConsumerCCGMember",
        "revenue",
        "",
        "USD_millions",
    )


def test_identity_tuple_falls_back_to_local_label_when_qname_missing():
    from _shared.audit_metadata import build_supplement_identity
    row = _mk(axis_qname=None, source_account_qname=None,
              axis="business segment", source_account="CCG (Consumer)")
    ident = build_supplement_identity(row)
    # Both keys go to "local:" prefix
    assert ident[2].startswith("local:")
    assert ident[3].startswith("local:")


def test_identity_different_members_no_collision():
    """Same (period, uni_account) but different members → distinct identity."""
    from _shared.audit_metadata import build_supplement_identity
    r1 = _mk(source_account="CCG", source_account_qname="us-gaap:CCG")
    r2 = _mk(source_account="DCAI", source_account_qname="us-gaap:DCAI")
    assert build_supplement_identity(r1) != build_supplement_identity(r2)


def test_identity_other_dimensions_distinguished():
    """Same primary axis × member but different other_dimensions → distinct."""
    from _shared.audit_metadata import build_supplement_identity
    r1 = _mk(other_dimensions=[{"axis": "srt:StatementGeographicalAxis",
                                 "member": "country:US"}])
    r2 = _mk(other_dimensions=[{"axis": "srt:StatementGeographicalAxis",
                                 "member": "country:JP"}])
    assert build_supplement_identity(r1) != build_supplement_identity(r2)


def test_identity_other_dimensions_canonical_order():
    """other_dimensions sort is deterministic — same dims in different order
    produce same identity."""
    from _shared.audit_metadata import build_supplement_identity
    r1 = _mk(other_dimensions=[
        {"axis": "A", "member": "M1"},
        {"axis": "B", "member": "M2"},
    ])
    r2 = _mk(other_dimensions=[
        {"axis": "B", "member": "M2"},
        {"axis": "A", "member": "M1"},
    ])
    assert build_supplement_identity(r1) == build_supplement_identity(r2)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 4.2: preservation matrix
# ─────────────────────────────────────────────────────────────────────────────

def test_match_copies_audit_provenance_no_event(tmp_path):
    import extract_supplement_v3 as e3
    existing_path = _write_existing(tmp_path, [_mk(
        value=379.2,
        audit_source="MANUAL_AUDIT_FROM_OFFICIAL_FILING",
        audit_source_raw="MANUAL_AUDIT_FROM_OFFICIAL_FILING",
        audit_note="from 10-Q Note 15",
    )])
    new_facts = [_mk(value=379.2)]   # MATCH
    merged, log, confs = e3.preserve_supplement_audited_cells(new_facts, existing_path)
    assert not confs
    assert len(merged) == 1
    assert merged[0]["audit_source"] == "MANUAL_AUDIT_FROM_OFFICIAL_FILING"
    assert merged[0]["audit_note"] == "from 10-Q Note 15"
    assert "preservation_event" not in merged[0]
    assert log[0]["kind"] == "MATCH"


def test_added_back_carries_old_row_with_audit_event(tmp_path):
    import extract_supplement_v3 as e3
    existing_path = _write_existing(tmp_path, [_mk(
        value=379.2,
        audit_source="MANUAL_AUDIT_FROM_OFFICIAL_FILING",
    )])
    new_facts = []  # row dropped from new extract
    merged, log, confs = e3.preserve_supplement_audited_cells(new_facts, existing_path)
    assert not confs
    assert len(merged) == 1
    assert merged[0]["value"] == 379.2
    assert merged[0]["preservation_event"] == "REEXTRACT_PRESERVED_PRIOR_AUDIT"
    assert log[0]["kind"] == "ADDED_BACK"


def test_added_back_classification_only_uses_classification_event(tmp_path):
    import extract_supplement_v3 as e3
    existing_path = _write_existing(tmp_path, [_mk(
        value=10.0,
        classification_source="AGENT_CLASSIFIED",
    )])
    new_facts = []
    merged, *_ = e3.preserve_supplement_audited_cells(new_facts, existing_path)
    assert merged[0]["preservation_event"] == "REEXTRACT_PRESERVED_PRIOR_CLASSIFICATION"
    assert merged[0]["preserved_from_audit"] is False


def test_conflict_default_keeps_audit_writes_conflict_json(tmp_path):
    """CONFLICT (no --accept-new-values): value restored to audit_value,
    PRIOR_AUDIT event set, AND conflict entry returned for separate
    conflict.json output."""
    import extract_supplement_v3 as e3
    existing_path = _write_existing(tmp_path, [_mk(
        value=379.2,
        audit_source="MANUAL_AUDIT_FROM_OFFICIAL_FILING",
    )])
    new_facts = [_mk(value=999.0)]
    merged, log, confs = e3.preserve_supplement_audited_cells(new_facts, existing_path)
    assert len(confs) == 1
    assert confs[0]["prior_audit_value"] == 379.2
    assert confs[0]["new_extracted_value"] == 999.0
    assert merged[0]["value"] == 379.2  # restored
    assert merged[0]["preservation_event"] == "REEXTRACT_PRESERVED_PRIOR_AUDIT"
    assert merged[0]["new_extract_value_rejected"] == 999.0


def test_accept_new_clears_audit_no_conflict_json(tmp_path):
    """--accept-new-values: drop audit metadata, no conflict.json entry."""
    import extract_supplement_v3 as e3
    existing_path = _write_existing(tmp_path, [_mk(
        value=379.2,
        audit_source="MANUAL_AUDIT_FROM_OFFICIAL_FILING",
        audit_note="x",
    )])
    new_facts = [_mk(value=999.0)]
    merged, log, confs = e3.preserve_supplement_audited_cells(
        new_facts, existing_path, accept_new_values=True,
    )
    assert not confs  # no unresolved conflicts
    assert merged[0]["value"] == 999.0
    assert "audit_source" not in merged[0]
    assert "audit_note" not in merged[0]
    assert merged[0]["accepted_new_value_replaces_audit"]["prior_audit_value"] == 379.2


def test_classification_only_conflict_uses_classification_event(tmp_path):
    """Classification-only CONFLICT: event must be PRIOR_CLASSIFICATION,
    NOT PRIOR_AUDIT (schema §5)."""
    import extract_supplement_v3 as e3
    existing_path = _write_existing(tmp_path, [_mk(
        value=5.0,
        classification_source="AGENT_CLASSIFIED",
        long_tail_metadata={"rolls_up_to": "revenue"},
    )])
    new_facts = [_mk(value=7.5)]
    merged, _, confs = e3.preserve_supplement_audited_cells(new_facts, existing_path)
    assert len(confs) == 1
    assert merged[0]["value"] == 5.0
    assert merged[0]["preservation_event"] == "REEXTRACT_PRESERVED_PRIOR_CLASSIFICATION"
    assert merged[0]["preserved_from_audit"] is False


def test_duplicate_identity_in_new_extract_fails_closed(tmp_path):
    import extract_supplement_v3 as e3
    existing_path = _write_existing(tmp_path, [_mk(
        audit_source="MANUAL_AUDIT_FROM_OFFICIAL_FILING",
    )])
    # Two new rows with same identity
    new_facts = [_mk(value=100.0), _mk(value=200.0)]
    with pytest.raises(Exception) as exc:
        e3.preserve_supplement_audited_cells(new_facts, existing_path)
    assert "duplicate" in str(exc.value).lower()


def test_long_tail_dimensional_no_collision_distinct_members(tmp_path):
    """Two segment rows in same period — different members must coexist."""
    import extract_supplement_v3 as e3
    existing_path = _write_existing(tmp_path, [
        _mk(source_account="CCG", source_account_qname="us-gaap:CCG", value=100.0,
            audit_source="MANUAL_AUDIT_FROM_OFFICIAL_FILING"),
        _mk(source_account="DCAI", source_account_qname="us-gaap:DCAI", value=50.0,
            audit_source="MANUAL_AUDIT_FROM_OFFICIAL_FILING"),
    ])
    new_facts = []  # both ADDED_BACK
    merged, log, _ = e3.preserve_supplement_audited_cells(new_facts, existing_path)
    assert len(merged) == 2
    members = {r["source_account"] for r in merged}
    assert members == {"CCG", "DCAI"}


# ─────────────────────────────────────────────────────────────────────────────
# Phase 4.3: conflict.json file output
# ─────────────────────────────────────────────────────────────────────────────

def test_write_conflict_json_shape(tmp_path):
    import extract_supplement_v3 as e3
    conflicts = [{
        "identity": ["Q1_FY2026", "single_quarter", "axis", "member", "rev", "", "USD_millions"],
        "period": "Q1_FY2026", "axis": "business_segment", "uni_account": "revenue",
        "source_account": "CCG", "prior_audit_value": 100.0,
        "new_extracted_value": 999.0, "unit": "USD_millions",
        "has_audit": True, "has_classification": False,
    }]
    path = e3.write_supplement_conflict_json(tmp_path, "LITE", conflicts)
    assert path.exists()
    doc = json.loads(path.read_text())
    assert doc["metadata"]["audit_conflicts_unresolved"] is True
    assert doc["metadata"]["conflict_count"] == 1
    assert doc["conflicts"][0]["prior_audit_value"] == 100.0


def test_write_conflict_json_empty_when_no_conflicts(tmp_path):
    import extract_supplement_v3 as e3
    path = e3.write_supplement_conflict_json(tmp_path, "LITE", [])
    doc = json.loads(path.read_text())
    assert doc["metadata"]["audit_conflicts_unresolved"] is False
    assert doc["metadata"]["conflict_count"] == 0
    assert doc["conflicts"] == []


# ─────────────────────────────────────────────────────────────────────────────
# No-op when no audit rows
# ─────────────────────────────────────────────────────────────────────────────

def test_no_op_when_no_audit_rows(tmp_path):
    import extract_supplement_v3 as e3
    existing_path = _write_existing(tmp_path, [_mk(value=100.0)])   # no audit
    new_facts = [_mk(value=200.0)]
    merged, log, confs = e3.preserve_supplement_audited_cells(new_facts, existing_path)
    assert merged[0]["value"] == 200.0  # new wins
    assert not log
    assert not confs


def test_no_existing_file_passthrough(tmp_path):
    import extract_supplement_v3 as e3
    new_facts = [_mk(value=100.0)]
    merged, log, confs = e3.preserve_supplement_audited_cells(
        new_facts, tmp_path / "nonexistent.json",
    )
    assert merged == new_facts
    assert not log
    assert not confs
