import { NextRequest, NextResponse } from "next/server";
import { createServerClient } from "@/lib/supabase";

export async function GET(req: NextRequest) {
  const ticker = req.nextUrl.searchParams.get("ticker");
  const status = req.nextUrl.searchParams.get("status");

  const supabase = createServerClient();
  let query = supabase
    .from("research_todos")
    .select("*")
    .order("session_date", { ascending: false })
    .order("created_at", { ascending: true });

  if (ticker) query = query.eq("ticker", ticker);
  if (status) query = query.eq("status", status);

  const { data, error } = await query;
  if (error)
    return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json(data);
}

export async function POST(req: NextRequest) {
  const body = await req.json();
  const { ticker, session_date, session_label, category, title, content } =
    body;

  if (!ticker || !session_date || !title) {
    return NextResponse.json(
      { error: "ticker, session_date, and title are required" },
      { status: 400 },
    );
  }

  const supabase = createServerClient();
  const { data, error } = await supabase
    .from("research_todos")
    .insert({
      ticker,
      session_date,
      session_label: session_label || null,
      category: category || null,
      title,
      content: content || null,
      status: "open",
    })
    .select()
    .single();

  if (error)
    return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json(data);
}

export async function PATCH(req: NextRequest) {
  const body = await req.json();
  const { id, ...updates } = body;

  if (!id) {
    return NextResponse.json({ error: "id is required" }, { status: 400 });
  }

  // Only allow updating specific fields
  const allowed = [
    "status",
    "response",
    "anchor",
    "anchor_locked",
    "category",
    "title",
    "content",
    "session_label",
  ];
  const filtered: Record<string, unknown> = {};
  for (const key of allowed) {
    if (key in updates) filtered[key] = updates[key];
  }
  filtered.updated_at = new Date().toISOString();

  const supabase = createServerClient();
  const { data, error } = await supabase
    .from("research_todos")
    .update(filtered)
    .eq("id", id)
    .select()
    .single();

  if (error)
    return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json(data);
}

export async function DELETE(req: NextRequest) {
  const id = req.nextUrl.searchParams.get("id");
  if (!id) {
    return NextResponse.json({ error: "id is required" }, { status: 400 });
  }

  const supabase = createServerClient();
  const { error } = await supabase
    .from("research_todos")
    .delete()
    .eq("id", id);

  if (error)
    return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json({ success: true });
}
