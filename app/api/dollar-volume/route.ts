import { NextResponse } from "next/server";
import { createServerClient } from "@/lib/supabase";

export async function GET() {
  const supabase = createServerClient();

  try {
    // Get the latest fetched_at date
    const { data: latest } = await supabase
      .from("dollar_volume")
      .select("fetched_at")
      .order("fetched_at", { ascending: false })
      .limit(1)
      .single();

    if (!latest) {
      return NextResponse.json({ timeframes: {} });
    }

    const latestDate = latest.fetched_at;

    // Get all rows for the latest date
    const { data, error } = await supabase
      .from("dollar_volume")
      .select("*")
      .eq("fetched_at", latestDate)
      .order("dollar_volume", { ascending: false });

    if (error) {
      console.error("dollar_volume query error:", error.message);
      return NextResponse.json({ timeframes: {} });
    }

    // Group by days into timeframes
    const timeframes: Record<
      string,
      { period: string; rankings: Array<Record<string, unknown>> }
    > = {};

    for (const row of data ?? []) {
      const key = String(row.days);
      if (!timeframes[key]) {
        timeframes[key] = { period: `${row.days}D`, rankings: [] };
      }
      timeframes[key].rankings.push({
        rank: timeframes[key].rankings.length + 1,
        ticker: row.ticker,
        company: row.company,
        industry: row.industry,
        last_price: row.last_price,
        total_volume: row.total_volume,
        dollar_volume: row.dollar_volume,
        avg_daily_dv: row.avg_daily_dv,
        is_etf: row.is_etf,
      });
    }

    return NextResponse.json({ timeframes });
  } catch {
    return NextResponse.json({ timeframes: {} });
  }
}
