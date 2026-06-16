import { NextResponse } from "next/server";
import { createServerClient } from "@/lib/supabase";
import config from "@/lib/macro/indicators.json";
import { computeLamp } from "@/lib/macro/lamp";
import type { Indicator } from "@/lib/macro/types";

export const dynamic = "force-dynamic";

export async function GET() {
  const supabase = createServerClient();
  const indicators = config.indicators as Indicator[];

  // 取每指標最近兩期(period_end desc)
  const results = await Promise.all(
    indicators.map(async (ind) => {
      const { data, error } = await supabase
        .from("macro_facts")
        .select("value, period_end")
        .eq("indicator_key", ind.indicator_key)
        .order("period_end", { ascending: false })
        .limit(2);
      if (error) console.error("macro_facts query error:", ind.indicator_key, error.message);
      const curr = data?.[0]?.value ?? null;
      const prev = data?.[1]?.value ?? null;
      return {
        indicator_key: ind.indicator_key,
        label: ind.label,
        layer: ind.layer,
        edge_id: ind.edge_id,
        primary: ind.primary,
        unit: ind.unit,
        as_of: data?.[0]?.period_end ?? null,
        lamp: computeLamp(curr, prev, ind.polarity),
      };
    }),
  );

  return NextResponse.json({
    indicators: results,
    graph: config.graph,
    top_lamp: { color: "grey", basis: "v1 未合成 / 資料不足（spec §5.3）" },
    generated_at: new Date().toISOString(),
  });
}
