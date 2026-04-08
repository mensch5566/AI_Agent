/* eslint-disable @typescript-eslint/no-explicit-any */

export type ValMap = Record<string, number | null>;
export type FinData = any;

export const TICKER_LABELS: Record<string, string> = {
  "2454": "聯發科",
};

export const LABEL_MAP: Record<string, string> = {
  revenue: "Revenue",
  cost_of_goods_sold: "Cost of Goods Sold",
  cost_of_goods_and_services_sold: "Cost of Goods Sold",
  gross_profit: "Gross Profit",
  gross_margin: "Gross Margin",
  gross_margin_pct: "  Gross Margin %",
  research_and_development: "R&D Expense",
  selling_general_administrative: "SG&A Expense",
  selling_general_and_administrative: "SG&A Expense",
  restructuring_charges: "Restructuring Charges",
  advanced_technology_costs: "Advanced Technology Costs",
  equity_related_compensation: "Equity-related Compensation",
  amortization_of_intangible_assets: "Amortization of Intangibles",
  operating_expenses: "Operating Expenses",
  other_operating_income_expense_net: "Other Operating Income/Exp",
  operating_income: "Operating Income (Loss)",
  operating_margin_pct: "  Operating Margin %",
  interest_expense: "Interest Expense",
  interest_income: "Interest Income",
  interest_income_net: "Interest Income (net)",
  investment_income: "Investment Income",
  other_nonoperating_income_expense: "Other Non-op Income/Exp",
  nonoperating_income_expense_total: "Total Interest and Other Income (Expense), net",
  total_operating_expenses: "Total Operating Expenses",
  income_before_taxes: "Income Before Taxes",
  income_tax_expense: "Income Tax Expense",
  income_tax_provision: "Income Tax Provision",
  effective_tax_rate: "  Effective Tax Rate",
  equity_method_investments: "Equity Method Investments",
  equity_in_net_income_of_investees: "Equity in Investees",
  net_income: "Net Income (Loss)",
  net_margin_pct: "  Net Margin %",
  eps_basic: "EPS — Basic",
  eps_diluted: "EPS — Diluted",
  shares_basic_millions: "Shares Basic (M)",
  shares_diluted_millions: "Shares Diluted (M)",
  cash_and_cash_equivalents: "Cash & Cash Equivalents",
  short_term_investments: "Short-term Investments",
  accounts_receivable: "Accounts Receivable",
  receivables: "Receivables",
  inventories: "Inventories",
  other_current_assets: "Other Current Assets",
  total_current_assets: "Total Current Assets",
  property_plant_equipment_net: "PP&E (net)",
  operating_lease_rou_asset: "Operating Lease ROU",
  operating_lease_right_of_use: "Operating Lease ROU",
  long_term_marketable_investments: "LT Marketable Investments",
  goodwill: "Goodwill",
  intangible_assets: "Intangible Assets",
  deferred_tax_assets: "Deferred Tax Assets",
  deferred_tax_assets_net: "Deferred Tax Assets (net)",
  other_noncurrent_assets: "Other Noncurrent Assets",
  total_assets: "Total Assets",
  accounts_payable_and_accrued_expenses: "AP & Accrued Expenses",
  accrued_liabilities_current: "Accrued Liabilities",
  employee_related_liabilities_current: "Employee Liabilities",
  current_debt: "Current Debt",
  operating_lease_liability_current: "Operating Lease (Current)",
  other_current_liabilities: "Other Current Liabilities",
  total_current_liabilities: "Total Current Liabilities",
  long_term_debt: "Long-term Debt",
  long_term_debt_noncurrent: "Long-term Debt",
  noncurrent_operating_lease_liabilities: "Operating Lease (NC)",
  operating_lease_liability_noncurrent: "Operating Lease (NC)",
  noncurrent_unearned_gov_incentives: "Unearned Gov Incentives",
  other_noncurrent_liabilities: "Other Noncurrent Liabilities",
  total_liabilities: "Total Liabilities",
  common_stock: "Common Stock",
  additional_capital: "Additional Paid-in Capital",
  additional_paid_in_capital: "Additional Paid-in Capital",
  retained_earnings: "Retained Earnings (Deficit)",
  retained_earnings_accumulated_deficit: "Retained Earnings (Deficit)",
  treasury_stock: "Treasury Stock",
  aoci: "AOCI",
  accumulated_other_comprehensive_income_loss: "AOCI",
  total_equity: "Total Equity",
  total_liabilities_and_equity: "Total Liabilities & Equity",
  net_cash_from_operating: "Net Cash from Operating",
  net_cash_from_operating_activities: "Net Cash from Operating",
  depreciation_and_amortization: "Depreciation & Amortization",
  share_based_compensation: "Share-based Compensation",
  stock_based_compensation: "Share-based Compensation",
  deferred_income_tax: "Deferred Income Tax",
  goodwill_impairment: "Goodwill Impairment",
  other_asset_impairment: "Other Asset Impairment",
  gain_loss_on_sale_of_business: "Gain/Loss on Sale of Business",
  change_in_receivables: "Change in Receivables",
  change_in_inventories: "Change in Inventories",
  change_in_accounts_payable: "Change in AP",
  change_in_accounts_payable_accrued: "Change in AP & Accrued",
  change_in_accrued_liabilities: "Change in Accrued Liabilities",
  change_in_employee_liabilities: "Change in Employee Liabilities",
  change_in_other_current_liabilities: "Change in Other CL",
  change_in_other_noncurrent_liabilities: "Change in Other NCL",
  other_operating: "Other Operating",
  other: "Other",
  capital_expenditures: "Capital Expenditures",
  proceeds_from_sale_of_business: "Proceeds from Sale of Business",
  proceeds_from_sale_of_ppe: "Proceeds from Sale of PP&E",
  purchases_of_afs_securities: "Purchases of AFS Securities",
  proceeds_from_government_incentives: "Gov Incentive Proceeds",
  proceeds_from_maturities_sales_of_afs: "Proceeds from AFS",
  net_cash_from_investing: "Net Cash from Investing",
  net_cash_used_for_investing_activities: "Net Cash from Investing",
  proceeds_from_debt: "Proceeds from Debt",
  repayments_of_debt: "Repayments of Debt",
  repayments_stock_withholdings: "Stock Withholdings",
  repurchases_stock_program: "Stock Repurchases",
  proceeds_from_equity: "Proceeds from Equity",
  tax_withholding_payments: "Tax Withholding Payments",
  dividends_paid: "Dividends Paid",
  net_cash_from_financing: "Net Cash from Financing",
  net_cash_used_for_financing_activities: "Net Cash from Financing",
  net_cash_from_financing_activities: "Net Cash from Financing",
  fx_effect_on_cash: "FX Effect on Cash",
  net_change_in_cash: "Net Change in Cash",
  beginning_cash: "Beginning Cash",
  ending_cash: "Ending Cash",
  free_cash_flow: "Free Cash Flow",
  current_ratio: "Current Ratio",
  quick_ratio: "Quick Ratio",
  debt_to_equity: "Debt-to-Equity",
  net_debt_to_equity: "Net Debt-to-Equity",
  equity_ratio: "Equity Ratio",
  roe: "ROE",
  roa: "ROA",
  asset_turnover: "Asset Turnover",
  interest_coverage: "Interest Coverage",
  fcf_margin_pct: "FCF Margin %",
};

// ── Canonical display orders ────────────────────────────────────────────────

// Metrics to exclude from IS table (effective_tax_rate lives in Financial Ratios only)
export const IS_PCT_EXCLUDE = new Set(["effective_tax_rate"]);

export const IS_METRIC_ORDER = [
  "revenue",
  "cost_of_goods_sold", "cost_of_goods_and_services_sold",
  "gross_profit", "gross_margin_pct",
  "research_and_development", "selling_general_administrative",
  "operating_expenses",
  "restructuring_charges", "other_operating_income_expense_net",
  "operating_income", "operating_margin_pct",
  "interest_income", "interest_income_net", "investment_income",
  "interest_expense",
  "other_nonoperating_income_expense", "nonoperating_income_expense_total",
  "equity_method_investments", "equity_in_net_income_of_investees",
  "income_before_taxes",
  "income_tax_expense",
  "net_income", "net_margin_pct",
  "eps_basic", "eps_diluted",
  "shares_basic_millions", "shares_diluted_millions",
];

export const BS_ASSETS_ORDER = [
  "cash_and_cash_equivalents", "short_term_investments",
  "accounts_receivable", "inventories",
  "other_current_assets", "total_current_assets",
  "property_plant_equipment_net",
  "goodwill", "intangible_assets",
  "operating_lease_rou_asset",
  "deferred_tax_assets", "other_noncurrent_assets",
  "total_assets",
];

export const BS_LIABILITIES_ORDER = [
  "current_debt", "accounts_payable",
  "accrued_liabilities", "deferred_revenue",
  "other_current_liabilities", "total_current_liabilities",
  "long_term_debt",
  "operating_lease_noncurrent", "deferred_tax_liabilities",
  "other_noncurrent_liabilities", "total_liabilities",
];

export const BS_EQUITY_ORDER = [
  "common_stock", "additional_paid_in_capital",
  "retained_earnings", "aoci",
  "total_equity", "total_liabilities_and_equity",
];

export const CF_OPERATING_ORDER = [
  "net_income",
  "depreciation_and_amortization", "depreciation", "amortization",
  "stock_based_compensation", "equity_related_compensation",
  "deferred_income_taxes",
  "changes_in_working_capital", "changes_in_accounts_receivable",
  "changes_in_inventories", "changes_in_accounts_payable",
  "other_operating_activities",
  "net_cash_from_operating", "net_cash_from_operating_activities",
];

export const CF_INVESTING_ORDER = [
  "capital_expenditures", "purchases_of_investments",
  "proceeds_from_investments", "acquisitions",
  "other_investing_activities",
  "net_cash_from_investing", "net_cash_used_for_investing_activities",
];

export const CF_FINANCING_ORDER = [
  "proceeds_from_debt", "repayments_of_debt",
  "proceeds_from_stock_issuance", "stock_repurchases",
  "dividends_paid", "other_financing_activities",
  "net_cash_from_financing", "net_cash_from_financing_activities",
  "net_cash_used_for_financing_activities",
];

export const CF_SUMMARY_ORDER = [
  "fx_effect_on_cash", "fx_effect",
  "net_change_in_cash", "beginning_cash", "ending_cash",
  "free_cash_flow",
];

/** Sort `metrics` according to a canonical order; unknowns go to the end. */
export function sortMetrics(metrics: string[], order: string[]): string[] {
  const idx = new Map(order.map((k, i) => [k, i]));
  return [...metrics].sort((a, b) => {
    const ia = idx.has(a) ? idx.get(a)! : 9999;
    const ib = idx.has(b) ? idx.get(b)! : 9999;
    return ia - ib;
  });
}

/** Secondary subtotals — displayed with yellow highlight (not red) */
export const SUBTOTAL_KEYS = new Set([
  "total_operating_expenses",
  "nonoperating_income_expense_total",
]);

/** IS metrics to hide from display */
export const IS_HIDDEN = new Set<string>();

export const TOTAL_KEYS = new Set([
  "gross_profit", "gross_margin", "operating_income",
  "income_before_taxes", "net_income", "total_current_assets", "total_assets",
  "total_current_liabilities", "total_liabilities", "total_equity",
  "total_liabilities_and_equity", "net_cash_from_operating",
  "net_cash_from_operating_activities", "net_cash_from_investing",
  "net_cash_used_for_investing_activities", "net_cash_from_financing",
  "net_cash_used_for_financing_activities", "net_cash_from_financing_activities",
  "free_cash_flow", "ending_cash", "current_ratio", "eps_diluted",
]);

export const RATIO_CATEGORIES: { label: string; metrics: string[] }[] = [
  {
    label: "Profitability",
    metrics: ["gross_margin_pct", "operating_margin_pct", "net_margin_pct", "fcf_margin_pct", "roe", "roa"],
  },
  {
    label: "Liquidity",
    metrics: ["current_ratio", "quick_ratio"],
  },
  {
    label: "Leverage",
    metrics: ["debt_to_equity", "net_debt_to_equity", "equity_ratio", "interest_coverage"],
  },
  {
    label: "Efficiency",
    metrics: ["asset_turnover"],
  },
  {
    label: "Tax",
    metrics: ["effective_tax_rate"],
  },
];

/** Flat ordered list derived from categories — used as fallback sort order */
export const RATIO_ORDER = RATIO_CATEGORIES.flatMap((c) => c.metrics);

export const RATIO_DEFINITIONS: Record<string, string> = {
  gross_margin_pct: "Gross Profit ÷ Revenue",
  operating_margin_pct: "Operating Income ÷ Revenue",
  net_margin_pct: "Net Income ÷ Revenue",
  fcf_margin_pct: "Free Cash Flow ÷ Revenue",
  roe: "Net Income ÷ Total Equity (quarterly, not annualized)",
  roa: "Net Income ÷ Total Assets (quarterly, not annualized)",
  current_ratio: "Current Assets ÷ Current Liabilities",
  quick_ratio: "(Current Assets − Inventory) ÷ Current Liabilities",
  debt_to_equity: "Total Liabilities ÷ Total Equity",
  net_debt_to_equity: "(Total Debt − Cash) ÷ Total Equity",
  equity_ratio: "Total Equity ÷ Total Assets",
  interest_coverage: "Operating Income ÷ Interest Expense",
  asset_turnover: "Revenue ÷ Total Assets (quarterly, not annualized)",
  effective_tax_rate: "Income Tax Expense ÷ Income Before Taxes",
};

export const CHART_COLORS = [
  "#1f4e79", "#c0392b", "#27ae60", "#8e44ad", "#e67e22",
  "#2980b9", "#d35400", "#16a085", "#7f8c8d", "#f39c12",
  "#6c3483", "#1abc9c", "#e74c3c",
];

export const PERIOD_ORDER_WEIGHT = (p: string) => {
  const m = p.match(/Q(\d+)_FY(\d+)/);
  if (m) return parseInt(m[2]) * 10 + parseInt(m[1]);
  const fy = p.match(/^FY(\d+)$/);
  if (fy) return parseInt(fy[1]) * 10 + 5;
  if (p.includes("START")) return -1;
  return 0;
};

export const sortPeriods = (periods: string[]) =>
  [...periods].sort((a, b) => PERIOD_ORDER_WEIGHT(a) - PERIOD_ORDER_WEIGHT(b));

export const isPct = (key: string) =>
  key.includes("pct") || key.includes("rate") || key === "equity_ratio" || key === "roe" || key === "roa" || key === "asset_turnover";

export const isEps = (key: string) => key.startsWith("eps");

export function fmtVal(val: number | null | undefined, key: string, currency?: string) {
  if (val === null || val === undefined) return { text: "—", cls: "null-val" };
  if (isPct(key)) return { text: (val * 100).toFixed(1) + "%", cls: val < 0 ? "negative" : "" };
  if (isEps(key)) {
    const sym = currency === "TWD" ? "NT$" : "$";
    return { text: sym + val.toFixed(2), cls: val < 0 ? "negative" : "" };
  }
  if (key.includes("ratio") || key === "debt_to_equity" || key === "net_debt_to_equity")
    return { text: val.toFixed(2), cls: "" };
  const neg = val < 0;
  const abs = Math.abs(val);
  const text = abs >= 1 ? abs.toLocaleString("en-US", { maximumFractionDigits: 1 }) : abs.toFixed(2);
  return { text: neg ? `(${text})` : text, cls: neg ? "negative" : "" };
}

export function labelFor(key: string) {
  return LABEL_MAP[key] || key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

/* ================================================================
   Growth rate helpers (QoQ / YoY)
   ================================================================ */
export type GrowthMode = "value" | "qoq" | "yoy";

/** Get previous quarter key for QoQ */
export function prevQoQ(p: string): string | null {
  const m = p.match(/^Q(\d)_FY(\d{4})$/);
  if (!m) return null;
  const q = Number(m[1]), fy = Number(m[2]);
  return q === 1 ? `Q4_FY${fy - 1}` : `Q${q - 1}_FY${fy}`;
}

/** Get same-quarter-last-year key for YoY */
export function prevYoY(p: string): string | null {
  const qm = p.match(/^Q(\d)_FY(\d{4})$/);
  if (qm) return `Q${qm[1]}_FY${Number(qm[2]) - 1}`;
  const fm = p.match(/^FY(\d{4})$/);
  if (fm) return `FY${Number(fm[1]) - 1}`;
  return null;
}

/** Compute growth % */
export function growthPct(curr: number | null | undefined, prev: number | null | undefined): number | null {
  if (curr == null || prev == null || prev === 0) return null;
  return (curr - prev) / Math.abs(prev);
}

/** Format growth as percentage */
export function fmtGrowth(pct: number | null): { text: string; cls: string } {
  if (pct === null) return { text: "—", cls: "null-val" };
  const text = (pct >= 0 ? "+" : "") + (pct * 100).toFixed(1) + "%";
  return { text, cls: pct < 0 ? "negative" : pct > 0 ? "positive" : "" };
}

/** Should skip growth calculation for this metric type */
export function skipGrowthForKey(key: string): boolean {
  return isPct(key) || key.includes("ratio") || key === "debt_to_equity" || key === "net_debt_to_equity";
}

/* ================================================================
   Incomplete FY detection (for annual mode)
   ================================================================ */

/** Given quarterly periods like ["Q1_FY2025","Q2_FY2025",...], return FYs with < 4 quarters */
export function getIncompleteFYs(quarterlyPeriods: string[]): Map<string, number> {
  const fyCount = new Map<string, number>();
  for (const p of quarterlyPeriods) {
    const m = p.match(/^Q\d_FY(\d{4})$/);
    if (!m) continue;
    const fy = `FY${m[1]}`;
    fyCount.set(fy, (fyCount.get(fy) || 0) + 1);
  }
  const incomplete = new Map<string, number>();
  for (const [fy, count] of fyCount) {
    if (count < 4) incomplete.set(fy, count);
  }
  return incomplete;
}
