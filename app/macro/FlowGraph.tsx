"use client";
import type { GraphEdge, GraphNode, LampColor } from "@/lib/macro/types";

// Bilateral layout (viewBox 1040×560). CSP is the plate in the middle:
//   LEFT  = inflows  → financing (FED→BANK) on top, monetization (B2B/B2C) on bottom
//   RIGHT = outflows → capex fan to chips, then foundry/equipment chain
const NODE: Record<string, { x: number; y: number; w: number; h: number; hub?: boolean }> = {
  // left · inflows
  FED:     { x: 30,  y: 95,  w: 120, h: 46 },
  BANK:    { x: 215, y: 95,  w: 120, h: 46 },
  B2B:     { x: 30,  y: 360, w: 140, h: 46 },
  B2C:     { x: 30,  y: 452, w: 140, h: 46 },
  // center · hub
  CSP:     { x: 445, y: 222, w: 150, h: 58, hub: true },
  // right · outflows
  GPU:     { x: 660, y: 70,  w: 140, h: 46 },
  CPU:     { x: 660, y: 165, w: 140, h: 46 },
  MEM:     { x: 660, y: 260, w: 140, h: 46 },
  SYS:     { x: 660, y: 355, w: 140, h: 46 },
  FOUNDRY: { x: 862, y: 70,  w: 128, h: 46 },
  EQUIP:   { x: 862, y: 165, w: 128, h: 46 },
};

const LAMP_STROKE: Record<LampColor, string> = { green: "#1a7f37", red: "#c02734", grey: "#d2c6c6" };
const DOT_COLOR: Record<LampColor, string> = { green: "#1a7f37", red: "#c02734", grey: "#b9a0a4" };
const SELECTED = "#c02734";

// rough text width (CJK ≈ fontSize, space ≈ .35em, latin ≈ .6em) for centered label chips
function labelWidth(s: string, fs: number) {
  return [...s].reduce((w, ch) => w + (/[　-鿿]/.test(ch) ? fs : ch === " " ? fs * 0.35 : fs * 0.6), 0);
}

// Bezier between two node borders; exit/entry side chosen by dominant axis.
function path(s: typeof NODE[string], t: typeof NODE[string]) {
  const sc = { x: s.x + s.w / 2, y: s.y + s.h / 2 };
  const tc = { x: t.x + t.w / 2, y: t.y + t.h / 2 };
  const dx = tc.x - sc.x, dy = tc.y - sc.y;
  let a, b;
  if (Math.abs(dx) >= Math.abs(dy)) {
    a = { x: dx > 0 ? s.x + s.w : s.x, y: sc.y };
    b = { x: dx > 0 ? t.x : t.x + t.w, y: tc.y };
    const o = (b.x - a.x) * 0.5;
    return { d: `M${a.x},${a.y} C${a.x + o},${a.y} ${b.x - o},${b.y} ${b.x},${b.y}`, c1: { x: a.x + o, y: a.y }, c2: { x: b.x - o, y: b.y }, a, b };
  }
  a = { x: sc.x, y: dy > 0 ? s.y + s.h : s.y };
  b = { x: tc.x, y: dy > 0 ? t.y : t.y + t.h };
  const o = (b.y - a.y) * 0.5;
  return { d: `M${a.x},${a.y} C${a.x},${a.y + o} ${b.x},${b.y - o} ${b.x},${b.y}`, c1: { x: a.x, y: a.y + o }, c2: { x: b.x, y: b.y - o }, a, b };
}

// Cubic-bezier midpoint (t=0.5) for the label anchor.
function mid(a: any, c1: any, c2: any, b: any) {
  return { x: (a.x + 3 * c1.x + 3 * c2.x + b.x) / 8, y: (a.y + 3 * c1.y + 3 * c2.y + b.y) / 8 };
}

export default function FlowGraph({
  nodes, edges, edgeLamp, selected, hovered, onSelect, onHover,
}: {
  nodes: GraphNode[]; edges: GraphEdge[]; edgeLamp: Record<string, LampColor>;
  selected: string | null; hovered: string | null;
  onSelect: (id: string | null) => void; onHover: (id: string | null) => void;
}) {
  const activeNodes = new Set<string>();
  if (selected) { const e = edges.find((x) => x.id === selected); if (e) { activeNodes.add(e.from); activeNodes.add(e.to); } }
  const dimmed = (id: string) => selected !== null && !activeNodes.has(id);

  return (
    <svg viewBox="0 0 1040 560" className="w-full h-auto select-none" onClick={() => onSelect(null)}>
      <defs>
        {(["green", "red", "grey"] as LampColor[]).map((c) => (
          <marker key={c} id={`mk-${c}`} markerWidth="9" markerHeight="9" refX="6.5" refY="3" orient="auto">
            <path d="M0,0 L6.5,3 L0,6 Z" fill={LAMP_STROKE[c]} />
          </marker>
        ))}
        <marker id="mk-sel" markerWidth="11" markerHeight="11" refX="6.5" refY="3" orient="auto">
          <path d="M0,0 L6.5,3 L0,6 Z" fill={SELECTED} />
        </marker>
        <filter id="glow" x="-40%" y="-40%" width="180%" height="180%">
          <feGaussianBlur stdDeviation="4" result="b" /><feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge>
        </filter>
        <filter id="nshadow" x="-30%" y="-30%" width="160%" height="160%">
          <feDropShadow dx="0" dy="2" stdDeviation="2.5" floodColor="#2c1517" floodOpacity="0.12" />
        </filter>
        <linearGradient id="hubFill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#fff" /><stop offset="1" stopColor="var(--bg-highlight)" />
        </linearGradient>
      </defs>

      {/* group eyebrows — make the inflow/outflow structure legible at a glance */}
      <g style={{ pointerEvents: "none" }} fontWeight={700} letterSpacing="0.08em">
        <text x={182} y={40} fontSize="17" textAnchor="middle" fill="var(--text)">資金流入</text>
        <text x={820} y={40} fontSize="17" textAnchor="middle" fill="var(--text)">資金流出</text>
      </g>

      {/* EDGES */}
      {edges.map((e) => {
        const s = NODE[e.from], t = NODE[e.to];
        if (!s || !t) return null;
        const p = path(s, t);
        const m = mid(p.a, p.c1, p.c2, p.b);
        const lamp = edgeLamp[e.id] ?? "grey";
        const isSel = selected === e.id;
        const isHov = hovered === e.id;
        const dim = selected !== null && !isSel;
        const stroke = isSel ? SELECTED : LAMP_STROKE[lamp];
        const dotCol = isSel ? SELECTED : DOT_COLOR[lamp];
        const fs = 11;
        const lineH = 12.5;
        const lines = e.label.split("／"); // wrap "A／B" labels onto stacked lines so short arrows aren't covered
        const chipW = Math.max(...lines.map((l) => labelWidth(l, fs))) + 16;
        const chipH = lines.length * lineH + 5;
        const lit = isSel || isHov;
        return (
          <g key={e.id} className="edge-group" opacity={dim ? 0.26 : 1}
            onClick={(ev) => { ev.stopPropagation(); onSelect(isSel ? null : e.id); }}
            onMouseEnter={() => onHover(e.id)} onMouseLeave={() => onHover(null)} style={{ cursor: "pointer" }}>
            {/* fat invisible hit area */}
            <path d={p.d} fill="none" stroke="transparent" strokeWidth={20} />
            {/* visible line (also the motion path for flowing dots) */}
            <path id={`p-${e.id}`} d={p.d} fill="none" stroke={stroke}
              strokeWidth={isSel ? 4 : isHov ? 3 : 2.2}
              markerEnd={`url(#${isSel ? "mk-sel" : `mk-${lamp}`})`}
              className={isSel ? "edge-selected-glow" : ""} filter={isSel ? "url(#glow)" : undefined} />
            {/* flowing particles → direction of money flow */}
            {[0, 1, 2].map((k) => (
              <circle key={k} r={isSel ? 3.2 : 2.4} fill={dotCol} opacity={isSel ? 0.95 : 0.5} style={{ pointerEvents: "none" }}>
                <animateMotion dur={isSel ? "1.5s" : "2.6s"} begin={`-${k * (isSel ? 0.5 : 0.87)}s`} repeatCount="indefinite">
                  <mpath href={`#p-${e.id}`} />
                </animateMotion>
              </circle>
            ))}
            {/* centered label chip (wraps "A／B" onto stacked lines) */}
            <g style={{ pointerEvents: "none" }}>
              <rect x={m.x - chipW / 2} y={m.y - chipH / 2} rx={9} width={chipW} height={chipH}
                fill={lit ? SELECTED : "var(--bg-card)"} stroke={lit ? SELECTED : "var(--border)"} strokeWidth={1} />
              {lines.map((ln, li) => (
                <text key={li} x={m.x} y={m.y - (lines.length - 1) / 2 * lineH + li * lineH + fs * 0.35}
                  fontSize={fs} textAnchor="middle" fontWeight={600} fill={lit ? "#fff" : "var(--text-muted)"}>{ln}</text>
              ))}
            </g>
          </g>
        );
      })}

      {/* NODES */}
      {nodes.map((n) => {
        const b = NODE[n.id];
        if (!b) return null;
        const active = selected !== null && activeNodes.has(n.id);
        return (
          <g key={n.id} opacity={dimmed(n.id) ? 0.3 : 1} style={{ pointerEvents: "none" }}>
            <rect x={b.x} y={b.y} width={b.w} height={b.h} rx={b.hub ? 16 : 11}
              fill={b.hub ? "url(#hubFill)" : "var(--bg-card)"}
              stroke={active || b.hub ? SELECTED : "var(--border)"} strokeWidth={active ? 2 : b.hub ? 1.6 : 1}
              filter="url(#nshadow)" />
            <text x={b.x + b.w / 2} y={b.y + b.h / 2 + (b.hub ? 6 : 5)} fontSize={b.hub ? 17 : 13.5}
              fontWeight={b.hub ? 700 : 600} textAnchor="middle" fill="var(--text)">{n.label}</text>
          </g>
        );
      })}
    </svg>
  );
}
