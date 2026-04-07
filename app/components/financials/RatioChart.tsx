"use client";

/* eslint-disable @typescript-eslint/no-explicit-any */
import { useState, useMemo } from "react";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Tooltip,
  Legend,
} from "chart.js";
import { Line } from "react-chartjs-2";
import {
  RATIO_ORDER,
  RATIO_DEFINITIONS,
  CHART_COLORS,
  isPct,
  labelFor,
} from "./constants";
import { useFinancialData } from "./useFinancialData";

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Tooltip, Legend);

interface RatioChartProps {
  ticker: string;
  metrics: string[];
  defaultSelected?: string[];
  height?: number;
  defaultView?: "quarterly" | "annual";
}

export default function RatioChart({
  ticker, metrics, defaultSelected, height = 300, defaultView = "quarterly",
}: RatioChartProps) {
  const { store: rawStore, loading, error } = useFinancialData(ticker);
  const [viewMode, setViewMode] = useState<"quarterly" | "annual">(defaultView);
  const [selected, setSelected] = useState<Set<string>>(
    () => new Set(defaultSelected ?? metrics),
  );

  const store = useMemo(() => {
    if (!rawStore) return null;
    return viewMode === "annual" ? rawStore.toAnnual() : rawStore;
  }, [rawStore, viewMode]);

  if (loading) return <div className="flex items-center justify-center py-10 text-sm text-[var(--text-faint)]">載入財務數據中...</div>;
  if (error || !store) return <div className="py-6 text-center text-sm text-[var(--text-faint)]">{error ? `無法載入 ${ticker} 財務數據：${error}` : "無數據"}</div>;

  const periods = store.periods("financial_ratios");
  const allMetrics = store.metrics("financial_ratios");
  if (!allMetrics.length) return <div className="py-6 text-center text-sm text-[var(--text-faint)]">無財務比率數據</div>;

  const available = metrics.filter((m) => allMetrics.includes(m));
  const ordered = RATIO_ORDER.filter((k) => available.includes(k));
  for (const k of available) if (!ordered.includes(k)) ordered.push(k);

  const toggleMetric = (m: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(m)) next.delete(m); else next.add(m);
      return next;
    });
  };

  const selArr = ordered.filter((k) => selected.has(k));
  const usePercent = selArr.some((k) => isPct(k));

  const chartData = {
    labels: periods,
    datasets: selArr.map((key, i) => ({
      label: labelFor(key).trim(),
      data: periods.map((p) => store.val("financial_ratios", key, p)),
      borderColor: CHART_COLORS[i % CHART_COLORS.length],
      backgroundColor: CHART_COLORS[i % CHART_COLORS.length] + "22",
      tension: 0.3, pointRadius: 3, spanGaps: true,
    })),
  };

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-1.5">
        {ordered.map((key) => {
          const def = RATIO_DEFINITIONS[key];
          return (
            <button key={key} onClick={() => toggleMetric(key)} title={def}
              className={`cursor-pointer rounded-full border px-3 py-1 text-xs transition-all select-none ${
                selected.has(key)
                  ? "border-[#1f4e79] bg-[#1f4e79] text-white"
                  : "border-[var(--border)] bg-[var(--bg-subtle)] text-[var(--text)] hover:border-[#2a6da8] hover:text-[#2a6da8]"
              }`}
            >{labelFor(key).trim()}</button>
          );
        })}
        <div className="ml-auto flex gap-1">
          {(["quarterly", "annual"] as const).map((m) => (
            <button key={m} onClick={() => setViewMode(m)}
              className={`rounded border px-2.5 py-1 text-xs font-semibold transition-all select-none ${
                viewMode === m ? "border-[var(--primary)] bg-[var(--primary)] text-white" : "border-[var(--border)] bg-[var(--bg-subtle)] text-[var(--text-muted)] hover:border-[var(--primary)]"
              }`}
            >{m === "quarterly" ? "季度" : "年度"}</button>
          ))}
        </div>
      </div>
      <div style={{ height }}>
        {selArr.length > 0 ? (
          <Line data={chartData} options={{
            responsive: true, maintainAspectRatio: false,
            interaction: { mode: "index" as const, intersect: false },
            plugins: {
              tooltip: { callbacks: { label: (ctx: any) => {
                const key = selArr[ctx.datasetIndex]; const v = ctx.parsed.y;
                if (v === null) return `${ctx.dataset.label}: —`;
                return isPct(key) ? `${ctx.dataset.label}: ${(v * 100).toFixed(1)}%` : `${ctx.dataset.label}: ${v.toFixed(2)}`;
              }}},
              legend: { position: "bottom" as const, labels: { boxWidth: 12, font: { size: 11 } } },
            },
            scales: {
              x: { ticks: { font: { size: 10 }, maxRotation: 45 } },
              y: { ticks: { font: { size: 10 }, callback: (v: any) => usePercent ? (v * 100).toFixed(0) + "%" : Number(v).toFixed(2) } },
            },
          }} />
        ) : (
          <div className="flex h-full items-center justify-center text-sm text-[var(--text-faint)]">請選擇至少一個指標</div>
        )}
      </div>
    </div>
  );
}
