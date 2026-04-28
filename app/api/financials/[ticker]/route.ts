import { NextResponse } from "next/server";
import { createServerClient } from "@/lib/supabase";

function decodeAnnualDirectMetric(encoded: string): { statement: string; metric: string } | null {
  const prefix = "annual_direct__";
  if (!encoded.startsWith(prefix)) return null;
  const body = encoded.slice(prefix.length);
  const sep = body.indexOf("__");
  if (sep === -1) return null;
  return {
    statement: body.slice(0, sep),
    metric: body.slice(sep + 2),
  };
}

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ ticker: string }> }
) {
  const { ticker } = await params;
  const t = ticker.toUpperCase();
  const supabase = createServerClient();

  const PAGE = 1000;
  const factsPage = (from: number) =>
    supabase
      .from("financial_facts")
      .select("period, period_end, statement, metric, dimension, value, unit, source")
      .eq("ticker", t)
      .range(from, from + PAGE - 1);

  const [p0, p1, p2, p3, metricsRes, supplementRes, companyRes] = await Promise.all([
    factsPage(0),
    factsPage(1000),
    factsPage(2000),
    factsPage(3000),
    // financial_metrics → 轉成 statement="financial_ratios"
    supabase
      .from("financial_metrics")
      .select("period, period_end, metric, value, source")
      .eq("ticker", t),
    // financial_supplement → category=geography/segment 轉成 statement="segments"
    supabase
      .from("financial_supplement")
      .select("period, period_end, category, metric, dimension, value, unit, source")
      .eq("ticker", t),
    supabase.from("financial_companies").select("*").eq("ticker", t).single(),
  ]);

  if (p0.error) {
    return NextResponse.json({ error: p0.error.message }, { status: 500 });
  }

  // Raw facts
  const facts = [
    ...(p0.data ?? []),
    ...(p1.data ?? []),
    ...(p2.data ?? []),
    ...(p3.data ?? []),
  ];

  // financial_metrics → inject as statement="financial_ratios"
  for (const row of metricsRes.data ?? []) {
    if (row.source === "ANNUAL_DIRECT_XBRL_TWSE") {
      const decoded = decodeAnnualDirectMetric(row.metric);
      if (!decoded) continue;
      facts.push({
        period: row.period,
        period_end: row.period_end ?? null,
        statement: decoded.statement,
        metric: decoded.metric,
        dimension: "",
        value: row.value,
        unit: null,
        source: row.source,
      });
      continue;
    }
    facts.push({
      period:     row.period,
      period_end: row.period_end ?? null,
      statement:  "financial_ratios",
      metric:     row.metric,
      dimension:  "",
      value:      row.value,
      unit:       null,
      source:     row.source,
    });
  }

  // financial_supplement → inject by category
  for (const row of supplementRes.data ?? []) {
    // shares → inject as income_statement rows (displayed at bottom of IS)
    if (row.category === "shares") {
      facts.push({
        period:     row.period,
        period_end: row.period_end ?? null,
        statement:  "income_statement",
        metric:     row.metric,
        dimension:  row.dimension ?? "",
        value:      row.value,
        unit:       row.unit ?? null,
        source:     row.source,
      });
      continue;
    }
    // geography / segment → inject as statement="segments"
    if (!["geography", "segment"].includes(row.category)) continue;
    if (!row.dimension) continue;  // 必須有維度
    const normalizedMetric =
      row.category === "segment"
        ? row.metric.includes("_profit")
          ? "profit_by_business"
          : "revenue_by_business"
        : row.category === "geography"
          ? "revenue_by_geography"
          : row.metric;
    facts.push({
      period:     row.period,
      period_end: row.period_end ?? null,
      statement:  "segments",
      metric:     normalizedMetric,
      dimension:  row.dimension,
      value:      row.value,
      unit:       row.unit ?? null,
      source:     row.source,
    });
  }

  return NextResponse.json({
    ticker: t,
    company: companyRes.data ?? null,
    facts,
  });
}
