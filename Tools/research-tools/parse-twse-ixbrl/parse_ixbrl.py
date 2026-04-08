#!/usr/bin/env python3
"""
台股 XBRL 解析 skill 執行器
用法: python3 parse_ixbrl.py <ticker> [file_path]
"""

import sys
import re
from pathlib import Path
from lxml import html as html_lib
from supabase import create_client

# Supabase 配置
SUPABASE_URL = "https://zpriwdyjmqvbtaektnlq.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inpwcml3ZHlqbXF2YnRhZWt0bmxxIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3MzQ4OTYzMywiZXhwIjoyMDg5MDY1NjMzfQ.VSsBqjOgZPK142kBI3FjbezmJ3ShBtk2XD-LZo2wSmQ"

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# 關鍵指標對應表（台股報表 → 標準欄位名）
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
    'Equity': 'total_equity',
}


def find_ixbrl_file(ticker: str) -> str:
    """自動尋找下載目錄中最新的 XBRL 檔案"""
    download_dir = Path.home() / "Downloads"

    if not download_dir.exists():
        raise FileNotFoundError(f"下載目錄不存在: {download_dir}")

    # 尋找符合模式的檔案：tifrs-fr1-m1-ci-cr-{ticker}-*.html
    pattern = f"tifrs-fr1-m1-ci-cr-{ticker}-*.html"
    matching_files = list(download_dir.glob(pattern))

    if not matching_files:
        raise FileNotFoundError(
            f"找不到 {ticker} 的 XBRL 檔案\n"
            f"請從 TWSE 下載:\n"
            f"https://mopsov.twse.com.tw/server-java/t164sb01?step=1&CO_ID={ticker}&SYEAR=2025&SSEASON=4"
        )

    # 返回最新的檔案
    latest_file = max(matching_files, key=lambda p: p.stat().st_mtime)
    return str(latest_file)


def parse_ixbrl_html(file_path: str) -> dict:
    """從 iXBRL HTML 解析財務數據"""

    with open(file_path, 'rb') as f:
        doc_parsed = html_lib.parse(f)
        root = doc_parsed.getroot()

    company_info = {
        'ticker': Path(file_path).stem.split('-')[5],  # 從檔名提取 ticker
        'period': 'FY2025_Q4'
    }

    # 提取數值
    financial_data = {}
    tables = root.xpath('//table')

    print(f"  找到 {len(tables)} 個表格\n")

    # 先蒐集所有候選，然後按優先級選擇
    metric_candidates = {}

    for table_idx, table in enumerate(tables):
        rows = table.xpath('.//tr')
        for row_idx, row in enumerate(rows):
            cells = row.xpath('.//td | .//th')
            if len(cells) < 2:
                continue

            label_text = cells[1].text_content().strip() if len(cells) > 1 else cells[0].text_content().strip()

            # 檢查所有指標
            for tw_name, metric_key in METRIC_MAPPING.items():
                if tw_name not in label_text:
                    continue

                # 取第一個數字
                for cell in cells[2:]:
                    text = cell.text_content().strip()
                    cleaned = re.sub(r'[,\s]', '', text)
                    if cleaned and cleaned.lstrip('-').replace('.', '').isdigit():
                        try:
                            value = float(cleaned)
                            # 優先級：1 = 中文匹配，0 = 英文匹配
                            is_chinese = any('\u4e00' <= c <= '\u9fff' for c in tw_name)
                            score = 1 if is_chinese else 0

                            if metric_key not in metric_candidates:
                                metric_candidates[metric_key] = []

                            metric_candidates[metric_key].append((score, tw_name, value, table_idx, row_idx))
                        except ValueError:
                            pass
                        break

    # 選擇最佳候選（優先級最高）
    for metric_key, candidates in metric_candidates.items():
        best = max(candidates, key=lambda x: x[0])
        score, tw_name, value, table_idx, row_idx = best

        financial_data[metric_key] = value
        print(f"  表 {table_idx + 1} 行 {row_idx}: {tw_name}")
        print(f"    → {metric_key} = {value:,.0f}")

    return {
        'info': company_info,
        'metrics': financial_data,
    }


def compare_with_supabase(ticker: str, parsed_data: dict):
    """與 Supabase 的數據比對"""

    print(f"\n🔍 與 Supabase 比對 (ticker={ticker}):\n")

    # 查詢 Supabase（查所有期別）
    result = supabase.table('financial_facts').select('metric, value, period').eq('ticker', ticker).limit(500).execute()

    if not result.data:
        print(f"  ⚠️  Supabase 中沒有 {ticker} 的數據")
        return

    # 按指標分組所有期別的記錄
    metric_by_period = {}
    for row in result.data:
        metric = row['metric']
        if metric not in metric_by_period:
            metric_by_period[metric] = []
        metric_by_period[metric].append(row)

    # 比對
    matches = 0
    mismatches = 0
    not_found = 0

    for metric, value in parsed_data['metrics'].items():
        if metric not in metric_by_period:
            print(f"  ⓘ {metric} — Supabase 無此指標")
            not_found += 1
            continue

        sb_records = metric_by_period[metric]
        # 按期別排序，取最新的
        sb_records_sorted = sorted(sb_records, key=lambda r: r['period'], reverse=True)
        sb_row = sb_records_sorted[0]
        sb_value = sb_row['value']
        sb_period = sb_row['period']

        # 比較（允許單位差異）
        if isinstance(sb_value, (int, float)):
            # 先嘗試直接比較
            diff_pct = abs(value - sb_value) / max(abs(sb_value), 1) * 100

            # 如果差異很大，試試看單位是否差 1000 倍
            if diff_pct > 99 and abs(value / 1000 - sb_value) < 1:
                # 將 XBRL 值轉換為千位
                diff_pct = abs(value / 1000 - sb_value) / max(abs(sb_value), 1) * 100
                xbrl_display = f"{value/1000:,.0f} (÷1000)"
            else:
                xbrl_display = f"{value:,.0f}"

            if diff_pct < 0.5:
                print(f"  ✅ {metric} ({sb_period})")
                print(f"     XBRL: {xbrl_display}")
                print(f"     SB:   {sb_value:,.0f}")
                matches += 1
            else:
                print(f"  ❌ {metric} ({sb_period}) — 差異 {diff_pct:.2f}%")
                print(f"     XBRL: {xbrl_display}")
                print(f"     SB:   {sb_value:,.0f}")
                mismatches += 1
        else:
            not_found += 1

    print(f"\n統計: ✅ {matches} 個匹配, ❌ {mismatches} 個差異, ⓘ {not_found} 個未找到")

    return {'matches': matches, 'mismatches': mismatches, 'not_found': not_found}


def main():
    # 解析命令行參數
    if len(sys.argv) < 2:
        print("用法: python3 parse_ixbrl.py <ticker> [file_path]")
        print("\n範例:")
        print("  python3 parse_ixbrl.py 2454")
        print("  python3 parse_ixbrl.py 2454 /path/to/file.html")
        sys.exit(1)

    ticker = sys.argv[1]
    file_path = sys.argv[2] if len(sys.argv) > 2 else None

    # 驗證 ticker
    if not re.match(r'^\d{4}$', ticker):
        print(f"❌ 無效的 ticker: {ticker}（應為 4 位數字）")
        sys.exit(1)

    # 尋找或驗證檔案
    if not file_path:
        print(f"📂 自動尋找 {ticker} 的 XBRL 檔案...")
        try:
            file_path = find_ixbrl_file(ticker)
            print(f"   ✅ 找到: {Path(file_path).name}\n")
        except FileNotFoundError as e:
            print(f"❌ {e}")
            sys.exit(1)
    else:
        file_path_obj = Path(file_path)
        if not file_path_obj.exists():
            print(f"❌ 檔案不存在: {file_path}")
            sys.exit(1)

    # 解析
    print(f"📄 解析: {Path(file_path).name}\n")
    try:
        parsed = parse_ixbrl_html(file_path)
    except Exception as e:
        print(f"❌ 解析失敗: {e}")
        sys.exit(1)

    print(f"\n公司信息: {parsed['info']}")
    print(f"提取 {len(parsed['metrics'])} 個財務指標")

    # 與 Supabase 比對
    result = compare_with_supabase(ticker, parsed)

    # 返回 exit code（0 = 全部匹配，1 = 有差異）
    sys.exit(0 if result['mismatches'] == 0 and result['not_found'] == 0 else 1)


if __name__ == '__main__':
    main()
