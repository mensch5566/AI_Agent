"""
xbrl_extract.py — Extract financials from SEC EDGAR XBRL API
Generic for any US-listed company.

Usage:
    python3 xbrl_extract.py --cik 0002023554 --ticker SNDK --fy-end-month 6 \
        --start Q1_FY2025 --out-dir ~/Investment_Data/financials/SNDK/

Output:
    {TICKER}_financials.json (tidy/long format + structured statements)

The script:
1. Downloads XBRL companyfacts from data.sec.gov
2. Maps CY frames to the company's fiscal quarters
3. Derives Q4 from full year minus 9-month YTD when needed
4. Computes financial ratios
5. Outputs structured JSON with long_format tidy data

Fiscal Calendar Notes (4-4-5 / 5-4-4 / 4-5-4):
    Many companies use a 52/53-week fiscal year instead of calendar months.
    Quarter-end dates ("period_end" in SEC filings) can deviate from calendar
    month-end by up to ±7 days. For example, a June FY-end company's Q1
    (Jul-Sep) might have period_end = Oct 3 instead of Sep 30.

    This script uses "nearest quarter-end matching" — the same approach SEC's
    own XBRL frames API uses ("dates that best align with a calendar quarter").
    For each period_end, we find which expected quarter-end date (last day of
    the quarter-end month) is closest in absolute days. This handles all fiscal
    calendar variants without heuristics.

    For annual/YTD periods used in Q4 derivation, FY is determined from the
    period's END date (which is always at or near the FY-end), not the start.

    Ref: https://en.wikipedia.org/wiki/4-4-5_Calendar
    Ref: https://www.sec.gov/search-filings/edgar-application-programming-interfaces
"""
import argparse, json, os, sys, shutil, subprocess, re
from datetime import date, datetime
from collections import OrderedDict

USER_AGENT = "Mozilla/5.0 (research tool) claude-code/1.0 contact@researchbot.local"

# ── Metric descriptions (for LLM inference context) ──
METRIC_DESCRIPTIONS = {
    "revenue": "Total top-line revenue from core business operations",
    "cost_of_goods_sold": "Direct costs of producing goods/services sold (COGS)",
    "gross_profit": "Revenue minus cost of goods sold",
    "research_and_development": "R&D expenses",
    "selling_general_administrative": "SG&A operating expenses",
    "amortization_of_intangible_assets": "Amortization of intangible assets (income statement)",
    "restructuring_charges": "One-time restructuring and impairment charges",
    "operating_income": "Income from core operations (EBIT proxy)",
    "interest_expense": "Interest paid on debt obligations",
    "interest_income": "Interest earned on investments/cash",
    "other_nonoperating_income_expense": "Non-operating income or expenses",
    "income_before_taxes": "Pre-tax income from continuing operations",
    "income_tax_expense": "Total income tax expense or benefit",
    "equity_method_investments": "Income from equity method investments",
    "net_income": "Bottom-line net income (loss)",
    "eps_basic": "Basic earnings per share",
    "eps_diluted": "Diluted earnings per share",
    "shares_basic": "Weighted average basic shares outstanding",
    "shares_diluted": "Weighted average diluted shares outstanding",
    "cash_and_cash_equivalents": "Cash and cash equivalents on balance sheet",
    "short_term_investments": "Short-term marketable securities",
    "accounts_receivable": "Net accounts receivable (current)",
    "inventories": "Net inventory on balance sheet",
    "total_current_assets": "Total current assets",
    "property_plant_equipment_net": "Net PP&E",
    "goodwill": "Goodwill from acquisitions (balance)",
    "total_assets": "Total assets",
    "accounts_payable": "Accounts payable (current)",
    "total_current_liabilities": "Total current liabilities",
    "long_term_debt": "Long-term debt (noncurrent portion)",
    "total_liabilities": "Total liabilities",
    "retained_earnings": "Accumulated retained earnings",
    "total_equity": "Total stockholders' equity",
    "total_liabilities_and_equity": "Total liabilities and stockholders' equity",
    "depreciation_and_amortization": "D&A in cash flow from operations",
    "share_based_compensation": "Stock-based compensation expense (non-cash)",
    "net_cash_from_operating": "Net cash from operating activities",
    "capital_expenditures": "Capital expenditures (purchases of PP&E)",
    "net_cash_from_investing": "Net cash from investing activities",
    "net_cash_from_financing": "Net cash from financing activities",
}


def fetch_xbrl(cik_padded):
    """Download XBRL companyfacts JSON from SEC EDGAR."""
    import subprocess
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik_padded}.json"
    result = subprocess.run(
        ["curl", "-s", "-A", USER_AGENT, url],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"ERROR: Failed to fetch XBRL data from {url}", file=sys.stderr)
        sys.exit(1)
    return json.loads(result.stdout)


def fetch_submissions(cik_padded):
    """Download submissions JSON to get filing details."""
    import subprocess
    url = f"https://data.sec.gov/submissions/CIK{cik_padded}.json"
    result = subprocess.run(
        ["curl", "-s", "-A", USER_AGENT, url],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        return None
    return json.loads(result.stdout)


# ── Fiscal year / period mapping ──

def fy_quarter_for_date(period_end_str, fy_end_month):
    """
    Given a period_end date and fiscal year end month,
    determine FY quarter (Q1-Q4) and fiscal year.

    Uses nearest-quarter-end matching to handle any fiscal calendar variant
    (4-4-5, 5-4-4, 4-5-4, etc.) where quarter-end dates can deviate from
    calendar month-ends by up to ~10 days.

    Example: fy_end_month=6 (June), period_end=2024-09-27 → Q1 FY2025
             fy_end_month=8 (Aug),  period_end=2024-11-28 → Q1 FY2025
             fy_end_month=12 (Dec), period_end=2025-03-31 → Q1 FY2025
             fy_end_month=6 (June), period_end=2025-10-03 → Q1 FY2026 (4-4-5)
             fy_end_month=6 (June), period_end=2026-01-02 → Q2 FY2026 (4-4-5)
    """
    import calendar as _cal
    d = datetime.strptime(period_end_str, "%Y-%m-%d")

    # Expected quarter-end months: Q1 = fy_end+3, Q2 = fy_end+6, Q3 = fy_end+9, Q4 = fy_end
    q_end_months = [((fy_end_month + q * 3 - 1) % 12) + 1 for q in range(1, 5)]

    best_q, best_fy, best_dist = None, None, 9999

    for year_offset in (-1, 0, 1):
        for q_idx, end_month in enumerate(q_end_months):
            candidate_year = d.year + year_offset
            last_day = _cal.monthrange(candidate_year, end_month)[1]
            candidate_date = datetime(candidate_year, end_month, last_day)
            dist = abs((d - candidate_date).days)
            if dist < best_dist:
                best_dist = dist
                best_q = q_idx + 1
                if end_month > fy_end_month:
                    best_fy = candidate_year + 1
                else:
                    best_fy = candidate_year

    return best_q, best_fy


def build_frame_mapping(fy_end_month, start_q, start_fy, end_q=None, end_fy=None):
    """
    Build mapping from CY XBRL frames to FY quarters.
    Returns dict: { "CY2024Q3": "Q1_FY2025", ... } for duration tags
    and { "CY2024Q2I": "FY2025_START", ... } for instant tags.
    """
    # This is complex because XBRL uses calendar year frames.
    # We rely on actual date matching instead of frame names.
    # Frame names are used as hints but dates are authoritative.
    return {}  # We use date-based matching instead


def get_val_by_frame(entries, frame):
    for e in entries:
        if e.get("frame") == frame:
            return e["val"]
    return None


def get_val_by_dates(entries, start, end):
    for e in entries:
        if e.get("start") == start and e.get("end") == end:
            return e["val"]
    return None


def get_instant_val(entries, end_date):
    for e in entries:
        if e.get("end") == end_date and "start" not in e:
            return e["val"]
    return None


def extract_duration_tag(facts, tag_name, quarterly_periods, fy_full_year_period=None,
                         ytd_9m_dates=None, unit="USD"):
    """
    Extract quarterly values for a duration tag (IS/CF).

    quarterly_periods: dict { "Q1_FY2025": {"start": "2024-06-29", "end": "2024-09-27"}, ... }
    fy_full_year_period: {"start": "...", "end": "..."} for full year (to derive Q4)
    ytd_9m_dates: {"start": "...", "end": "..."} for 9-month YTD
    """
    if tag_name not in facts:
        return {}
    entries = facts[tag_name]["units"].get(unit, [])
    result = {}

    # Direct match by date range
    for fq, dates in quarterly_periods.items():
        val = get_val_by_dates(entries, dates["start"], dates["end"])
        if val is not None:
            result[fq] = val

    # Also try frame-based matching
    for e in entries:
        frame = e.get("frame", "")
        if not frame or frame.endswith("I"):
            continue
        start = e.get("start", "")
        end = e.get("end", "")
        if not start or not end:
            continue
        for fq, dates in quarterly_periods.items():
            if fq not in result and dates["start"] == start and dates["end"] == end:
                result[fq] = e["val"]

    # Derive Q4 if we have full year and 9-month YTD
    q4_key = None
    for fq in quarterly_periods:
        if fq.startswith("Q4_"):
            q4_key = fq
            break

    if q4_key and q4_key not in result and fy_full_year_period and ytd_9m_dates:
        fy_val = get_val_by_dates(entries, fy_full_year_period["start"], fy_full_year_period["end"])
        ytd_val = get_val_by_dates(entries, ytd_9m_dates["start"], ytd_9m_dates["end"])
        if fy_val is not None and ytd_val is not None:
            result[q4_key] = fy_val - ytd_val
        elif fy_val is not None:
            # Fallback: sum Q1+Q2+Q3
            q1k = q4_key.replace("Q4_", "Q1_")
            q2k = q4_key.replace("Q4_", "Q2_")
            q3k = q4_key.replace("Q4_", "Q3_")
            if all(k in result for k in [q1k, q2k, q3k]):
                result[q4_key] = fy_val - sum(result[k] for k in [q1k, q2k, q3k])

    return result


def extract_instant_tag(facts, tag_name, bs_date_map, unit="USD"):
    """
    Extract values for an instant (balance sheet) tag.
    bs_date_map: { "Q2_FY2025": "2024-12-27", ... }
    """
    if tag_name not in facts:
        return {}
    entries = facts[tag_name]["units"].get(unit, [])
    result = {}
    for fq, end_date in bs_date_map.items():
        # Try frame match first
        for e in entries:
            if e.get("end") == end_date and "start" not in e:
                result[fq] = e["val"]
                break
    return result


def to_millions(d, decimals=1):
    return {k: round(v / 1_000_000, decimals) if v is not None else None for k, v in d.items()}


def compute_pct(num_dict, den_dict):
    result = {}
    for k in set(num_dict) | set(den_dict):
        n = num_dict.get(k)
        d = den_dict.get(k)
        if n is not None and d is not None and d != 0:
            result[k] = round(n / d, 4)
    return result


# ── Multi-tag extraction (auto-aligns when companies change XBRL tags) ──

def extract_duration_multi_tag(facts, candidates, quarterly_periods, fy_end_month,
                                annuals_by_fy, ytd_9m_by_fy, ytd_6m_by_fy,
                                unit="USD", derive_q4=True):
    """
    Try ALL candidate XBRL tags for a metric, merge results.
    Priority: first candidate that has data for a period wins.
    Returns: (values_dict, tag_by_period_dict)
    """
    vals = {}
    tag_by_period = {}

    for tag in candidates:
        if tag not in facts:
            continue
        # Direct quarterly + YTD derivation for Q2/Q3
        tag_vals = extract_duration_tag_with_ytd(
            facts, tag, quarterly_periods, fy_end_month,
            ytd_6m_by_fy, ytd_9m_by_fy, unit=unit
        )
        # Also basic extraction
        basic = extract_duration_tag(facts, tag, quarterly_periods, unit=unit)
        for k, v in basic.items():
            if k not in tag_vals:
                tag_vals[k] = v

        # Derive Q4 from annual - 9M YTD for each FY
        if derive_q4:
            for fy_yr, annual in annuals_by_fy.items():
                q4k = f"Q4_FY{fy_yr}"
                if q4k not in tag_vals and q4k in quarterly_periods:
                    fy_dates = {"start": annual["start"], "end": annual["end"]}
                    ytd = ytd_9m_by_fy.get(fy_yr)
                    ytd_dates = {"start": ytd["start"], "end": ytd["end"]} if ytd else None
                    q4_vals = extract_duration_tag(
                        facts, tag, {q4k: quarterly_periods[q4k]},
                        fy_full_year_period=fy_dates,
                        ytd_9m_dates=ytd_dates,
                        unit=unit
                    )
                    tag_vals.update(q4_vals)

        # Merge: only fill periods not yet covered (priority order)
        for p, v in tag_vals.items():
            if p not in vals:
                vals[p] = v
                tag_by_period[p] = tag

    return vals, tag_by_period


def extract_instant_multi_tag(facts, candidates, bs_date_map, unit="USD"):
    """Try ALL candidate tags for a BS metric, merge results."""
    vals = {}
    tag_by_period = {}
    for tag in candidates:
        if tag not in facts:
            continue
        tag_vals = extract_instant_tag(facts, tag, bs_date_map, unit=unit)
        for p, v in tag_vals.items():
            if p not in vals:
                vals[p] = v
                tag_by_period[p] = tag
    return vals, tag_by_period


# ── Tag discovery ──

# Common XBRL tags for the 3 statements, in priority order (first match wins)
IS_TAG_MAP = OrderedDict([
    ("revenue", ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueNet"]),
    ("cost_of_goods_sold", ["CostOfGoodsAndServicesSold", "CostOfRevenue", "CostOfGoodsSold", "CostOfGoodsAndServiceExcludingDepreciationDepletionAndAmortization"]),
    ("gross_profit", ["GrossProfit"]),
    ("research_and_development", ["ResearchAndDevelopmentExpense"]),
    ("selling_general_administrative", ["SellingGeneralAndAdministrativeExpense"]),
    ("amortization_of_intangible_assets", ["AmortizationOfIntangibleAssets"]),
    ("restructuring_charges", ["RestructuringCharges", "RestructuringSettlementAndImpairmentProvisions"]),
    ("operating_income", ["OperatingIncomeLoss"]),
    ("interest_expense", ["InterestExpense", "InterestExpenseNonoperating"]),
    ("interest_income", ["InvestmentIncomeInterest", "InterestIncomeOther", "InterestAndDividendIncomeOperating"]),
    ("other_nonoperating_income_expense", ["OtherNonoperatingIncomeExpense", "NonoperatingIncomeExpense"]),
    ("income_before_taxes", ["IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest", "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments"]),
    ("income_tax_expense", ["IncomeTaxExpenseBenefit"]),
    ("equity_method_investments", ["IncomeLossFromEquityMethodInvestments"]),
    ("net_income", ["NetIncomeLoss"]),
    ("eps_basic", ["EarningsPerShareBasic"]),
    ("eps_diluted", ["EarningsPerShareDiluted"]),
    ("shares_basic", ["WeightedAverageNumberOfSharesOutstandingBasic"]),
    ("shares_diluted", ["WeightedAverageNumberOfDilutedSharesOutstanding"]),
])

BS_TAG_MAP = OrderedDict([
    ("cash_and_cash_equivalents", ["CashAndCashEquivalentsAtCarryingValue"]),
    ("short_term_investments", ["ShortTermInvestments", "AvailableForSaleSecuritiesDebtSecuritiesCurrent", "MarketableSecuritiesCurrent"]),
    ("accounts_receivable", ["AccountsReceivableNetCurrent"]),
    ("inventories", ["InventoryNet"]),
    ("other_current_assets", ["OtherAssetsCurrent", "PrepaidExpenseAndOtherAssetsCurrent"]),
    ("total_current_assets", ["AssetsCurrent"]),
    ("property_plant_equipment_net", ["PropertyPlantAndEquipmentNet"]),
    ("operating_lease_rou_asset", ["OperatingLeaseRightOfUseAsset"]),
    ("goodwill", ["Goodwill"]),
    ("intangible_assets", ["IntangibleAssetsNetExcludingGoodwill"]),
    ("deferred_tax_assets", ["DeferredIncomeTaxAssetsNet"]),
    ("other_noncurrent_assets", ["OtherAssetsNoncurrent"]),
    ("total_assets", ["Assets"]),
    ("accounts_payable", ["AccountsPayableCurrent"]),
    ("accrued_liabilities", ["AccruedLiabilitiesCurrent"]),
    ("current_debt", ["LongTermDebtCurrent", "ShortTermBorrowings"]),
    ("other_current_liabilities", ["OtherLiabilitiesCurrent"]),
    ("total_current_liabilities", ["LiabilitiesCurrent"]),
    ("long_term_debt", ["LongTermDebtNoncurrent", "LongTermDebt"]),
    ("operating_lease_noncurrent", ["OperatingLeaseLiabilityNoncurrent"]),
    ("other_noncurrent_liabilities", ["OtherLiabilitiesNoncurrent"]),
    ("total_liabilities", ["Liabilities"]),
    ("common_stock", ["CommonStockValue"]),
    ("additional_paid_in_capital", ["AdditionalPaidInCapital", "AdditionalPaidInCapitalCommonStock"]),
    ("retained_earnings", ["RetainedEarningsAccumulatedDeficit"]),
    ("treasury_stock", ["TreasuryStockValue"]),
    ("aoci", ["AccumulatedOtherComprehensiveIncomeLossNetOfTax"]),
    ("total_equity", ["StockholdersEquity"]),
    ("total_liabilities_and_equity", ["LiabilitiesAndStockholdersEquity"]),
])

CF_TAG_MAP = OrderedDict([
    ("depreciation_and_amortization", ["DepreciationAndAmortization", "DepreciationDepletionAndAmortization"]),
    ("share_based_compensation", ["ShareBasedCompensation", "AllocatedShareBasedCompensationExpense"]),
    ("deferred_income_tax", ["DeferredIncomeTaxExpenseBenefit"]),
    ("goodwill_impairment", ["GoodwillImpairmentLoss"]),
    ("other_asset_impairment", ["OtherAssetImpairmentCharges", "AssetImpairmentCharges"]),
    ("change_in_receivables", ["IncreaseDecreaseInAccountsReceivable"]),
    ("change_in_inventories", ["IncreaseDecreaseInInventories"]),
    ("change_in_accounts_payable", ["IncreaseDecreaseInAccountsPayableTrade", "IncreaseDecreaseInAccountsPayable"]),
    ("change_in_accrued_liabilities", ["IncreaseDecreaseInAccruedLiabilities"]),
    ("net_cash_from_operating", ["NetCashProvidedByUsedInOperatingActivities"]),
    ("capital_expenditures", ["PaymentsToAcquirePropertyPlantAndEquipment"]),
    ("net_cash_from_investing", ["NetCashProvidedByUsedInInvestingActivities"]),
    ("proceeds_from_debt", ["ProceedsFromIssuanceOfDebt", "ProceedsFromIssuanceOfLongTermDebt"]),
    ("repayments_of_debt", ["RepaymentsOfDebt", "RepaymentsOfLongTermDebt"]),
    ("net_cash_from_financing", ["NetCashProvidedByUsedInFinancingActivities"]),
    ("fx_effect", ["EffectOfExchangeRateOnCashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"]),
    ("net_change_in_cash", ["CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect"]),
])


def find_first_tag(facts, candidates, min_year=None):
    """Return the first tag name that exists in facts with recent data.
    If min_year is set, prefer tags that have entries ending in or after that year.
    Falls back to first existing tag if none have recent data."""
    fallback = None
    for tag in candidates:
        if tag not in facts:
            continue
        if fallback is None:
            fallback = tag
        if min_year is None:
            return tag
        # Check if tag has recent data
        for unit_entries in facts[tag].get("units", {}).values():
            for e in unit_entries:
                end = e.get("end", "")
                if end and end[:4] >= str(min_year):
                    return tag
    return fallback


def resolve_tag_map(facts, tag_map, min_year=None):
    """Resolve a tag_map to actual tag names found in XBRL data.
    If min_year is set, prefer tags with data from that year onward."""
    resolved = {}
    for metric, candidates in tag_map.items():
        tag = find_first_tag(facts, candidates, min_year=min_year)
        if tag:
            resolved[metric] = tag
    return resolved


# ── Label-based auto-discovery ──
# Each metric has: (positive_keywords, negative_keywords)
# Matched against the tag's label field (case-insensitive)
# Positive: ANY keyword must appear; Negative: NONE must appear

METRIC_LABEL_RULES = {
    # Income Statement (duration, USD)
    "revenue": (
        ["revenue from contract with customer", "revenues", "net revenue", "total revenue", "net sales"],
        ["deferred", "cost", "remaining performance", "recognized", "pro forma", "related party"],
    ),
    "cost_of_goods_sold": (
        ["cost of goods and services", "cost of revenue", "cost of goods sold", "cost of sales"],
        ["depreciation"],
    ),
    "gross_profit": (["gross profit"], []),
    "research_and_development": (["research and development expense"], []),
    "selling_general_administrative": (
        ["selling, general and administrative"],
        [],
    ),
    "restructuring_charges": (
        ["restructuring charges", "restructuring and related cost, incurred cost"],
        ["reversal", "reserve", "payment", "expected", "number of positions", "remaining"],
    ),
    "operating_income": (["operating income (loss)", "operating income"], ["non"]),
    "interest_expense": (
        ["interest expense"],
        ["income", "net of interest", "finance lease", "capitalized"],
    ),
    "interest_income": (
        ["interest income", "investment income, interest"],
        ["expense", "dividend"],
    ),
    "other_nonoperating_income_expense": (
        ["nonoperating income (expense)", "other income (expense)"],
        [],
    ),
    "income_before_taxes": (
        ["income (loss) from continuing operations before income tax"],
        ["domestic", "foreign"],
    ),
    "income_tax_expense": (
        ["income tax expense (benefit)"],
        ["deferred", "current", "rate", "tax cuts", "measurement"],
    ),
    "equity_method_investments": (
        ["income (loss) from equity method investments"],
        [],
    ),
    "net_income": (
        ["net income (loss)"],
        ["comprehensive", "per share", "noncontrolling", "parent", "attributable to", "pro forma"],
    ),
    "eps_basic": (["earnings per share, basic"], []),
    "eps_diluted": (["earnings per share, diluted"], ["pro forma"]),
    "shares_basic": (
        ["weighted average number of shares outstanding, basic",
         "weighted average number of common shares outstanding, basic"],
        [],
    ),
    "shares_diluted": (
        ["weighted average number of diluted shares outstanding",
         "weighted average number of shares outstanding, diluted"],
        [],
    ),
    # Balance Sheet (instant, USD)
    "cash_and_cash_equivalents": (
        ["cash and cash equivalents, at carrying value", "cash and cash equivalents, end of period"],
        ["restricted", "increase", "decrease", "period", "effect", "fair value", "measured"],
    ),
    "short_term_investments": (
        ["short-term investments", "marketable securities, current"],
        ["unrealized", "amortized", "proceeds", "maturit", "fair value", "comprehensive", "realized"],
    ),
    "accounts_receivable": (
        ["accounts receivable", "trade receivable"],
        ["allowance", "increase", "decrease", "noncurrent"],
    ),
    "inventories": (
        ["inventory, net", "inventories"],
        ["increase", "decrease"],
    ),
    "other_current_assets": (
        ["other assets, current", "prepaid expense and other assets, current"],
        [],
    ),
    "total_current_assets": (["assets, current"], ["non", "total"]),
    "property_plant_equipment_net": (
        ["property, plant and equipment, net"],
        [],
    ),
    "operating_lease_rou_asset": (["operating lease, right-of-use asset"], []),
    "goodwill": (["goodwill"], ["impairment", "acquired", "written", "other", "increase", "decrease", "change"]),
    "intangible_assets": (["intangible assets, net"], ["goodwill"]),
    "deferred_tax_assets": (["deferred income tax assets, net"], []),
    "other_noncurrent_assets": (["other assets, noncurrent"], []),
    "total_assets": (
        ["assets"],
        ["current", "deferred", "lease", "intangible", "other", "tax", "fair value",
         "geographic", "long-lived", "fixed", "noncash", "identifiable", "measured"],
    ),
    "accounts_payable": (
        ["accounts payable"],
        ["increase", "decrease", "noncurrent"],
    ),
    "accrued_liabilities": (
        ["accrued liabilities, current"],
        ["increase", "decrease"],
    ),
    "current_debt": (
        ["long-term debt, current maturities", "short-term borrowings"],
        [],
    ),
    "other_current_liabilities": (["other liabilities, current"], []),
    "total_current_liabilities": (["liabilities, current"], ["non", "employee"]),
    "long_term_debt": (
        ["long-term debt, excluding current maturities", "long-term debt, noncurrent"],
        ["current maturit", "fair value", "maturity, year", "maturity, after", "maturity, remainder", "gross"],
    ),
    "operating_lease_noncurrent": (
        ["operating lease, liability, noncurrent"],
        [],
    ),
    "other_noncurrent_liabilities": (["other liabilities, noncurrent"], []),
    "total_liabilities": (
        ["liabilities"],
        ["current", "and stockholders", "lease", "other", "deferred",
         "identifiable", "recognized", "business combination"],
    ),
    "common_stock": (["common stock, value"], []),
    "additional_paid_in_capital": (["additional paid-in capital"], []),
    "retained_earnings": (["retained earnings"], []),
    "treasury_stock": (["treasury stock, value"], []),
    "aoci": (
        ["accumulated other comprehensive income (loss), net of tax"],
        ["cash flow", "foreign currency", "pension", "unrealized", "available-for-sale"],
    ),
    "total_equity": (
        ["stockholders' equity"],
        ["and liabilities", "per share", "note"],
    ),
    "total_liabilities_and_equity": (["liabilities and stockholders' equity"], []),
    # Cash Flow (duration, USD)
    "depreciation_and_amortization": (
        ["depreciation, depletion and amortization", "depreciation and amortization"],
        ["accumulated"],
    ),
    "share_based_compensation": (
        ["share-based compensation expense", "share-based payment arrangement, noncash expense",
         "allocated share-based compensation expense"],
        ["tax", "option", "grant", "exercise", "vest", "forfeit", "authorized",
         "outstanding", "rate", "price", "period", "percent", "deferred", "withholding", "capitalized"],
    ),
    "deferred_income_tax": (["deferred income tax expense (benefit)"], []),
    "goodwill_impairment": (["goodwill, impairment loss"], []),
    "other_asset_impairment": (["asset impairment charges", "other asset impairment"], []),
    "change_in_receivables": (
        ["increase (decrease) in accounts receivable"],
        [],
    ),
    "change_in_inventories": (["increase (decrease) in inventories"], []),
    "change_in_accounts_payable": (
        ["increase (decrease) in accounts payable"],
        [],
    ),
    "change_in_accrued_liabilities": (
        ["increase (decrease) in accrued liabilities"],
        [],
    ),
    "net_cash_from_operating": (
        ["net cash provided by (used in) operating activities"],
        ["continuing operations", "discontinued"],
    ),
    "capital_expenditures": (
        ["payments to acquire property, plant, and equipment"],
        [],
    ),
    "net_cash_from_investing": (
        ["net cash provided by (used in) investing activities"],
        ["continuing operations", "discontinued"],
    ),
    "proceeds_from_debt": (
        ["proceeds from issuance of debt", "proceeds from issuance of long-term debt"],
        [],
    ),
    "repayments_of_debt": (
        ["repayments of debt", "repayments of long-term debt"],
        ["maturing in more than", "maturing within"],
    ),
    "net_cash_from_financing": (
        ["net cash provided by (used in) financing activities"],
        ["continuing operations", "discontinued"],
    ),
    "fx_effect": (
        ["effect of exchange rate on cash"],
        ["disposal", "discontinued"],
    ),
    "net_change_in_cash": (
        ["period increase (decrease), including exchange rate effect"],
        ["disposal", "discontinued"],
    ),
}


def _label_matches(label_lower, positive_kws, negative_kws):
    """Check if a label matches positive keywords and doesn't match negative ones."""
    if not any(kw in label_lower for kw in positive_kws):
        return False
    if any(neg in label_lower for neg in negative_kws):
        return False
    return True


def _get_tag_label(facts, tag):
    """Get the human-readable label for an XBRL tag."""
    info = facts.get(tag, {})
    return (info.get("label") or tag)


def _tag_data_type(facts, tag):
    """Determine if a tag is 'duration' (IS/CF) or 'instant' (BS)."""
    info = facts.get(tag, {})
    for unit_entries in info.get("units", {}).values():
        for e in unit_entries[:3]:
            if "start" in e:
                return "duration"
            return "instant"
    return "unknown"


# ── LLM inference (Layer 3) ──

def llm_classify_unmatched(facts, metrics_missing, all_tag_maps, verbose=True):
    """
    Use Claude API to classify XBRL tags that Layer 1+2 couldn't match.

    Args:
        facts: XBRL us-gaap facts dict
        metrics_missing: list of metric names that have no candidates
        all_tag_maps: list of TAG_MAPs to know which tags are already claimed

    Returns:
        dict { metric: [{"tag": ..., "confidence": ..., "reasoning": ...}] }
    """
    if not metrics_missing:
        return {}

    # Build set of tags already claimed by known/label-discovered candidates
    claimed_tags = set()
    for tag_map in all_tag_maps:
        for candidates in tag_map.values():
            for c in candidates:
                if c in facts:
                    claimed_tags.add(c)

    # Build list of unclaimed tags with useful info
    unclaimed = []
    for tag, info in facts.items():
        if tag in claimed_tags:
            continue
        label = (info.get("label") or "")
        data_type = _tag_data_type(facts, tag)
        units = list(info.get("units", {}).keys())
        unit_str = units[0] if units else "?"
        # Count data points
        n = sum(len(entries) for entries in info.get("units", {}).values())
        if n < 2:
            continue  # Skip tags with almost no data
        unclaimed.append({"tag": tag, "label": label, "type": data_type, "unit": unit_str, "n": n})

    if not unclaimed:
        return {}

    # Pre-filter: prioritize tags likely relevant to missing metrics
    # Build keyword set from metric names and descriptions
    metric_keywords = set()
    for m in metrics_missing:
        metric_keywords.update(m.replace("_", " ").lower().split())
        desc = METRIC_DESCRIPTIONS.get(m, "")
        metric_keywords.update(w.lower() for w in desc.split() if len(w) > 3)

    # Score each tag: higher if label/name contains metric keywords
    def _relevance_score(t):
        text = (t["tag"] + " " + t["label"]).lower()
        keyword_hits = sum(1 for kw in metric_keywords if kw in text)
        return (keyword_hits, t["n"])  # keyword hits first, then data count

    unclaimed.sort(key=_relevance_score, reverse=True)

    # Build prompt
    metrics_block = "\n".join(
        f"- {m}: {METRIC_DESCRIPTIONS.get(m, m)}"
        for m in metrics_missing
    )
    tags_block = "\n".join(
        f"  {i+1}. {t['tag']}: \"{t['label']}\" (type={t['type']}, unit={t['unit']}, entries={t['n']})"
        for i, t in enumerate(unclaimed[:200])  # Cap at 200 to avoid token limits
    )

    prompt = f"""You are an XBRL/accounting classification expert.

I need to find XBRL tags for these financial metrics (currently unmatched):
{metrics_block}

Below are the company's available XBRL tags that haven't been matched yet:
{tags_block}

For each metric listed above, identify the BEST matching tag from the list.
- Only match if you are genuinely confident the tag represents that metric.
- Do NOT match sub-items, breakdowns, or detail tags — only match the main aggregate figure.
- If no good match exists for a metric, skip it.

Return ONLY a JSON array (no markdown fences):
[
  {{"metric": "metric_name", "tag": "XBRLTagName", "confidence": 0.0-1.0, "reasoning": "brief explanation"}}
]
Return [] if no matches found."""

    # Call Claude API
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        if verbose:
            print("  [LLM] No ANTHROPIC_API_KEY — skipping LLM inference")
        return {}

    if verbose:
        print(f"  [LLM] Calling Claude API for {len(metrics_missing)} unmatched metrics...")

    try:
        result = subprocess.run(
            [sys.executable, "-c", f"""
import json
try:
    from anthropic import Anthropic
except ImportError:
    import subprocess, sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "anthropic", "-q"])
    from anthropic import Anthropic

client = Anthropic()
response = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=2000,
    messages=[{{"role": "user", "content": {json.dumps(prompt)}}}],
)
print(response.content[0].text)
"""],
            capture_output=True, text=True, timeout=30,
            env={**os.environ, "ANTHROPIC_API_KEY": api_key}
        )
        if result.returncode != 0:
            if verbose:
                print(f"  [LLM] API call failed: {result.stderr[:200]}")
            return {}

        # Parse response
        raw = result.stdout.strip()
        # Strip markdown fences if present
        raw = re.sub(r'^```json\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)
        matches = json.loads(raw)

    except (json.JSONDecodeError, subprocess.TimeoutExpired, Exception) as e:
        if verbose:
            print(f"  [LLM] Error: {e}")
        return {}

    # Build result dict
    llm_results = {}
    for match in matches:
        metric = match.get("metric")
        tag = match.get("tag")
        confidence = match.get("confidence", 0)
        reasoning = match.get("reasoning", "")

        if not metric or not tag or tag not in facts:
            continue
        if confidence < 0.7:
            if verbose:
                print(f"  [LLM] Skipping {metric} → {tag} (confidence {confidence:.2f} < 0.7)")
            continue

        if verbose:
            print(f"  [LLM] {metric} → {tag} (confidence {confidence:.2f}): {reasoning}")

        llm_results[metric] = [{"tag": tag, "confidence": confidence, "reasoning": reasoning}]

    return llm_results


def discover_tags_for_company(facts, tag_maps, use_llm=False, verbose=True):
    """
    Scan ALL XBRL tags and build an expanded candidate list per metric.

    Three layers:
    1. Known candidates (from TAG_MAPs) — method: "known"
    2. Label keyword matching (METRIC_LABEL_RULES) — method: "label_discovery"
    3. LLM inference (Claude API) — method: "llm_inference"

    Returns:
        expanded_maps: list of expanded OrderedDict {metric: [candidates]}
        classification_methods: dict {tag_name: {"method": ..., "confidence": ..., ...}}
    """
    # Build label index: tag → label (original case + lowercase)
    label_index = {}       # tag → lowercase label
    label_original = {}    # tag → original label
    for tag, info in facts.items():
        label = (info.get("label") or "")
        label_index[tag] = label.lower()
        label_original[tag] = label

    # Build set of all tags already in known candidate lists
    known_tags = set()
    for tag_map in tag_maps:
        for candidates in tag_map.values():
            known_tags.update(candidates)

    # Track classification method for each tag
    # tag → {"method": "known"|"label_discovery"|"llm_inference", "metric": ..., ...}
    classification_methods = {}

    # Mark known candidates
    for tag_map in tag_maps:
        for metric, candidates in tag_map.items():
            for c in candidates:
                if c in facts:
                    classification_methods[c] = {
                        "method": "known",
                        "metric": metric,
                        "label": label_original.get(c, c),
                        "confidence": 1.0,
                    }

    # Layer 2: Label discovery — find tags not in known lists
    auto_discovered = {}  # metric → [tag_names]
    for metric, (pos_kws, neg_kws) in METRIC_LABEL_RULES.items():
        matches = []
        for tag, label_lower in label_index.items():
            if tag in known_tags:
                continue
            if _label_matches(label_lower, pos_kws, neg_kws):
                matches.append(tag)
                classification_methods[tag] = {
                    "method": "label_discovery",
                    "metric": metric,
                    "label": label_original.get(tag, tag),
                    "confidence": 0.95,
                }
        if matches:
            auto_discovered[metric] = matches

    if verbose and auto_discovered:
        print("\n  Auto-discovered tags (label matching):")
        for metric, tags in auto_discovered.items():
            labels = [f"{t} (\"{label_original.get(t, '')}\")" for t in tags]
            print(f"    {metric}: {labels}")

    # Build expanded TAG_MAPs (Layer 1 + Layer 2)
    expanded_maps = []
    for tag_map in tag_maps:
        expanded = OrderedDict()
        for metric, candidates in tag_map.items():
            extra = auto_discovered.get(metric, [])
            expanded[metric] = candidates + extra
        expanded_maps.append(expanded)

    # Layer 3: LLM inference — only for metrics with NO data after L1+L2
    if use_llm:
        # Find metrics where none of the expanded candidates exist in facts
        all_metrics_in_maps = set()
        metrics_missing = []
        for exp_map in expanded_maps:
            for metric, candidates in exp_map.items():
                all_metrics_in_maps.add(metric)
                if not any(c in facts for c in candidates):
                    metrics_missing.append(metric)

        if metrics_missing:
            llm_results = llm_classify_unmatched(facts, metrics_missing, expanded_maps, verbose)
            for metric, matches in llm_results.items():
                for match in matches:
                    tag = match["tag"]
                    classification_methods[tag] = {
                        "method": "llm_inference",
                        "metric": metric,
                        "label": label_original.get(tag, tag),
                        "confidence": match["confidence"],
                        "reasoning": match["reasoning"],
                    }
                    # Add to expanded maps
                    for exp_map in expanded_maps:
                        if metric in exp_map:
                            exp_map[metric] = exp_map[metric] + [tag]
        elif verbose:
            print("  [LLM] All metrics have candidates — no LLM inference needed")

    return expanded_maps, classification_methods


# ── Period detection from filings ──

def detect_periods_from_submissions(submissions, fy_end_month, start_q, start_fy):
    """
    Analyze 10-Q/10-K filings to determine quarterly periods and date ranges.
    Returns: quarterly_periods, bs_date_map, fy_full_year_period, ytd_9m_dates, filing_info
    """
    recent = submissions.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    filing_dates = recent.get("filingDate", [])
    report_dates = recent.get("reportDate", [])
    accessions = recent.get("accessionNumber", [])
    primary_docs = recent.get("primaryDocument", [])

    filings = []
    for i in range(len(forms)):
        if forms[i] in ("10-Q", "10-K", "10-Q/A"):
            filings.append({
                "form": forms[i],
                "filing_date": filing_dates[i],
                "period_end": report_dates[i],
                "accession": accessions[i],
                "primary_doc": primary_docs[i],
            })

    # Sort by period_end
    filings.sort(key=lambda x: x["period_end"])

    # Determine quarters
    quarterly_periods = {}
    bs_date_map = {}
    filing_info = {}
    prev_end = None

    for f in filings:
        q, fy = fy_quarter_for_date(f["period_end"], fy_end_month)
        fq = f"Q{q}_FY{fy}"

        # Skip if before start
        if fy < start_fy or (fy == start_fy and q < start_q):
            prev_end = f["period_end"]
            continue

        # Skip 10-Q/A (amended) if we already have the period
        if f["form"] == "10-Q/A" and fq in filing_info:
            continue

        bs_date_map[fq] = f["period_end"]

        # For filing info, prefer 10-Q/10-K over amendments
        if fq not in filing_info or f["form"] != "10-Q/A":
            filing_info[fq] = {
                "form": "10-K" if f["form"] == "10-K" else "10-Q",
                "period_end": f["period_end"],
                "filing_date": f["filing_date"],
                "accession_number": f["accession"],
                "primary_doc": f["primary_doc"],
            }

        prev_end = f["period_end"]

    # Build quarterly date ranges (start = day after previous period end)
    # We need to figure out the start dates from the XBRL entries
    # For now, we'll rely on XBRL date matching

    return quarterly_periods, bs_date_map, filing_info


def build_periods_from_xbrl(facts, tag_name, fy_end_month, start_q, start_fy, unit="USD"):
    """
    Analyze a well-populated XBRL tag (like Revenue) to discover
    all quarterly periods with their exact date ranges.
    Returns: quarterly, annuals_by_fy, ytd_9m_by_fy, ytd_6m_by_fy
    """
    if tag_name not in facts:
        return {}, {}, {}, {}
    entries = facts[tag_name]["units"].get(unit, [])

    quarterly = {}
    annuals_by_fy = {}
    ytd_9m_by_fy = {}
    ytd_6m_by_fy = {}

    for e in entries:
        start = e.get("start")
        end = e.get("end")
        if not start or not end:
            continue

        start_dt = datetime.strptime(start, "%Y-%m-%d")
        end_dt = datetime.strptime(end, "%Y-%m-%d")
        days = (end_dt - start_dt).days

        q, fy = fy_quarter_for_date(end, fy_end_month)
        fq = f"Q{q}_FY{fy}"

        if fy < start_fy or (fy == start_fy and q < start_q):
            continue

        # For multi-quarter periods (annual/YTD), determine FY from the end date.
        # Annual end = Q4 end → same FY. YTD 9M end = Q3 end → same FY.
        # YTD 6M end = Q2 end → same FY. This is more robust than start+offset.
        _, end_fy_of_entry = (fy_quarter_for_date(end, fy_end_month)
                              if days > 100 else (0, 0))

        if 60 <= days <= 105:  # Quarterly (~90 days)
            if fq not in quarterly:
                quarterly[fq] = {"start": start, "end": end}
        elif 340 <= days <= 380:  # Annual (~365 days)
            annuals_by_fy[end_fy_of_entry] = {"start": start, "end": end, "fy": end_fy_of_entry}
        elif 240 <= days <= 290:  # 9-month YTD (~270 days)
            ytd_9m_by_fy[end_fy_of_entry] = {"start": start, "end": end, "fy": end_fy_of_entry}
        elif 160 <= days <= 200:  # 6-month YTD (~180 days)
            ytd_6m_by_fy[end_fy_of_entry] = {"start": start, "end": end, "fy": end_fy_of_entry}

    return quarterly, annuals_by_fy, ytd_9m_by_fy, ytd_6m_by_fy


def extract_duration_tag_with_ytd(facts, tag_name, quarterly_periods, fy_end_month,
                                   ytd_6m_by_fy, ytd_9m_by_fy, unit="USD"):
    """
    Extract quarterly values, deriving Q2/Q3 from YTD when standalone quarterly data is missing.
    Q2 = YTD_6M - Q1, Q3 = YTD_9M - YTD_6M
    """
    if tag_name not in facts:
        return {}
    entries = facts[tag_name]["units"].get(unit, [])
    result = {}

    # First get direct quarterly matches
    for fq, dates in quarterly_periods.items():
        if dates.get("start") == "DERIVED":
            continue
        val = get_val_by_dates(entries, dates["start"], dates["end"])
        if val is not None:
            result[fq] = val

    # Derive Q2 from YTD_6M - Q1
    for fy, ytd6 in ytd_6m_by_fy.items():
        q2_key = f"Q2_FY{fy}"
        q1_key = f"Q1_FY{fy}"
        if q2_key not in result and q2_key in quarterly_periods:
            ytd6_val = get_val_by_dates(entries, ytd6["start"], ytd6["end"])
            q1_val = result.get(q1_key)
            if ytd6_val is not None and q1_val is not None:
                result[q2_key] = ytd6_val - q1_val

    # Derive Q3 from YTD_9M - YTD_6M
    for fy, ytd9 in ytd_9m_by_fy.items():
        q3_key = f"Q3_FY{fy}"
        if q3_key not in result and q3_key in quarterly_periods:
            ytd9_val = get_val_by_dates(entries, ytd9["start"], ytd9["end"])
            ytd6 = ytd_6m_by_fy.get(fy)
            if ytd9_val is not None and ytd6:
                ytd6_val = get_val_by_dates(entries, ytd6["start"], ytd6["end"])
                if ytd6_val is not None:
                    result[q3_key] = ytd9_val - ytd6_val

    return result


def main():
    parser = argparse.ArgumentParser(description="Extract financials from SEC XBRL API")
    parser.add_argument("--cik", required=True, help="SEC CIK (zero-padded 10 digits)")
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--fy-end-month", type=int, required=True, help="Fiscal year end month (1-12)")
    parser.add_argument("--start", required=True, help="Start period e.g. Q1_FY2025")
    parser.add_argument("--out-dir", required=True, help="Output directory")
    parser.add_argument("--exchange", default="", help="Exchange name")
    parser.add_argument("--company", default="", help="Company name")
    args = parser.parse_args()

    ticker = args.ticker.upper()
    cik = args.cik.zfill(10)
    fy_end_month = args.fy_end_month
    out_dir = os.path.expanduser(args.out_dir)
    os.makedirs(out_dir, exist_ok=True)

    # Parse start period
    m = args.start.upper().replace(" ", "_")
    start_q = int(m.split("_")[0].replace("Q", ""))
    start_fy = int(m.split("_")[1].replace("FY", ""))

    # Fetch data
    print(f"Fetching XBRL data for {ticker} (CIK {cik})...")
    xbrl = fetch_xbrl(cik)
    facts = xbrl.get("facts", {}).get("us-gaap", {})
    entity_name = xbrl.get("entityName", args.company or ticker)

    print(f"Fetching submissions for filing details...")
    submissions = fetch_submissions(cik)

    # Save raw XBRL
    raw_path = os.path.join(out_dir, f"{ticker.lower()}_xbrl_raw.json")
    with open(raw_path, "w") as f:
        json.dump(xbrl, f)
    print(f"  Raw XBRL saved: {raw_path}")

    # ── Tag inventory & auto-discovery ──
    use_llm = os.environ.get("ANTHROPIC_API_KEY", "") != ""
    print(f"\nScanning {len(facts)} XBRL tags for auto-classification...")
    (expanded_is, expanded_bs, expanded_cf), classification_methods = discover_tags_for_company(
        facts, [IS_TAG_MAP, BS_TAG_MAP, CF_TAG_MAP], use_llm=use_llm
    )

    # Count available tags (using expanded maps)
    is_count = sum(1 for m, cc in expanded_is.items() if any(c in facts for c in cc))
    bs_count = sum(1 for m, cc in expanded_bs.items() if any(c in facts for c in cc))
    cf_count = sum(1 for m, cc in expanded_cf.items() if any(c in facts for c in cc))
    print(f"  IS: {is_count}/{len(expanded_is)} metrics available")
    print(f"  BS: {bs_count}/{len(expanded_bs)} metrics available")
    print(f"  CF: {cf_count}/{len(expanded_cf)} metrics available")

    # Discover periods — merge from ALL revenue tag candidates to handle tag transitions
    rev_candidates = expanded_is["revenue"]
    ni_candidates = expanded_is.get("net_income", [])
    ni_tag = None
    for c in ni_candidates:
        if c in facts:
            ni_tag = c
            break
    merged_quarterly = {}
    merged_annuals = {}
    merged_ytd9 = {}
    merged_ytd6 = {}
    discover_tags_used = []
    for candidate in rev_candidates:
        if candidate in facts:
            q, a, y9, y6 = build_periods_from_xbrl(
                facts, candidate, fy_end_month, start_q, start_fy
            )
            if q:
                discover_tags_used.append(candidate)
                # Merge: fill in periods not yet covered (first tag has priority for overlaps)
                for p, v in q.items():
                    if p not in merged_quarterly:
                        merged_quarterly[p] = v
                for fy, v in a.items():
                    if fy not in merged_annuals:
                        merged_annuals[fy] = v
                for fy, v in y9.items():
                    if fy not in merged_ytd9:
                        merged_ytd9[fy] = v
                for fy, v in y6.items():
                    if fy not in merged_ytd6:
                        merged_ytd6[fy] = v
    # Fallback to net_income if revenue tags yield nothing
    if not merged_quarterly and ni_tag:
        discover_tags_used = [ni_tag]
        merged_quarterly, merged_annuals, merged_ytd9, merged_ytd6 = build_periods_from_xbrl(
            facts, ni_tag, fy_end_month, start_q, start_fy
        )
    if not discover_tags_used:
        print("ERROR: Cannot find Revenue or Net Income tag with period data", file=sys.stderr)
        sys.exit(1)

    print(f"Discovering periods from {discover_tags_used}...")
    quarterly_periods = merged_quarterly
    annuals_by_fy = merged_annuals
    ytd_9m_by_fy = merged_ytd9
    ytd_6m_by_fy = merged_ytd6

    # Get filing info
    _, bs_date_map, filing_info = detect_periods_from_submissions(
        submissions, fy_end_month, start_q, start_fy
    )

    # Determine all periods
    all_is_periods = sorted(quarterly_periods.keys(),
                            key=lambda p: (int(p.split("_")[1].replace("FY","")), int(p.split("_")[0].replace("Q",""))))

    # Check which Q4s need derivation — use annuals_by_fy (XBRL data) as primary source,
    # not just filing_info (which may not include older 10-K filings)
    q4_derivations = {}
    for fy, annual in annuals_by_fy.items():
        q4_key = f"Q4_FY{fy}"
        if q4_key not in quarterly_periods:
            ytd = ytd_9m_by_fy.get(fy)
            q4_derivations[q4_key] = {
                "fy_dates": {"start": annual["start"], "end": annual["end"]},
                "ytd_dates": {"start": ytd["start"], "end": ytd["end"]} if ytd else None,
            }
            if q4_key not in all_is_periods:
                all_is_periods.append(q4_key)
            quarterly_periods[q4_key] = {"start": "DERIVED", "end": "DERIVED"}

    all_is_periods.sort(key=lambda p: (int(p.split("_")[1].replace("FY","")), int(p.split("_")[0].replace("Q",""))))

    all_bs_periods = sorted(bs_date_map.keys(),
                            key=lambda p: (int(p.split("_")[1].replace("FY","")) if "FY" in p else 0,
                                           int(p.split("_")[0].replace("Q","")) if p[0]=="Q" else 0))

    print(f"\nPeriods found:")
    print(f"  IS: {all_is_periods}")
    print(f"  BS: {all_bs_periods}")
    for q4k in q4_derivations:
        print(f"  Q4 derivation: {q4k} (full year minus 9-month YTD)")

    # ── Extract Income Statement (multi-tag with auto-alignment) ──
    print("\nExtracting Income Statement...")
    income_statement = {}
    tag_history = {}  # metric → { "tags_used": [...], "tag_by_period": {...} }
    # EPS: "annual - 9M YTD" works (both are cumulative per-share figures).
    # Shares: NOT additive — "annual avg - 9M avg" is meaningless.
    #   → Q4 shares filled post-extraction with annual weighted average.
    SHARES_METRICS = {"shares_basic", "shares_diluted"}

    for metric, candidates in expanded_is.items():
        unit = "USD"
        if metric in ("eps_basic", "eps_diluted"):
            unit = "USD/shares"
        elif metric in SHARES_METRICS:
            unit = "shares"

        vals, tbp = extract_duration_multi_tag(
            facts, candidates, quarterly_periods, fy_end_month,
            annuals_by_fy, ytd_9m_by_fy, ytd_6m_by_fy,
            unit=unit, derive_q4=(metric not in SHARES_METRICS)
        )

        if not vals:
            continue

        # Record tag history
        tags_used = sorted(set(tbp.values()))
        if len(tags_used) > 1 or (len(tags_used) == 1 and tags_used[0] != candidates[0]):
            tag_history[metric] = {"tags_used": tags_used, "tag_by_period": tbp}

        if metric in ("shares_basic", "shares_diluted"):
            vals = {k: round(v / 1_000_000, 1) for k, v in vals.items()}
            metric = metric + "_millions"
        elif metric in ("eps_basic", "eps_diluted"):
            vals = {k: round(v, 2) for k, v in vals.items()}
        else:
            vals = to_millions(vals)

        income_statement[metric] = vals

    # Fill Q4 shares with annual weighted average (shares aren't additive)
    for shares_key in ("shares_basic_millions", "shares_diluted_millions"):
        if shares_key not in income_statement:
            continue
        shares_vals = income_statement[shares_key]
        raw_metric = shares_key.replace("_millions", "")
        candidates = expanded_is.get(raw_metric, [])
        for tag in candidates:
            if tag not in facts:
                continue
            entries = facts[tag]["units"].get("shares", [])
            for fy_yr, annual in annuals_by_fy.items():
                q4k = f"Q4_FY{fy_yr}"
                if q4k in shares_vals:
                    continue
                # Find annual weighted average shares
                annual_val = get_val_by_dates(entries, annual["start"], annual["end"])
                if annual_val is not None:
                    shares_vals[q4k] = round(annual_val / 1_000_000, 1)
            break  # use first tag that exists

    # Compute margins
    rev = income_statement.get("revenue", {})
    gp = income_statement.get("gross_profit", {})
    oi = income_statement.get("operating_income", {})
    ni = income_statement.get("net_income", {})
    pretax = income_statement.get("income_before_taxes", {})
    tax = income_statement.get("income_tax_expense", {})

    income_statement["gross_margin_pct"] = compute_pct(gp, rev)
    income_statement["operating_margin_pct"] = compute_pct(oi, rev)
    income_statement["net_margin_pct"] = compute_pct(ni, rev)
    income_statement["effective_tax_rate"] = compute_pct(tax, pretax)

    # ── Extract Balance Sheet ──
    print("Extracting Balance Sheet...")
    bs_assets = {}
    bs_liabilities = {}
    bs_equity = {}

    ASSET_KEYS = ["cash_and_cash_equivalents", "short_term_investments", "accounts_receivable",
                  "inventories", "other_current_assets", "total_current_assets",
                  "property_plant_equipment_net", "operating_lease_rou_asset", "goodwill",
                  "intangible_assets", "deferred_tax_assets", "other_noncurrent_assets", "total_assets"]
    LIAB_KEYS = ["accounts_payable", "accrued_liabilities", "current_debt",
                 "other_current_liabilities", "total_current_liabilities",
                 "long_term_debt", "operating_lease_noncurrent",
                 "other_noncurrent_liabilities", "total_liabilities"]
    EQUITY_KEYS = ["common_stock", "additional_paid_in_capital", "retained_earnings",
                   "treasury_stock", "aoci", "total_equity", "total_liabilities_and_equity"]

    for metric, candidates in expanded_bs.items():
        vals, tbp = extract_instant_multi_tag(facts, candidates, bs_date_map)
        if not vals:
            continue
        tags_used = sorted(set(tbp.values()))
        if len(tags_used) > 1 or (len(tags_used) == 1 and tags_used[0] != candidates[0]):
            tag_history[metric] = {"tags_used": tags_used, "tag_by_period": tbp}
        vals = to_millions(vals)
        if metric in ASSET_KEYS:
            bs_assets[metric] = vals
        elif metric in LIAB_KEYS:
            bs_liabilities[metric] = vals
        elif metric in EQUITY_KEYS:
            bs_equity[metric] = vals

    # ── Extract Cash Flow ──
    print("Extracting Cash Flow Statement...")
    cf_ops = {}
    cf_inv = {}
    cf_fin = {}
    cf_summary = {}

    OPS_KEYS = ["depreciation_and_amortization", "share_based_compensation", "deferred_income_tax",
                "goodwill_impairment", "other_asset_impairment", "change_in_receivables",
                "change_in_inventories", "change_in_accounts_payable", "change_in_accrued_liabilities",
                "net_cash_from_operating"]
    INV_KEYS = ["capital_expenditures", "net_cash_from_investing"]
    FIN_KEYS = ["proceeds_from_debt", "repayments_of_debt", "net_cash_from_financing"]
    SUMMARY_KEYS = ["fx_effect", "net_change_in_cash"]

    for metric, candidates in expanded_cf.items():
        vals, tbp = extract_duration_multi_tag(
            facts, candidates, quarterly_periods, fy_end_month,
            annuals_by_fy, ytd_9m_by_fy, ytd_6m_by_fy
        )
        if not vals:
            continue
        tags_used = sorted(set(tbp.values()))
        if len(tags_used) > 1 or (len(tags_used) == 1 and tags_used[0] != candidates[0]):
            tag_history[metric] = {"tags_used": tags_used, "tag_by_period": tbp}
        vals = to_millions(vals)
        if metric in OPS_KEYS:
            cf_ops[metric] = vals
        elif metric in INV_KEYS:
            cf_inv[metric] = vals
        elif metric in FIN_KEYS:
            cf_fin[metric] = vals
        elif metric in SUMMARY_KEYS:
            cf_summary[metric] = vals

    # Add net_income to operating activities
    cf_ops = {"net_income": income_statement.get("net_income", {}), **cf_ops}

    # Ending cash (instant, multi-tag)
    ending_cash_candidates = ["CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
                               "CashAndCashEquivalentsAtCarryingValue"]
    ending_cash_raw, _ = extract_instant_multi_tag(facts, ending_cash_candidates, bs_date_map)
    ending_cash = to_millions(ending_cash_raw)

    # Free cash flow
    fcf = {}
    ocf = cf_ops.get("net_cash_from_operating", {})
    capex = cf_inv.get("capital_expenditures", {})
    for p in all_is_periods:
        o = ocf.get(p)
        c = capex.get(p)
        if o is not None and c is not None:
            fcf[p] = round(o - c, 1)

    # ── Financial Ratios ──
    print("Computing financial ratios...")
    ratios = {}
    # Use union of BS and IS periods
    all_ratio_periods = sorted(set(all_bs_periods) | set(all_is_periods),
                                key=lambda p: (int(p.split('FY')[1]) if 'FY' in p else 0,
                                               int(p[1]) if p.startswith('Q') else 0))
    for p in all_ratio_periods:
        ca = bs_assets.get("total_current_assets", {}).get(p)
        cl = bs_liabilities.get("total_current_liabilities", {}).get(p)
        inv = bs_assets.get("inventories", {}).get(p)
        cash = bs_assets.get("cash_and_cash_equivalents", {}).get(p)
        ta = bs_assets.get("total_assets", {}).get(p)
        tl = bs_liabilities.get("total_liabilities", {}).get(p)
        te = bs_equity.get("total_equity", {}).get(p)
        ltd = bs_liabilities.get("long_term_debt", {}).get(p, 0) or 0
        cd = bs_liabilities.get("current_debt", {}).get(p, 0) or 0
        total_debt = ltd + cd

        rev = income_statement.get("revenue", {}).get(p)
        gp = income_statement.get("gross_profit", {}).get(p)
        oi = income_statement.get("operating_income", {}).get(p)
        ni = income_statement.get("net_income", {}).get(p)
        int_exp = income_statement.get("interest_expense", {}).get(p)
        fcf_val = fcf.get(p)

        r = {}
        # Balance sheet ratios
        if ca and cl and cl != 0:
            r["current_ratio"] = round(ca / cl, 2)
        if ca is not None and inv is not None and cl and cl != 0:
            r["quick_ratio"] = round((ca - (inv or 0)) / cl, 2)
        if tl is not None and te and te != 0:
            r["debt_to_equity"] = round(tl / te, 2)
        if total_debt and te and te != 0:
            r["net_debt_to_equity"] = round((total_debt - (cash or 0)) / te, 2)
        if ta and ta != 0 and te is not None:
            r["equity_ratio"] = round(te / ta, 4)
        # Profitability ratios
        if gp is not None and rev and rev != 0:
            r["gross_margin_pct"] = round(gp / rev, 4)
        if oi is not None and rev and rev != 0:
            r["operating_margin_pct"] = round(oi / rev, 4)
        if ni is not None and rev and rev != 0:
            r["net_margin_pct"] = round(ni / rev, 4)
        if ni is not None and te and te != 0:
            r["roe"] = round(ni / te, 4)
        if ni is not None and ta and ta != 0:
            r["roa"] = round(ni / ta, 4)
        # Efficiency / coverage
        if rev is not None and ta and ta != 0:
            r["asset_turnover"] = round(rev / ta, 4)
        if oi is not None and int_exp and int_exp != 0:
            r["interest_coverage"] = round(oi / int_exp, 2)
        if fcf_val is not None and rev and rev != 0:
            r["fcf_margin_pct"] = round(fcf_val / rev, 4)
        if r:
            ratios[p] = r

    # ── Period end dates ──
    period_ends = {}
    for p in all_is_periods:
        if p in filing_info:
            period_ends[p] = filing_info[p]["period_end"]
    for p in all_bs_periods:
        if p in bs_date_map:
            period_ends[p] = bs_date_map[p]

    # ── Build long format ──
    print("Building long format...")
    long_rows = []
    for metric, vals in income_statement.items():
        for p in all_is_periods:
            v = vals.get(p)
            if v is not None:
                unit = "pct" if "pct" in metric or "rate" in metric else (
                    "USD_per_share" if "eps" in metric else (
                    "millions_shares" if "shares" in metric else "USD_millions"))
                long_rows.append({"period": p, "period_end": period_ends.get(p, ""),
                                  "statement": "income_statement", "metric": metric,
                                  "value": v, "unit": unit})

    for section, section_data in [("assets", bs_assets), ("liabilities", bs_liabilities), ("equity", bs_equity)]:
        for metric, vals in section_data.items():
            for p in all_bs_periods:
                v = vals.get(p)
                if v is not None:
                    long_rows.append({"period": p, "period_end": period_ends.get(p, ""),
                                      "statement": f"balance_sheet_{section}", "metric": metric,
                                      "value": v, "unit": "USD_millions"})

    # ── Build classification_audit ──
    # Combine tag_history (which tag was used per period) with classification_methods (how each tag was found)
    classification_audit = {}
    for metric, info in tag_history.items():
        tags_detail = []
        for tag in info["tags_used"]:
            periods_for_tag = sorted([p for p, t in info["tag_by_period"].items() if t == tag])
            cm = classification_methods.get(tag, {})
            entry = {
                "tag": tag,
                "label": _get_tag_label(facts, tag),
                "method": cm.get("method", "known"),
                "confidence": cm.get("confidence", 1.0),
                "periods": periods_for_tag,
            }
            if cm.get("reasoning"):
                entry["reasoning"] = cm["reasoning"]
            tags_detail.append(entry)
        classification_audit[metric] = {"tags": tags_detail}

    # Also add metrics that used a single tag (not in tag_history) but were non-obvious
    # (i.e., method != "known")
    all_metric_tags = {}  # metric → tag used
    for tag_map_name, tag_map in [("is", expanded_is), ("bs", expanded_bs), ("cf", expanded_cf)]:
        for metric, candidates in tag_map.items():
            for c in candidates:
                if c in facts and c in classification_methods:
                    cm = classification_methods[c]
                    if cm.get("metric") == metric and cm.get("method") != "known":
                        if metric not in classification_audit:
                            classification_audit[metric] = {"tags": [{
                                "tag": c,
                                "label": _get_tag_label(facts, c),
                                "method": cm["method"],
                                "confidence": cm.get("confidence", 0.95),
                                "periods": ["all"],
                                **({"reasoning": cm["reasoning"]} if cm.get("reasoning") else {}),
                            }]}
                    break

    # ── Assemble output ──
    notes_parts = []
    for q4k in q4_derivations:
        notes_parts.append(f"{q4k} income statement and cash flow are DERIVED (full-year 10-K minus 9-month YTD).")

    data = {
        "metadata": {
            "company": entity_name,
            "ticker": ticker,
            "exchange": args.exchange or "",
            "cik": cik,
            "fiscal_year_end_month": fy_end_month,
            "currency": "USD",
            "unit": "millions_except_per_share",
            "last_updated": str(date.today()),
            "data_source": "SEC EDGAR XBRL API (data.sec.gov/api/xbrl/companyfacts)",
            "periods_income_statement": all_is_periods,
            "periods_balance_sheet": all_bs_periods,
            "notes": " ".join(notes_parts) if notes_parts else "",
        },
        "filings": filing_info,
        "income_statement": income_statement,
        "balance_sheet": {
            "assets": bs_assets,
            "liabilities": bs_liabilities,
            "equity": bs_equity,
        },
        "cash_flow_statement": {
            "operating_activities": cf_ops,
            "investing_activities": cf_inv,
            "financing_activities": cf_fin,
            "ending_cash": ending_cash,
            "free_cash_flow": fcf,
            **{k: v for k, v in cf_summary.items()},
        },
        "financial_ratios": ratios,
        "classification_audit": classification_audit,
        "tag_history": tag_history if tag_history else {},
        "notable_events": [],
        "long_format": long_rows,
    }

    if tag_history:
        print(f"\nTag alignment (metrics with multiple XBRL tags):")
        for m, info in tag_history.items():
            print(f"  {m}: {info['tags_used']}")
    if classification_audit:
        print(f"\nClassification audit ({len(classification_audit)} metrics with tag mappings recorded)")
        for m, info in classification_audit.items():
            for t in info["tags"]:
                method_badge = {"known": "K", "label_discovery": "L", "llm_inference": "AI"}.get(t["method"], "?")
                print(f"  [{method_badge}] {m} → {t['tag']} ({len(t['periods'])} periods, conf={t['confidence']})")

    # Backup existing JSON if present
    json_path = os.path.join(out_dir, f"{ticker}_financials.json")
    if os.path.exists(json_path):
        backup = json_path.replace(".json", f"_backup_{date.today()}.json")
        shutil.copy(json_path, backup)
        print(f"  Backup: {backup}")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*60}")
    print(f"  {ticker} financials extracted successfully")
    print(f"  JSON: {json_path}")
    print(f"  IS periods: {all_is_periods}")
    print(f"  BS periods: {all_bs_periods}")
    print(f"  Long format rows: {len(long_rows)}")
    print(f"  IS metrics: {len(income_statement)}")
    print(f"  BS metrics: {sum(len(v) for v in [bs_assets, bs_liabilities, bs_equity])}")
    print(f"  CF metrics: {sum(len(v) for v in [cf_ops, cf_inv, cf_fin, cf_summary])}")
    print(f"{'='*60}")

    # Print revenue summary
    print(f"\nRevenue (USD M):")
    for p in all_is_periods:
        v = income_statement.get("revenue", {}).get(p, "—")
        print(f"  {p}: {v}")

    return data


if __name__ == "__main__":
    main()
