import { NextResponse } from "next/server";
import { createServerClient } from "@/lib/supabase";

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ ticker: string }> }
) {
  const { ticker } = await params;
  const supabase = createServerClient();

  const [factsRes, companyRes] = await Promise.all([
    supabase
      .from("financial_facts")
      .select("period, period_end, statement, metric, dimension, value, unit, source")
      .eq("ticker", ticker.toUpperCase()),
    supabase
      .from("financial_companies")
      .select("*")
      .eq("ticker", ticker.toUpperCase())
      .single(),
  ]);

  if (factsRes.error) {
    return NextResponse.json({ error: factsRes.error.message }, { status: 500 });
  }

  return NextResponse.json({
    ticker: ticker.toUpperCase(),
    company: companyRes.data ?? null,
    facts: factsRes.data ?? [],
  });
}
