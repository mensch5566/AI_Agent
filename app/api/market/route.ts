import { NextResponse } from "next/server";
import { createServerClient } from "@/lib/supabase";

export async function GET() {
  const supabase = createServerClient();

  try {
    const { data, error } = await supabase
      .from("market_indices")
      .select("*")
      .order("id");

    if (error) {
      console.error("market_indices query error:", error.message);
      return NextResponse.json({ indices: [], fetched_at: null });
    }

    const indices = (data ?? []).map((row) => ({
      id: row.id,
      symbol: row.symbol,
      name: row.name,
      price: row.price,
      change: row.change,
      change_pct: row.change_pct,
      prev_close: row.prev_close,
      high: row.high,
      low: row.low,
      open: row.open,
    }));

    const fetched_at =
      data && data.length > 0 ? data[0].fetched_at : null;

    return NextResponse.json({ indices, fetched_at });
  } catch {
    return NextResponse.json({ indices: [], fetched_at: null });
  }
}
