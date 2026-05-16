// Placeholder stubs for equity-research embedded blocks.
//
// The original RatioChart / FinancialTable / SegmentTable read from the
// legacy financial_facts / financial_metrics / financial_supplement tables,
// which were dropped in the 2026-05-16 SEC v2 migration.
//
// These stubs preserve type compatibility for app/equity-research/[ticker]
// so the report renders without crashing while the equity-research blocks
// are migrated to the new /api/financials/[ticker] (SEC v2) shape in a
// follow-up task.

import Link from "next/link";

type CommonProps = {
  ticker: string;
};

function Placeholder({ ticker, label }: CommonProps & { label: string }) {
  return (
    <div className="rounded border border-dashed border-gray-300 p-4 text-sm text-gray-500">
      <p className="font-medium">{label} (migrating to SEC v2)</p>
      <p className="mt-1">
        This block is being ported to the new SEC v2 Financials data source.
        For now, view the full statement here:{" "}
        <Link
          href={`/financials/${ticker}`}
          className="text-blue-600 underline"
        >
          /financials/{ticker}
        </Link>
      </p>
    </div>
  );
}

export type RatioChartProps = CommonProps & {
  metrics: string[];
  defaultSelected?: string[];
  height?: number;
  defaultView?: "quarterly" | "annual";
};

export default function RatioChart(props: RatioChartProps) {
  return <Placeholder ticker={props.ticker} label="Ratio chart" />;
}

export type FinancialTableProps = CommonProps & {
  statement: "income_statement" | "balance_sheet" | "cash_flow_statement";
  metrics?: string[];
  maxPeriods?: number;
  defaultView?: "quarterly" | "annual";
};

export function FinancialTable(props: FinancialTableProps) {
  return <Placeholder ticker={props.ticker} label={`Financial table (${props.statement})`} />;
}

export type SegmentTableProps = CommonProps & {
  maxPeriods?: number;
  defaultView?: "quarterly" | "annual";
  defaultCategory?: string;
};

export function SegmentTable(props: SegmentTableProps) {
  return <Placeholder ticker={props.ticker} label="Segment table" />;
}
