"use client";

import { useEffect, useMemo, useState } from "react";
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

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Tooltip, Legend);

type Frame = "day" | "month" | "quarter";
type EpsMode = "diluted" | "basic";

interface ApiPoint {
  date: string;
  close: number;
  basicEpsTtm: number | null;
  dilutedEpsTtm: number | null;
}

interface ApiResponse {
  ticker: string;
  currency: string | null;
  series: ApiPoint[];
  note?: string;
}

interface DisplayPoint {
  date: string;
  pe: number | null;
  epsTtm: number | null;
}

const WINDOW_MAP: Record<Frame, Record<1 | 2 | 3 | 5, number>> = {
  day: { 1: 252, 2: 504, 3: 756, 5: 1260 },
  month: { 1: 12, 2: 24, 3: 36, 5: 60 },
  quarter: { 1: 4, 2: 8, 3: 12, 5: 20 },
};

function mean(values: Array<number | null>) {
  const valid = values.filter((value): value is number => typeof value === "number" && Number.isFinite(value));
  if (!valid.length) return null;
  return valid.reduce((sum, value) => sum + value, 0) / valid.length;
}

function movingAverage(values: Array<number | null>, windowSize: number) {
  return values.map((_, idx) => {
    const start = Math.max(0, idx - windowSize + 1);
    return mean(values.slice(start, idx + 1));
  });
}

function resampleSeries(points: DisplayPoint[], frame: Frame) {
  if (frame === "day") return points;

  const map = new Map<string, DisplayPoint>();
  for (const point of points) {
    const date = new Date(point.date);
    const key =
      frame === "month"
        ? `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, "0")}`
        : `${date.getUTCFullYear()}-Q${Math.floor(date.getUTCMonth() / 3) + 1}`;
    map.set(key, point);
  }
  return Array.from(map.values());
}

function formatNumber(value: number | null, digits = 2) {
  return value === null ? "N/A" : value.toFixed(digits);
}

function formatPercent(value: number | null) {
  return value === null ? "N/A" : `${value.toFixed(2)}%`;
}

function colorForPremium(value: number | null) {
  if (value === null) return "text-[var(--text-faint)]";
  return value >= 0 ? "text-[#c0392b]" : "text-[#1e8449]";
}

export default function ValuationChart({ ticker }: { ticker: string }) {
  const [frame, setFrame] = useState<Frame>("quarter");
  const [epsMode, setEpsMode] = useState<EpsMode>("diluted");
  const [data, setData] = useState<ApiResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!ticker) {
      setData(null);
      setError(null);
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);

    fetch(`/api/valuation/${ticker}`)
      .then((response) => {
        return response.json().then((json) => {
          if (!response.ok) {
            const message =
              typeof json?.error === "string" && json.error.trim().length
                ? json.error
                : `HTTP ${response.status}`;
            throw new Error(message);
          }
          return json as ApiResponse;
        });
      })
      .then((json) => {
        if (cancelled) return;
        setData(json);
        setLoading(false);
      })
      .catch((err: Error) => {
        if (cancelled) return;
        setError(err.message);
        setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [ticker]);

  const displaySeries = useMemo(() => {
    const raw = data?.series ?? [];
    const normalized = raw.map((point) => {
      const epsTtm = epsMode === "diluted" ? point.dilutedEpsTtm : point.basicEpsTtm;
      return {
        date: point.date,
        epsTtm,
        pe: epsTtm === null ? null : epsTtm > 0 ? point.close / epsTtm : 0,
      };
    });
    return resampleSeries(normalized, frame);
  }, [data, epsMode, frame]);

  const peValues = useMemo(() => displaySeries.map((point) => point.pe), [displaySeries]);
  const windows = WINDOW_MAP[frame];
  const ma1 = useMemo(() => movingAverage(peValues, windows[1]), [peValues, windows]);
  const ma2 = useMemo(() => movingAverage(peValues, windows[2]), [peValues, windows]);
  const ma3 = useMemo(() => movingAverage(peValues, windows[3]), [peValues, windows]);
  const ma5 = useMemo(() => movingAverage(peValues, windows[5]), [peValues, windows]);

  const summary = useMemo(() => {
    const current = peValues.length ? peValues[peValues.length - 1] : null;
    const avg = (count: number) => {
      if (peValues.length < count) return null;
      return mean(peValues.slice(-count));
    };
    const avg5 = avg(windows[5]);
    const premium = current !== null && avg5 !== null && avg5 !== 0 ? (current / avg5 - 1) * 100 : null;
    const epsTtm = displaySeries.length ? displaySeries[displaySeries.length - 1].epsTtm : null;
    return {
      current,
      avg1: avg(windows[1]),
      avg2: avg(windows[2]),
      avg3: avg(windows[3]),
      avg5,
      premium,
      epsTtm,
    };
  }, [displaySeries, peValues, windows]);

  const chartData = useMemo(() => ({
    labels: displaySeries.map((point) => {
      if (frame === "day") return point.date;
      const date = new Date(point.date);
      if (frame === "month") return `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, "0")}`;
      return `${date.getUTCFullYear()}Q${Math.floor(date.getUTCMonth() / 3) + 1}`;
    }),
    datasets: [
      {
        label: "PE Ratio",
        data: peValues,
        borderColor: "#ffffff",
        backgroundColor: "#ffffff22",
        borderWidth: 2,
        pointRadius: frame === "day" ? 0 : 2,
        spanGaps: true,
        tension: 0.2,
      },
      {
        label: "1Y Avg",
        data: ma1,
        borderColor: "#f1c40f",
        borderWidth: 2,
        pointRadius: 0,
        spanGaps: true,
        tension: 0.2,
      },
      {
        label: "2Y Avg",
        data: ma2,
        borderColor: "#e67e22",
        borderWidth: 2,
        pointRadius: 0,
        spanGaps: true,
        tension: 0.2,
      },
      {
        label: "3Y Avg",
        data: ma3,
        borderColor: "#e74c3c",
        borderWidth: 2,
        pointRadius: 0,
        spanGaps: true,
        tension: 0.2,
      },
      {
        label: "5Y Avg",
        data: ma5,
        borderColor: "#8e44ad",
        borderWidth: 2,
        pointRadius: 0,
        spanGaps: true,
        tension: 0.2,
      },
    ],
  }), [displaySeries, frame, ma1, ma2, ma3, ma5, peValues]);

  if (!ticker) {
    return <div className="py-12 text-center text-sm text-[var(--text-faint)]">Select a ticker to view valuation history.</div>;
  }
  if (loading) {
    return <div className="py-12 text-center text-sm text-[var(--text-faint)]">Loading valuation data...</div>;
  }
  if (error || !data || !displaySeries.length) {
    const message = error
      ? `Unable to load valuation data: ${error}`
      : data?.note || "No valuation data.";
    return <div className="py-12 text-center text-sm text-[var(--text-faint)]">{message}</div>;
  }

  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-card)] p-4 shadow-sm">
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="text-sm font-semibold text-[var(--text)]">
          {ticker.toUpperCase()} TTM P/E History
        </div>
        <div className="ml-auto flex gap-1">
          {(["day", "month", "quarter"] as const).map((value) => (
            <button
              key={value}
              onClick={() => setFrame(value)}
              className={`rounded border px-2.5 py-1 text-xs font-semibold ${
                frame === value
                  ? "border-[var(--primary)] bg-[var(--primary)] text-white"
                  : "border-[var(--border)] bg-[var(--bg-subtle)] text-[var(--text-muted)]"
              }`}
            >
              {value === "day" ? "日" : value === "month" ? "月" : "季"}
            </button>
          ))}
        </div>
        <div className="flex gap-1">
          {(["diluted", "basic"] as const).map((value) => (
            <button
              key={value}
              onClick={() => setEpsMode(value)}
              className={`rounded border px-2.5 py-1 text-xs font-semibold ${
                epsMode === value
                  ? "border-[#1f4e79] bg-[#1f4e79] text-white"
                  : "border-[var(--border)] bg-[var(--bg-subtle)] text-[var(--text-muted)]"
              }`}
            >
              {value === "diluted" ? "Diluted EPS" : "Basic EPS"}
            </button>
          ))}
        </div>
      </div>

      <div className="mb-4 grid gap-3 md:grid-cols-[minmax(0,1fr)_320px]">
        <div className="h-[420px] rounded-lg border border-[var(--border)] bg-[#151a20] p-3">
          <Line
            data={chartData}
            options={{
              responsive: true,
              maintainAspectRatio: false,
              interaction: { mode: "index", intersect: false },
              plugins: {
                legend: {
                  position: "bottom",
                  labels: { color: "#d7dde5", boxWidth: 12, font: { size: 11 } },
                },
                tooltip: {
                  callbacks: {
                    label: (ctx) => {
                      const value = ctx.parsed.y;
                      return `${ctx.dataset.label}: ${value === null ? "N/A" : Number(value).toFixed(2)}`;
                    },
                  },
                },
              },
              scales: {
                x: {
                  ticks: { color: "#c7ced6", maxRotation: 45, autoSkip: true, maxTicksLimit: frame === "day" ? 16 : 12 },
                  grid: { color: "rgba(255,255,255,0.08)" },
                },
                y: {
                  ticks: { color: "#c7ced6" },
                  grid: { color: "rgba(255,255,255,0.08)" },
                },
              },
            }}
          />
        </div>

        <div className="overflow-hidden rounded-lg border border-[var(--border)] bg-[var(--bg-subtle)]">
          <table className="w-full text-sm">
            <thead className="bg-[#1f4e79] text-white">
              <tr>
                <th className="px-3 py-2 text-left">Metric</th>
                <th className="px-3 py-2 text-right">Value</th>
              </tr>
            </thead>
            <tbody>
              <tr className="border-t border-[var(--border)]">
                <td className="px-3 py-2 font-semibold text-[var(--primary)]">Current</td>
                <td className="px-3 py-2 text-right font-semibold text-[var(--primary)]">{formatNumber(summary.current)}</td>
              </tr>
              <tr className="border-t border-[var(--border)]">
                <td className="px-3 py-2">1Y Average</td>
                <td className="px-3 py-2 text-right">{formatNumber(summary.avg1)}</td>
              </tr>
              <tr className="border-t border-[var(--border)]">
                <td className="px-3 py-2">2Y Average</td>
                <td className="px-3 py-2 text-right">{formatNumber(summary.avg2)}</td>
              </tr>
              <tr className="border-t border-[var(--border)]">
                <td className="px-3 py-2">3Y Average</td>
                <td className="px-3 py-2 text-right">{formatNumber(summary.avg3)}</td>
              </tr>
              <tr className="border-t border-[var(--border)]">
                <td className="px-3 py-2">5Y Average</td>
                <td className="px-3 py-2 text-right">{formatNumber(summary.avg5)}</td>
              </tr>
              <tr className="border-t border-[var(--border)]">
                <td className="px-3 py-2">EPS TTM</td>
                <td className="px-3 py-2 text-right">{formatNumber(summary.epsTtm)}</td>
              </tr>
              <tr className="border-t border-[var(--border)]">
                <td className="px-3 py-2">vs 5Y</td>
                <td className={`px-3 py-2 text-right font-semibold ${colorForPremium(summary.premium)}`}>
                  {formatPercent(summary.premium)}
                </td>
              </tr>
              <tr className="border-t border-[var(--border)]">
                <td className="px-3 py-2">Mode</td>
                <td className="px-3 py-2 text-right">{epsMode === "diluted" ? "Diluted TTM" : "Basic TTM"}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div className="space-y-1 text-[11px] text-[var(--text-faint)]">
        <div>PE = sampled close / latest reported TTM EPS. Daily, monthly, and quarterly views use the same underlying TTM EPS series with different price sampling frequencies.</div>
        <div>When TTM EPS is zero or negative, the chart clamps P/E to 0 so the timeline remains visible.</div>
        {data.note && <div>{data.note}</div>}
      </div>
    </div>
  );
}
