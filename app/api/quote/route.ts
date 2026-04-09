import { NextRequest, NextResponse } from "next/server";

export async function GET(req: NextRequest) {
  const ticker = req.nextUrl.searchParams.get("ticker");
  if (!ticker) {
    return NextResponse.json({ error: "missing ticker" }, { status: 400 });
  }

  try {
    // 台股 ticker 全為數字，Yahoo Finance 需要加 .TW 後綴
    const yTicker = /^\d+$/.test(ticker) ? `${ticker}.TW` : ticker;
    const res = await fetch(
      `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(yTicker)}?range=1d&interval=1d`,
      { headers: { "User-Agent": "Mozilla/5.0" }, next: { revalidate: 300 } },
    );
    const data = await res.json();
    const price = data?.chart?.result?.[0]?.meta?.regularMarketPrice;
    if (!price) {
      return NextResponse.json({ error: "no price data" }, { status: 404 });
    }
    return NextResponse.json({ ticker, price });
  } catch {
    return NextResponse.json({ error: "fetch failed" }, { status: 502 });
  }
}
