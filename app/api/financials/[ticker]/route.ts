import { NextResponse } from "next/server";
import { createServerClient } from "@/lib/supabase";

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ ticker: string }> }
) {
  const { ticker } = await params;
  const supabase = createServerClient();

  const [factsRes, supRes] = await Promise.all([
    supabase
      .from("financial_facts")
      .select("period, period_end, statement, metric, value, unit")
      .eq("ticker", ticker.toUpperCase()),
    supabase
      .from("financial_supplemental")
      .select("period, section, subsection, dimension, value, unit, source")
      .eq("ticker", ticker.toUpperCase()),
  ]);

  if (factsRes.error) {
    return NextResponse.json({ error: factsRes.error.message }, { status: 500 });
  }

  return NextResponse.json({
    ticker: ticker.toUpperCase(),
    facts: factsRes.data ?? [],
    supplemental: supRes.data ?? [],
  });
}
