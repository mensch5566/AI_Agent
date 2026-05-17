from rules_identity import calc_rules_from_edges


def test_calc_rules_groups_by_parent_and_role():
    edges = [
        {"role_uri": "stmt-is", "parent_qname": "us-gaap:OperatingIncomeLoss",
         "child_qname": "us-gaap:GrossProfit",            "weight": 1, "edge_type": "calc"},
        {"role_uri": "stmt-is", "parent_qname": "us-gaap:OperatingIncomeLoss",
         "child_qname": "us-gaap:OperatingExpenses",       "weight": -1, "edge_type": "calc"},
        {"role_uri": "stmt-is", "parent_qname": "us-gaap:GrossProfit",
         "child_qname": "us-gaap:Revenues",                "weight": 1, "edge_type": "calc"},
        {"role_uri": "stmt-is", "parent_qname": "us-gaap:GrossProfit",
         "child_qname": "us-gaap:CostOfGoodsAndServicesSold", "weight": -1, "edge_type": "calc"},
    ]
    rules = calc_rules_from_edges(edges)
    keys = sorted(rules.keys())
    assert keys == [("stmt-is", "us-gaap:GrossProfit"), ("stmt-is", "us-gaap:OperatingIncomeLoss")]
    op = rules[("stmt-is", "us-gaap:OperatingIncomeLoss")]
    assert sorted(c["child_qname"] for c in op) == [
        "us-gaap:GrossProfit", "us-gaap:OperatingExpenses",
    ]


def test_calc_rules_filters_non_calc_edges():
    edges = [
        {"role_uri": "r", "parent_qname": "P", "child_qname": "C", "weight": 1, "edge_type": "presentation"},
    ]
    assert calc_rules_from_edges(edges) == {}


from rules_identity import apply_identity_rules
from _shared.sec_json_adapter import FactRow


def _f(**kw):
    base = dict(
        ticker="X", period="Q1_FY2024", period_end="2024-03-31",
        period_kind="quarter_duration", statement="IS", version="GAAP",
        source_account="t", xbrl_tag="t", unit="USD_thousands", weight=1,
        status="SOURCE_OF_TRUTH", ordinal=None, long_tail_metadata=None,
        provenance={}, cell_id="c",
    )
    base.update(kw)
    return FactRow(**base)


def test_calc_identity_fills_missing_parent():
    # We have GrossProfit children (Revenues + COGS) but no GrossProfit itself.
    # Calc rule should derive GrossProfit = Revenues + (-1 * COGS).
    facts = [
        _f(cell_id="r",  uni_account="revenue",            xbrl_tag="us-gaap:Revenues",                value=100.0),
        _f(cell_id="c",  uni_account="cost_of_goods_sold", xbrl_tag="us-gaap:CostOfGoodsAndServicesSold", value=60.0),
    ]
    calc_rules = {
        ("stmt-is", "us-gaap:GrossProfit"): [
            {"child_qname": "us-gaap:Revenues",                "weight": 1,  "source": None},
            {"child_qname": "us-gaap:CostOfGoodsAndServicesSold","weight": -1, "source": None},
        ],
    }
    # caller must tell us which uni_account name to assign to each qname
    qname_to_uni = {
        "us-gaap:Revenues":                  "revenue",
        "us-gaap:CostOfGoodsAndServicesSold":"cost_of_goods_sold",
        "us-gaap:GrossProfit":               "gross_profit",
    }
    cands = apply_identity_rules(facts, calc_rules, qname_to_uni)
    gp = [c for c in cands if c.uni_account == "gross_profit"]
    assert len(gp) == 1
    assert gp[0].value == 40.0    # 100 - 60
    assert gp[0].rule_id == "CALC_LINKBASE"
    assert gp[0].rule_priority == 3


def test_calc_identity_skips_when_child_missing():
    facts = [
        _f(cell_id="r", uni_account="revenue", xbrl_tag="us-gaap:Revenues", value=100.0),
        # COGS missing
    ]
    calc_rules = {
        ("stmt-is", "us-gaap:GrossProfit"): [
            {"child_qname": "us-gaap:Revenues",                "weight": 1,  "source": None},
            {"child_qname": "us-gaap:CostOfGoodsAndServicesSold","weight": -1, "source": None},
        ],
    }
    qname_to_uni = {
        "us-gaap:Revenues":                  "revenue",
        "us-gaap:CostOfGoodsAndServicesSold":"cost_of_goods_sold",
        "us-gaap:GrossProfit":               "gross_profit",
    }
    assert apply_identity_rules(facts, calc_rules, qname_to_uni) == []


def test_calc_identity_skips_when_parent_already_direct():
    """If gross_profit is already a direct fact, calc rule must NOT emit a
    Candidate even when both children (Revenues + COGS) are present —
    facts always win."""
    facts = [
        _f(cell_id="r",  uni_account="revenue",            xbrl_tag="us-gaap:Revenues",                value=100.0),
        _f(cell_id="c",  uni_account="cost_of_goods_sold", xbrl_tag="us-gaap:CostOfGoodsAndServicesSold", value=60.0),
        _f(cell_id="gp", uni_account="gross_profit",       xbrl_tag="us-gaap:GrossProfit",              value=42.0),
    ]
    calc_rules = {
        ("stmt-is", "us-gaap:GrossProfit"): [
            {"child_qname": "us-gaap:Revenues",                "weight": 1,  "source": None},
            {"child_qname": "us-gaap:CostOfGoodsAndServicesSold","weight": -1, "source": None},
        ],
    }
    qname_to_uni = {
        "us-gaap:Revenues":                  "revenue",
        "us-gaap:CostOfGoodsAndServicesSold":"cost_of_goods_sold",
        "us-gaap:GrossProfit":               "gross_profit",
    }
    cands = apply_identity_rules(facts, calc_rules, qname_to_uni)
    # gross_profit is direct — no candidate should be emitted
    assert [c for c in cands if c.uni_account == "gross_profit"] == []


from rules_identity import apply_static_allowlist


def test_static_allowlist_gaap_gross_profit_fallback():
    # No calc edges, Revenue + COGS present, parent missing → GP derived.
    facts = [
        _f(uni_account="revenue", value=100.0),
        _f(uni_account="cost_of_goods_sold", value=60.0, cell_id="cogs"),
    ]
    cands = apply_static_allowlist(facts, version="GAAP")
    gp = [c for c in cands if c.uni_account == "gross_profit"]
    assert len(gp) == 1
    assert gp[0].value == 40.0
    assert gp[0].rule_id == "STATIC_ALLOWLIST"
    assert gp[0].rule_priority == 4


def test_nongaap_allowlist_cogs_from_rev_minus_gp():
    facts = [
        _f(uni_account="revenue",      value=100.0, version="NON_GAAP"),
        _f(uni_account="gross_profit", value=40.0,  version="NON_GAAP", cell_id="gp"),
    ]
    cands = apply_static_allowlist(facts, version="NON_GAAP")
    cogs = [c for c in cands if c.uni_account == "cost_of_goods_sold"]
    assert len(cogs) == 1
    assert cogs[0].value == 60.0
    assert cogs[0].rule_id == "NG_ALLOWLIST"
    assert cogs[0].rule_priority == 5


def test_allowlist_skips_when_parent_present():
    facts = [
        _f(uni_account="revenue",            value=100.0),
        _f(uni_account="cost_of_goods_sold", value=60.0, cell_id="c"),
        _f(uni_account="gross_profit",       value=39.0, cell_id="g"),   # direct disclosed
    ]
    cands = apply_static_allowlist(facts, version="GAAP")
    # gross_profit is direct, so allowlist shouldn't propose another one.
    assert [c for c in cands if c.uni_account == "gross_profit"] == []


from rules_identity import build_qname_to_uni


def test_build_qname_to_uni_from_inline_metadata():
    inline = {
        "metadata": {},
        "income_statement": [
            {"uni_account": "revenue",      "source_account": "RevenueFromContractWithCustomerExcludingAssessedTax"},
            {"uni_account": "gross_profit", "source_account": "GrossProfit"},
        ],
        "balance_sheet": [
            {"uni_account": "total_assets", "source_account": "Assets"},
        ],
        "cash_flow_statement": [],
    }
    m = build_qname_to_uni(inline)
    assert m["us-gaap:GrossProfit"] == "gross_profit"
    assert m["us-gaap:Assets"] == "total_assets"
    assert m["us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax"] == "revenue"
