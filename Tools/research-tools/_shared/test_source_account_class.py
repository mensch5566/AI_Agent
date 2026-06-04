import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from source_account_class import classify_source_account as c

def test_tag_like():
    assert c("GrossProfit") == "tag_like"
    assert c("CostOfGoodsAndServicesSold") == "tag_like"

def test_null():
    assert c(None) == "null"
    assert c("") == "null"

def test_synthetic():
    assert c("SUM(D&A components)") == "synthetic"
    assert c("SUM(S&M+G&A)") == "synthetic"

def test_preserved_pdf_label():
    # human PDF text stored as source_account (LITE/SNDK real cases)
    assert c("Income before income taxes") == "preserved_pdf_label"
    assert c("Gain on business divestiture") == "preserved_pdf_label"
    assert c("Loss before income taxes") == "preserved_pdf_label"
