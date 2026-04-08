#!/usr/bin/env python3
"""
台股 XBRL 批量解析 - 統一數據管道
流程：本地 XBRL HTML → 解析 → NotebookLM 驗證 → 寫入 financial_facts → 計算 financial_metrics
"""

import sys
import re
import json
import time
from pathlib import Path
from collections import defaultdict
from lxml import html as html_lib
from supabase import create_client

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

# 派生指標計算規則：(metric_name, formula_str, numerator_key, denominator_key, is_percent)
DERIVED_METRICS = [
    ('current_ratio',  'total_current_assets / total_current_liabilities',  'total_current_assets',   'total_current_liabilities', False),
    ('debt_to_equity', 'total_liabilities / total_equity',                  'total_liabilities',      'total_equity',              False),
    ('equity_ratio',   'total_equity / total_assets',                       'total_equity',           'total_assets',              False),
    ('net_margin_pct', 'net_income / operating_revenue * 100',              'net_income',             'operating_revenue',         True),
    ('roe',            'net_income / total_equity * 100',                   'net_income',             'total_equity',              True),
    ('roa',            'net_income / total_assets * 100',                   'net_income',             'total_assets',              True),
    ('pretax_margin',  'income_before_taxes / operating_revenue * 100',     'income_before_taxes',    'operating_revenue',         True),
]

INCOME_METRICS = {'operating_revenue', 'income_before_taxes', 'net_income'}


def find_local_xbrl_files(ticker: str) -> dict:
    """
    在本地尋找所有 XBRL 檔案，搜尋順序：
    1. ~/Downloads/
    2. iCloud Obsidian Vault（Semiconductors/{TICKER}/MOPS Filings/XML/）
    """
    search_dirs = [
        Path.home() / "Downloads",
        Path.home() / "Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian/Khouse/Semiconductors",
    ]

    pattern = f"tifrs-fr1-m1-ci-cr-{ticker}-*.html"
    files_by_period = {}

    for base_dir in search_dirs:
        # 直接搜尋 base_dir
        for file_path in base_dir.glob(pattern):
            _add_xbrl_file(files_by_period, file_path)

        # 搜尋子目錄（Obsidian vault 有額外層級）
        for file_path in base_dir.rglob(pattern):
            _add_xbrl_file(files_by_period, file_path)

    return files_by_period


def _add_xbrl_file(files_by_period: dict, file_path: Path):
    match = re.search(r'(\d{4})Q(\d)', file_path.name)
    if match:
        year = match.group(1)
        quarter = match.group(2)
        period = f"Q{quarter}_FY{year}"
        if period not in files_by_period:  # 先找到的優先（Downloads > Obsidian）
            files_by_period[period] = str(file_path)


def parse_ixbrl_html(file_path: str) -> dict:
    """解析 iXBRL HTML，提取財務指標"""
    with open(file_path, 'rb') as f:
        root = html_lib.parse(f).getroot()

    metric_candidates = {}
    for table in root.xpath('//table'):
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
                    text = re.sub(r'[,\s]', '', cell.text_content().strip())
                    if text and text.lstrip('-').replace('.', '').isdigit():
                        try:
                            value = float(text)
                            is_chinese = any('\u4e00' <= c <= '\u9fff' for c in tw_name)
                            score = 1 if is_chinese else 0
                            if metric_key not in metric_candidates:
                                metric_candidates[metric_key] = []
                            metric_candidates[metric_key].append((score, value))
                        except ValueError:
                            pass
                        break

    return {k: max(v, key=lambda x: x[0])[1] for k, v in metric_candidates.items()}


def compute_metrics(facts: dict) -> dict:
    """根據原始指標計算派生比率"""
    computed = {}
    for metric_name, formula, num_key, den_key, pct in DERIVED_METRICS:
        num = facts.get(num_key)
        den = facts.get(den_key)
        if num is None or den is None or den == 0:
            continue
        computed[metric_name] = (round(num / den * (100 if pct else 1), 4), formula)
    return computed


def period_to_end_date(period: str) -> str:
    """將 Q{n}_FY{year} 轉成期末日"""
    parts = period.split('_')
    q = int(parts[0][1:])
    year = parts[1][2:]
    month = q * 3
    last_day = ['31', '30', '30', '31'][q - 1]
    return f"{year}-{month:02d}-{last_day}"


def query_notebooklm_for_verification(ticker: str, period: str, parsed: dict, notebook_name: str = None) -> list:
    """
    從 NotebookLM 查詢該 ticker 的對應期別數據，回傳差異列表。
    需要 Claude Code agent 透過 NotebookLM MCP 執行，此函式為接口定義。

    參數：
      notebook_name：筆記本名稱（如「聯發科研究筆記」），由用戶在執行時提供
    回傳：
      [(metric, xbrl_value, nb_value, diff_pct), ...]
    """
    # 由 Claude Code agent 執行時：
    # 1. 用 notebook_name 呼叫 notebooklm.notebook_list() 找到對應 notebook_id
    # 2. 呼叫 notebooklm.notebook_query(id, f"{ticker} {period} 各項財務指標")
    # 3. 解析回傳，提取各 metric 的數值，與 parsed 逐一比對
    # 4. 回傳差異 > 1% 的項目
    return []


def write_financial_facts(ticker: str, period: str, period_end: str, facts: dict) -> int:
    """寫入 financial_facts（XBRL 原始數據）"""
    records = []
    for metric, value in facts.items():
        records.append({
            'ticker': ticker,
            'period': period,
            'period_end': period_end,
            'statement': 'income_statement' if metric in INCOME_METRICS else 'balance_sheet',
            'metric': metric,
            'value': value,
            'unit': None,
            'dimension': '',
            'source': 'XBRL_TWSE'
        })
    if records:
        supabase.table('financial_facts').upsert(records, ignore_duplicates=False).execute()
    return len(records)


def write_financial_metrics(ticker: str, period: str, period_end: str, computed: dict) -> int:
    """寫入 financial_metrics（派生指標）"""
    records = []
    for metric, (value, formula) in computed.items():
        records.append({
            'ticker': ticker,
            'period': period,
            'period_end': period_end,
            'metric': metric,
            'value': value,
            'formula': formula,
            'source': 'COMPUTED_FROM_XBRL_TWSE'
        })
    if records:
        supabase.table('financial_metrics').upsert(records, on_conflict='ticker,period,metric,source').execute()
    return len(records)


def parse_and_insert(ticker: str, period: str, file_path: str, skip_verify: bool = False, notebook_name: str = None) -> bool:
    """完整管道：解析 → 驗證 → 寫入 facts → 寫入 metrics"""
    print(f"\n📄 {period}")

    # Step 1: 解析
    try:
        facts = parse_ixbrl_html(file_path)
        if not facts:
            print(f"  ⚠️  無數據")
            return False
        print(f"  ✓ 解析 {len(facts)} 項原始指標")
    except Exception as e:
        print(f"  ✗ 解析失敗: {e}")
        return False

    period_end = period_to_end_date(period)

    # Step 2: NotebookLM 驗證（有差異則人工複審）
    if not skip_verify:
        diffs = query_notebooklm_for_verification(ticker, period, facts, notebook_name)
        if diffs:
            print(f"  ⚠️  NotebookLM 差異 {len(diffs)} 項（需人工複審）:")
            for metric, xbrl_val, nb_val, diff_pct in diffs:
                print(f"     {metric}: XBRL={xbrl_val:,.0f} / NB={nb_val:,.0f} ({diff_pct:+.1f}%)")
            # 繼續寫入，但標記待複審
    else:
        print(f"  → 跳過 NotebookLM 驗證")

    # Step 3: 計算派生指標
    computed = compute_metrics(facts)
    print(f"  ✓ 計算 {len(computed)} 項派生指標")

    # Step 4: 寫入 Supabase
    try:
        n_facts = write_financial_facts(ticker, period, period_end, facts)
        n_metrics = write_financial_metrics(ticker, period, period_end, computed)
        print(f"  ✓ 寫入 facts={n_facts}, metrics={n_metrics}")
        return True
    except Exception as e:
        print(f"  ✗ 寫入失敗: {e}")
        return False


def main():
    if len(sys.argv) < 2:
        print("用法: python3 batch_parse.py <ticker> [--skip-verify] [--notebook <name>] [periods...]")
        print("\n範例:")
        print("  python3 batch_parse.py 2454                              # 解析所有本地檔案（會詢問筆記本名稱）")
        print("  python3 batch_parse.py 2454 --skip-verify               # 跳過 NotebookLM 驗證")
        print("  python3 batch_parse.py 2454 --notebook 聯發科研究筆記   # 指定筆記本名稱")
        print("  python3 batch_parse.py 2454 Q4_FY2025                   # 只解析指定期別")
        sys.exit(1)

    ticker = sys.argv[1]
    args = sys.argv[2:]
    skip_verify = '--skip-verify' in args

    # 解析 --notebook 參數
    notebook_name = None
    if '--notebook' in args:
        nb_idx = args.index('--notebook')
        if nb_idx + 1 < len(args):
            notebook_name = args[nb_idx + 1]
            args = [a for i, a in enumerate(args) if i != nb_idx and i != nb_idx + 1]

    # 若未提供筆記本且未跳過驗證，互動式詢問
    if not skip_verify and notebook_name is None:
        print("📚 NotebookLM 驗證：請提供筆記本名稱")
        print("   （直接按 Enter 跳過驗證）")
        try:
            name = input("   筆記本名稱: ").strip()
            if name:
                notebook_name = name
            else:
                skip_verify = True
        except (EOFError, KeyboardInterrupt):
            skip_verify = True

    requested_periods = [a for a in args if not a.startswith('--')]

    files_by_period = find_local_xbrl_files(ticker)
    if not files_by_period:
        print(f"❌ 找不到 {ticker} 的 XBRL 檔案（Downloads 目錄）")
        sys.exit(1)

    if requested_periods:
        periods_to_parse = {p: files_by_period[p] for p in requested_periods if p in files_by_period}
        missing = [p for p in requested_periods if p not in files_by_period]
        if missing:
            print(f"⚠️  找不到以下期別的檔案: {', '.join(missing)}")
    else:
        periods_to_parse = files_by_period

    print(f"\n📊 解析 {ticker} — {len(periods_to_parse)} 個期別\n")
    if skip_verify:
        print("  （已跳過 NotebookLM 驗證）\n")

    success = 0
    for period in sorted(periods_to_parse.keys(), reverse=True):
        if parse_and_insert(ticker, period, periods_to_parse[period], skip_verify, notebook_name):
            success += 1
        time.sleep(0.3)

    print(f"\n{'='*50}")
    print(f"完成: {success}/{len(periods_to_parse)} 個期別")
    print(f"  financial_facts  → XBRL_TWSE")
    print(f"  financial_metrics → COMPUTED_FROM_XBRL_TWSE")


if __name__ == '__main__':
    main()
