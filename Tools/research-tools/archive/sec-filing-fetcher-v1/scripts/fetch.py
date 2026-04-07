"""
fetch.py — SEC EDGAR 抓檔工具
用法：
    # 列出某公司的所有 10-Q/10-K（需先從 stdin 讀 submissions JSON）
    curl -s -A "..." "https://data.sec.gov/submissions/CIK{CIK}.json" \
      | python3 fetch.py --mode list --ticker MU

    # 下載特定申報文件
    python3 fetch.py --mode download \
      --ticker MU \
      --cik 723125 \
      --accession 0000723125-25-000046 \
      --out-dir /path/to/filings/
"""

import argparse, json, os, sys, re, subprocess
from pathlib import Path

USER_AGENT = "Mozilla/5.0 (research tool) claude-code/1.0 contact@researchbot.local"
BASE_URL   = "https://www.sec.gov/Archives/edgar/data"
API_BASE   = "https://data.sec.gov"


def list_filings(ticker):
    """從 stdin 讀取 submissions JSON，輸出 10-Q/10-K 清單"""
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        print("ERROR: 無法解析 submissions JSON", file=sys.stderr)
        sys.exit(1)

    filings = data.get("filings", {}).get("recent", {})
    forms       = filings.get("form", [])
    dates       = filings.get("filingDate", [])
    accessions  = filings.get("accessionNumber", [])
    primary_docs= filings.get("primaryDocument", [])

    results = []
    for form, date, acc, doc in zip(forms, dates, accessions, primary_docs):
        if form in ("10-Q", "10-K"):
            results.append({
                "form": form,
                "date": date,
                "accession": acc,
                "primary_doc": doc,
            })

    print(json.dumps(results, indent=2))


def download_filing(ticker, cik, accession, out_dir):
    """下載申報文件主體 HTM 並儲存"""
    # accession: 0000723125-25-000046 → 000072312525000046
    acc_clean = accession.replace("-", "")
    cik_str   = str(cik).lstrip("0")

    # 先取 filing index 找主文件名
    index_url = f"{API_BASE}/submissions/CIK{str(cik).zfill(10)}.json"

    # 嘗試直接從已知的 accession 取得 index
    index_url2 = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik_str}&type=10-Q&dateb=&owner=include&count=40&search_text="

    # 用 accession number 推算 HTM URL
    # 慣例：主文件通常是 {ticker_lower}-{yyyymmdd}.htm
    # 直接用 EDGAR API 取 index JSON
    filing_index_url = f"https://data.sec.gov/Archives/edgar/data/{cik_str}/{acc_clean}/{accession}-index.json"

    cmd = ["curl", "-s", "-A", USER_AGENT, filing_index_url]
    result = subprocess.run(cmd, capture_output=True, text=True)

    primary_doc = None
    form_type   = None

    if result.returncode == 0 and result.stdout.strip():
        try:
            idx = json.loads(result.stdout)
            for doc in idx.get("documents", []):
                if doc.get("type") in ("10-Q", "10-K"):
                    primary_doc = doc.get("name")
                    form_type   = doc.get("type")
                    break
        except (json.JSONDecodeError, KeyError):
            pass

    if not primary_doc:
        # Fallback：從 submissions JSON 找
        print(f"WARNING: 無法從 index 取得主文件名，請手動指定", file=sys.stderr)
        print(f"index URL: {filing_index_url}", file=sys.stderr)
        sys.exit(1)

    htm_url = f"{BASE_URL}/{cik_str}/{acc_clean}/{primary_doc}"

    # 決定輸出檔名
    os.makedirs(out_dir, exist_ok=True)
    # 從 URL 反推期間（通常是 {ticker}-{YYYYMMDD}.htm）
    out_filename = f"{ticker}_{accession}_{form_type.replace('-','')}.htm"
    out_path = os.path.join(out_dir, out_filename)

    print(f"Downloading: {htm_url}", file=sys.stderr)
    cmd = ["curl", "-s", "-A", USER_AGENT, "-o", out_path, htm_url]
    result = subprocess.run(cmd)

    if result.returncode == 0 and os.path.getsize(out_path) > 1000:
        print(f"SAVED: {out_path}")
        print(f"SIZE: {os.path.getsize(out_path):,} bytes")
    else:
        print(f"ERROR: 下載失敗或檔案太小 ({out_path})", file=sys.stderr)
        sys.exit(1)


def lookup_cik(ticker):
    """用 ticker 查詢 CIK"""
    url = f"https://efts.sec.gov/LATEST/search-index?q=%22{ticker}%22&forms=10-K"
    cmd = ["curl", "-s", "-A", USER_AGENT, url]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return None
    try:
        data = json.loads(result.stdout)
        hits = data.get("hits", {}).get("hits", [])
        if hits:
            entity_id = hits[0].get("_source", {}).get("entity_id")
            return entity_id
    except Exception:
        pass
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode",      choices=["list", "download", "cik"], required=True)
    parser.add_argument("--ticker",    required=True)
    parser.add_argument("--cik",       type=int, help="SEC CIK number")
    parser.add_argument("--accession", help="Accession number (with dashes)")
    parser.add_argument("--out-dir",   help="Output directory for downloaded files")
    args = parser.parse_args()

    if args.mode == "list":
        list_filings(args.ticker.upper())

    elif args.mode == "download":
        if not args.cik or not args.accession or not args.out_dir:
            print("ERROR: --cik, --accession, --out-dir 皆為必填", file=sys.stderr)
            sys.exit(1)
        download_filing(args.ticker.upper(), args.cik, args.accession, args.out_dir)

    elif args.mode == "cik":
        cik = lookup_cik(args.ticker.upper())
        if cik:
            print(f"CIK: {cik}")
        else:
            print("ERROR: 找不到 CIK，請手動查詢 SEC EDGAR", file=sys.stderr)
            sys.exit(1)

if __name__ == "__main__":
    main()
