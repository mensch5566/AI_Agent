"""Macro FRED fetch/normalize tests.
Run: cd /Users/mensch5566/AI_Agent && uv run --with pytest python3 -m pytest scripts/tests/test_macro_fetch.py -v
"""
from __future__ import annotations
import sys, hashlib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from macro.fetch_fred import normalize_observations, fact_id  # noqa: E402


def test_normalize_skips_missing_values():
    obs = [
        {"date": "2026-06-01", "value": "."},      # FRED missing marker
        {"date": "2026-06-08", "value": "7100.5"},
    ]
    rows = normalize_observations("fed_total_assets", "WALCL", "L1", "usd_millions", "weekly", obs)
    assert len(rows) == 1
    assert rows[0]["value"] == 7100.5
    assert rows[0]["period_end"] == "2026-06-08"
    assert rows[0]["indicator_key"] == "fed_total_assets"
    assert rows[0]["source_ref"] == "FRED:WALCL"
    assert rows[0]["source_type"] == "api"


def test_fact_id_is_deterministic():
    a = fact_id("hy_oas", "2026-06-08", 1)
    b = fact_id("hy_oas", "2026-06-08", 1)
    assert a == b == hashlib.sha256(b"hy_oas|2026-06-08|1").hexdigest()
