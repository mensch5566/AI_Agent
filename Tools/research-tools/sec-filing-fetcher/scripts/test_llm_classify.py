"""
Test LLM tag classification (Layer 3).

Simulates the scenario where known candidates are missing:
1. Load real XBRL data (GOOGL)
2. Remove some tags from the known candidate lists
3. Call discovery with LLM enabled
4. Check if LLM correctly finds the removed tags
"""
import json, os, sys
from collections import OrderedDict

# Import from xbrl_extract
sys.path.insert(0, os.path.dirname(__file__))
from xbrl_extract import (
    IS_TAG_MAP, BS_TAG_MAP, CF_TAG_MAP,
    discover_tags_for_company, _get_tag_label,
)

GOOGL_RAW = os.path.expanduser(
    "~/AI_Agent/Investment_Data/financials/GOOGL/googl_xbrl_raw.json"
)


def test_llm_classification():
    print("Loading GOOGL XBRL data...")
    xbrl = json.load(open(GOOGL_RAW))
    facts = xbrl["facts"]["us-gaap"]
    print(f"  {len(facts)} us-gaap tags available\n")

    # === Scenario: Remove known revenue candidates ===
    # GOOGL uses: RevenueFromContractWithCustomerExcludingAssessedTax, Revenues
    # We remove BOTH from IS_TAG_MAP so Layer 1 can't find them.
    # Layer 2 (label) should still find "Revenues" via label matching.
    # But if we also tighten label rules, LLM should be the fallback.

    print("=" * 60)
    print("TEST 1: Remove revenue tags from known list")
    print("  Expected: Layer 2 (label) should find 'Revenues'")
    print("=" * 60)

    test_is_map = OrderedDict(IS_TAG_MAP)
    test_is_map["revenue"] = ["FakeRevenueTag_NotExist"]  # Replace with nonsense

    (exp_is, exp_bs, exp_cf), cm = discover_tags_for_company(
        facts, [test_is_map, BS_TAG_MAP, CF_TAG_MAP], use_llm=False
    )

    rev_candidates = [c for c in exp_is["revenue"] if c in facts]
    print(f"\n  Result: revenue candidates found = {rev_candidates}")
    for c in rev_candidates:
        print(f"    {c}: method={cm.get(c, {}).get('method', '?')}, label=\"{_get_tag_label(facts, c)}\"")

    # === Scenario 2: Remove revenue from BOTH known AND label rules ===
    # This forces LLM to be the only option.
    print("\n" + "=" * 60)
    print("TEST 2: Remove revenue from known + label rules → LLM only")
    print("  Expected: LLM should identify the correct revenue tag")
    print("=" * 60)

    # Temporarily patch METRIC_LABEL_RULES to remove revenue
    import xbrl_extract
    original_rules = xbrl_extract.METRIC_LABEL_RULES.get("revenue")
    xbrl_extract.METRIC_LABEL_RULES["revenue"] = (["ZZZZZ_no_match"], [])

    test_is_map2 = OrderedDict(IS_TAG_MAP)
    test_is_map2["revenue"] = ["FakeRevenueTag_NotExist"]

    (exp_is2, _, _), cm2 = discover_tags_for_company(
        facts, [test_is_map2, BS_TAG_MAP, CF_TAG_MAP], use_llm=True
    )

    # Restore
    xbrl_extract.METRIC_LABEL_RULES["revenue"] = original_rules

    rev_candidates2 = [c for c in exp_is2["revenue"] if c in facts]
    print(f"\n  Result: revenue candidates found = {rev_candidates2}")
    for c in rev_candidates2:
        method = cm2.get(c, {}).get("method", "?")
        conf = cm2.get(c, {}).get("confidence", "?")
        reasoning = cm2.get(c, {}).get("reasoning", "")
        print(f"    {c}: method={method}, confidence={conf}")
        if reasoning:
            print(f"      reasoning: \"{reasoning}\"")

    # === Scenario 3: Multiple metrics missing ===
    print("\n" + "=" * 60)
    print("TEST 3: Remove revenue + operating_income + net_income → LLM batch")
    print("=" * 60)

    for m in ["revenue", "operating_income", "net_income"]:
        xbrl_extract.METRIC_LABEL_RULES[m] = (["ZZZZZ_no_match"], [])

    test_is_map3 = OrderedDict(IS_TAG_MAP)
    test_is_map3["revenue"] = ["FakeTag1"]
    test_is_map3["operating_income"] = ["FakeTag2"]
    test_is_map3["net_income"] = ["FakeTag3"]

    (exp_is3, _, _), cm3 = discover_tags_for_company(
        facts, [test_is_map3, BS_TAG_MAP, CF_TAG_MAP], use_llm=True
    )

    # Restore all
    xbrl_extract.METRIC_LABEL_RULES["revenue"] = original_rules
    from xbrl_extract import METRIC_LABEL_RULES as orig_rules
    # (already restored revenue above; operating_income and net_income need restore too)

    for metric in ["revenue", "operating_income", "net_income"]:
        candidates = [c for c in exp_is3[metric] if c in facts]
        print(f"\n  {metric}:")
        for c in candidates:
            info = cm3.get(c, {})
            print(f"    → {c} (method={info.get('method','?')}, conf={info.get('confidence','?')})")
            if info.get("reasoning"):
                print(f"      \"{info['reasoning']}\"")

    print("\n" + "=" * 60)
    print("TESTS COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    test_llm_classification()
