import { NextRequest, NextResponse } from "next/server";
import { createServerClient } from "@/lib/supabase";

function isoWeekToDateRange(isoWeek: string): { start: string; end: string } | null {
  const match = isoWeek.match(/^(\d{4})-W(\d{2})$/);
  if (!match) return null;

  const year = parseInt(match[1]);
  const week = parseInt(match[2]);
  if (week < 1 || week > 53) return null;

  // ISO 8601: Week 1 contains January 4th
  // Find Monday of week 1
  const jan4 = new Date(Date.UTC(year, 0, 4));
  const dayOfWeek = jan4.getUTCDay() || 7; // Mon=1 ... Sun=7
  const mondayWeek1 = new Date(Date.UTC(year, 0, 4 - dayOfWeek + 1));

  // Monday of target week
  const start = new Date(mondayWeek1.getTime() + (week - 1) * 7 * 86400000);
  const end = new Date(start.getTime() + 6 * 86400000);

  const fmt = (d: Date) => d.toISOString().slice(0, 10);
  return { start: fmt(start), end: fmt(end) };
}

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const days = searchParams.get("days");
  const ticker = searchParams.get("ticker");
  const week = searchParams.get("week");

  const supabase = createServerClient();

  try {
    let query = supabase
      .from("news_archive")
      .select("id, date, ticker, headline, summary, url, source, sentiment, parent_id")
      .order("date", { ascending: false });

    if (ticker && week) {
      // Mode: ticker + ISO week
      const range = isoWeekToDateRange(week);
      if (!range) {
        return NextResponse.json(
          { error: "Invalid ISO week format. Use YYYY-WNN (e.g. 2026-W12)" },
          { status: 400 },
        );
      }
      query = query
        .eq("ticker", ticker.toUpperCase())
        .gte("date", range.start)
        .lte("date", range.end);
    } else if (days) {
      // Mode: last N days
      const n = parseInt(days);
      if (isNaN(n) || n < 1 || n > 90) {
        return NextResponse.json(
          { error: "days must be between 1 and 90" },
          { status: 400 },
        );
      }
      const since = new Date();
      since.setDate(since.getDate() - n);
      query = query.gte("date", since.toISOString().slice(0, 10));
    } else {
      // Default: last 7 days
      const since = new Date();
      since.setDate(since.getDate() - 7);
      query = query.gte("date", since.toISOString().slice(0, 10));
    }

    const { data, error } = await query;

    if (error) {
      console.error("news_archive query error:", error.message);
      return NextResponse.json({ items: [], updated_at: null });
    }

    const items = (data ?? []).map((row) => ({
      id: row.id,
      date: row.date,
      headline: row.headline,
      summary: row.summary ?? "",
      url: row.url,
      ticker: row.ticker,
      sentiment: row.sentiment,
      source: row.source,
      parent_id: row.parent_id,
    }));

    const updated_at = items.length > 0 ? items[0].date : null;

    return NextResponse.json({ items, updated_at });
  } catch {
    return NextResponse.json({ items: [], updated_at: null });
  }
}
