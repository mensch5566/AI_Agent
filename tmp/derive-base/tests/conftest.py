"""Make derive_types and sibling modules importable from tests/."""
import sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Also add _shared module (research-tools) for FactRow import
AI_AGENT_ROOT = ROOT.parent.parent
sys.path.insert(0, str(AI_AGENT_ROOT / "Tools" / "research-tools"))

import pytest

@pytest.fixture
def sample_gaap_revenue_facts():
    """Hand-crafted FactRow-like dicts (not real FactRow — keeps test light).

    AAOI-shaped: Q1/Q2/Q3 + 6M + 9M + FY for one IS metric (revenue).
    Engine code should treat these like FactRow via duck typing.
    """
    from _shared.sec_json_adapter import FactRow

    base = dict(
        ticker="AAOI", statement="IS", version="GAAP",
        uni_account="revenue", source_account="us-gaap:Revenues",
        xbrl_tag="Revenues", unit="USD_thousands", weight=1,
        status="SOURCE_OF_TRUTH", ordinal=None, long_tail_metadata=None,
        provenance={"source_filing": "10-K"},
    )
    rows = [
        {**base, "cell_id": "q1", "period": "Q1_FY2024", "period_kind": "quarter_duration",   "period_end": "2024-03-31", "value": 40000.0},
        {**base, "cell_id": "q2", "period": "Q2_FY2024", "period_kind": "quarter_duration",   "period_end": "2024-06-30", "value": 43000.0},
        {**base, "cell_id": "h1", "period": "6M_FY2024", "period_kind": "ytd_duration",       "period_end": "2024-06-30", "value": 83000.0},
        {**base, "cell_id": "q3", "period": "Q3_FY2024", "period_kind": "quarter_duration",   "period_end": "2024-09-30", "value": 65000.0},
        {**base, "cell_id": "9m", "period": "9M_FY2024", "period_kind": "ytd_duration",       "period_end": "2024-09-30", "value": 148000.0},
        {**base, "cell_id": "fy", "period": "FY2024",    "period_kind": "fy_annual_duration", "period_end": "2024-12-31", "value": 249000.0},
    ]
    # turn into FactRow instances so production code can rely on attribute access
    return [FactRow(**r) for r in rows]
