// SEC Financials v2 — shared types
// Mirrors API route /api/financials/[ticker] response shape.

export type Statement = "IS" | "BS" | "CF" | "RATIO";
export type Version = "GAAP" | "NON_GAAP";
export type PeriodKind =
  | "quarter_duration"
  | "fy_annual_duration"
  | "ytd_duration"
  | "instant_period_end"
  | "derived_q4";
export type CellStatus =
  | "SOURCE_OF_TRUTH"
  | "DERIVED_FROM_DISCLOSED"
  | "EXCLUDED_FROM_NONGAAP"
  | "PENDING"; // synthetic, never in DB

export type Cell = {
  ticker: string;
  period: string;
  period_end: string;
  period_kind: PeriodKind;
  statement: Statement;
  version: Version;
  uni_account: string;
  source_account: string | null;
  xbrl_tag: string | null;
  value: number;
  weight: number | null;
  unit: string;
  status: CellStatus;
  ordinal: number | null;
  long_tail_metadata: Record<string, unknown> | null;
  provenance: Record<string, unknown>;
  source_table: "facts" | "metrics";
};

export type DimCell = {
  ticker: string;
  period: string;
  period_end: string;
  period_kind: PeriodKind;
  axis: string;
  axis_key: string;
  member: string;
  member_key: string;
  uni_account: string;
  value: number;
  unit: string;
  decimals: number | null;
  other_dimensions: unknown[] | null;
  provenance: Record<string, unknown>;
};

export type Company = {
  ticker: string;
  company_name: string;
  exchange: string;
  cik: string;
  currency: string;
  fiscal_year_end_month: number;
  filings: Record<string, { form?: string; period_end?: string; accession_number?: string }>;
  sign_flip_concepts: string[];
};

export type ApiResponse = {
  ticker: string;
  company: Company;
  cells: Cell[];
  dimensional: DimCell[];
  counts: { facts: number; metrics: number; dimensional: number };
};

// MatrixCell = one (uni_account × period) intersection after pivot
export type MatrixCell = {
  cell?: Cell;
  status: CellStatus;
};
