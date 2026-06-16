"use client";
import { useEffect, useState } from "react";
import FlowGraph from "./FlowGraph";
import type { LampColor } from "@/lib/macro/types";

const LAYER_COLOR: Record<string, string> = {
  L1: "#0d9488", L2: "#1d4ed8", L3: "#b45309", L4: "#c02734", L5: "#7c3aed",
};
const DOT: Record<LampColor, string> = { green: "#1a7f37", red: "#c02734", grey: "#b09898" };

interface IndCard {
  indicator_key: string; label: string; layer: string; edge_id: string; primary: boolean;
  unit: string; as_of: string | null; lamp: { color: LampColor; curr: number | null; prev: number | null; basis: string };
}

export default function Dashboard() {
  const [data, setData] = useState<any>(null);
  useEffect(() => { fetch("/api/macro").then((r) => r.json()).then(setData); }, []);
  if (!data) return <div className="p-6 text-sm">載入中…</div>;

  // 邊燈號 = 該邊 primary 指標的燈;無則 grey
  const edgeLamp: Record<string, LampColor> = {};
  (data.indicators as IndCard[]).forEach((i) => {
    if (i.primary || !(i.edge_id in edgeLamp)) edgeLamp[i.edge_id] = i.lamp.color;
  });
  data.graph.edges.forEach((e: any) => { if (!(e.id in edgeLamp)) edgeLamp[e.id] = "grey"; });

  return (
    <main className="max-w-screen-xl mx-auto p-6 space-y-6">
      <header className="flex items-center justify-between">
        <h1 className="text-xl font-bold">AI 資金流儀表板 <span className="text-xs text-[var(--text-faint)]">v1</span></h1>
        <div className="flex items-center gap-2 text-sm">
          <span className="w-3 h-3 rounded-full" style={{ background: DOT[data.top_lamp.color as LampColor] }} />
          盤子裡還有沒有錢:<b>{data.top_lamp.color === "grey" ? "待補" : data.top_lamp.color}</b>
        </div>
      </header>
      <p className="text-xs text-[var(--text-muted)]">⚠ v1 簡化:燈號=本期 vs 上一期+polarity(綠=bull/紅=bear),門檻未校準;頂層燈 v1 未合成。</p>

      <section className="border rounded-xl p-4">
        <FlowGraph nodes={data.graph.nodes} edges={data.graph.edges} edgeLamp={edgeLamp} />
      </section>

      <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {(data.indicators as IndCard[]).map((i) => (
          <div key={i.indicator_key} className="border rounded-lg p-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full" style={{ background: DOT[i.lamp.color] }} />
                <span className="font-semibold text-sm">{i.label}</span>
              </div>
              <span className="text-[10px] px-1.5 py-0.5 rounded" style={{ color: LAYER_COLOR[i.layer], border: `1px solid ${LAYER_COLOR[i.layer]}55` }}>{i.layer}</span>
            </div>
            <div className="mt-2 text-sm font-mono">
              {i.lamp.curr ?? "—"} <span className="text-[var(--text-faint)]">(前 {i.lamp.prev ?? "—"})</span>
            </div>
            <div className="text-[11px] text-[var(--text-muted)] mt-1">{i.as_of ?? "待補"} · {i.lamp.basis}</div>
          </div>
        ))}
      </section>
    </main>
  );
}
