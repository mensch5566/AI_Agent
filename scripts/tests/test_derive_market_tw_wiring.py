"""--market tw source discovery + loading (derive-A spec §5.6)."""
import json, sys
from pathlib import Path

sys.path.insert(0, "/Users/mensch5566/CC_Switch_Config/skills/derive-base/scripts")
import io_loader as db_io


def _mk_tw_vault(tmp_path: Path) -> Path:
    d = tmp_path / "Khouse/Semiconductors/聯亞/01_Source/MOPS Filings/Skill_Output/parse-twse-ixbrl"
    d.mkdir(parents=True)
    (d / "3081_twse_facts.json").write_text(json.dumps({
        "ticker": "3081", "report_category": "ir", "unit": "TWD_thousands",
        "periods": ["Q1_FY2025"],
        "facts_by_period": {"Q1_FY2025": {"period_end": "2025-03-31", "report_category": "ir",
            "facts": {"revenue": {"value": 100.0, "statement": "income_statement",
                                  "sort_order": 4000, "period_kind": "ytd",
                                  "xbrl_concept": "ifrs-full:Revenue"}}}}}))
    return tmp_path


def test_discover_sources_tw_globs_chinese_folder(tmp_path):
    vault = _mk_tw_vault(tmp_path)
    srcs = db_io.discover_sources_tw(vault, "3081")
    assert srcs["twse_facts"] is not None and srcs["twse_facts"].exists()


def test_load_facts_tw_returns_factrows(tmp_path):
    vault = _mk_tw_vault(tmp_path)
    rows = db_io.load_facts_tw(db_io.discover_sources_tw(vault, "3081"))
    assert len(rows) == 1 and rows[0].unit == "TWD_thousands"
    assert rows[0].period == "Q1_FY2025"


def test_output_dir_tw_lands_beside_facts(tmp_path):
    vault = _mk_tw_vault(tmp_path)
    srcs = db_io.discover_sources_tw(vault, "3081")
    od = db_io.output_dir_tw(srcs, "2026-07-02-1200")
    assert od.name == "2026-07-02-1200" and od.parent.name == "derive-base"
    assert od.parent.parent.name == "Skill_Output"


def test_missing_facts_fails_closed(tmp_path):
    srcs = db_io.discover_sources_tw(tmp_path, "9999")
    try:
        db_io.load_facts_tw(srcs)
        assert False, "should raise"
    except FileNotFoundError:
        pass
