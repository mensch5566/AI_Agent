import { NextResponse } from "next/server";
import { createServerClient } from "@/lib/supabase";

/**
 * SEC Financials v2 API
 *
 * Returns unified cells for one ticker, combining:
 *   - sec_financial_facts (direct disclosed: GAAP + NON_GAAP, statement IS/BS/CF/RATIO)
 *   - sec_financial_metrics (derived: Q4 reconstruction, margin ratios, ...)
 *   - sec_financial_dimensional_facts (segment / geography / customer)
 *
 * Frontend pivots cells by (statement, version, uni_account, period).
 *
 * Spec: tmp/financials-viewer-redesign-plan.md §16.2 + §20 + docs/financials-data-rules.md
 */

type Cell = {
  ticker: string;
  period: string;
  period_end: string;
  period_kind: string;
  statement: string;
  version: string;
  uni_account: string;
  source_account: string | null;
  xbrl_tag: string | null;
  value: number;
  weight: number | null;
  unit: string;
  status: string;
  ordinal: number | null;
  long_tail_metadata: Record<string, unknown> | null;
  provenance: Record<string, unknown>;
  source_table: "facts" | "metrics";
};

type DimCell = {
  ticker: string;
  period: string;
  period_end: string;
  period_kind: string;
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

const PAGE = 1000;

type PageResult<T> = { data: T[] | null; error: unknown };

async function fetchAllPages<T>(
  fetcher: (from: number) => PromiseLike<PageResult<T>>,
): Promise<T[]> {
  const out: T[] = [];
  let from = 0;
  while (true) {
    const { data, error } = await fetcher(from);
    if (error) throw error;
    if (!data || data.length === 0) break;
    out.push(...data);
    if (data.length < PAGE) break;
    from += PAGE;
  }
  return out;
}

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ ticker: string }> },
) {
  const { ticker } = await params;
  const t = ticker.toUpperCase();
  const supabase = createServerClient();

  // Run independent queries in parallel
  const [companyRes, factsRaw, metricsRaw, dimRaw] = await Promise.all([
    supabase
      .from("sec_financial_companies")
      .select("*")
      .eq("ticker", t)
      .maybeSingle(),
    // .order("cell_id") gives a stable unique total order so the .range() page
    // windows are a deterministic contract. Without it Postgres/PostgREST make
    // NO ordering guarantee across separate paged requests, so adjacent pages
    // could overlap or skip rows — and LITE already exceeds one 1000-row page.
    fetchAllPages<Omit<Cell, "source_table">>((from) =>
      supabase
        .from("sec_financial_facts")
        .select(
          "ticker, period, period_end, period_kind, statement, version, uni_account, source_account, xbrl_tag, value, weight, unit, status, ordinal, long_tail_metadata, provenance",
        )
        .eq("ticker", t)
        .order("cell_id")
        .range(from, from + PAGE - 1),
    ),
    fetchAllPages<Omit<Cell, "source_table" | "source_account" | "xbrl_tag" | "weight" | "ordinal" | "long_tail_metadata">>(
      (from) =>
        supabase
          .from("sec_financial_metrics")
          .select(
            "ticker, period, period_end, period_kind, statement, version, uni_account, value, unit, status, provenance",
          )
          .eq("ticker", t)
          .order("cell_id")
          .range(from, from + PAGE - 1),
    ),
    fetchAllPages<DimCell>((from) =>
      supabase
        .from("sec_financial_dimensional_facts")
        .select(
          "ticker, period, period_end, period_kind, axis, axis_key, member, member_key, uni_account, value, unit, decimals, other_dimensions, provenance",
        )
        .eq("ticker", t)
        .order("cell_id")
        .range(from, from + PAGE - 1),
    ),
  ]);

  if (companyRes.error) {
    return NextResponse.json({ error: companyRes.error.message }, { status: 500 });
  }
  if (!companyRes.data) {
    return NextResponse.json({ error: `Ticker ${t} not found` }, { status: 404 });
  }

  // Tag cells with source_table; metrics rows fill the gaps that facts left.
  // facts-wins guardrail (Phase 0 / P0.1): a derived (metrics) row must never
  // shadow a direct-disclosed (facts) row for the same logical cell. facts and
  // metrics use different cell_id schemes (facts_cell_id vs metrics_cell_id), so
  // collisions are keyed on the logical identity tuple, not cell_id. Today there
  // is zero overlap (disclosed RATIO are NON_GAAP, derived RATIO are GAAP); this
  // is a forward guardrail for when derived Non-GAAP ratios or disclosed GAAP
  // ratios land.
  const identity = (c: { period: string; period_kind: string; version: string; statement: string; uni_account: string }) =>
    `${c.period}|${c.period_kind}|${c.version}|${c.statement}|${c.uni_account}`;
  const factKeys = new Set(factsRaw.map(identity));
  const cells: Cell[] = [];
  for (const f of factsRaw) {
    cells.push({ ...f, source_table: "facts" });
  }
  for (const m of metricsRaw) {
    if (factKeys.has(identity(m))) continue; // facts win — drop colliding derived row
    cells.push({
      ...m,
      source_account: null,
      xbrl_tag: null,
      weight: null,
      ordinal: null,
      long_tail_metadata: null,
      source_table: "metrics",
    });
  }

  return NextResponse.json({
    ticker: t,
    company: companyRes.data,
    cells,
    dimensional: dimRaw,
    counts: {
      facts: factsRaw.length,
      metrics: metricsRaw.length,
      dimensional: dimRaw.length,
    },
  });
}
