import json
from pathlib import Path
import importlib.util
import sys


def _import_upsert():
    p = Path(__file__).resolve().parents[1] / "upsert_sec_financials.py"
    spec = importlib.util.spec_from_file_location("upsert_mod", str(p))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["upsert_mod"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_load_derived_metrics_latest_run(tmp_path):
    upsert = _import_upsert()
    # Build a vault skeleton with two run folders → expect the later one wins.
    vault = tmp_path
    base = vault / "Khouse" / "Semiconductors" / "ABC" / "01_Source" / "SEC Filings" / "Skill_Output" / "derive-base"
    (base / "2026-05-01-1000").mkdir(parents=True)
    (base / "2026-05-17-1200").mkdir(parents=True)
    (base / "2026-05-01-1000" / "ABC_derived.json").write_text(json.dumps({
        "metadata": {"ticker": "ABC", "skill_version": "0.1"},
        "derived_metrics": [{"cell_id": "old"}],
    }))
    (base / "2026-05-17-1200" / "ABC_derived.json").write_text(json.dumps({
        "metadata": {"ticker": "ABC", "skill_version": "1.0"},
        "derived_metrics": [{"cell_id": "new"}],
    }))
    rows = upsert.load_derived_metrics(vault, "ABC")
    assert len(rows) == 1
    assert rows[0]["cell_id"] == "new"
