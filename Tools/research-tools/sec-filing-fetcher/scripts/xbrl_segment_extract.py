"""
xbrl_segment_extract.py — Extract segment revenue from SEC EDGAR inline XBRL Instance files.

Parses dimensional data (ProductOrServiceAxis, StatementGeographicalAxis,
StatementBusinessSegmentsAxis) from XBRL Instance XML files to extract
segment-level revenue breakdowns.

Q4 derivation: 10-K filings only contain annual totals for segments.
Q4 = Annual - Q1 - Q2 - Q3 (derived from 10-Q quarterly data).

Usage:
    uv run --with requests --with lxml python3 xbrl_segment_extract.py \
        --cik 0002023554 --ticker SNDK --fy-end-month 6 \
        --out public/data/financials/SNDK/SNDK_supplemental.json

    # Merge into existing supplemental (preserves non_gaap section):
    uv run --with requests --with lxml python3 xbrl_segment_extract.py \
        --cik 0002023554 --ticker SNDK --fy-end-month 6 \
        --out public/data/financials/SNDK/SNDK_supplemental.json --merge

Data source: SEC EDGAR inline XBRL Instance files (_htm.xml)
    - Downloaded from: https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{doc}_htm.xml
    - Each 10-Q/10-K filing contains segment revenue with XBRL dimensional contexts
    - Uses srt:ProductOrServiceAxis, srt:StatementGeographicalAxis,
      and us-gaap:StatementBusinessSegmentsAxis dimensions

Fiscal Calendar:
    Same nearest-quarter-end matching as xbrl_extract.py for 4-4-5 calendars.
"""
import argparse, json, os, sys
from datetime import date

# ---------------------------------------------------------------------------
# Fiscal quarter mapping (same logic as xbrl_extract.py)
# ---------------------------------------------------------------------------

def quarter_end_months(fy_end_month: int) -> list[int]:
    """Return the 4 quarter-end months for a given fiscal year end month."""
    return [(fy_end_month + 3 * i) % 12 or 12 for i in range(1, 5)]


def nearest_fiscal_quarter(end_date: str, fy_end_month: int) -> str | None:
    """Map a period end date to fiscal quarter label (e.g. Q1_FY2025)."""
    dt = date.fromisoformat(end_date)
    q_months = quarter_end_months(fy_end_month)  # [Q1_end, Q2_end, Q3_end, Q4_end]

    best_q, best_dist = None, 999
    for qi, m in enumerate(q_months, 1):
        # Last day of that month in the same year
        for yr_offset in [-1, 0, 1]:
            yr = dt.year + yr_offset
            try:
                # Last day of month m in year yr
                if m == 12:
                    candidate = date(yr, 12, 31)
                else:
                    candidate = date(yr, m + 1, 1).replace(day=1)
                    candidate = candidate.replace(day=1)
                    from datetime import timedelta
                    candidate = date(yr, m + 1, 1) - timedelta(days=1)
            except ValueError:
                continue
            dist = abs((dt - candidate).days)
            if dist < best_dist:
                best_dist = dist
                best_q = qi
                # FY: determined by which fiscal year this quarter belongs to
                # Q4 end month = fy_end_month, so FY = yr if qi==4
                # Otherwise FY is the year containing the FY end
                if m > fy_end_month or (m == fy_end_month and qi == 4):
                    best_fy = yr
                elif m <= fy_end_month:
                    best_fy = yr
                else:
                    best_fy = yr

    if best_q is None or best_dist > 15:
        return None

    # Determine FY: the fiscal year that this quarter belongs to
    # FY ends at fy_end_month. Q1 starts after FY end.
    # E.g. FY end June: Q1=Jul-Sep, Q2=Oct-Dec, Q3=Jan-Mar, Q4=Apr-Jun
    # Q1 end ~Sep/Oct of year Y → FY = Y+1
    # Q4 end ~Jun of year Y → FY = Y
    dt_month = dt.month
    # If the end date is in the second half relative to FY end, it's next FY
    months_after_fy_end = (dt_month - fy_end_month) % 12
    if months_after_fy_end > 0 and months_after_fy_end <= 6:
        fy = dt.year + 1
    elif months_after_fy_end > 6:
        fy = dt.year + 1
    else:
        fy = dt.year
    # Correction for month == fy_end_month (Q4 end)
    if dt_month == fy_end_month or (dt_month == fy_end_month + 1 and dt.day <= 7):
        fy = dt.year

    return f"Q{best_q}_FY{fy}"


def simple_fq(end_date: str, fy_end_month: int) -> str | None:
    """Fiscal quarter mapping based on nearest quarter-end month.

    Handles 4-4-5 calendar drift where quarter-end dates can fall
    up to ~7 days into the next calendar month (e.g. Q1 ending Oct 3
    instead of Sep 30 for a June FY-end company).

    Each quarter's target end month is (fy_end_month + 3*Q) % 12.
    We accept the target month AND the next month (for 4-4-5 drift).
    """
    dt = date.fromisoformat(end_date)
    month = dt.month
    year = dt.year

    # Build lookup: month -> quarter
    # Each quarter Q (1-4) ends at target month = (fy_end_month + 3*Q) % 12 or 12
    # Accept target_month and target_month+1 (4-4-5 drift)
    month_to_q = {}
    for q in range(1, 5):
        target = (fy_end_month + 3 * q) % 12 or 12
        month_to_q[target] = q
        drift = target % 12 + 1  # next month
        if drift not in month_to_q:  # don't overwrite if already mapped
            month_to_q[drift] = q

    q = month_to_q.get(month)
    if q is None:
        return None

    # FY determination: Q1-Q3 months after FY end belong to next FY
    # Q4 end month == fy_end_month (or +1 for drift) belongs to current FY
    if month > fy_end_month:
        fy = year + 1
    else:
        fy = year

    return f"Q{q}_FY{fy}"


# ---------------------------------------------------------------------------
# XBRL Instance parser
# ---------------------------------------------------------------------------

USER_AGENT = "Mozilla/5.0 (research tool) claude-code/1.0 contact@researchbot.local"

XBRLI_NS = "http://www.xbrl.org/2003/instance"
XBRLDI_NS = "http://xbrl.org/2006/xbrldi"

# Dimensions we care about
TARGET_DIMS = {"ProductOrServiceAxis", "StatementGeographicalAxis", "StatementBusinessSegmentsAxis"}

# Skip aggregate/parent segments
SKIP_MEMBERS = {"ReportableSegmentMember", "EquityMethodInvestmentNonconsolidatedInvesteeOrGroupOfInvesteesMember"}


def fetch_filing_list(cik: str) -> list[dict]:
    """Fetch list of 10-K/10-Q filings from SEC EDGAR."""
    import requests
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    resp = requests.get(url, headers={"User-Agent": USER_AGENT})
    resp.raise_for_status()
    data = resp.json()

    recent = data["filings"]["recent"]
    filings = []
    for i in range(len(recent["form"])):
        form = recent["form"][i]
        if form in ("10-Q", "10-K"):
            filings.append({
                "form": form,
                "report_date": recent["reportDate"][i],
                "accession": recent["accessionNumber"][i],
                "primary_doc": recent["primaryDocument"][i],
            })
    return filings


def fetch_xbrl_instance(cik_num: str, accession: str, primary_doc: str) -> bytes | None:
    """Download the XBRL Instance XML file for a filing."""
    import requests
    acc_path = accession.replace("-", "")
    doc_base = primary_doc.replace(".htm", "")
    url = f"https://www.sec.gov/Archives/edgar/data/{cik_num}/{acc_path}/{doc_base}_htm.xml"
    resp = requests.get(url, headers={"User-Agent": USER_AGENT})
    if resp.status_code == 200:
        return resp.content
    return None


def parse_segment_revenue(xml_content: bytes) -> list[dict]:
    """Parse segment revenue facts from XBRL Instance XML."""
    from lxml import etree

    root = etree.fromstring(xml_content)

    # Find us-gaap namespace
    usgaap_ns = None
    for k, v in root.nsmap.items():
        if k == "us-gaap":
            usgaap_ns = v
            break
    if not usgaap_ns:
        return []

    # Build context map
    contexts = {}
    for ctx in root.findall(f"{{{XBRLI_NS}}}context"):
        ctx_id = ctx.get("id")
        period = ctx.find(f"{{{XBRLI_NS}}}period")
        start = period.findtext(f"{{{XBRLI_NS}}}startDate")
        end = period.findtext(f"{{{XBRLI_NS}}}endDate") or period.findtext(f"{{{XBRLI_NS}}}instant")

        dims = {}
        for member in ctx.iter(f"{{{XBRLDI_NS}}}explicitMember"):
            dim = member.get("dimension", "").split(":")[-1]
            val = member.text.strip().split(":")[-1] if member.text else ""
            dims[dim] = val

        contexts[ctx_id] = {"start": start, "end": end, "dims": dims}

    # Find Revenue facts with target dimensions
    rev_tag = f"{{{usgaap_ns}}}RevenueFromContractWithCustomerExcludingAssessedTax"
    results = []
    for fact in root.iter(rev_tag):
        ctx_id = fact.get("contextRef")
        ctx = contexts.get(ctx_id, {})
        dims = ctx.get("dims", {})

        target_dims = {k: v for k, v in dims.items() if k in TARGET_DIMS}
        if not target_dims:
            continue

        # Priority: BusinessSegments > Product/Geo
        # If a fact has BusinessSegmentsAxis (possibly with other dims), record on business axis
        # If a fact has exactly one of Product/Geo axis, record on that axis
        if "StatementBusinessSegmentsAxis" in target_dims:
            dim_type = "StatementBusinessSegmentsAxis"
            dim_val = target_dims[dim_type]
        elif len(target_dims) == 1:
            dim_type = list(target_dims.keys())[0]
            dim_val = list(target_dims.values())[0]
        else:
            # Multiple non-business dims (e.g. Product × Geo) — skip
            continue

        # Skip aggregate members
        if dim_val in SKIP_MEMBERS:
            continue

        results.append({
            "value": int(float(fact.text)) if fact.text else None,
            "start": ctx.get("start"),
            "end": ctx.get("end"),
            "dim_type": dim_type,
            "dim_value": dim_val,
        })

    return results


def period_days(start: str, end: str) -> int:
    """Return number of days in a period, or -1 if invalid."""
    if not start or not end:
        return -1
    return (date.fromisoformat(end) - date.fromisoformat(start)).days


def is_single_quarter(start: str, end: str) -> bool:
    """Check if a period is approximately one quarter (~60-100 days)."""
    days = period_days(start, end)
    return 60 <= days <= 100


def is_annual(start: str, end: str) -> bool:
    """Check if a period is approximately one year (~350-380 days)."""
    days = period_days(start, end)
    return 350 <= days <= 380


def annual_fy(end_date: str, fy_end_month: int) -> str | None:
    """Map an annual period end date to FY label (e.g. FY2025).

    For annual periods, the end date should be near the FY end month.
    """
    dt = date.fromisoformat(end_date)
    month = dt.month
    # Accept fy_end_month and fy_end_month+1 (4-4-5 drift)
    target = fy_end_month
    drift = target % 12 + 1
    if month == target or month == drift:
        return f"FY{dt.year}"
    return None


def clean_member_name(raw: str) -> str:
    """Convert XBRL member name to display name.
    e.g. 'DatacenterMember' -> 'Datacenter', 'EMEAMember' -> 'EMEA'
    """
    name = raw.replace("Member", "")
    # Handle country codes (2-letter)
    if len(name) == 2 and name.isupper():
        return name
    # Handle known mappings
    mappings = {
        "ClientDevices": "Edge",      # SNDK naming change FY2026
        "Cloud": "Datacenter",         # SNDK naming change FY2026
        "RestOfAsia": "Rest of Asia",
        "OtherGeographical": "Other",
    }
    return mappings.get(name, name)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Extract segment revenue from inline XBRL")
    parser.add_argument("--cik", required=True, help="SEC CIK (e.g. 0002023554)")
    parser.add_argument("--ticker", required=True, help="Ticker symbol")
    parser.add_argument("--fy-end-month", type=int, required=True, help="Fiscal year end month (1-12)")
    parser.add_argument("--out", required=True, help="Output JSON path")
    parser.add_argument("--merge", action="store_true", help="Merge into existing supplemental.json")
    parser.add_argument("--name-map", type=str, default=None,
                        help='JSON string for custom member name mappings, e.g. \'{"ClientDevices":"Edge"}\'')
    args = parser.parse_args()

    cik_num = args.cik.lstrip("0") or "0"

    # Custom name mappings
    custom_map = {}
    if args.name_map:
        custom_map = json.loads(args.name_map)

    print(f"Fetching filing list for CIK {args.cik}...")
    filings = fetch_filing_list(args.cik)
    print(f"  Found {len(filings)} filings (10-K/10-Q)")

    all_facts = []
    for f in filings:
        print(f"  Fetching {f['form']} {f['report_date']}...", end=" ", flush=True)
        xml = fetch_xbrl_instance(cik_num, f["accession"], f["primary_doc"])
        if xml is None:
            print("SKIP (no XBRL Instance)")
            continue
        facts = parse_segment_revenue(xml)
        doc_base = f["primary_doc"].replace(".htm", "")
        for fact in facts:
            fact["doc"] = f"{doc_base}_htm.xml"
            fact["filing_form"] = f["form"]
        all_facts.extend(facts)
        print(f"{len(facts)} segment facts")

    # Separate quarterly and annual facts
    quarterly = [f for f in all_facts if is_single_quarter(f["start"], f["end"])]
    annual = [f for f in all_facts if is_annual(f["start"], f["end"])]
    print(f"\nTotal single-quarter segment facts: {len(quarterly)}")
    print(f"Total annual segment facts: {len(annual)}")

    # Deduplicate: same (start, end, dim_type, dim_value) → keep first
    def dedup(facts):
        seen = set()
        unique = []
        for f in facts:
            key = (f["start"], f["end"], f["dim_type"], f["dim_value"])
            if key not in seen:
                seen.add(key)
                unique.append(f)
        return unique

    quarterly = dedup(quarterly)
    annual = dedup(annual)

    # Helper: classify a fact into the right segment bucket
    def dim_category(dim_type: str) -> str:
        if dim_type == "ProductOrServiceAxis":
            return "product"
        elif dim_type == "StatementGeographicalAxis":
            return "geo"
        elif dim_type == "StatementBusinessSegmentsAxis":
            return "business"
        return "other"

    # Map quarterly facts to fiscal quarters
    product_segments = {}
    geo_segments = {}
    business_segments = {}

    for f in quarterly:
        fq = simple_fq(f["end"], args.fy_end_month)
        if not fq:
            continue

        raw_name = f["dim_value"].replace("Member", "")
        name = custom_map.get(raw_name, clean_member_name(f["dim_value"]))

        entry = {
            "value": f["value"] // 1_000_000,  # Convert to millions
            "source": f"SEC EDGAR inline XBRL — {f['doc']}"
        }

        cat = dim_category(f["dim_type"])
        if cat == "product":
            product_segments.setdefault(fq, {})[name] = entry
        elif cat == "geo":
            geo_segments.setdefault(fq, {})[name] = entry
        elif cat == "business":
            business_segments.setdefault(fq, {})[name] = entry

    # --- Q4 derivation from annual totals ---
    # Build annual lookup: { FY_label: { dim_category: { member_name: value_in_millions } } }
    annual_data = {}  # { "FY2025": { "product": { "Edge": { "value": 4127, "doc": "..." } } } }
    for f in annual:
        fy_label = annual_fy(f["end"], args.fy_end_month)
        if not fy_label:
            continue
        raw_name = f["dim_value"].replace("Member", "")
        name = custom_map.get(raw_name, clean_member_name(f["dim_value"]))
        cat = dim_category(f["dim_type"])
        if cat == "other":
            continue
        annual_data.setdefault(fy_label, {}).setdefault(cat, {})[name] = {
            "value": f["value"] // 1_000_000,
            "doc": f["doc"],
        }

    # For each FY with annual data, derive Q4 if Q1+Q2+Q3 exist
    for fy_label, cats in annual_data.items():
        fy_year = int(fy_label.replace("FY", ""))
        q4_key = f"Q4_{fy_label}"

        for cat, members in cats.items():
            if cat == "product":
                target = product_segments
            elif cat == "geo":
                target = geo_segments
            elif cat == "business":
                target = business_segments
            else:
                continue

            # Check if Q1, Q2, Q3 all exist for this FY
            q1_key = f"Q1_{fy_label}"
            q2_key = f"Q2_{fy_label}"
            q3_key = f"Q3_{fy_label}"

            q1 = target.get(q1_key, {})
            q2 = target.get(q2_key, {})
            q3 = target.get(q3_key, {})

            if not (q1 and q2 and q3):
                print(f"  SKIP Q4 derivation for {fy_label}/{cat}: missing Q1-Q3 data")
                continue

            # Check that annual and quarterly use the same member names
            # e.g. 10-K may report granular geo (US/CN/HK) while 10-Q uses aggregated (Asia/Americas)
            annual_members = set(members.keys())
            quarterly_members = set(q1.keys()) | set(q2.keys()) | set(q3.keys())
            if annual_members != quarterly_members:
                print(f"  SKIP Q4 derivation for {fy_label}/{cat}: member mismatch")
                print(f"    Annual:    {sorted(annual_members)}")
                print(f"    Quarterly: {sorted(quarterly_members)}")
                continue

            q4_data = {}
            for member_name, ann in members.items():
                q1_val = q1.get(member_name, {}).get("value", 0)
                q2_val = q2.get(member_name, {}).get("value", 0)
                q3_val = q3.get(member_name, {}).get("value", 0)
                q4_val = ann["value"] - q1_val - q2_val - q3_val

                if q4_val < 0:
                    print(f"  WARNING: Q4 {member_name} = {q4_val} (negative!) — skipping")
                    continue

                q4_data[member_name] = {
                    "value": q4_val,
                    "source": f"SEC EDGAR inline XBRL — {ann['doc']} (Q4 = Annual - Q1-Q3)"
                }

            if q4_data:
                target[q4_key] = q4_data
                print(f"  Derived {q4_key}/{cat}: {', '.join(f'{k}=${v['value']}M' for k, v in q4_data.items())}")

    # Sort by period
    product_segments = dict(sorted(product_segments.items()))
    geo_segments = dict(sorted(geo_segments.items()))
    business_segments = dict(sorted(business_segments.items()))

    # Build segment dict (only include non-empty categories)
    seg = {}
    if product_segments:
        seg["revenue_by_product"] = product_segments
    if geo_segments:
        seg["revenue_by_geography"] = geo_segments
    if business_segments:
        seg["revenue_by_business"] = business_segments

    # Build or merge output
    if args.merge and os.path.exists(args.out):
        with open(args.out) as fp:
            existing = json.load(fp)
        existing["metadata"]["last_updated"] = date.today().isoformat()
        existing.setdefault("segments", {})
        existing["segments"].update(seg)
        output = existing
    else:
        output = {
            "metadata": {
                "company": "",
                "ticker": args.ticker,
                "last_updated": date.today().isoformat(),
                "notes": "Segment data from SEC EDGAR inline XBRL Instance files."
            },
            "non_gaap": {},
            "segments": seg
        }

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w") as fp:
        json.dump(output, fp, indent=2, ensure_ascii=False)
        fp.write("\n")

    print(f"\nWritten to {args.out}")
    for k, v in seg.items():
        print(f"  {k}: {len(v)} periods")


if __name__ == "__main__":
    main()
