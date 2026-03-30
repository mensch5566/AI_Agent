"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
  ArcElement,
} from "chart.js";
import { Line, Doughnut } from "react-chartjs-2";

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Filler,
  Tooltip,
  Legend,
  ArcElement,
);

const doughnutOpts = {
  responsive: true,
  cutout: "60%",
  plugins: {
    legend: { display: true, position: "bottom" as const, labels: { font: { size: 12 }, padding: 12 } },
  },
};

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
      images?: { src: string; label: string }[];
    };
  };
  news?: { date: string; headline?: string; title?: string; summary?: string; link?: string; ticker?: string; sentiment?: string }[];
  newsAnalysis?: {
    title: string;
    points: string[];
    table?: { headers: string[]; rows: string[][] };
    charts?: { type: string; title: string; labels: string[]; values: number[]; colors: string[] }[];
    sources?: { label: string; url: string }[];
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
   TradingView Advanced Chart — embedded via official widget script
   ================================================================ */
function TradingViewChart({ symbol }: { symbol: string }) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    el.innerHTML = "";

    const script = document.createElement("script");
    script.src = "https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js";
    script.async = true;
    script.type = "text/javascript";
    script.textContent = JSON.stringify({
      autosize: true,
      symbol,
      interval: "D",
      timezone: "America/New_York",
      theme: "light",
      style: "1",
      locale: "en",
      hide_top_toolbar: false,
      hide_legend: false,
      allow_symbol_change: false,
      save_image: false,
      calendar: false,
      studies: [
        { id: "MASimple@tv-basicstudies", inputs: { length: 20 } },
        { id: "MASimple@tv-basicstudies", inputs: { length: 60 } },
        { id: "MASimple@tv-basicstudies", inputs: { length: 100 } },
      ],
      support_host: "https://www.tradingview.com",
    });

    const wrapper = document.createElement("div");
    wrapper.className = "tradingview-widget-container__widget";
    wrapper.style.height = "100%";
    wrapper.style.width = "100%";
    el.appendChild(wrapper);
    el.appendChild(script);

    return () => { el.innerHTML = ""; };
  }, [symbol]);

  return (
    <div className="mb-4 rounded-lg border border-[var(--border)] bg-[var(--bg-card)] shadow-sm overflow-hidden" style={{ height: 480 }}>
      <div ref={containerRef} className="tradingview-widget-container" style={{ height: "100%", width: "100%" }} />
    </div>
  );
}

/* ================================================================
   Slide builder — flattens sections into vertical snap slides
   ================================================================ */
interface Slide {
  key: string;
  type: "header" | "news" | "newsCard" | "technical" | "chips" | "footer";
  label: string;           // sticky header label
  cardIndex?: number;       // for newsCard: which card
  cardTotal?: number;
}

function buildSlides(data: ReportData): Slide[] {
  const slides: Slide[] = [];
  const analysis = data.newsAnalysis ?? [];

  // 1. Header + 消息面
  slides.push({ key: "header", type: "header", label: "01 · 消息面" });

  // 2. Each newsAnalysis card
  analysis.forEach((_, i) => {
    slides.push({
      key: `news-${i}`,
      type: "newsCard",
      label: `02 · 新聞分析（${i + 1}/${analysis.length}）`,
      cardIndex: i,
      cardTotal: analysis.length,
    });
  });

  // 3. 技術面
  slides.push({ key: "technical", type: "technical", label: "03 · 技術面" });

  // 4. 籌碼面
  slides.push({ key: "chips", type: "chips", label: "04 · 籌碼面" });

  // 5. Footer
  slides.push({ key: "footer", type: "footer", label: "" });

  return slides;
}

/* ================================================================
   Side TOC — floating table of contents on right edge
   ================================================================ */
interface TocItem { key: string; label: string }

function SideToc({ items, activeKey, onNavigate }: { items: TocItem[]; activeKey: string; onNavigate: (key: string) => void }) {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <>
      <button
        onClick={() => setIsOpen((v) => !v)}
        className="fixed right-0 top-1/2 z-40 -translate-y-1/2 rounded-l-lg border border-r-0 border-[var(--border)] bg-[var(--bg-card)] px-1.5 py-4 shadow-md transition-all hover:bg-[var(--bg-subtle)]"
        title={isOpen ? "關閉目錄" : "開啟目錄"}
      >
        <div className="flex flex-col items-center gap-1.5">
          <span className="text-sm">{isOpen ? "\u25B6" : "\u25C0"}</span>
          <span
            className="text-[0.6rem] font-bold tracking-widest text-[var(--text-muted)]"
            style={{ writingMode: "vertical-rl" }}
          >
            目錄
          </span>
        </div>
      </button>

      {isOpen && (
        <nav className="fixed right-10 top-1/2 z-40 -translate-y-1/2 rounded-lg border border-[var(--border)] bg-[var(--bg-card)] shadow-lg">
          <div className="max-h-[70vh] overflow-y-auto px-4 py-3 text-xs leading-relaxed">
            <ul className="border-l-2 border-[var(--border)]">
              {items.map((item) => {
                const isActive = activeKey === item.key;
                return (
                  <li
                    key={item.key}
                    className={`pl-3 py-1.5 ${isActive ? "-ml-0.5 border-l-2 border-[var(--primary)]" : ""}`}
                  >
                    <button
                      onClick={() => onNavigate(item.key)}
                      className={`whitespace-nowrap transition-colors text-left ${
                        isActive
                          ? "font-semibold text-[var(--primary)]"
                          : "text-[var(--text-muted)] hover:text-[var(--primary)]"
                      }`}
                    >
                      {item.label}
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        </nav>
      )}
    </>
  );
}

/* ================================================================
   Main Dashboard
   ================================================================ */
export default function Dashboard({ data }: { data: ReportData }) {
  const searchParams = useSearchParams();
  const isDebug = searchParams.has("debug");
  const td = data.technical;
  const scrollRef = useRef<HTMLDivElement>(null);
  const [activeLabel, setActiveLabel] = useState("");
  const [activeKey, setActiveKey] = useState("header");
  const [showSticky, setShowSticky] = useState(false);

  // Static snapshot: news items are baked into the weekly JSON at report creation time
  const newsItems: NewsItem[] = (data.news ?? []).map((n) => ({
    date: n.date,
    headline: n.headline || n.title || "",
    summary: n.summary || "",
    url: n.link,
    ticker: n.ticker,
    sentiment: n.sentiment as NewsItem["sentiment"],
  }));
  const market = data.chips.market || data.market;
  const slides = useMemo(() => buildSlides(data), [data]);

  // Track active slide via IntersectionObserver
  const slideRefs = useRef<Map<string, HTMLDivElement>>(new Map());
  const setSlideRef = useCallback((key: string, el: HTMLDivElement | null) => {
    if (el) slideRefs.current.set(key, el);
    else slideRefs.current.delete(key);
  }, []);

  useEffect(() => {
    const container = scrollRef.current;
    if (!container) return;
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting && entry.intersectionRatio > 0.5) {
            const key = entry.target.getAttribute("data-slide-key") ?? "";
            const slide = slides.find((s) => s.key === key);
            if (slide) {
              setActiveLabel(slide.label);
              setActiveKey(slide.key);
              setShowSticky(slide.type !== "header");
            }
          }
        }
      },
      { root: container, threshold: 0.5 },
    );
    slideRefs.current.forEach((el) => observer.observe(el));
    return () => observer.disconnect();
  }, [slides]);

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

  const analysis = data.newsAnalysis ?? [];

  const tocItems: TocItem[] = useMemo(() => {
    const items: TocItem[] = [
      { key: "header", label: "01 · 消息面" },
    ];
    if (analysis.length > 0) {
      items.push({ key: "news-section", label: "02 · 新聞分析" });
      analysis.forEach((block, i) => {
        items.push({ key: `news-${i}`, label: "　" + (block.title.length > 18 ? block.title.slice(0, 18) + "…" : block.title) });
      });
    }
    items.push({ key: "technical", label: "03 · 技術面" });
    items.push({ key: "chips", label: "04 · 籌碼面" });
    return items;
  }, [analysis]);

  return (
    <div
      ref={scrollRef}
      className="h-svh overflow-y-auto snap-y snap-mandatory"
    >
      {/* Side TOC */}
      <SideToc items={tocItems} activeKey={activeKey} onNavigate={(key) => {
        const resolvedKey = key === "news-section" ? "news-0" : key;
        const el = slideRefs.current.get(resolvedKey);
        if (el) el.scrollIntoView({ behavior: "smooth" });
      }} />

      {/* Sticky section header */}
      {showSticky && activeLabel && (
        <div className="pointer-events-none fixed top-0 left-0 right-0 z-30">
          <div className="mx-auto max-w-[1280px] px-6 pt-3">
            <div className="pointer-events-auto inline-block rounded-md bg-[var(--bg-card)]/90 backdrop-blur-sm border border-[var(--border)] px-4 py-1.5 text-sm font-semibold text-[var(--primary)] shadow-sm">
              {data.ticker} · {activeLabel}
            </div>
          </div>
        </div>
      )}

      {/* ── Slide: Header + 消息面 ── */}
      <div
        ref={(el) => setSlideRef("header", el)}
        data-slide-key="header"
        className="snap-start min-h-[100svh] pt-10 px-6"
      >
        <div className="mx-auto max-w-[1280px]">
          <Link
            href="/weekly"
            className="mb-3 inline-block text-sm font-semibold text-[var(--primary)] opacity-70 transition-opacity hover:opacity-100"
          >
            ← Stock Weekly
          </Link>

          {isDebug && (
            <div className="mb-6 rounded-md border border-[#FFEAA7] bg-[#FFF3CD] px-4 py-2.5 text-sm text-[#856404]">
              <strong className="text-[#533F03]">DEBUG MODE</strong> — 標注資料來自 debug
            </div>
          )}

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

          <SectionTitle debugTags={renderDebugSection("sec-news")}>
            01 · 消息面
          </SectionTitle>
          <NewsTable items={newsItems} />
          {renderDebugNotes("sec-news")}
        </div>
      </div>

      {/* ── Slides: 新聞分析 cards ── */}
      {analysis.map((block, bi) => (
        <div
          key={`news-${bi}`}
          ref={(el) => setSlideRef(`news-${bi}`, el)}
          data-slide-key={`news-${bi}`}
          className="snap-start min-h-[100svh] flex items-center px-6"
        >
          <div className="mx-auto max-w-[1280px] w-full">
            {bi === 0 && (
              <SectionTitle>02 · 新聞分析</SectionTitle>
            )}
            <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-card)] p-8 shadow-sm">
              <div className="flex items-center justify-between mb-5">
                <h3 className="text-xl font-bold">{block.title}</h3>
                <span className="text-sm text-[var(--text-muted)] font-mono">{bi + 1} / {analysis.length}</span>
              </div>
              <ul className="list-disc space-y-2.5 pl-5 text-[0.92rem] leading-relaxed">
                {block.points.map((p, pi) => (
                  <li key={pi}>{p}</li>
                ))}
              </ul>
              {block.table && (
                <div className="overflow-x-auto mt-5">
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
              {block.charts && block.charts.length > 0 && (
                <div className={`mt-6 grid gap-6 ${block.charts.length > 1 ? "grid-cols-2" : "grid-cols-1 max-w-xs mx-auto"}`}>
                  {block.charts.map((ch, ci) => (
                    <div key={ci} className="text-center">
                      <p className="text-sm font-medium mb-3">{ch.title}</p>
                      <div className="mx-auto" style={{ maxWidth: 200 }}>
                        <Doughnut
                          data={{
                            labels: ch.labels,
                            datasets: [{ data: ch.values, backgroundColor: ch.colors, borderWidth: 0 }],
                          }}
                          options={doughnutOpts}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              )}
              {block.sources && block.sources.length > 0 && (
                <div className="mt-5 pt-4 border-t border-[var(--border)]">
                  <div className="text-xs text-[var(--text-muted)] mb-1">Sources</div>
                  <ul className="space-y-0.5">
                    {block.sources.map((src, si) => (
                      <li key={si} className="text-sm">
                        <a href={src.url} target="_blank" rel="noopener noreferrer" className="text-[var(--primary)] hover:underline">{src.label}</a>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </div>
        </div>
      ))}

      {/* ── Slide: 技術面 ── */}
      <div
        ref={(el) => setSlideRef("technical", el)}
        data-slide-key="technical"
        className="snap-start min-h-[100svh] flex items-center px-6"
      >
        <div className="mx-auto max-w-[1280px] w-full">
          <SectionTitle debugTags={renderDebugSection("sec-technical")}>
            03 · 技術面
          </SectionTitle>

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

          <TradingViewChart symbol={`NASDAQ:${data.ticker}`} />

          {renderDebugNotes("sec-technical")}
        </div>
      </div>

      {/* ── Slide: 籌碼面 ── */}
      <div
        ref={(el) => setSlideRef("chips", el)}
        data-slide-key="chips"
        className="snap-start min-h-[100svh] flex items-center px-6"
      >
        <div className="mx-auto max-w-[1280px] w-full">
          <SectionTitle debugTags={renderDebugSection("sec-chips")}>
            04 · 籌碼面
          </SectionTitle>

          {market === "tw" && (
            <>
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

          {market === "us" && data.chips.us.images && data.chips.us.images.length > 0 && (
            <div className="space-y-5">
              {data.chips.us.images.map((img: { src: string; label: string }, idx: number) => (
                <div key={idx} className="rounded-lg border border-[var(--border)] bg-[var(--bg-card)] p-4 shadow-sm">
                  <div className="text-xs text-[var(--text-muted)] mb-2">{img.label}</div>
                  <img src={img.src} alt={img.label} className="w-full rounded" />
                </div>
              ))}
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
        </div>
      </div>

      {/* ── Footer slide ── */}
      <div
        ref={(el) => setSlideRef("footer", el)}
        data-slide-key="footer"
        className="snap-start min-h-[100svh] flex flex-col justify-end pb-8 px-6"
      >
        <div className="mx-auto max-w-[1280px] w-full">
          <footer className="border-t border-[var(--border)] pt-4 text-xs text-[var(--text-faint)]">
            Data sources: yfinance · FinMind · Fintel · Barchart
            {data.market && ` · Market: ${data.market.toUpperCase()}`}
          </footer>
        </div>
      </div>
    </div>
  );
}
