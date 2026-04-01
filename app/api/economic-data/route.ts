import { NextResponse } from "next/server";
import { createServerClient } from "@/lib/supabase";

export async function GET() {
  const supabase = createServerClient();

  try {
    const { data, error } = await supabase
      .from("economic_data")
      .select("data")
      .eq("id", "latest")
      .single();

    if (error || !data?.data) {
      console.error("economic_data query error:", error?.message);
      return NextResponse.json(null, { status: 404 });
    }

    return NextResponse.json(data.data);
  } catch {
    return NextResponse.json(null, { status: 500 });
  }
}
