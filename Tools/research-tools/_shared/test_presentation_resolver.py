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

from presentation_resolver import resolve_label_ordinal, AmbiguityError
import pytest

_LABELS = {"us-gaap:GrossProfit": [
    {"role":"http://www.xbrl.org/2003/role/terseLabel","text":"Gross margin"},
    {"role":"http://www.xbrl.org/2003/role/totalLabel","text":"Gross profit"}]}
_EDGES = [{"role_uri":"r/operations","child_qname":"us-gaap:GrossProfit","order":5.0,"preferred_label":"http://www.xbrl.org/2003/role/terseLabel"}]

def test_resolves_pdf_label_and_order():
    lbl, ordn = resolve_label_ordinal("GrossProfit", "r/operations", _EDGES, _LABELS)
    assert lbl == "Gross margin" and ordn == 5.0   # terseLabel = PDF wording

def test_ambiguous_local_name_fails_closed():
    edges = _EDGES + [{"role_uri":"r/operations","child_qname":"intc:GrossProfit","order":6.0,"preferred_label":"x"}]
    with pytest.raises(AmbiguityError):
        resolve_label_ordinal("GrossProfit", "r/operations", edges, _LABELS)
