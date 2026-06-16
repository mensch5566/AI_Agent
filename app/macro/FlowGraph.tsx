"use client";
import type { GraphEdge, GraphNode, LampColor } from "@/lib/macro/types";

const STAGE_X: Record<number, number> = { 1: 60, 3: 300, 4: 560, 5: 300 };
const LAMP_STROKE: Record<LampColor, string> = { green: "#1a7f37", red: "#c02734", grey: "#b09898" };

// 每個 stage 內節點縱向排列
function layout(nodes: GraphNode[]) {
  const byStage: Record<number, GraphNode[]> = {};
  nodes.forEach((n) => (byStage[n.stage] ??= []).push(n));
  const pos: Record<string, { x: number; y: number }> = {};
  Object.entries(byStage).forEach(([stage, ns]) => {
    ns.forEach((n, i) => {
      const baseY = stage === "5" ? 360 : 60;
      pos[n.id] = { x: STAGE_X[Number(stage)] ?? 300, y: baseY + i * 70 };
    });
  });
  return pos;
}

export default function FlowGraph({
  nodes, edges, edgeLamp,
}: { nodes: GraphNode[]; edges: GraphEdge[]; edgeLamp: Record<string, LampColor> }) {
  const pos = layout(nodes);
  return (
    <svg viewBox="0 0 760 460" className="w-full h-auto">
      {edges.map((e) => {
        const a = pos[e.from], b = pos[e.to];
        if (!a || !b) return null;
        const color = LAMP_STROKE[edgeLamp[e.id] ?? "grey"];
        return (
          <g key={e.id}>
            <line x1={a.x + 50} y1={a.y + 16} x2={b.x} y2={b.y + 16}
              stroke={color} strokeWidth={2.5} markerEnd="url(#arrow)" />
            <text x={(a.x + b.x) / 2 + 25} y={(a.y + b.y) / 2 + 8} fontSize="10" fill="#7a5860">{e.label}</text>
          </g>
        );
      })}
      {nodes.map((n) => {
        const p = pos[n.id];
        return (
          <g key={n.id}>
            <rect x={p.x} y={p.y} width={100} height={32} rx={8} fill="#fff" stroke="#e2d8d8" />
            <text x={p.x + 50} y={p.y + 20} fontSize="11" textAnchor="middle" fill="#2c1517">{n.label}</text>
          </g>
        );
      })}
      <defs>
        <marker id="arrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
          <path d="M0,0 L6,3 L0,6 Z" fill="#b09898" />
        </marker>
      </defs>
    </svg>
  );
}
