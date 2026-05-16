// SEC Financials v2 — display constants.
// Source dictionary: docs/sec-financials-v2-schema.md.
// uni_account row order on the statement matrix and human-readable labels.

import type { Statement } from "./types";

export type MetricSpec = {
  key: string;            // uni_account
  label: string;          // display label
  kind: "core" | "subtotal" | "long_tail_bucket" | "derived_ratio";
  indent?: number;        // 0..2
};

// Income Statement
export const IS_ROWS: MetricSpec[] = [
  { key: "revenue", label: "Revenue", kind: "core" },
  { key: "cost_of_goods_sold", label: "Cost of Revenue", kind: "core" },
  { key: "gross_profit", label: "Gross Profit", kind: "subtotal" },
  { key: "selling_general_administrative", label: "SG&A", kind: "core" },
  { key: "research_and_development", label: "R&D", kind: "core" },
  { key: "amortization_of_acquired_intangibles", label: "Amortization of Intangibles", kind: "core" },
  { key: "total_operating_expenses", label: "Total Operating Expenses", kind: "subtotal" },
  { key: "operating_expense_long_tail", label: "Other Operating Items (long-tail)", kind: "long_tail_bucket" },
  { key: "operating_income", label: "Operating Income", kind: "subtotal" },
  { key: "interest_income", label: "Interest Income", kind: "core", indent: 1 },
  { key: "interest_expense", label: "Interest Expense", kind: "core", indent: 1 },
  { key: "interest_and_other_net", label: "Interest & Other, net", kind: "core" },
  { key: "other_nonoperating_income_expense", label: "Other Non-Operating", kind: "core" },
  { key: "nonoperating_long_tail", label: "Other Non-Op (long-tail)", kind: "long_tail_bucket" },
  { key: "income_before_taxes", label: "Pretax Income", kind: "subtotal" },
  { key: "income_tax_expense", label: "Income Tax Expense", kind: "core" },
  { key: "net_income", label: "Net Income", kind: "subtotal" },
  { key: "below_line_long_tail", label: "Below-Line Items (long-tail)", kind: "long_tail_bucket" },
  { key: "eps_basic", label: "EPS Basic", kind: "core" },
  { key: "eps_diluted", label: "EPS Diluted", kind: "core" },
  { key: "shares_basic_millions", label: "Shares Basic (M)", kind: "core" },
  { key: "shares_diluted_millions", label: "Shares Diluted (M)", kind: "core" },
];

// Balance Sheet
export const BS_ROWS: MetricSpec[] = [
  { key: "cash_and_cash_equivalents", label: "Cash & Equivalents", kind: "core" },
  { key: "accounts_receivable", label: "Accounts Receivable", kind: "core" },
  { key: "inventories", label: "Inventories", kind: "core" },
  { key: "other_current_assets", label: "Other Current Assets", kind: "core" },
  { key: "current_asset_long_tail", label: "Other Current Assets (long-tail)", kind: "long_tail_bucket" },
  { key: "total_current_assets", label: "Total Current Assets", kind: "subtotal" },
  { key: "ppe_gross", label: "PP&E (Gross)", kind: "core", indent: 1 },
  { key: "accumulated_depreciation", label: "Accumulated Depreciation", kind: "core", indent: 1 },
  { key: "property_plant_equipment_net", label: "PP&E (Net)", kind: "core" },
  { key: "operating_lease_rou_asset", label: "Operating Lease ROU Asset", kind: "core" },
  { key: "intangible_assets", label: "Intangible Assets", kind: "core" },
  { key: "deferred_tax_assets", label: "Deferred Tax Assets", kind: "core" },
  { key: "other_noncurrent_assets", label: "Other Non-Current Assets", kind: "core" },
  { key: "noncurrent_asset_long_tail", label: "Other Non-Current (long-tail)", kind: "long_tail_bucket" },
  { key: "total_assets", label: "Total Assets", kind: "subtotal" },
  { key: "accounts_payable", label: "Accounts Payable", kind: "core" },
  { key: "accrued_liabilities", label: "Accrued Liabilities", kind: "core" },
  { key: "income_taxes_payable_current", label: "Income Taxes Payable", kind: "core" },
  { key: "current_portion_of_long_term_debt", label: "ST Debt (Current LT Debt)", kind: "core" },
  { key: "current_portion_of_lease_obligations", label: "ST Lease Obligations", kind: "core" },
  { key: "deferred_revenue_current", label: "Deferred Revenue (Current)", kind: "core" },
  { key: "current_liability_long_tail", label: "Other Current Liabilities (long-tail)", kind: "long_tail_bucket" },
  { key: "total_current_liabilities", label: "Total Current Liabilities", kind: "subtotal" },
  { key: "long_term_debt", label: "Long-Term Debt", kind: "core" },
  { key: "operating_lease_noncurrent", label: "LT Lease Obligations", kind: "core" },
  { key: "deferred_revenue_noncurrent", label: "Deferred Revenue (Non-Current)", kind: "core" },
  { key: "noncurrent_liability_long_tail", label: "Other Non-Current Liabilities (long-tail)", kind: "long_tail_bucket" },
  { key: "total_liabilities", label: "Total Liabilities", kind: "subtotal" },
  { key: "common_stock", label: "Common Stock", kind: "core" },
  { key: "additional_paid_in_capital", label: "Additional Paid-In Capital", kind: "core" },
  { key: "retained_earnings", label: "Retained Earnings", kind: "core" },
  { key: "aoci", label: "AOCI", kind: "core" },
  { key: "equity_long_tail", label: "Other Equity (long-tail)", kind: "long_tail_bucket" },
  { key: "total_equity", label: "Total Equity", kind: "subtotal" },
  { key: "total_liabilities_and_equity", label: "Total Liabilities & Equity", kind: "subtotal" },
];

// Cash Flow
export const CF_ROWS: MetricSpec[] = [
  { key: "net_income", label: "Net Income (CF starting)", kind: "core" },
  { key: "depreciation_and_amortization", label: "D&A", kind: "core" },
  { key: "share_based_compensation", label: "Share-Based Compensation", kind: "core" },
  { key: "deferred_income_tax", label: "Deferred Income Tax", kind: "core" },
  { key: "other_asset_impairment", label: "Asset Impairment", kind: "core" },
  { key: "gain_loss_on_sale_cf", label: "Gain/Loss on Sale", kind: "core" },
  { key: "change_in_receivables", label: "Δ Receivables", kind: "core" },
  { key: "change_in_inventories", label: "Δ Inventories", kind: "core" },
  { key: "change_in_accounts_payable", label: "Δ Accounts Payable", kind: "core" },
  { key: "change_in_accrued_liabilities", label: "Δ Accrued Liabilities", kind: "core" },
  { key: "operating_cf_long_tail", label: "Other Operating (long-tail)", kind: "long_tail_bucket" },
  { key: "net_cash_from_operating", label: "Cash from Operating", kind: "subtotal" },
  { key: "capital_expenditures", label: "Capital Expenditures", kind: "core" },
  { key: "investing_cf_long_tail", label: "Other Investing (long-tail)", kind: "long_tail_bucket" },
  { key: "net_cash_from_investing", label: "Cash from Investing", kind: "subtotal" },
  { key: "issuance_of_common_stock", label: "Issuance of Common Stock", kind: "core" },
  { key: "financing_cf_long_tail", label: "Other Financing (long-tail)", kind: "long_tail_bucket" },
  { key: "net_cash_from_financing", label: "Cash from Financing", kind: "subtotal" },
  { key: "net_change_in_cash", label: "Net Change in Cash", kind: "subtotal" },
  { key: "ending_cash", label: "Ending Cash", kind: "subtotal" },
  { key: "cash_income_tax_paid", label: "Cash Taxes Paid", kind: "core", indent: 1 },
  { key: "cash_interest_paid", label: "Cash Interest Paid", kind: "core", indent: 1 },
];

// RATIO statement rows (mostly derived; show even when empty for visual continuity)
export const RATIO_ROWS: MetricSpec[] = [
  { key: "gross_margin_pct", label: "Gross Margin %", kind: "derived_ratio" },
  { key: "operating_margin_pct", label: "Operating Margin %", kind: "derived_ratio" },
  { key: "net_margin_pct", label: "Net Margin %", kind: "derived_ratio" },
  { key: "ebitda_margin_pct", label: "EBITDA Margin %", kind: "derived_ratio" },
  { key: "adjusted_ebitda_margin_pct", label: "Adjusted EBITDA Margin %", kind: "derived_ratio" },
  { key: "effective_tax_rate", label: "Effective Tax Rate", kind: "derived_ratio" },
  { key: "roe", label: "Return on Equity", kind: "derived_ratio" },
  { key: "roa", label: "Return on Assets", kind: "derived_ratio" },
  { key: "current_ratio", label: "Current Ratio", kind: "derived_ratio" },
];

export const ROWS_BY_STATEMENT: Record<Statement, MetricSpec[]> = {
  IS: IS_ROWS,
  BS: BS_ROWS,
  CF: CF_ROWS,
  RATIO: RATIO_ROWS,
};

// Non-GAAP spotlight metrics — shown as parallel column on these IS rows only.
// Spec: docs/sec-financials-v2-schema.md §5.
export const NONGAAP_SPOTLIGHT_METRICS = new Set([
  "revenue",
  "gross_profit",
  "operating_income",
  "net_income",
  "eps_diluted",
  "adjusted_ebitda",
]);

// Chart defaults per statement — the metrics auto-selected when the user
// switches to a new view. Capped at `CHART_MAX_SELECTION` in the toggle
// handler; entries past the cap are ignored.
export const CHART_DEFAULT_KEYS: Record<Statement, string[]> = {
  IS: ["revenue", "gross_profit", "net_income"],
  BS: ["cash_and_cash_equivalents", "total_assets", "total_equity"],
  CF: ["net_cash_from_operating", "capital_expenditures", "net_change_in_cash"],
  RATIO: ["gross_margin_pct", "operating_margin_pct", "net_margin_pct"],
};

// Maximum simultaneous metrics on the line chart. Clicking a fourth row in
// the table evicts the oldest selection (FIFO).
export const CHART_MAX_SELECTION = 3;

// Line colors cycled for chart datasets. Mid-saturation palette that reads
// well on both light and dark backgrounds.
export const CHART_COLORS = [
  "#3b82f6", // blue
  "#ef4444", // red
  "#10b981", // emerald
  "#f59e0b", // amber
  "#8b5cf6", // violet
  "#ec4899", // pink
  "#14b8a6", // teal
  "#f97316", // orange
];

// Group units so the chart can lock chips to compatible measurement types.
// Mixing $ and % on one axis is misleading; mixing $ and shares is also
// misleading. Per-share lives in its own group too because absolute EPS
// doesn't compare against revenue dollars.
export type UnitGroup = "monetary" | "pct" | "per_share" | "shares" | "other";

export function unitGroupOf(unit: string | null | undefined): UnitGroup {
  if (!unit) return "other";
  if (unit === "USD_thousands" || unit === "USD_millions") return "monetary";
  if (unit === "Pure" || unit === "percent" || unit === "pct") return "pct";
  if (unit === "USD_per_share") return "per_share";
  if (unit === "millions_shares" || unit === "thousands_shares") return "shares";
  return "other";
}

// Long-tail rollup hints: when a long-tail bucket child carries one of these
// XBRL tags AND the target core uni_account row already has a populated cell
// for the same (statement, version, period), suppress the child from the
// bucket aggregation. This avoids double-display when the issuer only files
// component tags (e.g. AAOI files SellingAndMarketingExpense +
// GeneralAndAdministrativeExpense, parse-10QK-gaap synthesises a core
// `selling_general_administrative = SUM(...)` cell and also keeps the two
// children in `operating_expense_long_tail` for provenance).
//
// Keep this map small — only entries where the parse skill explicitly writes
// the same numbers to BOTH a synthetic core row and the long-tail bucket.
// New entries require a corresponding fact in the parse skill output.
export const LONG_TAIL_ROLLUP_HINTS: Record<string, string> = {
  SellingAndMarketingExpense: "selling_general_administrative",
  GeneralAndAdministrativeExpense: "selling_general_administrative",
};

// Display formatting

export function fmtValue(value: number | null | undefined, unit: string): string {
  if (value === null || value === undefined) return "—";
  if (unit === "Pure") return `${(value * 100).toFixed(1)}%`;
  if (unit === "USD_per_share") return `$${value.toFixed(2)}`;
  if (unit === "USD_thousands") {
    if (Math.abs(value) >= 1_000_000) return `${(value / 1000).toFixed(0)}M`;
    if (Math.abs(value) >= 1000) return `${(value / 1000).toFixed(1)}M`;
    return `${value.toFixed(0)}K`;
  }
  if (unit === "USD_millions") return `${value.toFixed(0)}M`;
  if (unit === "millions_shares") return `${value.toFixed(1)}M`;
  if (unit === "thousands_shares") return `${(value / 1000).toFixed(1)}M`;
  return String(value);
}

// Comparator for sorting periods so quarterly view shows oldest → newest
// Examples: Q1_FY2023 < Q2_FY2023 < Q3_FY2023 < Q4_FY2023 < Q1_FY2024
//          FY2023 < FY2024 < FY2025
export function comparePeriods(a: string, b: string): number {
  const parse = (p: string) => {
    if (p.startsWith("FY")) return [parseInt(p.slice(2), 10), 9] as const; // FY sits after Q4
    const m = /^Q(\d)_FY(\d{4})$/.exec(p);
    if (m) return [parseInt(m[2], 10), parseInt(m[1], 10)] as const;
    const m2 = /^(\d+)M_FY(\d{4})$/.exec(p);
    if (m2) return [parseInt(m2[2], 10), 4 + parseInt(m2[1], 10) / 12] as const;
    return [0, 0] as const;
  };
  const [ay, aq] = parse(a);
  const [by, bq] = parse(b);
  if (ay !== by) return ay - by;
  return aq - bq;
}
