"""Upsert dry-run / JSON-write tests.
Run: cd /Users/mensch5566/AI_Agent && uv run --with pytest python3 -m pytest scripts/tests/test_macro_upsert.py -v
"""
from __future__ import annotations
import json, sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from macro.upsert_macro_facts import write_local_json  # noqa: E402


def test_write_local_json_roundtrip(tmp_path):
    rows = [{"fact_id": "x", "indicator_key": "vix", "value": 17.8, "period_end": "2026-06-08"}]
    out = tmp_path / "macro_facts.json"
    write_local_json(rows, out)
    saved = json.loads(out.read_text())
    assert saved["count"] == 1
    assert saved["facts"][0]["indicator_key"] == "vix"
