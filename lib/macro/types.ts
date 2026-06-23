export type Layer = "L1" | "L2" | "L3" | "L4" | "L5";
export type Polarity = "higher_better" | "lower_better";
export type LampColor = "green" | "red" | "grey";

export interface Indicator {
  indicator_key: string;
  fred_series: string;
  label: string;
  source_label?: string;
  layer: Layer;
  polarity: Polarity;
  edge_id: string;
  unit: string;
  freq: string;
  primary: boolean;
}

export interface MacroFact {
  indicator_key: string;
  value: number;
  period_end: string; // ISO date
}

export interface Lamp {
  color: LampColor;
  curr: number | null;
  prev: number | null;
  polarity: Polarity;
  basis: string;
}

export interface GraphNode { id: string; label: string; stage: number; }
export interface GraphEdge { id: string; from: string; to: string; label: string; }
export interface IndicatorConfig {
  version: number;
  indicators: Indicator[];
  graph: { nodes: GraphNode[]; edges: GraphEdge[] };
}
