#!/usr/bin/env python3
"""
台股 XBRL 批量解析 - 統一數據管道（全量版）
流程：本地 XBRL HTML → 解析所有三表 ix:nonFraction 標籤 → 寫入 financial_facts → 計算 financial_metrics
"""

import sys
import re
import json
import time
from pathlib import Path
from supabase import create_client

SUPABASE_URL = "https://zpriwdyjmqvbtaektnlq.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inpwcml3ZHlqbXF2YnRhZWt0bmxxIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3MzQ4OTYzMywiZXhwIjoyMDg5MDY1NjMzfQ.VSsBqjOgZPK142kBI3FjbezmJ3ShBtk2XD-LZo2wSmQ"

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ─────────────────────────────────────────────
# XBRL 概念 → (metric 名稱, 報表類型, 排序號)
# 報表類型：IS = 損益表 / BS = 資產負債表 / CF = 現金流量表
# 排序號對應 PDF 科目代碼，CF 用 800x 系列
# ─────────────────────────────────────────────
XBRL_MAP = {
    # ── 損益表 IS ──
    'ifrs-full:Revenue':                                                                                ('operating_revenue',              'IS', 4000),
    'tifrs-bsci-ci:OperatingCosts':                                                                    ('cost_of_revenue',                 'IS', 5000),
    'tifrs-bsci-ci:GrossProfitLossFromOperations':                                                     ('gross_profit',                    'IS', 5900),
    'ifrs-full:GrossProfit':                                                                            ('gross_profit',                    'IS', 5900),
    'ifrs-full:SellingExpense':                                                                         ('selling_expenses',                'IS', 6100),
    'ifrs-full:AdministrativeExpense':                                                                  ('general_admin_expenses',          'IS', 6200),
    'ifrs-full:ResearchAndDevelopmentExpense':                                                          ('r_and_d_expenses',                'IS', 6300),
    'ifrs-full:ImpairmentLossImpairmentGainAndReversalOfImpairmentLossDeterminedInAccordanceWithIFRS9':('expected_credit_loss',            'IS', 6450),
    'ifrs-full:OperatingExpense':                                                                       ('operating_expenses',              'IS', 6800),
    'ifrs-full:ProfitLossFromOperatingActivities':                                                      ('operating_income',                'IS', 6900),
    'ifrs-full:RevenueFromInterest':                                                                    ('interest_income',                 'IS', 7100),
    'ifrs-full:OtherRevenue':                                                                           ('other_income',                    'IS', 7010),
    'ifrs-full:OtherGainsLosses':                                                                       ('other_gains_losses',              'IS', 7020),
    'ifrs-full:FinanceCosts':                                                                           ('interest_expense',                'IS', 7050),
    'ifrs-full:ShareOfProfitLossOfAssociatesAndJointVenturesAccountedForUsingEquityMethod':             ('equity_method_income',            'IS', 7060),
    'tifrs-bsci-ci:NonoperatingIncomeAndExpenses':                                                     ('non_operating_income_expense',    'IS', 7000),
    'ifrs-full:ProfitLossBeforeTax':                                                                    ('income_before_taxes',             'IS', 7900),
    'ifrs-full:IncomeTaxExpenseContinuingOperations':                                                   ('income_tax_expense',              'IS', 7950),
    'ifrs-full:ProfitLoss':                                                                             ('net_income',                      'IS', 8200),
    'ifrs-full:OtherComprehensiveIncomeThatWillNotBeReclassifiedToProfitOrLossNetOfTax':               ('oci_not_reclassified',            'IS', 8310),
    'ifrs-full:OtherComprehensiveIncomeBeforeTaxGainsLossesFromInvestmentsInEquityInstruments':        ('oci_fvoci_equity',                'IS', 8316),
    'ifrs-full:OtherComprehensiveIncomeThatWillBeReclassifiedToProfitOrLossNetOfTax':                  ('oci_reclassified',                'IS', 8360),
    'ifrs-full:OtherComprehensiveIncomeBeforeTaxExchangeDifferencesOnTranslation':                     ('oci_fx_translation',              'IS', 8361),
    'ifrs-full:OtherComprehensiveIncome':                                                               ('other_comprehensive_income',      'IS', 8300),
    'ifrs-full:ComprehensiveIncome':                                                                    ('total_comprehensive_income',      'IS', 8500),
    'ifrs-full:ProfitLossAttributableToOwnersOfParent':                                                ('net_income_parent',               'IS', 8610),
    'ifrs-full:ProfitLossAttributableToNoncontrollingInterests':                                       ('net_income_nci',                  'IS', 8620),
    'ifrs-full:ComprehensiveIncomeAttributableToOwnersOfParent':                                       ('comprehensive_income_parent',     'IS', 8710),
    'ifrs-full:ComprehensiveIncomeAttributableToNoncontrollingInterests':                              ('comprehensive_income_nci',        'IS', 8720),
    'ifrs-full:BasicEarningsLossPerShare':                                                              ('basic_eps',                       'IS', 9710),
    'ifrs-full:BasicEarningsLossPerShareFromContinuingOperations':                                     ('basic_eps',                       'IS', 9710),
    'ifrs-full:DilutedEarningsLossPerShare':                                                            ('diluted_eps',                     'IS', 9810),
    'ifrs-full:DilutedEarningsLossPerShareFromContinuingOperations':                                   ('diluted_eps',                     'IS', 9810),

    # ── 資產負債表 BS — 資產 ──
    'ifrs-full:CashAndCashEquivalents':                                                                 ('cash_and_equivalents',            'BS', 1110),
    'ifrs-full:CurrentFinancialAssetsAtFairValueThroughProfitOrLoss':                                  ('financial_assets_fvtpl_current',  'BS', 1120),
    'ifrs-full:CurrentFinancialAssetsAtFairValueThroughOtherComprehensiveIncome':                      ('financial_assets_fvoci_current',  'BS', 1125),
    'ifrs-full:CurrentFinancialAssetsAtAmortisedCost':                                                 ('financial_assets_ac_current',     'BS', 1130),
    'tifrs-bsci-ci:AccountsReceivableNet':                                                             ('accounts_receivable',             'BS', 1150),
    'ifrs-full:OtherCurrentReceivables':                                                               ('other_receivables',               'BS', 1160),
    'ifrs-full:Inventories':                                                                            ('inventories',                     'BS', 1170),
    'ifrs-full:CurrentPrepayments':                                                                     ('prepaid_expenses',                'BS', 1180),
    'ifrs-full:CurrentTaxAssets':                                                                       ('current_tax_assets',              'BS', 1185),
    'ifrs-full:OtherCurrentAssets':                                                                     ('other_current_assets',            'BS', 1190),
    'ifrs-full:CurrentAssets':                                                                          ('total_current_assets',            'BS', 1200),
    'ifrs-full:PropertyPlantAndEquipment':                                                              ('ppe_net',                         'BS', 1510),
    'ifrs-full:RightofuseAssets':                                                                       ('right_of_use_assets',             'BS', 1515),
    'ifrs-full:IntangibleAssetsAndGoodwill':                                                            ('intangibles_and_goodwill',        'BS', 1520),
    'ifrs-full:InvestmentAccountedForUsingEquityMethod':                                               ('equity_method_investments',       'BS', 1530),
    'ifrs-full:NoncurrentFinancialAssetsAtFairValueThroughOtherComprehensiveIncome':                   ('financial_assets_fvoci_nc',       'BS', 1540),
    'ifrs-full:NoncurrentFinancialAssetsAtAmortisedCost':                                              ('financial_assets_ac_nc',          'BS', 1545),
    'ifrs-full:DeferredTaxAssets':                                                                      ('deferred_tax_assets',             'BS', 1550),
    'ifrs-full:OtherNoncurrentAssets':                                                                  ('other_noncurrent_assets',         'BS', 1560),
    'ifrs-full:NoncurrentAssets':                                                                       ('total_noncurrent_assets',         'BS', 1600),
    'ifrs-full:Assets':                                                                                 ('total_assets',                    'BS', 1900),

    # ── 資產負債表 BS — 負債 ──
    'ifrs-full:ShorttermBorrowings':                                                                    ('short_term_borrowings',           'BS', 2110),
    'ifrs-full:TradeAndOtherCurrentPayablesToTradeSuppliers':                                          ('accounts_payable',                'BS', 2150),
    'ifrs-full:TradeAndOtherCurrentPayablesToRelatedParties':                                          ('accounts_payable_related',        'BS', 2155),
    'ifrs-full:OtherCurrentPayables':                                                                   ('other_payables',                  'BS', 2160),
    'ifrs-full:CurrentContractLiabilities':                                                             ('contract_liabilities_current',    'BS', 2170),
    'ifrs-full:CurrentTaxLiabilities':                                                                  ('current_tax_liabilities',         'BS', 2180),
    'tifrs-bsci-ci:CurrentLeaseLiabilities':                                                           ('lease_liabilities_current',       'BS', 2190),
    'ifrs-full:OtherCurrentLiabilities':                                                                ('other_current_liabilities',       'BS', 2195),
    'ifrs-full:CurrentLiabilities':                                                                     ('total_current_liabilities',       'BS', 2200),
    'tifrs-bsci-ci:LongtermLiabilitiesCurrentPortion':                                                ('long_term_debt_current',          'BS', 2310),
    'tifrs-bsci-ci:LongtermNotesAndAccountsPayable':                                                   ('long_term_payables',              'BS', 2320),
    'ifrs-full:NoncurrentFinanceLeaseLiabilities':                                                     ('lease_liabilities_noncurrent',    'BS', 2330),
    'ifrs-full:DeferredTaxLiabilities':                                                                 ('deferred_tax_liabilities',        'BS', 2340),
    'ifrs-full:NoncurrentRecognisedLiabilitiesDefinedBenefitPlan':                                    ('pension_liabilities',             'BS', 2350),
    'ifrs-full:OtherNoncurrentLiabilities':                                                             ('other_noncurrent_liabilities',    'BS', 2360),
    'ifrs-full:NoncurrentLiabilities':                                                                  ('total_noncurrent_liabilities',    'BS', 2400),
    'ifrs-full:Liabilities':                                                                            ('total_liabilities',               'BS', 2900),

    # ── 資產負債表 BS — 權益 ──
    'ifrs-full:IssuedCapital':                                                                          ('common_stock',                    'BS', 3110),
    'ifrs-full:CapitalReserve':                                                                         ('capital_surplus',                 'BS', 3200),
    'ifrs-full:StatutoryReserve':                                                                       ('legal_reserve',                   'BS', 3310),
    'tifrs-bsci-ci:UnappropriatedRetainedEarningsAaccumulatedDeficit':                                ('retained_earnings',               'BS', 3320),
    'ifrs-full:OtherEquityInterest':                                                                    ('other_equity',                    'BS', 3400),
    'ifrs-full:TreasuryShares':                                                                         ('treasury_shares',                 'BS', 3500),
    'ifrs-full:EquityAttributableToOwnersOfParent':                                                    ('equity_attributable_to_parent',   'BS', 3600),
    'ifrs-full:NoncontrollingInterests':                                                                ('non_controlling_interests',       'BS', 3700),
    'ifrs-full:Equity':                                                                                 ('total_equity',                    'BS', 3900),

    # ── 現金流量表 CF ──
    'ifrs-full:CashFlowsFromUsedInOperatingActivities':                                                ('operating_cash_flow',             'CF', 8010),
    'tifrs-SCF:NetCashFlowsFromUsedInInvestingActivities':                                             ('investing_cash_flow',             'CF', 8020),
    'tifrs-SCF:CashFlowsFromUsedInFinancingActivities':                                                ('financing_cash_flow',             'CF', 8030),
    'ifrs-full:PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities':                    ('capex',                           'CF', 8021),
    'ifrs-full:AdjustmentsForDepreciationExpense':                                                      ('depreciation_expense',            'CF', 8011),
    'ifrs-full:AdjustmentsForAmortisationExpense':                                                      ('amortization_expense',            'CF', 8012),
    'ifrs-full:DividendsPaidClassifiedAsFinancingActivities':                                           ('dividends_paid',                  'CF', 8031),
    'ifrs-full:IncreaseDecreaseInCashAndCashEquivalents':                                               ('net_change_in_cash',              'CF', 8040),
    'tifrs-SCF:CashAndCashEquivalentsAtEndOfPeriod':                                                   ('ending_cash',                     'CF', 8050),
    'tifrs-SCF:CashAndCashEquivalentsAtBeginningOfPeriod':                                             ('beginning_cash',                  'CF', 8045),
}

# 派生指標
# (metric_name, formula_str, numerator_key, denominator_key, is_percent)
DERIVED_METRICS = [
    # ── IS 比率 ──
    ('gross_margin_pct',        'gross_profit / operating_revenue * 100',            'gross_profit',           'operating_revenue',         True),
    ('operating_margin_pct',    'operating_income / operating_revenue * 100',        'operating_income',       'operating_revenue',         True),
    ('pretax_margin',           'income_before_taxes / operating_revenue * 100',     'income_before_taxes',    'operating_revenue',         True),
    ('net_margin_pct',          'net_income / operating_revenue * 100',              'net_income',             'operating_revenue',         True),
    ('r_and_d_ratio',           'r_and_d_expenses / operating_revenue * 100',        'r_and_d_expenses',       'operating_revenue',         True),
    ('opex_ratio',              'operating_expenses / operating_revenue * 100',      'operating_expenses',     'operating_revenue',         True),
    ('effective_tax_rate',      'income_tax_expense / income_before_taxes * 100',    'income_tax_expense',     'income_before_taxes',       True),
    ('interest_coverage',       'operating_income / interest_expense',               'operating_income',       'interest_expense',          False),
    # ── BS 比率 ──
    ('current_ratio',           'total_current_assets / total_current_liabilities',  'total_current_assets',   'total_current_liabilities', False),
    ('debt_to_equity',          'total_liabilities / total_equity',                  'total_liabilities',      'total_equity',              False),
    ('equity_ratio',            'total_equity / total_assets',                       'total_equity',           'total_assets',              False),
    # ── IS + BS ──
    ('roe',                     'net_income / total_equity * 100',                   'net_income',             'total_equity',              True),
    ('roa',                     'net_income / total_assets * 100',                   'net_income',             'total_assets',              True),
    # ── CF 衍生 ──
    ('fcf',                     'operating_cash_flow + capex',                       'operating_cash_flow',    None,                        False),
]
# NOTE: shares_outstanding 需特殊處理：
# Q1/Q2/Q3 可從 net_income_parent / basic_eps 計算（均為單季值）
# Q4 若年報只揭露全年 EPS，應優先用 FY EPS - 9M cumulative EPS，
# 若 9M cumulative EPS 不可得才 fallback 到 FY EPS - Q1 - Q2 - Q3
# derived Q4 weighted-average shares 不寫入 financial_facts，應另存 financial_metrics


def find_local_xbrl_files(ticker: str) -> dict:
    search_dirs = [
        Path.home() / "Downloads",
        Path.home() / "Obsidian/Khouse/Semiconductors",
    ]
    pattern = f"tifrs-fr1-m1-ci-cr-{ticker}-*.html"
    files_by_period = {}
    for base_dir in search_dirs:
        for file_path in base_dir.rglob(pattern):
            m = re.search(r'(\d{4})Q(\d)', file_path.name)
            if m and f"Q{m.group(2)}_FY{m.group(1)}" not in files_by_period:
                files_by_period[f"Q{m.group(2)}_FY{m.group(1)}"] = str(file_path)
    return files_by_period


def _sort_order_to_statement(sort_order: int) -> str:
    """將 XBRL_MAP 的 sort_order 對應到前端 FactStore 期待的 statement 名稱"""
    if 1000 <= sort_order < 2000: return "balance_sheet_assets"
    if 2000 <= sort_order < 3000: return "balance_sheet_liabilities"
    if 3000 <= sort_order < 4000: return "balance_sheet_equity"
    if 8010 <= sort_order <= 8019: return "cash_flow_operating"
    if 8020 <= sort_order <= 8029: return "cash_flow_investing"
    if 8030 <= sort_order <= 8039: return "cash_flow_financing"
    if 8040 <= sort_order <= 8060: return "cash_flow_summary"
    return "income_statement"


def _parse_content(content: str, as_of_ctx: str, from_ctx: str) -> dict:
    """
    從 iXBRL HTML 提取財務數據。
    - BS 指標：用 as_of_ctx（點時間）
    - CF 的 beginning_cash / ending_cash：也用 as_of_ctx
    - IS / CF 其餘：用 from_ctx（期間）
    回傳：{metric: (value, statement, sort_order)}
    """
    # 這些 CF 指標在 XBRL 用 AsOf context，不是 From...To...
    CF_ASOF = {'beginning_cash', 'ending_cash'}

    tag_pat = re.compile(
        r'<ix:nonFraction\s+([^>]*?)>\s*([^<]*?)\s*</ix:nonFraction>',
        re.DOTALL
    )
    results = {}

    for attrs_str, raw_value in tag_pat.findall(content):
        name_m = re.search(r'\bname="([^"]+)"', attrs_str)
        ctx_m  = re.search(r'\bcontextRef="([^"]+)"', attrs_str)
        sign_m = re.search(r'\bsign="([^"]+)"', attrs_str)
        if not name_m or not ctx_m:
            continue

        xbrl_name = name_m.group(1)
        ctx       = ctx_m.group(1)
        if xbrl_name not in XBRL_MAP:
            continue

        metric_name, _stmt_raw, sort_order = XBRL_MAP[xbrl_name]
        stmt = _sort_order_to_statement(sort_order)

        # 確定這個 metric 該用哪個 context
        is_bs     = stmt.startswith('balance_sheet')
        use_as_of = is_bs or metric_name in CF_ASOF
        expected  = as_of_ctx if use_as_of else from_ctx

        # 無維度後綴、且符合期望 context
        has_member = '_' in ctx and not ctx.endswith('_Total3')
        if has_member or ctx != expected:
            continue

        val_str = re.sub(r'[,\s]', '', raw_value)
        if not val_str or val_str in ('-', '—', ''):
            continue
        try:
            value = float(val_str)
        except ValueError:
            continue

        if sign_m and sign_m.group(1) == '-':
            value = -value

        if metric_name not in results:
            results[metric_name] = (value, stmt, sort_order)

    return results


def _subtract_ytd(current: dict, prior: dict, also_is: bool = False) -> dict:
    """
    從 YTD 計算單季值：current − prior。
    - also_is=False（Q2/Q3 用）：只減 CF，IS 保留原值（已是單季）
    - also_is=True（Q4 用）：IS 和 CF 都減
    BS、ending_cash、beginning_cash 永遠不相減。
    """
    CF_STMTS = {'cash_flow_operating', 'cash_flow_investing',
                'cash_flow_financing', 'cash_flow_summary'}
    NO_SUB   = {'ending_cash', 'beginning_cash'}
    result   = dict(current)
    for metric, (cur_val, stmt, sort_order) in current.items():
        if metric in NO_SUB:
            continue
        is_cf = stmt in CF_STMTS
        is_is = stmt == 'income_statement'
        if not (is_cf or (also_is and is_is)):
            continue
        prior_val = prior.get(metric, (None,))[0]
        if prior_val is not None:
            result[metric] = (round(cur_val - prior_val, 4), stmt, sort_order)
    return result


def _drop_statements(data: dict, statements: set[str]) -> dict:
    result = {}
    for metric, (value, stmt, sort_order) in data.items():
        if stmt in statements:
            continue
        result[metric] = (value, stmt, sort_order)
    return result


def _derive_q4_eps_from_annual(
    fy_data: dict,
    year: str,
    q3_ytd_data: dict | None = None,
    files_by_period: dict | None = None,
) -> dict:
    """
    台股年報 Q4 常只揭露全年 EPS。
    優先：
      Q4 EPS = FY EPS - 9M cumulative EPS
    若 9M cumulative EPS 不可得，且 Q1/Q2/Q3 單季 EPS 都可取得，才 fallback：
      Q4 EPS = FY EPS - Q1 EPS - Q2 EPS - Q3 EPS
    """
    fbp = files_by_period or {}

    derived = {}
    for metric in ("basic_eps", "diluted_eps"):
        annual_entry = fy_data.get(metric)
        if annual_entry is None:
            continue
        annual_val, stmt, sort_order = annual_entry

        q3_cum_entry = q3_ytd_data.get(metric) if q3_ytd_data else None
        if q3_cum_entry is not None:
            derived[metric] = (
                round(annual_val - q3_cum_entry[0], 4),
                stmt,
                sort_order,
                "DERIVED_Q4_EPS_FROM_FY_MINUS_9M_CUMULATIVE_EPS",
            )
            continue

        prior_quarters: dict[str, dict] = {}
        ok = True
        for q in (1, 2, 3):
            period = f"Q{q}_FY{year}"
            file_path = fbp.get(period)
            if not file_path:
                ok = False
                break
            parsed = parse_ixbrl_full(file_path, period, fbp)
            if not parsed:
                ok = False
                break
            prior_quarters[period] = parsed
        if not ok:
            continue

        quarter_vals = []
        for q in (1, 2, 3):
            period = f"Q{q}_FY{year}"
            quarter_entry = prior_quarters.get(period, {}).get(metric)
            if quarter_entry is None:
                ok = False
                break
            quarter_vals.append(quarter_entry[0])
        if not ok:
            continue

        derived[metric] = (
            round(annual_val - sum(quarter_vals), 4),
            stmt,
            sort_order,
            "DERIVED_Q4_EPS_FROM_FY_MINUS_Q1_Q2_Q3",
        )
    return derived


def parse_ixbrl_full(file_path: str, period: str, files_by_period: dict | None = None) -> dict:
    """
    解析單季財務數據：
    ┌──────┬──────────────────────────────────────────────────────────┐
    │ Q1   │ IS/CF：From Jan-Mar（YTD = 單季），BS：AsOf Mar 31       │
    │ Q2   │ IS：From Apr-Jun（單季 context），                        │
    │      │ CF：Q2_YTD − Q1（YTD），BS：AsOf Jun 30                 │
    │ Q3   │ IS：From Jul-Sep（單季 context），                        │
    │      │ CF：Q3_YTD − Q2_YTD，BS：AsOf Sep 30                    │
    │ Q4   │ IS/CF：FY_total − Q3_YTD，BS：AsOf Dec 31（無計算）     │
    └──────┴──────────────────────────────────────────────────────────┘
    """
    m = re.match(r'Q(\d)_FY(\d{4})', period)
    if not m:
        return {}
    q, year = int(m.group(1)), m.group(2)

    # 期末日期
    end_month = q * 3
    end_day   = ['31', '30', '30', '31'][q - 1]
    as_of_ctx = f"AsOf{year}{end_month:02d}{end_day}"

    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    fbp = files_by_period or {}

    if q == 1:
        # Q1：單季 = YTD（Jan-Mar）
        from_ctx = f"From{year}0101To{year}0331"
        return _parse_content(content, as_of_ctx, from_ctx)

    if q in (2, 3):
        # IS：單季 context
        q_start_month = (q - 1) * 3 + 1
        q_start = f"{year}{q_start_month:02d}01"
        is_ctx = f"From{q_start}To{year}{end_month:02d}{end_day}"

        # CF：YTD context（From Jan to 本季末）
        cf_ytd_ctx = f"From{year}0101To{year}{end_month:02d}{end_day}"

        # 取當期：IS 用 is_ctx，CF 用 cf_ytd_ctx
        # 分兩次 parse，以 cf_ytd_ctx 為主（含 CF），再覆蓋 IS 部分
        cur_cf  = _parse_content(content, as_of_ctx, cf_ytd_ctx)   # CF YTD
        cur_is  = _parse_content(content, as_of_ctx, is_ctx)        # IS 單季

        # 合併：IS 用單季值，CF 用 YTD（稍後再相減）
        merged = {**cur_cf}
        for k, v in cur_is.items():
            stmt = _sort_order_to_statement(v[2])
            if stmt == 'income_statement':
                merged[k] = v

        # 前一季期末日期（用來找前期 YTD）
        prev_q       = q - 1
        prev_month   = prev_q * 3
        prev_day     = ['31', '30', '30', '31'][prev_q - 1]
        prev_as_of   = f"AsOf{year}{prev_month:02d}{prev_day}"
        prev_cf_ctx  = f"From{year}0101To{year}{prev_month:02d}{prev_day}"
        prev_period  = f"Q{prev_q}_FY{year}"
        prev_file    = fbp.get(prev_period)

        if prev_file:
            with open(prev_file, 'r', encoding='utf-8', errors='ignore') as f:
                prev_content = f.read()
            prior_cf = _parse_content(prev_content, prev_as_of, prev_cf_ctx)
            # 只減 CF，IS 已是單季值，不再相減
            return _subtract_ytd(merged, prior_cf, also_is=False)
        else:
            print(f"  ⚠️  找不到 {prev_period} 檔案，移除當期 CF（避免寫入 YTD）")
            return _drop_statements(merged, CF_STMTS)

    # Q4：IS/CF = FY − Q3_YTD，BS 直接用 Dec 31（AsOf20xx1231）
    fy_ctx  = f"From{year}0101To{year}1231"
    fy_data = _parse_content(content, as_of_ctx, fy_ctx)

    q3_period = f"Q3_FY{year}"
    q3_file   = fbp.get(q3_period)
    if q3_file:
        q3_as_of = f"AsOf{year}0930"
        q3_ytd   = f"From{year}0101To{year}0930"
        with open(q3_file, 'r', encoding='utf-8', errors='ignore') as f:
            q3_content = f.read()
        q3_data = _parse_content(q3_content, q3_as_of, q3_ytd)
        # IS 和 CF 都要減（Q4 = FY − Q3_YTD）
        result = _subtract_ytd(fy_data, q3_data, also_is=True)

        # FY EPS 是全年值，不能直接放進 Q4；優先用 FY - 9M cumulative EPS，
        # 若 9M cumulative EPS 不可得，才 fallback 到 FY - (Q1 + Q2 + Q3)。
        for metric in ("basic_eps", "diluted_eps"):
            result.pop(metric, None)
        result.update(_derive_q4_eps_from_annual(fy_data, year, q3_data, fbp))
        return result
    else:
        print(f"  ⚠️  找不到 Q3_FY{year} 檔案，移除 Q4 的 IS/CF（避免寫入全年數）")
        return _drop_statements(fy_data, {'income_statement', 'cash_flow_operating', 'cash_flow_investing', 'cash_flow_financing', 'cash_flow_summary'})


def parse_ixbrl_annual_facts(file_path: str, period: str) -> dict:
    """
    從 Q4 年報直接提取 FY facts。
    Annual mode 對台股應優先使用年報直接揭露值，不用季度加總替代。
    """
    m = re.match(r'Q4_FY(\d{4})', period)
    if not m:
        return {}
    year = m.group(1)
    as_of_ctx = f"AsOf{year}1231"
    fy_ctx = f"From{year}0101To{year}1231"
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    return _parse_content(content, as_of_ctx, fy_ctx)


def compute_metrics(facts_flat: dict) -> dict:
    """facts_flat: {metric: value}"""
    computed = {}
    for name, formula, num_k, den_k, pct in DERIVED_METRICS:
        num = facts_flat.get(num_k)
        if num is None:
            continue

        if den_k is None:
            # 加法型指標（如 FCF = OCF + capex）
            # formula 格式：'a + b'，從 facts_flat 加總
            operands = [k.strip() for k in formula.split('+')]
            total = 0.0
            ok = True
            for k in operands:
                v = facts_flat.get(k)
                if v is None:
                    ok = False
                    break
                total += v
            if ok:
                computed[name] = (round(total, 4), formula)
            continue

        den = facts_flat.get(den_k)
        if den is None or den == 0:
            continue
        # pct 指標存小數（0.4814），不乘 100，與前端 fmtVal(val*100) 一致
        computed[name] = (round(num / den, 6), formula)
    return computed


def encode_annual_direct_metric(statement: str, metric: str) -> str:
    return f"annual_direct__{statement}__{metric}"


def period_to_end_date(period: str) -> str:
    m = re.match(r'Q(\d)_FY(\d{4})', period)
    q, year = int(m.group(1)), m.group(2)
    month = q * 3
    day = ['31', '30', '30', '31'][q - 1]
    return f"{year}-{month:02d}-{day}"


def extract_company_name(file_path: str, ticker: str) -> str:
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    patterns = [
        r'<ix:nonNumeric name="tifrs-notes:CompanyChineseName"[^>]*>([^<]+)</ix:nonNumeric>',
        r'<ix:nonNumeric name="tifrs-notes:CompanyName"[^>]*>([^<]+)</ix:nonNumeric>',
        r'<span class="zh">\s*' + re.escape(ticker) + r'\s+([^<]+?)<br',
    ]
    for pattern in patterns:
        m = re.search(pattern, content, re.DOTALL)
        if m:
            return m.group(1).strip()
    return ticker


def ensure_company_entry(ticker: str, file_path: str) -> None:
    company_name = extract_company_name(file_path, ticker)
    record = {
        'ticker': ticker,
        'company': company_name,
        'cik': None,
        'exchange': 'TWSE',
        'currency': 'TWD',
        'fiscal_year_end_month': 12,
        'last_updated': time.strftime('%Y-%m-%d'),
        'notes': 'TWSE MOPS iXBRL consolidated financial statements parsed from local HTML files.',
    }
    supabase.table('financial_companies').upsert(record, on_conflict='ticker').execute()


def write_financial_facts(ticker: str, period: str, period_end: str, facts: dict, default_source: str = 'XBRL_TWSE') -> int:
    """facts: {metric: (value, statement, sort_order) | (value, statement, sort_order, source)}"""
    records = []
    for metric, payload in facts.items():
        value, stmt, sort_order = payload[:3]
        source = payload[3] if len(payload) >= 4 else default_source
        records.append({
            'ticker':     ticker,
            'period':     period,
            'period_end': period_end,
            'statement':  stmt,
            'metric':     metric,
            'value':      value,
            'unit':       None,
            'dimension':  '',
            'source':     source,
        })
    if records:
        supabase.table('financial_facts').upsert(records, ignore_duplicates=False).execute()
    return len(records)


def write_financial_metrics(ticker: str, period: str, period_end: str, computed: dict, source: str = 'COMPUTED_FROM_XBRL_TWSE') -> int:
    records = []
    for metric, (value, formula) in computed.items():
        records.append({
            'ticker':     ticker,
            'period':     period,
            'period_end': period_end,
            'metric':     metric,
            'value':      value,
            'formula':    formula,
            'source':     source,
        })
    if records:
        supabase.table('financial_metrics').upsert(records, on_conflict='ticker,period,metric,source').execute()
    return len(records)


def purge_legacy_annual_direct_metrics(ticker: str, period: str) -> None:
    supabase.table('financial_metrics') \
        .delete() \
        .eq('ticker', ticker) \
        .eq('period', period) \
        .eq('source', 'ANNUAL_DIRECT_XBRL_TWSE') \
        .execute()


def parse_and_insert(ticker: str, period: str, file_path: str, files_by_period: dict | None = None) -> bool:
    print(f"\n📄 {period}")

    facts = parse_ixbrl_full(file_path, period, files_by_period)
    if not facts:
        print(f"  ⚠️  無數據")
        return False

    facts_flat = {k: payload[0] for k, payload in facts.items()}
    by_stmt = {}
    for m, payload in facts.items():
        _v, s, _sort_order = payload[:3]
        by_stmt.setdefault(s, 0)
        by_stmt[s] += 1
    print(f"  ✓ 解析 {len(facts)} 項：" + ", ".join(f"{s}={n}" for s, n in sorted(by_stmt.items())))

    period_end = period_to_end_date(period)
    computed   = compute_metrics(facts_flat)
    print(f"  ✓ 計算 {len(computed)} 項派生指標")

    try:
        n_facts   = write_financial_facts(ticker, period, period_end, facts)
        n_metrics = write_financial_metrics(ticker, period, period_end, computed)
        annual_note = ""
        if period.startswith("Q4_"):
            fy_period = period.replace("Q4_", "")
            annual_facts = parse_ixbrl_annual_facts(file_path, period)
            annual_flat = {k: payload[0] for k, payload in annual_facts.items()}
            annual_metrics = compute_metrics(annual_flat)
            fy_end = period_end
            purge_legacy_annual_direct_metrics(ticker, fy_period)
            annual_fact_written = write_financial_facts(
                ticker,
                fy_period,
                fy_end,
                annual_facts,
                default_source='XBRL_TWSE_ANNUAL_DIRECT',
            )
            annual_metric_written = write_financial_metrics(
                ticker,
                fy_period,
                fy_end,
                annual_metrics,
                source='COMPUTED_FROM_XBRL_TWSE',
            )
            n_facts += annual_fact_written
            n_metrics += annual_metric_written
            annual_note = f" + annual_facts={annual_fact_written} + annual_metrics={annual_metric_written}"
        print(f"  ✓ 寫入 facts={n_facts}, metrics={n_metrics}{annual_note}")
        return True
    except Exception as e:
        print(f"  ✗ 寫入失敗: {e}")
        import traceback; traceback.print_exc()
        return False


def main():
    if len(sys.argv) < 2:
        print("用法: python3 batch_parse.py <ticker> [periods...]")
        print("  python3 batch_parse.py 2454")
        print("  python3 batch_parse.py 2454 Q4_FY2025")
        sys.exit(1)

    ticker = sys.argv[1]
    requested = [a for a in sys.argv[2:] if not a.startswith('--')]

    files = find_local_xbrl_files(ticker)
    if not files:
        print(f"❌ 找不到 {ticker} 的 XBRL 檔案")
        sys.exit(1)

    periods = {p: files[p] for p in requested if p in files} if requested else files
    missing = [p for p in requested if p not in files]
    if missing:
        print(f"⚠️  找不到: {', '.join(missing)}")

    seed_file = next(iter(periods.values()))
    ensure_company_entry(ticker, seed_file)

    print(f"\n📊 解析 {ticker} — {len(periods)} 個期別")
    ok = sum(parse_and_insert(ticker, p, periods[p], files) for p in sorted(periods, reverse=True))
    print(f"\n{'='*50}")
    print(f"完成: {ok}/{len(periods)}")


if __name__ == '__main__':
    main()
