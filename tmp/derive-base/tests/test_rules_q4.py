from rules_q4 import q4_candidates


def test_q4_prefer_fy_minus_9m(sample_gaap_revenue_facts):
    # FY=249000, 9M=148000 → Q4=101000
    cands = q4_candidates(sample_gaap_revenue_facts)
    # Expect one Q4 candidate per (uni_account, fy) where inputs are sufficient
    q4 = [c for c in cands if c.period == "Q4_FY2024"]
    assert len(q4) == 1
    assert q4[0].value == 101000.0
    assert q4[0].rule_id == "Q4_FY_MINUS_9M"
    assert q4[0].rule_priority == 1
    assert q4[0].uni_account == "revenue"
    assert q4[0].period_kind == "derived_q4"
    assert q4[0].chain_depth == 1


def test_q4_fallback_when_9m_missing(sample_gaap_revenue_facts):
    rows_no_9m = [f for f in sample_gaap_revenue_facts if f.period != "9M_FY2024"]
    cands = q4_candidates(rows_no_9m)
    q4 = [c for c in cands if c.period == "Q4_FY2024"]
    assert len(q4) == 1
    # FY 249000 - (40000+43000+65000) = 101000
    assert q4[0].value == 101000.0
    assert q4[0].rule_id == "Q4_FY_MINUS_Q1Q2Q3"
    assert q4[0].rule_priority == 2


def test_q4_skipped_when_missing_inputs(sample_gaap_revenue_facts):
    rows_no_fy = [f for f in sample_gaap_revenue_facts if f.period != "FY2024"]
    cands = q4_candidates(rows_no_fy)
    assert [c for c in cands if c.period == "Q4_FY2024"] == []


def test_q4_only_for_is_cf_gaap(sample_gaap_revenue_facts):
    # If we relabel everything as BS, nothing should be derived
    for f in sample_gaap_revenue_facts:
        f.statement = "BS"
    cands = q4_candidates(sample_gaap_revenue_facts)
    assert cands == []


def test_q4_skipped_when_units_mismatch(sample_gaap_revenue_facts):
    """If FY is in USD_millions but YTD/quarters are in USD_thousands,
    _units_match() should drop the candidate silently — derive must never
    mix units."""
    for f in sample_gaap_revenue_facts:
        if f.period == "FY2024":
            f.unit = "USD_millions"   # mismatch vs other periods (USD_thousands)
    cands = q4_candidates(sample_gaap_revenue_facts)
    assert [c for c in cands if c.period == "Q4_FY2024"] == []


def test_q4_dates_inherit_from_fy_for_dec_fy_end(sample_gaap_revenue_facts):
    """Dec FY-end (AAOI/INTC shape): Q4 period_end matches FY period_end,
    Q4 period_start = Q3.period_end + 1 day."""
    cands = q4_candidates(sample_gaap_revenue_facts)
    q4 = next(c for c in cands if c.period == "Q4_FY2024")
    assert q4.period_end == "2024-12-31"  # = FY2024 period_end
    assert q4.period_start == "2024-10-01"  # = Q3 (2024-09-30) + 1 day


def test_q4_skipped_for_weighted_average_shares():
    """Codex F1: WASO/shares facts must NOT emit Q4 candidates.
    weighted-average shares are not additive — Q4 = FY - 9M is mathematically
    invalid for shares. Skill spec and design doc both forbid this."""
    from _shared.sec_json_adapter import FactRow
    base = dict(
        ticker="INTC", statement="IS", version="GAAP",
        uni_account="shares_diluted_millions", source_account="us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding",
        xbrl_tag="WeightedAverageNumberOfDilutedSharesOutstanding", unit="millions_shares", weight=1,
        status="SOURCE_OF_TRUTH", ordinal=None, long_tail_metadata=None,
        provenance={"source_filing": "10-K"},
    )
    rows = [
        FactRow(**{**base, "cell_id": "q1", "period": "Q1_FY2025", "period_kind": "quarter_duration",   "period_end": "2025-03-29", "value": 4337.0}),
        FactRow(**{**base, "cell_id": "q2", "period": "Q2_FY2025", "period_kind": "quarter_duration",   "period_end": "2025-06-28", "value": 4339.0}),
        FactRow(**{**base, "cell_id": "q3", "period": "Q3_FY2025", "period_kind": "quarter_duration",   "period_end": "2025-09-27", "value": 4350.0}),
        FactRow(**{**base, "cell_id": "fy", "period": "FY2025",    "period_kind": "fy_annual_duration", "period_end": "2025-12-27", "value": 4341.0}),
    ]
    cands = q4_candidates(rows)
    assert [c for c in cands if c.period == "Q4_FY2025"] == []


def test_q4_skipped_when_source_account_mismatch_across_inputs():
    """Codex round-3 F1: same uni_account populated by different XBRL
    concepts (INTC: FY=IncreaseDecreaseInEquitySecuritiesFvNi vs
    Q1/Q2/Q3=EquitySecuritiesFvNiGainLoss) must not be subtracted."""
    from _shared.sec_json_adapter import FactRow
    base = dict(
        ticker="INTC", statement="IS", version="GAAP",
        uni_account="gain_loss_on_equity_investments", unit="USD_millions",
        xbrl_tag="", weight=1,
        status="SOURCE_OF_TRUTH", ordinal=None, long_tail_metadata=None,
        provenance={},
    )
    rows = [
        FactRow(**{**base, "cell_id": "fy",  "period": "FY2025",   "period_kind": "fy_annual_duration", "period_end": "2025-12-27",
                   "source_account": "us-gaap:IncreaseDecreaseInEquitySecuritiesFvNi", "value": 100.0}),
        FactRow(**{**base, "cell_id": "q1",  "period": "Q1_FY2025","period_kind": "quarter_duration",   "period_end": "2025-03-29",
                   "source_account": "intc:EquitySecuritiesFvNiGainLoss",  "value": 50.0}),
        FactRow(**{**base, "cell_id": "q2",  "period": "Q2_FY2025","period_kind": "quarter_duration",   "period_end": "2025-06-28",
                   "source_account": "intc:EquitySecuritiesFvNiGainLoss",  "value": 60.0}),
        FactRow(**{**base, "cell_id": "q3",  "period": "Q3_FY2025","period_kind": "quarter_duration",   "period_end": "2025-09-27",
                   "source_account": "intc:EquitySecuritiesFvNiGainLoss",  "value": 70.0}),
    ]
    cands = q4_candidates(rows)
    assert [c for c in cands if c.period == "Q4_FY2025"] == []


def test_q4_skipped_for_canonical_pure_and_thousands_shares():
    """Codex round-2 F4: denylist missed canonical units `Pure` (pct/ratio
    after unit_canonicalize) and `thousands_shares`. Switched to allowlist
    {USD_thousands, USD_millions} — these canonical units must now be denied."""
    from _shared.sec_json_adapter import FactRow
    for unit in ("Pure", "thousands_shares", "USD"):
        base = dict(
            ticker="X", statement="IS", version="GAAP",
            uni_account="some_metric", source_account="x:SomeMetric",
            xbrl_tag="SomeMetric", unit=unit, weight=1,
            status="SOURCE_OF_TRUTH", ordinal=None, long_tail_metadata=None,
            provenance={},
        )
        rows = [
            FactRow(**{**base, "cell_id": f"9m_{unit}", "period": "9M_FY2024", "period_kind": "ytd_duration",       "period_end": "2024-09-30", "value": 30.0}),
            FactRow(**{**base, "cell_id": f"fy_{unit}", "period": "FY2024",    "period_kind": "fy_annual_duration", "period_end": "2024-12-31", "value": 40.0}),
        ]
        cands = q4_candidates(rows)
        assert [c for c in cands if c.period == "Q4_FY2024"] == [], f"unit={unit} should be denied by allowlist"


def test_q4_candidate_carries_source_concept_identity():
    """Codex round-2 F2: derived Q4 Candidate must carry source_account /
    xbrl_tag from FY input so Pass 3 calc-linkbase identity can match it."""
    from _shared.sec_json_adapter import FactRow
    base = dict(
        ticker="AAOI", statement="IS", version="GAAP",
        uni_account="revenue", source_account="us-gaap:Revenues",
        xbrl_tag="Revenues", unit="USD_thousands", weight=1,
        status="SOURCE_OF_TRUTH", ordinal=None, long_tail_metadata=None,
        provenance={},
    )
    rows = [
        FactRow(**{**base, "cell_id": "9m", "period": "9M_FY2024", "period_kind": "ytd_duration",       "period_end": "2024-09-30", "value": 148000.0}),
        FactRow(**{**base, "cell_id": "fy", "period": "FY2024",    "period_kind": "fy_annual_duration", "period_end": "2024-12-31", "value": 249000.0}),
    ]
    cands = q4_candidates(rows)
    q4 = next(c for c in cands if c.period == "Q4_FY2024")
    assert q4.source_account == "us-gaap:Revenues"
    assert q4.xbrl_tag == "Revenues"


def test_q4_skipped_for_eps_per_share():
    """Self-review F1-extension: EPS facts must NOT emit Q4 candidates.
    EPS is net_income / weighted_avg_shares; both numerator and denominator
    change quarter-by-quarter, so Q4 = FY - 9M produces nonsense values
    (e.g. AAOI Q4_FY2023 eps_diluted derive = -0.36 vs 8-K disclosed 0.04)."""
    from _shared.sec_json_adapter import FactRow
    base = dict(
        ticker="AAOI", statement="IS", version="GAAP",
        uni_account="eps_diluted", source_account="us-gaap:EarningsPerShareDiluted",
        xbrl_tag="EarningsPerShareDiluted", unit="USD_per_share", weight=1,
        status="SOURCE_OF_TRUTH", ordinal=None, long_tail_metadata=None,
        provenance={"source_filing": "10-K"},
    )
    rows = [
        FactRow(**{**base, "cell_id": "9m", "period": "9M_FY2024", "period_kind": "ytd_duration",       "period_end": "2024-09-30", "value": 0.08}),
        FactRow(**{**base, "cell_id": "fy", "period": "FY2024",    "period_kind": "fy_annual_duration", "period_end": "2024-12-31", "value": 0.06}),
    ]
    cands = q4_candidates(rows)
    assert [c for c in cands if c.period == "Q4_FY2024"] == []


def test_q4_skipped_for_pct_and_ratio_units():
    """Self-review F1-extension: margins/percentages/ratios must NOT emit Q4
    candidates. e.g. gross_margin_pct Q4 ≠ FY_margin - 9M_margin."""
    from _shared.sec_json_adapter import FactRow
    for unit in ("pct", "ratio"):
        base = dict(
            ticker="X", statement="IS", version="GAAP",
            uni_account="gross_margin_pct", source_account="custom:GrossMarginPct",
            xbrl_tag="GrossMarginPct", unit=unit, weight=1,
            status="SOURCE_OF_TRUTH", ordinal=None, long_tail_metadata=None,
            provenance={},
        )
        rows = [
            FactRow(**{**base, "cell_id": f"9m_{unit}", "period": "9M_FY2024", "period_kind": "ytd_duration",       "period_end": "2024-09-30", "value": 35.0}),
            FactRow(**{**base, "cell_id": f"fy_{unit}", "period": "FY2024",    "period_kind": "fy_annual_duration", "period_end": "2024-12-31", "value": 33.0}),
        ]
        cands = q4_candidates(rows)
        assert [c for c in cands if c.period == "Q4_FY2024"] == [], f"unit={unit} should be denied"


def test_q4_skipped_for_long_tail_bucket_uni_accounts():
    """Codex F2: *_long_tail bucket facts must NOT emit Q4 candidates.
    Long-tail aggregates multiple source_accounts into one uni_account; Q4 =
    FY - 9M would silently discard which source contributed and the
    sec_financial_metrics row can't preserve the bucket-member identity."""
    from _shared.sec_json_adapter import FactRow
    base = dict(
        ticker="AAOI", statement="IS", version="GAAP",
        uni_account="operating_expense_long_tail", source_account="us-gaap:GeneralAndAdministrativeExpense",
        xbrl_tag="GeneralAndAdministrativeExpense", unit="USD_thousands", weight=1,
        status="SOURCE_OF_TRUTH", ordinal=None,
        long_tail_metadata={"rolls_up_to": "selling_general_administrative"},
        provenance={"source_filing": "10-K"},
    )
    rows = [
        FactRow(**{**base, "cell_id": "9m", "period": "9M_FY2024", "period_kind": "ytd_duration",       "period_end": "2024-09-30", "value": 30000.0}),
        FactRow(**{**base, "cell_id": "fy", "period": "FY2024",    "period_kind": "fy_annual_duration", "period_end": "2024-12-31", "value": 44813.0}),
    ]
    cands = q4_candidates(rows)
    assert [c for c in cands if c.period == "Q4_FY2024"] == []


def test_q4_dates_inherit_from_fy_for_non_dec_fy_end():
    """Non-Dec FY-end (SNDK shape, June FY-end): Q4 period_end must follow
    FY's period_end (not hardcoded Dec 31), so CY mapping works on frontend."""
    from _shared.sec_json_adapter import FactRow
    base = dict(
        ticker="SNDK", statement="IS", version="GAAP",
        uni_account="revenue", source_account="us-gaap:Revenues",
        xbrl_tag="Revenues", unit="USD_millions", weight=1,
        status="SOURCE_OF_TRUTH", ordinal=None, long_tail_metadata=None,
        provenance={"source_filing": "10-K"},
    )
    rows = [
        FactRow(**{**base, "cell_id": "q3", "period": "Q3_FY2025", "period_kind": "quarter_duration",   "period_end": "2025-03-28", "value": 1695.0}),
        FactRow(**{**base, "cell_id": "9m", "period": "9M_FY2025", "period_kind": "ytd_duration",       "period_end": "2025-03-28", "value": 5454.0}),
        FactRow(**{**base, "cell_id": "fy", "period": "FY2025",    "period_kind": "fy_annual_duration", "period_end": "2025-06-27", "value": 7355.0}),
    ]
    cands = q4_candidates(rows)
    q4 = next(c for c in cands if c.period == "Q4_FY2025")
    assert q4.value == 1901.0
    assert q4.period_end == "2025-06-27"   # NOT 2025-12-31
    assert q4.period_start == "2025-03-29" # Q3.period_end + 1 day, NOT 2025-10-01


def test_q4_skipped_when_q4_already_direct(sample_gaap_revenue_facts):
    """If Q4 is already a direct fact, derive must NOT emit a candidate
    (facts always win — disclosed > derived)."""
    from _shared.sec_json_adapter import FactRow
    direct_q4 = FactRow(
        cell_id="q4_direct", ticker="AAOI", period="Q4_FY2024",
        period_end="2024-12-31", period_kind="quarter_duration",
        statement="IS", version="GAAP", uni_account="revenue",
        source_account="us-gaap:Revenues", xbrl_tag="Revenues",
        value=101050.0, weight=1, unit="USD_thousands",
        status="SOURCE_OF_TRUTH", ordinal=None, long_tail_metadata=None,
        provenance={},
    )
    facts = list(sample_gaap_revenue_facts) + [direct_q4]
    cands = q4_candidates(facts)
    assert [c for c in cands if c.period == "Q4_FY2024"] == []
