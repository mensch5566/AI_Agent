import json, os, subprocess, sys
from pathlib import Path
import pytest

VAULT = Path(os.environ.get(
    "OBSIDIAN_VAULT",
    os.path.expanduser("~/Obsidian"),
))


@pytest.fixture(scope="module")
def intc_derived():
    if not VAULT.exists():
        pytest.skip("Obsidian vault not present (CI run)")
    cli = Path(__file__).resolve().parents[1] / "derive_base.py"
    r = subprocess.run([sys.executable, str(cli), "--ticker", "INTC"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    out_dir = Path([ln for ln in r.stdout.splitlines() if ln.strip()][-1])
    return json.loads((out_dir / "INTC_derived.json").read_text())


def test_intc_q4_revenue(intc_derived):
    # INTC FY2025 = 52,853 (USD_millions), 9M_FY2025 = 39,179 → Q4 = 13,674
    row = next((r for r in intc_derived["derived_metrics"]
                if r["uni_account"] == "revenue"
                and r["period"] == "Q4_FY2025"
                and r["version"] == "GAAP"), None)
    assert row is not None
    assert abs(row["value"] - 13674.0) < 1.0
    assert row["unit"] == "USD_millions"


def test_intc_q4_uses_fy_minus_9m(intc_derived):
    # 2026-06-03: INTC was re-parsed to the current contract (YTD first-class),
    # so 9M_FY YTD is now disclosed for every fiscal year. Q4 reconstruction
    # therefore prefers FY − 9M (priority 1), like AAOI/SNDK — the old
    # FY − Q1Q2Q3 fallback no longer fires for INTC. (Pre-reparse INTC lacked
    # 9M YTD and used the Q1Q2Q3 fallback; that history is now stale.)
    rule_ids = {r["provenance"]["rule_id"] for r in intc_derived["derived_metrics"]}
    assert "Q4_FY_MINUS_9M" in rule_ids
    # CALC_LINKBASE optional — log but don't hard-fail (depends on facts coverage)
    print("rule_ids fired:", rule_ids)
