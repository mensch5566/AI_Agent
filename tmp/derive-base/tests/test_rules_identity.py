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
