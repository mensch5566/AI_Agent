from audit import to_derived_metric_row, write_audit_md, write_conflict_md
from derive_types import Candidate


def test_audit_can_be_imported_standalone_from_all_mirrors():
    """Codex round-5 F2: audit.py must be import-able directly in each
    of the 4 mirror locations without relying on io_loader having run
    first to set sys.path. Regression guard for the AI_AGENT_ROOT
    discovery hardening."""
    import importlib.util, sys as _sys, os
    mirrors = [
        os.path.expanduser("~/CC_Switch_Config/skills/derive-base/scripts/audit.py"),
        os.path.expanduser("~/.claude/skills/derive-base/scripts/audit.py"),
        os.path.expanduser("~/.codex/skills/derive-base/scripts/audit.py"),
        os.path.expanduser("~/.cc-switch/skills/derive-base/scripts/audit.py"),
    ]
    tested = 0
    for path in mirrors:
        if not os.path.exists(path):
            continue
        spec = importlib.util.spec_from_file_location(f"audit_{abs(hash(path))}", path)
        mod = importlib.util.module_from_spec(spec)
        _sys.path.insert(0, os.path.dirname(path))
        try:
            spec.loader.exec_module(mod)
        finally:
            _sys.path.pop(0)
        assert callable(mod.metrics_cell_id), f"{path}: metrics_cell_id missing after import"
        assert callable(mod.write_audit_md), f"{path}: write_audit_md missing after import"
        tested += 1
    assert tested > 0, "at least one mirror should exist on this machine"


def _c():
    return Candidate(
        ticker="AAOI", period="Q4_FY2024", period_kind="derived_q4",
        period_start="2024-10-01", period_end="2024-12-31",
        statement="IS", version="GAAP", uni_account="revenue",
        value=101000.0, unit="USD_thousands",
        rule_id="Q4_FY_MINUS_9M", rule_priority=1,
        chain_depth=1, chained=False,
        inputs=[{"cell_id": "fy", "uni_account": "revenue", "period": "FY2024", "value": 249000.0, "status": "SOURCE_OF_TRUTH"}],
        extras={"formula": "FY2024 - 9M_FY2024"},
    )


def test_to_derived_metric_row_deterministic_cell_id():
    a = to_derived_metric_row(_c())
    b = to_derived_metric_row(_c())
    assert a.cell_id == b.cell_id
    assert a.status == "DERIVED_FROM_DISCLOSED"
    assert a.provenance["rule_id"] == "Q4_FY_MINUS_9M"
    assert a.provenance["formula"] == "FY2024 - 9M_FY2024"
    assert a.provenance["chain_depth"] == 1
    assert a.provenance["target_table"] == "sec_financial_metrics"


def test_write_audit_md_lists_pass_counts_and_chain_paths(tmp_path):
    result = {
        "winners": [],
        "conflicts": [],
        "fact_conflicts": [],
        "stats": {"pass1_count": 0, "pass2_count": 1, "pass3_count": 0, "final_count": 1, "conflicts": 0, "fact_skips": 0},
    }
    p = write_audit_md(tmp_path, "AAOI", result, meta_extras={"input_facts_count": 100})
    txt = p.read_text()
    assert "Pass 1" in txt and "Pass 2" in txt and "Pass 3" in txt
    assert "input_facts_count" in txt or "100" in txt


def test_write_conflict_md_lists_tolerance_breaches(tmp_path):
    result = {
        "conflicts": [{
            "ticker": "AAOI", "period": "Q4_FY2024", "statement": "IS",
            "version": "GAAP", "uni_account": "revenue",
            "preferred_rule": "Q4_FY_MINUS_9M",     "preferred_value": 101000.0,
            "other_rule":     "Q4_FY_MINUS_Q1Q2Q3", "other_value":     99000.0,
            "abs_diff": 2000.0, "rel_pct": 2.0, "unit": "USD_thousands",
        }],
        "fact_conflicts": [],
    }
    p = write_conflict_md(tmp_path, "AAOI", result)
    txt = p.read_text()
    assert "Q4_FY2024" in txt and "revenue" in txt and "2.0%" in txt
