import { NextResponse } from "next/server";
import { fetchPeHistory } from "@/lib/valuation/peHistory";

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ ticker: string }> },
) {
  const { ticker } = await params;
  if (!ticker) {
    return NextResponse.json({ error: "missing ticker" }, { status: 400 });
  }

  try {
    const data = await fetchPeHistory(ticker);
    return NextResponse.json(data, {
      headers: { "Cache-Control": "s-maxage=3600, stale-while-revalidate=86400" },
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "fetch failed";
    return NextResponse.json({ error: message }, { status: 502 });
  }
}
