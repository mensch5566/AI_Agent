#!/usr/bin/env python3
"""
台股 XBRL 批量解析 - 自動下載並解析多個期別
"""

import sys
import re
import time
from pathlib import Path
from lxml import html as html_lib
from supabase import create_client
import requests

SUPABASE_URL = "https://zpriwdyjmqvbtaektnlq.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inpwcml3ZHlqbXF2YnRhZWt0bmxxIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3MzQ4OTYzMywiZXhwIjoyMDg5MDY1NjMzfQ.VSsBqjOgZPK142kBI3FjbezmJ3ShBtk2XD-LZo2wSmQ"

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

METRIC_MAPPING = {
    '營業收入合計': 'operating_revenue',
    'Total operating revenue': 'operating_revenue',
    '繼續營業單位稅前淨利': 'income_before_taxes',
    'Profit (loss) from continued operations': 'income_before_taxes',
    '本期淨利': 'net_income',
    'Profit (loss) for the period': 'net_income',
    '流動資產合計': 'total_current_assets',
    'Total current assets': 'total_current_assets',
    '資產總計': 'total_assets',
    'Total assets': 'total_assets',
    '流動負債合計': 'total_current_liabilities',
    'Total current liabilities': 'total_current_liabilities',
    '負債總計': 'total_liabilities',
    'Total liabilities': 'total_liabilities',
    '權益總額': 'total_equity',
    'Total equity': 'total_equity',
}


def find_local_xbrl_files(ticker: str) -> dict:
    """在本地尋找所有 XBRL 檔案"""

    download_dir = Path.home() / "Downloads"
    pattern = f"tifrs-fr1-m1-ci-cr-{ticker}-*.html"

    files_by_period = {}
    for file_path in download_dir.glob(pattern):
        # 從檔名提取期別：tifrs-fr1-m1-ci-cr-2454-2025Q4.html
        match = re.search(r'(\d{4})Q(\d)', file_path.name)
        if match:
            year = match.group(1)
            quarter = match.group(2)
            period = f"Q{quarter}_FY{year}"
            files_by_period[period] = str(file_path)

    return files_by_period


def parse_ixbrl_html(file_path: str) -> dict:
    """解析 iXBRL HTML"""

    with open(file_path, 'rb') as f:
        doc_parsed = html_lib.parse(f)
        root = doc_parsed.getroot()

    financial_data = {}
    tables = root.xpath('//table')

    metric_candidates = {}

    for table_idx, table in enumerate(tables):
        rows = table.xpath('.//tr')
        for row_idx, row in enumerate(rows):
            cells = row.xpath('.//td | .//th')
            if len(cells) < 2:
                continue

            label_text = cells[1].text_content().strip() if len(cells) > 1 else cells[0].text_content().strip()

            for tw_name, metric_key in METRIC_MAPPING.items():
                if tw_name not in label_text:
                    continue

                for cell in cells[2:]:
                    text = cell.text_content().strip()
                    cleaned = re.sub(r'[,\s]', '', text)
                    if cleaned and cleaned.lstrip('-').replace('.', '').isdigit():
                        try:
                            value = float(cleaned)
                            is_chinese = any('\u4e00' <= c <= '\u9fff' for c in tw_name)
                            score = 1 if is_chinese else 0

                            if metric_key not in metric_candidates:
                                metric_candidates[metric_key] = []

                            metric_candidates[metric_key].append((score, tw_name, value, table_idx, row_idx))
                        except ValueError:
                            pass
                        break

    for metric_key, candidates in metric_candidates.items():
        best = max(candidates, key=lambda x: x[0])
        score, tw_name, value, table_idx, row_idx = best
        financial_data[metric_key] = value

    return financial_data


def parse_and_insert(ticker: str, period: str, file_path: str) -> bool:
    """解析並寫入 Supabase"""

    print(f"\n📄 {period}: 解析中...", end=" ")

    try:
        financial_data = parse_ixbrl_html(file_path)

        # 提取期末日期
        year, quarter = period.split('_')[0][1:], period.split('_')[0][0]
        quarter_num = int(quarter)
        month = quarter_num * 3
        period_end = f"{year}-{month:02d}-{['31', '30', '30', '31'][quarter_num-1]}"

        # 準備寫入的記錄
        records = []
        for metric, value in financial_data.items():
            records.append({
                'ticker': ticker,
                'period': period,
                'period_end': period_end,
                'statement': 'income_statement' if metric in ['operating_revenue', 'income_before_taxes', 'net_income'] else 'balance_sheet',
                'metric': metric,
                'value': value,  # 已轉換成千元
                'unit': None,
                'dimension': '',
                'source': 'XBRL_TWSE'
            })

        # 寫入
        if records:
            supabase.table('financial_facts').upsert(records, ignore_duplicates=False).execute()
            print(f"✅ ({len(records)} 項)")
            return True
        else:
            print(f"⚠️ (無數據)")
            return False

    except Exception as e:
        print(f"❌ {e}")
        return False


def main():
    if len(sys.argv) < 2:
        print("用法: python3 batch_parse.py <ticker> [periods]")
        print("\n範例:")
        print("  python3 batch_parse.py 2454             # 解析所有本地檔案")
        print("  python3 batch_parse.py 2454 Q1_FY2024 Q2_FY2024")
        sys.exit(1)

    ticker = sys.argv[1]
    requested_periods = sys.argv[2:] if len(sys.argv) > 2 else None

    # 尋找本地 XBRL 檔案
    files_by_period = find_local_xbrl_files(ticker)

    if not files_by_period:
        print(f"❌ 找不到 {ticker} 的 XBRL 檔案")
        print(f"   請先從 TWSE 下載: https://mopsov.twse.com.tw/server-java/t164sb01?step=1&CO_ID={ticker}")
        sys.exit(1)

    # 過濾要解析的期別
    if requested_periods:
        periods_to_parse = {p: files_by_period[p] for p in requested_periods if p in files_by_period}
    else:
        periods_to_parse = files_by_period

    if not periods_to_parse:
        print(f"❌ 未找到要求的期別")
        sys.exit(1)

    print(f"\n📊 批量解析 {ticker} - {len(periods_to_parse)} 個期別\n")

    success_count = 0
    for period in sorted(periods_to_parse.keys(), reverse=True):
        file_path = periods_to_parse[period]
        if parse_and_insert(ticker, period, file_path):
            success_count += 1
        time.sleep(0.5)  # 避免 API 限速

    print(f"\n✅ 完成: {success_count}/{len(periods_to_parse)} 個期別")


if __name__ == '__main__':
    main()
