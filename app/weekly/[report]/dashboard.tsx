"use client";

import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import ThemeToggle from "@/app/components/ThemeToggle";
import NewsTable from "@/app/components/news/NewsTable";
import type { NewsItem } from "@/app/components/news/types";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Filler,
  Tooltip,
  Legend,
} from "chart.js";
import { Line } from "react-chartjs-2";

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Filler,
  Tooltip,
  Legend,
);

/* ================================================================
   Types
   ================================================================ */
interface ReportData {
  reportDate: string;
  reportWeek: string;
  ticker: string;
  company: string;
  market: string;
  technical: {
    close: number | null;
    weekChangePct: number | null;
    volume: number | null;
    date: string;
    ma: Record<string, number | null>;
    macd: { macd: number | null; signal: number | null; hist: number | null };
    bollinger: { upper: number | null; mid: number | null; lower: number | null };
    weeklyLabels: string[];
    weeklyClose: number[];
  };
  chips: {
    market: string;
    tw: {
      institutional: {
        date: string;
        foreign_net: number | null;
        trust_net: number | null;
        dealer_net: number | null;
        foreign_5d_net: number | null;
      };
      margin: {
        date: string;
        margin_balance: number | null;
        short_balance: number | null;
        margin_change: number | null;
        short_change: number | null;
      };
    };
    us: {
      shortInterest: any;
      institutionalOwnership: any;
    };
  };
  news?: { date: string; headline?: string; title?: string; link?: string }[];
  newsAnalysis?: {
    title: string;
    points: string[];
    table?: { headers: string[]; rows: string[][] };
  }[];
  debug: Record<string, { notes?: { level: string; msg: string }[]; api?: Record<string, string> }>;
}

/* ================================================================
   Helpers
   ================================================================ */
const fmtNum = (v: number | null | undefined, d = 2) =>
  v == null ? "—" : Number(v).toLocaleString(undefined, { maximumFractionDigits: d });

const fmtPct = (v: number | null | undefined, sign = true) =>
  v == null ? "—" : (sign && v > 0 ? "+" : "") + Number(v).toFixed(2) + "%";

const fmtVol = (v: number | null | undefined) => {
  if (v == null) return "—";
  if (v >= 1e9) return (v / 1e9).toFixed(1) + "B";
  if (v >= 1e6) return (v / 1e6).toFixed(1) + "M";
  if (v >= 1e3) return (v / 1e3).toFixed(0) + "K";
  return String(v);
};

const chgCls = (v: number | null | undefined) =>
  v == null ? "text-[var(--text-faint)]" : v > 0 ? "text-[#2D8A4E]" : v < 0 ? "text-[var(--primary)]" : "text-[#B07D10]";

/* ── Sub-components ── */

function KvCard({
  label,
  value,
  sub,
  valueClass,
}: {
  label: string;
  value: string;
  sub?: string;
  valueClass?: string;
}) {
  return (
    <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-card)] px-5 py-4 shadow-sm">
      <div className="text-xs uppercase tracking-wide text-[var(--text-muted)]">
        {label}
      </div>
      <div className={`mt-1 text-2xl font-bold ${valueClass ?? ""}`}>
        {value}
      </div>
      {sub && <div className="mt-0.5 text-xs text-[#6B5E60]">{sub}</div>}
    </div>
  );
}

function SectionTitle({ children, debugTags }: { children: React.ReactNode; debugTags?: React.ReactNode }) {
  return (
    <div className="mb-5 flex items-center gap-2 border-l-[3px] border-[var(--primary)] pl-3 text-lg font-semibold uppercase tracking-wider text-[var(--primary)]">
      {children}
      {debugTags}
    </div>
  );
}

function DebugBadge({ status }: { status: string }) {
  const cls =
    status === "ok"
      ? "bg-green-100 text-green-800"
      : status === "empty"
        ? "bg-yellow-100 text-yellow-800"
        : "bg-red-100 text-red-800";
  return (
    <span className={`ml-1 rounded px-1.5 py-0.5 text-[0.72rem] font-semibold ${cls}`}>
      {status}
    </span>
  );
}

/* ================================================================
   Main Dashboard
   ================================================================ */
export default function Dashboard({ data }: { data: ReportData }) {
  const searchParams = useSearchParams();
  const isDebug = searchParams.has("debug");
  const td = data.technical;

  // Dynamic news from Supabase, fallback to static JSON
  const [newsItems, setNewsItems] = useState<NewsItem[]>(
    (data.news ?? []).map((n) => ({
      date: n.date,
      headline: n.headline || n.title || "",
      summary: "",
      url: n.link,
    })),
  );
  useEffect(() => {
    if (!data.ticker || !data.reportWeek) return;
    const match = data.reportWeek.match(/^(\d{4})-W(\d{2})$/);
    if (!match) return;
    const year = parseInt(match[1]);
    const week = parseInt(match[2]);
    const prevWeek = week > 1 ? `${year}-W${String(week - 1).padStart(2, "0")}` : data.reportWeek;
    Promise.all([
      fetch(`/api/news?ticker=${data.ticker}&week=${data.reportWeek}`).then((r) => r.ok ? r.json() : { items: [] }),
      fetch(`/api/news?ticker=${data.ticker}&week=${prevWeek}`).then((r) => r.ok ? r.json() : { items: [] }),
    ])
      .then(([curr, prev]) => {
        const all: NewsItem[] = [...(curr.items || []), ...(prev.items || [])];
        const seen = new Set<string>();
        const unique = all.filter((n) => {
          if (!n.url || seen.has(n.url)) return false;
          seen.add(n.url);
          return true;
        });
        if (unique.length) setNewsItems(unique);
      })
      .catch(() => {});
  }, [data.ticker, data.reportWeek]);
  const market = data.chips.market || data.market;

  const sparklineData = useMemo(
    () => ({
      labels: td.weeklyLabels,
      datasets: [
        {
          label: data.ticker,
          data: td.weeklyClose,
          borderColor: "#C02734",
          backgroundColor: "rgba(192,39,52,0.06)",
          tension: 0.3,
          fill: true,
          pointRadius: 3,
        },
      ],
    }),
    [td.weeklyLabels, td.weeklyClose, data.ticker],
  );

  const chartOpts = {
    responsive: true,
    plugins: {
      legend: { labels: { color: "#2C1517", font: { size: 11 } } },
    },
    scales: {
      x: { ticks: { color: "#8B7E80" }, grid: { color: "#E0D8D8" } },
      y: { ticks: { color: "#8B7E80" }, grid: { color: "#E0D8D8" } },
    },
  };

  const indRows: [string, string, string][] = [
    ["MA5", td.ma?.MA5 != null ? fmtNum(td.ma.MA5) : "—", ""],
    ["MA20", td.ma?.MA20 != null ? fmtNum(td.ma.MA20) : "—", ""],
    ["MA60", td.ma?.MA60 != null ? fmtNum(td.ma.MA60) : "—", ""],
    ["MACD", td.macd?.macd != null ? td.macd.macd.toFixed(4) : "—", ""],
    ["MACD Signal", td.macd?.signal != null ? td.macd.signal.toFixed(4) : "—", ""],
    [
      "MACD Hist",
      td.macd?.hist != null ? td.macd.hist.toFixed(4) : "—",
      td.macd?.hist != null ? (td.macd.hist > 0 ? "text-[#2D8A4E]" : "text-[var(--primary)]") : "",
    ],
    ["Bollinger 上軌", td.bollinger?.upper != null ? fmtNum(td.bollinger.upper) : "—", ""],
    ["Bollinger 中軌", td.bollinger?.mid != null ? fmtNum(td.bollinger.mid) : "—", ""],
    ["Bollinger 下軌", td.bollinger?.lower != null ? fmtNum(td.bollinger.lower) : "—", ""],
  ];

  const fmtNet = (v: number | null) =>
    v == null ? "—" : (v > 0 ? "+" : "") + Number(v).toLocaleString();

  const renderDebugSection = (secId: string) => {
    if (!isDebug) return null;
    const sec = data.debug?.[secId];
    if (!sec) return null;
    return (
      <>
        {sec.api && (
          <span className="inline-flex gap-1">
            {Object.entries(sec.api).map(([k, v]) => (
              <span key={k} className="inline-flex items-center gap-0.5">
                <span className="text-[0.72rem] text-[var(--text-muted)]">{k}:</span>
                <DebugBadge status={v} />
              </span>
            ))}
          </span>
        )}
      </>
    );
  };

  const renderDebugNotes = (secId: string) => {
    if (!isDebug) return null;
    const notes = data.debug?.[secId]?.notes;
    if (!notes?.length) return null;
    const levelCls: Record<string, string> = {
      info: "text-[#0C5460]",
      warn: "text-[#856404]",
      error: "text-[#721C24]",
    };
    return (
      <ul className="mt-2 list-disc pl-4 text-xs">
        {notes.map((n, i) => (
          <li key={i} className={levelCls[n.level] || ""}>
            [{n.level.toUpperCase()}] {n.msg}
          </li>
        ))}
      </ul>
    );
  };

  return (
    <div className="mx-auto max-w-[1280px] px-6 py-8 pb-16">
      <Link
        href="/weekly"
        className="mb-3 inline-block text-sm font-semibold text-[var(--primary)] opacity-70 transition-opacity hover:opacity-100"
      >
        ← Stock Weekly
      </Link>

      {/* Debug Banner */}
      {isDebug && (
        <div className="mb-6 rounded-md border border-[#FFEAA7] bg-[#FFF3CD] px-4 py-2.5 text-sm text-[#856404]">
          <strong className="text-[#533F03]">DEBUG MODE</strong> — 標注資料來自 debug
        </div>
      )}

      {/* Header */}
      <header className="mb-8 flex items-end justify-between border-b border-[var(--border)] pb-5">
        <div>
          <h1 className="text-3xl font-bold tracking-wide">
            個股 <span className="text-[var(--primary)]">{data.ticker}</span> 週報
          </h1>
          <div className="mt-1 text-sm text-[#6B5E60]">{data.company}</div>
        </div>
        <div className="flex items-end gap-4">
          <div className="text-right text-sm text-[var(--text-muted)]">
            <div className="font-bold text-[var(--text)]">{data.reportWeek}</div>
            <div>{data.reportDate}</div>
          </div>
          <ThemeToggle />
        </div>
      </header>

      {/* ── 01 · 消息面 ── */}
      <section className="mb-12">
        <SectionTitle debugTags={renderDebugSection("sec-news")}>
          01 · 消息面
        </SectionTitle>

        <NewsTable items={newsItems} />

        {renderDebugNotes("sec-news")}
      </section>

      {/* ── 02 · 新聞分析 ── */}
      {data.newsAnalysis && data.newsAnalysis.length > 0 && (
        <section className="mb-12">
          <SectionTitle>02 · 新聞分析</SectionTitle>

          <div className="space-y-6">
            {data.newsAnalysis.map((block, bi) => (
              <div
                key={bi}
                className="rounded-lg border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm"
              >
                <h3 className="mb-3 text-base font-bold">{block.title}</h3>
                <ul className="mb-4 list-disc space-y-1.5 pl-5 text-sm leading-relaxed">
                  {block.points.map((p, pi) => (
                    <li key={pi}>{p}</li>
                  ))}
                </ul>
                {block.table && (
                  <div className="overflow-x-auto">
                    <table className="w-full border-collapse text-sm">
                      <thead>
                        <tr>
                          {block.table.headers.map((h, hi) => (
                            <th
                              key={hi}
                              className="border-b border-[var(--border)] bg-[var(--bg-subtle)] px-3 py-2 text-left text-xs font-normal uppercase text-[var(--text-muted)]"
                            >
                              {h}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {block.table.rows.map((row, ri) => (
                          <tr key={ri}>
                            {row.map((cell, ci) => (
                              <td
                                key={ci}
                                className={`border-b border-[var(--border)] px-3 py-2 ${ci === 0 ? "font-medium whitespace-nowrap" : ""}`}
                              >
                                {cell}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            ))}
          </div>
        </section>
      )}

      {/* ── 03 · 技術面 ── */}
      <section className="mb-12">
        <SectionTitle debugTags={renderDebugSection("sec-technical")}>
          03 · 技術面
        </SectionTitle>

        {/* Price Cards */}
        <div className="mb-4 grid gap-4 grid-cols-[repeat(auto-fill,minmax(200px,1fr))]">
          <KvCard label="收盤價" value={fmtNum(td.close)} sub={td.date} />
          <KvCard
            label="週漲跌"
            value={fmtPct(td.weekChangePct)}
            valueClass={chgCls(td.weekChangePct)}
          />
          <KvCard
            label="成交量"
            value={fmtVol(td.volume)}
            valueClass="text-[#B07D10]"
          />
        </div>

        {/* Sparkline */}
        <div className="mb-4 rounded-lg border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
          <h3 className="mb-4 text-sm text-[#6B5E60]">
            {data.ticker} 近 5 週收盤走勢
          </h3>
          {td.weeklyClose?.length > 0 ? (
            <Line data={sparklineData} options={chartOpts} height={120} />
          ) : (
            <p className="py-4 text-center text-sm italic text-[var(--text-faint)]">
              無週線資料
            </p>
          )}
        </div>

        {renderDebugNotes("sec-technical")}
      </section>

      {/* ── 02 · 籌碼面 ── */}
      <section className="mb-12">
        <SectionTitle debugTags={renderDebugSection("sec-chips")}>
          04 · 籌碼面
        </SectionTitle>

        {market === "tw" && (
          <>
            {/* 三大法人 */}
            <div className="mb-4">
              <div className="mb-2 text-xs text-[var(--text-muted)]">三大法人</div>
              <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
                {data.chips.tw.institutional.foreign_net != null ? (
                  <table className="w-full border-collapse">
                    <thead>
                      <tr>
                        <th className="border-b border-[var(--border)] px-4 py-2 text-left text-xs font-normal uppercase text-[var(--text-muted)]">法人</th>
                        <th className="border-b border-[var(--border)] px-4 py-2 text-right text-xs font-normal uppercase text-[var(--text-muted)]">當日買賣超</th>
                        <th className="border-b border-[var(--border)] px-4 py-2 text-right text-xs font-normal uppercase text-[var(--text-muted)]">近5日外資累計</th>
                      </tr>
                    </thead>
                    <tbody>
                      {[
                        ["外資", data.chips.tw.institutional.foreign_net, data.chips.tw.institutional.foreign_5d_net],
                        ["投信", data.chips.tw.institutional.trust_net, null],
                        ["自營商", data.chips.tw.institutional.dealer_net, null],
                      ].map(([label, val, extra]) => (
                        <tr key={label as string}>
                          <td className="border-b border-[var(--border)] px-4 py-2 text-sm">{label}</td>
                          <td className={`border-b border-[var(--border)] px-4 py-2 text-right text-sm ${chgCls(val as number)}`}>
                            {fmtNet(val as number)}
                          </td>
                          <td className={`border-b border-[var(--border)] px-4 py-2 text-right text-sm ${extra != null ? chgCls(extra as number) : ""}`}>
                            {extra != null ? fmtNet(extra as number) : "—"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : (
                  <p className="py-4 text-center text-sm italic text-[var(--text-faint)]">無三大法人資料</p>
                )}
              </div>
            </div>

            {/* 融資融券 */}
            <div className="mb-4">
              <div className="mb-2 text-xs text-[var(--text-muted)]">融資融券</div>
              <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
                {data.chips.tw.margin.margin_balance != null ? (
                  <table className="w-full border-collapse">
                    <thead>
                      <tr>
                        <th className="border-b border-[var(--border)] px-4 py-2 text-left text-xs font-normal uppercase text-[var(--text-muted)]">項目</th>
                        <th className="border-b border-[var(--border)] px-4 py-2 text-right text-xs font-normal uppercase text-[var(--text-muted)]">餘額</th>
                        <th className="border-b border-[var(--border)] px-4 py-2 text-right text-xs font-normal uppercase text-[var(--text-muted)]">增減</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr>
                        <td className="border-b border-[var(--border)] px-4 py-2 text-sm">融資餘額</td>
                        <td className="border-b border-[var(--border)] px-4 py-2 text-right text-sm">{fmtNum(data.chips.tw.margin.margin_balance, 0)}</td>
                        <td className={`border-b border-[var(--border)] px-4 py-2 text-right text-sm ${chgCls(data.chips.tw.margin.margin_change)}`}>
                          {fmtNet(data.chips.tw.margin.margin_change)}
                        </td>
                      </tr>
                      <tr>
                        <td className="border-b border-[var(--border)] px-4 py-2 text-sm">融券餘額</td>
                        <td className="border-b border-[var(--border)] px-4 py-2 text-right text-sm">{fmtNum(data.chips.tw.margin.short_balance, 0)}</td>
                        <td className={`border-b border-[var(--border)] px-4 py-2 text-right text-sm ${chgCls(data.chips.tw.margin.short_change)}`}>
                          {fmtNet(data.chips.tw.margin.short_change)}
                        </td>
                      </tr>
                    </tbody>
                  </table>
                ) : (
                  <p className="py-4 text-center text-sm italic text-[var(--text-faint)]">無融資融券資料</p>
                )}
              </div>
            </div>
          </>
        )}

        {market === "us" && (
          <div className="grid gap-4 grid-cols-[repeat(auto-fill,minmax(200px,1fr))]">
            <KvCard
              label="Short Interest"
              value={
                data.chips.us.shortInterest && !data.chips.us.shortInterest.error
                  ? (() => {
                      const si = data.chips.us.shortInterest;
                      const pct = si.shortPercentFloat ?? si.shortPercent ?? si.short_float_pct;
                      return pct != null ? fmtPct(pct * 100, false) + " of float" : "—";
                    })()
                  : "—"
              }
              valueClass={data.chips.us.shortInterest ? "" : "text-[var(--text-faint)]"}
            />
            <KvCard
              label="Institutional Ownership"
              value={
                data.chips.us.institutionalOwnership && !data.chips.us.institutionalOwnership.error
                  ? (() => {
                      const io = data.chips.us.institutionalOwnership;
                      const pct = io.pctHeld ?? io.institutionalOwnership ?? io.total_pct;
                      return pct != null ? fmtPct(pct * 100, false) : "—";
                    })()
                  : "—"
              }
              valueClass={data.chips.us.institutionalOwnership ? "" : "text-[var(--text-faint)]"}
            />
          </div>
        )}

        {market !== "tw" && market !== "us" && (
          <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
            <p className="py-4 text-center text-sm italic text-[var(--text-faint)]">
              無籌碼資料（請設定 API Key）
            </p>
          </div>
        )}

        {renderDebugNotes("sec-chips")}
      </section>

      {/* Footer */}
      <footer className="border-t border-[var(--border)] pt-4 text-xs text-[var(--text-faint)]">
        Data sources: yfinance · FinMind · Fintel · Barchart
        {data.market && ` · Market: ${data.market.toUpperCase()}`}
      </footer>
    </div>
  );
}
