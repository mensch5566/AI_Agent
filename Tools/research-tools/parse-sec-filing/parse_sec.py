#!/usr/bin/env python3
"""
美股 SEC 10-Q/10-K 解析 skill 執行器
用法: python3 parse_sec.py <ticker> [form_type] [file_path]
"""

import sys
import re
from pathlib import Path
from lxml import html as html_lib
import requests
from supabase import create_client

# Supabase 配置
SUPABASE_URL = "https://zpriwdyjmqvbtaektnlq.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inpwcml3ZHlqbXF2YnRhZWt0bmxxIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3MzQ4OTYzMywiZXhwIjoyMDg5MDY1NjMzfQ.VSsBqjOgZPK142kBI3FjbezmJ3ShBtk2XD-LZo2wSmQ"

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# SEC Edgar API 基礎 URL
SEC_EDGAR_BASE = "https://www.sec.gov/cgi-bin/browse-edgar"
SEC_DATA_API = "https://data.sec.gov/api/xbrl/"

# 關鍵指標對應表（SEC XBRL 標籤 → 標準欄位名）
METRIC_MAPPING = {
    # Balance Sheet
    'Assets': 'total_assets',
    'AssetsCurrent': 'total_current_assets',
    'Liabilities': 'total_liabilities',
    'LiabilitiesCurrent': 'total_current_liabilities',
    'StockholdersEquity': 'stockholders_equity',

    # Income Statement
    'Revenues': 'operating_revenue',
    'RevenuesNetSales': 'operating_revenue',
    'GrossProfit': 'gross_profit',
    'OperatingIncomeLoss': 'operating_income',
    'IncomeLossFromContinuingOperations': 'income_before_taxes',
    'NetIncomeLoss': 'net_income',
    'EarningsPerShareBasic': 'eps_basic',
    'EarningsPerShareDiluted': 'eps_diluted',

    # Cash Flow
    'NetCashProvidedByUsedInOperatingActivities': 'operating_cash_flow',
    'NetCashProvidedByUsedInInvestingActivities': 'investing_cash_flow',
    'NetCashProvidedByUsedInFinancingActivities': 'financing_cash_flow',
}


def download_sec_filing(ticker: str, form_type: str = "10-Q") -> str:
    """從 SEC Edgar 下載最新 10-Q 或 10-K 檔案"""

    print(f"🔍 從 SEC Edgar 查詢 {ticker} 的最新 {form_type}...")

    try:
        # 設定 User-Agent（SEC 要求）
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }

        # 查詢 SEC Edgar CIK
        response = requests.get(
            SEC_EDGAR_BASE,
            params={
                'action': 'getcompany',
                'company': ticker,
                'type': form_type,
                'dateb': '',
                'owner': 'exclude',
                'count': '10',
                'output': 'json'
            },
            headers=headers,
            timeout=10
        )
        response.raise_for_status()

        results = response.json().get('filings', {}).get('filing', [])

        if not results:
            raise FileNotFoundError(
                f"找不到 {ticker} 的 {form_type} 檔案\n"
                f"請手動下載: https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company={ticker}"
            )

        # 取最新的檔案
        latest = results[0]
        filing_url = f"https://www.sec.gov/Archives/{latest['href']}"

        print(f"   ✅ 找到: {latest['filing-date']}")
        print(f"   📥 下載中...")

        # 下載 HTML 檔案
        doc_response = requests.get(filing_url, headers=headers, timeout=30)
        doc_response.raise_for_status()

        # 儲存到臨時目錄
        temp_file = Path("/tmp") / f"{ticker}_{form_type}_{latest['filing-date']}.html"
        temp_file.write_bytes(doc_response.content)

        print(f"   ✅ 已儲存: {temp_file}")
        return str(temp_file)

    except Exception as e:
        raise RuntimeError(f"SEC Edgar 下載失敗: {e}")


def parse_sec_filing(file_path: str) -> dict:
    """解析 SEC 10-Q/10-K iXBRL 檔案"""

    with open(file_path, 'rb') as f:
        doc_parsed = html_lib.parse(f)
        root = doc_parsed.getroot()

    financial_data = {}
    tables = root.xpath('//table')

    print(f"  找到 {len(tables)} 個表格\n")

    # 收集所有候選
    metric_candidates = {}

    for table_idx, table in enumerate(tables):
        rows = table.xpath('.//tr')
        for row_idx, row in enumerate(rows):
            cells = row.xpath('.//td | .//th')
            if len(cells) < 2:
                continue

            # 尋找標籤（通常在第一或第二欄）
            label_text = ' '.join([c.text_content().strip() for c in cells[:2]])

            # 檢查所有指標
            for xbrl_tag, metric_key in METRIC_MAPPING.items():
                if xbrl_tag not in label_text:
                    continue

                # 取第一個數字
                for cell in cells[2:]:
                    text = cell.text_content().strip()
                    cleaned = re.sub(r'[,\s]', '', text)
                    if cleaned and cleaned.lstrip('-').replace('.', '').isdigit():
                        try:
                            value = float(cleaned)

                            if metric_key not in metric_candidates:
                                metric_candidates[metric_key] = []

                            metric_candidates[metric_key].append(
                                (value, xbrl_tag, table_idx, row_idx)
                            )
                        except ValueError:
                            pass
                        break

    # 選擇最佳候選
    for metric_key, candidates in metric_candidates.items():
        best = candidates[0]
        value, xbrl_tag, table_idx, row_idx = best

        financial_data[metric_key] = value
        print(f"  表 {table_idx + 1} 行 {row_idx}: {xbrl_tag}")
        print(f"    → {metric_key} = {value:,.0f}")

    return financial_data


def compare_with_supabase(ticker: str, financial_data: dict):
    """與 Supabase 比對"""

    print(f"\n🔍 與 Supabase 比對 (ticker={ticker}):\n")

    result = supabase.table('financial_facts').select('metric, value, period').eq('ticker', ticker).limit(500).execute()

    if not result.data:
        print(f"  ⚠️  Supabase 中沒有 {ticker} 的數據")
        return

    # 按指標分組
    metric_by_period = {}
    for row in result.data:
        metric = row['metric']
        if metric not in metric_by_period:
            metric_by_period[metric] = []
        metric_by_period[metric].append(row)

    matches = 0
    mismatches = 0
    not_found = 0

    for metric, value in financial_data.items():
        if metric not in metric_by_period:
            print(f"  ⓘ {metric} — Supabase 無此指標")
            not_found += 1
            continue

        sb_records = metric_by_period[metric]
        sb_records_sorted = sorted(sb_records, key=lambda r: r['period'], reverse=True)
        sb_row = sb_records_sorted[0]
        sb_value = sb_row['value']
        sb_period = sb_row['period']

        if isinstance(sb_value, (int, float)):
            # 嘗試直接比較
            diff_pct = abs(value - sb_value) / max(abs(sb_value), 1) * 100

            # 檢查是否需要單位轉換
            if diff_pct > 99 and abs(value / 1000 - sb_value) < 1:
                diff_pct = abs(value / 1000 - sb_value) / max(abs(sb_value), 1) * 100
                display_value = f"{value/1000:,.0f} (÷1000)"
            else:
                display_value = f"{value:,.0f}"

            if diff_pct < 0.5:
                print(f"  ✅ {metric} ({sb_period})")
                print(f"     SEC: {display_value}")
                print(f"     SB:  {sb_value:,.0f}")
                matches += 1
            else:
                print(f"  ❌ {metric} ({sb_period}) — 差異 {diff_pct:.2f}%")
                print(f"     SEC: {display_value}")
                print(f"     SB:  {sb_value:,.0f}")
                mismatches += 1
        else:
            not_found += 1

    print(f"\n統計: ✅ {matches} 個匹配, ❌ {mismatches} 個差異, ⓘ {not_found} 個未找到")

    return {'matches': matches, 'mismatches': mismatches, 'not_found': not_found}


def main():
    if len(sys.argv) < 2:
        print("用法: python3 parse_sec.py <ticker> [form_type] [file_path]")
        print("\n範例:")
        print("  python3 parse_sec.py SNDK 10-Q")
        print("  python3 parse_sec.py MU 10-K /path/to/10k.html")
        sys.exit(1)

    ticker = sys.argv[1].upper()
    form_type = sys.argv[2] if len(sys.argv) > 2 else "10-Q"
    file_path = sys.argv[3] if len(sys.argv) > 3 else None

    # 驗證 ticker
    if not re.match(r'^[A-Z]{1,5}$', ticker):
        print(f"❌ 無效的 ticker: {ticker}")
        sys.exit(1)

    # 驗證 form_type
    if form_type not in ["10-Q", "10-K"]:
        print(f"❌ 無效的表單類型: {form_type}（應為 10-Q 或 10-K）")
        sys.exit(1)

    # 取得檔案
    if not file_path:
        try:
            file_path = download_sec_filing(ticker, form_type)
        except Exception as e:
            print(f"❌ {e}")
            sys.exit(1)
    else:
        file_path_obj = Path(file_path)
        if not file_path_obj.exists():
            print(f"❌ 檔案不存在: {file_path}")
            sys.exit(1)

    # 解析
    print(f"\n📄 解析: {Path(file_path).name}\n")
    try:
        financial_data = parse_sec_filing(file_path)
    except Exception as e:
        print(f"❌ 解析失敗: {e}")
        sys.exit(1)

    print(f"\n公司代號: {ticker}")
    print(f"表單類型: {form_type}")
    print(f"提取 {len(financial_data)} 個財務指標")

    # 比對
    compare_with_supabase(ticker, financial_data)


if __name__ == '__main__':
    main()
