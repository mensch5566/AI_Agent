import { NextResponse } from "next/server";
import { createServerClient } from "@/lib/supabase";

export async function GET(
  req: Request,
  { params }: { params: Promise<{ ticker: string }> }
) {
  const { ticker } = await params;
  const url = new URL(req.url);
  const start = url.searchParams.get("start"); // YYYY-MM-DD
  const end = url.searchParams.get("end"); // YYYY-MM-DD

  try {
    const supabase = createServerClient();

    let query = supabase
      .from("stock_prices")
      .select("date, open, high, low, close, volume")
      .eq("ticker", ticker.toUpperCase())
      .order("date", { ascending: true });

    if (start) {
      query = query.gte("date", start);
    }
    if (end) {
      query = query.lte("date", end);
    }

    const { data, error } = await query;

    if (error) {
      return NextResponse.json(
        { error: error.message },
        { status: 500 }
      );
    }

    return NextResponse.json({
      ticker: ticker.toUpperCase(),
      count: data?.length ?? 0,
      data: data ?? [],
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json(
      { error: message },
      { status: 500 }
    );
  }
}
