import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from presentation_resolver import select_network

def test_is_network_selected_case_hyphen_insensitive():
    edges = [
        {"role_uri": "http://x/role/statement-consolidated-statements-of-operations", "child_qname": "us-gaap:Revenues", "order": 1.0, "period": "FY2025"},
        {"role_uri": "http://x/role/statement-note-income-taxes-reconciliation", "child_qname": "us-gaap:Foo", "order": 1.0, "period": "FY2025"},
    ]
    net = select_network(edges, "IS")
    assert net is not None and "operations" in net.lower()

def test_bs_returns_none_when_absent():   # AAOI case
    edges = [{"role_uri": "http://ao-inc.com/role/statement-consolidated-statements-of-operations", "child_qname": "us-gaap:Revenues", "order": 1.0, "period":"FY2025"}]
    assert select_network(edges, "BS") is None
