"use client";
import { useEffect, useMemo, useState } from "react";
import FlowGraph from "./FlowGraph";
import type { LampColor } from "@/lib/macro/types";

const LAYER_COLOR: Record<string, string> = {
  L1: "#0d9488", L2: "#1d4ed8", L3: "#b45309", L4: "#c02734", L5: "#7c3aed",
};
const LAMP_CLASS: Record<LampColor, string> = { green: "lamp-green", red: "lamp-red", grey: "lamp-grey" };
const VERDICT: Record<LampColor, { word: string; note: string }> = {
  green: { word: "資金仍在流動", note: "上游水龍頭未關" },
  red: { word: "資金正在收緊", note: "上游已亮警訊" },
  grey: { word: "待資料", note: "尚未合成 · v1 靜默" },
};
// 每段箭頭的建議指標(empty-state 提示,引導之後補哪些)
const EDGE_HINT: Record<string, string> = {
  E1: "如 隔夜拆款利率、M1/M2、準備金",
  E2: "如 銀行放款標準、商業本票利差",
  E3: "如 CSP capex、NVDA 資料中心營收",
  E4: "如 伺服器 CPU 出貨", E5: "如 HBM 價格、DRAM 合約價",
  E6: "如 ODM/伺服器系統營收", E7: "如 晶圓代工稼動率、3nm 投片",
  E8: "如 半導體設備接單、EUV 出貨", E9: "如 AI 推論/訓練營收",
  E10: "如 雲端與廣告營收 YoY",
};

interface IndCard {
  indicator_key: string; label: string; source_label?: string; fred_series?: string; layer: string; edge_id: string; primary: boolean;
  unit: string; freq?: string; as_of: string | null;
  lamp: { color: LampColor; curr: number | null; prev: number | null; basis: string };
}

function fmt(n: number | null): string {
  if (n === null || n === undefined) return "—";
  const abs = Math.abs(n);
  return abs >= 1000 ? n.toLocaleString("en-US", { maximumFractionDigits: 0 })
    : n.toLocaleString("en-US", { maximumFractionDigits: 2 });
}
function delta(curr: number | null, prev: number | null) {
  if (curr === null || prev === null) return { arrow: "·", txt: "待資料" };
  const d = curr - prev;
  if (d === 0) return { arrow: "≈", txt: "持平" };
  return { arrow: d > 0 ? "▲" : "▼", txt: `${d > 0 ? "+" : ""}${fmt(d)}` };
}

function IndicatorCard({ i, idx }: { i: IndCard; idx: number }) {
  const dl = delta(i.lamp.curr, i.lamp.prev);
  const lit = i.lamp.color === "red" ? "lit-red" : i.lamp.color === "green" ? "lit-green" : "";
  return (
    <div className={`ind-card rounded-lg p-3.5 bloom ${lit}`} style={{ animationDelay: `${idx * 55}ms` }}>
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className={`lamp ${LAMP_CLASS[i.lamp.color]}`} />
          <div className="min-w-0">
            {i.fred_series ? (
              <a href={`https://fred.stlouisfed.org/series/${i.fred_series}`} target="_blank" rel="noopener noreferrer"
                className="group block min-w-0" title={`FRED: ${i.fred_series}`}>
                <div className="text-[13.5px] font-semibold truncate group-hover:underline"
                  style={{ textDecorationColor: "var(--primary)" }}>{i.source_label ?? i.label}</div>
                <div className="num text-[10.5px] truncate" style={{ color: "var(--text-faint)" }}>
                  {i.fred_series} <span style={{ color: "var(--primary)" }}>↗</span> · {i.freq ?? i.unit}
                </div>
              </a>
            ) : (
              <>
                <div className="text-[13.5px] font-semibold truncate">{i.source_label ?? i.label}</div>
                <div className="num text-[10.5px] truncate" style={{ color: "var(--text-faint)" }}>{i.freq ?? i.unit}</div>
              </>
            )}
          </div>
        </div>
        <span className="text-[9.5px] px-1.5 py-0.5 rounded shrink-0"
          style={{ color: LAYER_COLOR[i.layer], border: `1px solid ${LAYER_COLOR[i.layer]}55`, background: `${LAYER_COLOR[i.layer]}12` }}>{i.layer}</span>
      </div>
      <div className="flex items-end justify-between mt-3">
        <span className="num text-[20px] font-semibold leading-none">{fmt(i.lamp.curr)}</span>
        <span className="num text-[11px]" style={{ color: dl.txt === "待資料" ? "var(--text-faint)" : "var(--text-muted)" }}>{dl.arrow} {dl.txt}</span>
      </div>
      <div className="num text-[10.5px] mt-2 pt-2 flex items-center justify-between"
        style={{ color: "var(--text-faint)", borderTop: "1px solid var(--border)" }}>
        <span>前 {fmt(i.lamp.prev)}</span><span>{i.as_of ?? "待資料"}</span>
      </div>
    </div>
  );
}

export default function Dashboard() {
  const [data, setData] = useState<any>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [hovered, setHovered] = useState<string | null>(null);
  useEffect(() => { fetch("/api/macro").then((r) => r.json()).then(setData); }, []);

  const inds: IndCard[] = data?.indicators ?? [];
  const edgeLamp = useMemo(() => {
    const m: Record<string, LampColor> = {};
    inds.forEach((i) => { if (i.primary || !(i.edge_id in m)) m[i.edge_id] = i.lamp.color; });
    data?.graph.edges.forEach((e: any) => { if (!(e.id in m)) m[e.id] = "grey"; });
    return m;
  }, [data, inds]);
  const indCount = useMemo(() => {
    const c: Record<string, number> = {};
    inds.forEach((i) => { c[i.edge_id] = (c[i.edge_id] ?? 0) + 1; });
    return c;
  }, [inds]);

  if (!data) return <div className="p-6 text-sm text-[var(--text-muted)]">載入中…</div>;

  const top = (data.top_lamp.color as LampColor) ?? "grey";
  const verdict = VERDICT[top];
  const litCount = inds.filter((i) => i.lamp.color !== "grey").length;

  // edge meta + selected indicators
  const selEdge = selected ? data.graph.edges.find((e: any) => e.id === selected) : null;
  const nodeLabel: Record<string, string> = {};
  data.graph.nodes.forEach((n: any) => (nodeLabel[n.id] = n.label));
  const selInds = selected ? inds.filter((i) => i.edge_id === selected) : [];
  const envInds = inds.filter((i) => i.edge_id === "ENV" || i.edge_id === "BG");

  return (
    <div className="macro-page min-h-screen">
      {/* TOP BAR */}
      <header className="border-b sticky top-0 z-20"
        style={{ borderColor: "var(--border)", background: "color-mix(in srgb, var(--bg-page) 88%, transparent)", backdropFilter: "blur(8px)" }}>
        <div className="max-w-[1180px] mx-auto px-6 py-3.5 flex items-end justify-between gap-4 flex-wrap">
          <div>
            <div className="flex items-center gap-2.5">
              <span className={`lamp lamp-lg ${LAMP_CLASS[top]}`} />
              <h1 className="text-[21px] font-bold tracking-tight">AI 資金流儀表板</h1>
              <span className="num text-[11px] px-2 py-0.5 rounded" style={{ color: "var(--text-faint)", border: "1px solid var(--border)" }}>v1</span>
            </div>
          </div>
          <div className="text-right">
            <div className="text-[10px] uppercase tracking-wider" style={{ color: "var(--text-faint)" }}>盤子裡還有沒有錢</div>
            <div className="text-[19px] font-semibold leading-tight"
              style={{ color: top === "grey" ? "var(--text-faint)" : top === "red" ? "var(--primary)" : "#1a7f37" }}>{verdict.word}</div>
            <div className="num text-[11px]" style={{ color: "var(--text-faint)" }}>{verdict.note} · 亮燈 {litCount}/{inds.length}</div>
          </div>
        </div>
      </header>

      <main className="max-w-[1180px] mx-auto px-6 py-6 space-y-5">
        {/* MIND MAP */}
        <section className="panel rounded-xl p-4 pb-2">
          <div className="flex items-center justify-between mb-1 px-1 flex-wrap gap-2">
            <h2 className="text-[15px] font-semibold">資金鏈路 · 心智圖</h2>
            <span className="num text-[11px]" style={{ color: "var(--text-faint)" }}>
              {selected ? "已選一段 · 點空白處取消" : "點箭頭看該段資金流的指標"}
            </span>
          </div>
          <FlowGraph nodes={data.graph.nodes} edges={data.graph.edges} edgeLamp={edgeLamp}
            selected={selected} hovered={hovered} onSelect={setSelected} onHover={setHovered} indCount={indCount} />
        </section>

        {/* DETAIL PANEL — driven by selected edge */}
        <section className="panel rounded-xl p-5 detail-panel">
          {selEdge ? (
            <>
              <div className="flex items-center gap-2 mb-1 flex-wrap">
                <span className="text-[15px] font-semibold">{nodeLabel[selEdge.from]}</span>
                <span style={{ color: "var(--primary)" }}>→</span>
                <span className="text-[15px] font-semibold">{nodeLabel[selEdge.to]}</span>
                <span className="text-[12px] px-2 py-0.5 rounded-full ml-1"
                  style={{ color: "var(--primary-dk)", background: "var(--tag-bg)" }}>{selEdge.label}</span>
              </div>
              <p className="text-[12px] mb-4" style={{ color: "var(--text-muted)" }}>這段資金流向上掛的監控指標。</p>
              {selInds.length > 0 ? (
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                  {selInds.map((i, idx) => <IndicatorCard key={i.indicator_key} i={i} idx={idx} />)}
                </div>
              ) : (
                <div className="rounded-lg p-6 text-center bloom"
                  style={{ border: "1px dashed var(--border)", background: "var(--bg-subtle)" }}>
                  <div className="text-[13px] font-semibold" style={{ color: "var(--text-muted)" }}>此段尚未掛指標</div>
                  <div className="text-[12px] mt-1" style={{ color: "var(--text-faint)" }}>待補 · {EDGE_HINT[selEdge.id] ?? "相關流量指標"}</div>
                </div>
              )}
            </>
          ) : envInds.length > 0 ? (
            <>
              <div className="flex items-center justify-between mb-1 flex-wrap gap-2">
                <h2 className="text-[15px] font-semibold">總體環境 · 背景</h2>
                <span className="num text-[11px]" style={{ color: "var(--text-faint)" }}>非單一箭頭 · 整個系統的水位與天氣</span>
              </div>
              <p className="text-[12px] mb-4" style={{ color: "var(--text-muted)" }}>👆 點上面任一箭頭可切到該段資金流的指標。</p>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {envInds.map((i, idx) => <IndicatorCard key={i.indicator_key} i={i} idx={idx} />)}
              </div>
            </>
          ) : (
            <div className="rounded-lg p-8 text-center" style={{ border: "1px dashed var(--border)", background: "var(--bg-subtle)" }}>
              <div className="text-[14px] font-semibold" style={{ color: "var(--text-muted)" }}>👆 點上方任一箭頭，看那段資金流的指標</div>
            </div>
          )}
        </section>

      </main>
    </div>
  );
}
