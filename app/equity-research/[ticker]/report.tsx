"use client";

import { useState, useEffect, useCallback, useRef, type ReactNode } from "react";
import Link from "next/link";
import dynamic from "next/dynamic";
import ThemeToggle from "@/app/components/ThemeToggle";
import TodoPanel from "@/app/components/TodoPanel";

const RatioChart = dynamic(() => import("@/app/components/financials/RatioChart"), { ssr: false });
const FinancialTable = dynamic(() => import("@/app/components/financials/FinancialTable"), { ssr: false });
const SegmentTable = dynamic(() => import("@/app/components/financials/SegmentTable"), { ssr: false });
const StaticChart = dynamic(() => import("./static-chart"), { ssr: false });

/* ================================================================
   Types — matches the JSON schema
   ================================================================ */
interface Source {
  label: string;
  href?: string;
  keyword?: string;
}

interface TableData {
  headers: string[];
  alignRight?: number[];
  rows: string[][];
}

interface ImageData {
  src: string;
  alt: string;
}

interface BulletList {
  items: string[];
}

interface ChartData {
  type: "bar" | "area";
  labels: string[];
  datasets: { label: string; data: (number | null)[]; color?: string }[];
  yLabel?: string;
}

interface ContentBoxBlock {
  type: "content-box";
  id?: string;
  title?: string;
  paragraphs?: string[];
  paragraphsToggle?: boolean;
  paragraphsToggleLabel?: string;
  table?: TableData;
  chart?: ChartData;
  image?: ImageData;
  bullets?: BulletList;
  footnote?: string;
  footnotes?: { id: string; text: string }[];
  sources?: Source[];
}

interface FinancialChartBlock {
  type: "financial-chart";
  title?: string;
  metrics: string[];
  defaultSelected?: string[];
  height?: number;
  defaultView?: "quarterly" | "annual";
}

interface FinancialTableBlock {
  type: "financial-table";
  title?: string;
  statement: "income_statement" | "balance_sheet" | "cash_flow_statement";
  metrics?: string[];
  maxPeriods?: number;
  defaultView?: "quarterly" | "annual";
}

interface SegmentTableBlock {
  type: "segment-table";
  title?: string;
  maxPeriods?: number;
  defaultView?: "quarterly" | "annual";
  defaultCategory?: string;
}

type Block = ContentBoxBlock | FinancialChartBlock | FinancialTableBlock | SegmentTableBlock;

interface Section {
  id: string;
  title: string;
  toggle?: boolean;
  toggleLabel?: string;
  kvCards?: { label: string; value: string; sub?: string; valueClass?: string }[];
  blocks: Block[];
}

interface QuarterEPS {
  label: string;
  bear: number;
  base: number;
  bull: number;
  isActual: boolean;
}

interface ValuationVersion {
  id: string;
  date: string;
  label: string;
  trigger: string;
  latestReport?: string;
  note: string;
  details?: string[];
  detailsTable?: { headers: string[]; rows: string[][] };
  peRatios: [number, number, number, number];
  eps: { bear: number; base: number; bull: number; ttm: number };
  quarterly: QuarterEPS[];
}

interface ValuationModel {
  type: string;
  title: string;
  placeholder?: string;
  // PE-specific fields
  peLabels?: string[];
  versions?: ValuationVersion[];
}

interface Chronicle {
  title: string;
  description: string;
  href: string;
  linkLabel?: string;
}

interface Chapter {
  id: string;
  title: string;
  numeral: string;
  sections: Section[];
  placeholder?: string;
  chronicle?: Chronicle;
  valuations?: ValuationModel[];
}

export interface ReportData {
  ticker: string;
  name: string;
  market: string;
  updated: string;
  chapters: Chapter[];
}

/* ================================================================
   Sub-components
   ================================================================ */
const TH =
  "border-b border-[var(--border)] px-4 py-2 text-left text-sm font-normal uppercase tracking-wide text-[var(--text-muted)]";
const TH_R = TH + " text-right";
const TD = "border-b border-[var(--border)] px-4 py-2 text-[0.95rem]";
const TD_R = TD + " text-right tabular-nums";

function Sources({ list }: { list: Source[] }) {
  if (!list?.length) return null;
  return (
    <div className="mt-2 text-xs text-[var(--text-faint)]">
      Sources:
      <ul className="mt-1 space-y-0.5">
        {list.map((s, i) => (
          <li key={i}>
            {s.href ? (
              <>
                [
                <a
                  href={s.href}
                  target="_blank"
                  rel="noopener"
                  className="text-[var(--text-muted)] hover:text-[var(--primary)] hover:underline"
                >
                  {s.label}
                </a>
                ]
              </>
            ) : (
              <span className="text-[var(--text-muted)]">
                [{s.label}]{s.keyword ? ` — "${s.keyword}"` : ""}
              </span>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

function ContentBox({ title, children }: { title?: string; children: ReactNode }) {
  return (
    <div className="mb-4 rounded-lg border border-[var(--border)] bg-[var(--bg-card)] p-6 shadow-sm">
      {title && (
        <h3 className="mb-3 border-b border-[#F0EAEA] pb-1.5 text-base font-semibold">
          {title}
        </h3>
      )}
      {children}
    </div>
  );
}

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
      <div className="text-xs uppercase tracking-wide text-[var(--text-muted)]">{label}</div>
      <div className={`mt-1 text-2xl font-bold ${valueClass ?? ""}`}>{value}</div>
      {sub && <div className="mt-0.5 text-xs text-[#6B5E60]">{sub}</div>}
    </div>
  );
}

function SectionTitle({ children }: { children: ReactNode }) {
  return (
    <div className="mb-5 border-l-[3px] border-[var(--primary)] pl-3 text-lg font-semibold uppercase tracking-wider text-[var(--primary)]">
      {children}
    </div>
  );
}

function SideToc({
  chapters,
  activeId,
}: {
  chapters: Chapter[];
  activeId: string;
}) {
  const [isOpen, setIsOpen] = useState(false);

  const items: { id: string; label: string; isChapter: boolean }[] = [];
  // Map section IDs not in TOC back to their parent chapter
  const sectionToChapter = new Map<string, string>();
  for (const ch of chapters) {
    items.push({ id: ch.id, label: `${ch.numeral}. ${ch.title}`, isChapter: true });
    if (ch.id !== "ch-archive") {
      for (const sec of ch.sections) {
        items.push({ id: sec.id, label: sec.title.replace(/^\d+\s*·\s*/, ""), isChapter: false });
      }
    } else {
      for (const sec of ch.sections) {
        sectionToChapter.set(sec.id, ch.id);
      }
    }
  }
  const resolvedActiveId = sectionToChapter.get(activeId) || activeId;

  return (
    <>
      {/* Toggle tab — always visible on right edge */}
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

      {/* Floating TOC popover */}
      {isOpen && (
        <nav
          className="fixed right-10 top-1/2 z-40 -translate-y-1/2 rounded-lg border border-[var(--border)] bg-[var(--bg-card)] shadow-lg"
        >
          <div className="max-h-[70vh] overflow-y-auto px-4 py-3 text-xs leading-relaxed">
            <ul className="border-l-2 border-[var(--border)]">
              {items.map((s) => {
                const isActive = resolvedActiveId === s.id;
                return (
                  <li
                    key={s.id}
                    className={`${
                      s.isChapter
                        ? "pt-2.5 pl-3 font-semibold first:pt-1"
                        : "pl-5 font-normal"
                    } py-1 ${isActive ? "-ml-0.5 border-l-2 border-[var(--primary)]" : ""}`}
                  >
                    <a
                      href={`#${s.id}`}
                      className={`whitespace-nowrap transition-colors ${
                        isActive
                          ? "font-semibold text-[var(--primary)]"
                          : s.isChapter
                            ? "text-[var(--text)] hover:text-[var(--primary)]"
                            : "text-[var(--text-muted)] hover:text-[var(--primary)]"
                      }`}
                    >
                      {s.label}
                    </a>
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
   Inline Markdown — minimal bold / italic / bold-italic support
   ================================================================ */
function renderInline(text: string): ReactNode {
  // Split by [text](url) links, [^N] footnote refs, **bold**, __underline-bold__
  const parts = text.split(/(\[[^\]^\n]+\]\([^)]+\)|\[\^\d+\]|\*\*[^*]+\*\*|__[^_]+__)/g);
  return parts.map((part, i) => {
    // Markdown link: [text](url)
    const linkMatch = part.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
    if (linkMatch) {
      return (
        <a key={i} href={linkMatch[2]} target="_blank" rel="noopener noreferrer"
          className="text-[var(--primary)] underline decoration-[var(--primary)]/30 hover:decoration-[var(--primary)]"
        >
          {linkMatch[1]}
        </a>
      );
    }
    // Footnote reference: [^1] → superscript
    if (/^\[\^\d+\]$/.test(part)) {
      const num = part.slice(2, -1);
      return (
        <sup key={i} className="ml-0.5 text-[0.6rem] text-[var(--primary)]">
          {num}
        </sup>
      );
    }
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={i}>{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith("__") && part.endsWith("__")) {
      return (
        <strong key={i} className="border-t-2 border-[var(--border)]">
          {part.slice(2, -2)}
        </strong>
      );
    }
    // Handle \n line breaks — recurse for each line to parse nested markup
    if (part.includes("\n")) {
      return part.split("\n").map((line, j, arr) => (
        <span key={`${i}-${j}`}>
          {renderInline(line)}
          {j < arr.length - 1 && <br />}
        </span>
      ));
    }
    return part;
  });
}

/* ================================================================
   Block Renderer — renders a single block from JSON
   ================================================================ */
function BlockRenderer({
  block,
  onImageClick,
  anchorPrefix,
}: {
  block: ContentBoxBlock;
  onImageClick: (src: string) => void;
  anchorPrefix?: string;
}) {
  // If block has an id, use it as the primary anchor; otherwise fall back to positional
  const blockAnchor = block.id || (anchorPrefix ? `${anchorPrefix}-content-box-0` : undefined);
  const a = (type: string, idx: number) => {
    if (block.id) return `${block.id}--${type}-${idx}`;
    return anchorPrefix ? `${anchorPrefix}-${type}-${idx}` : undefined;
  };

  return (
    <div data-anchor={blockAnchor}>
      <ContentBox title={block.title}>
        {/* Image */}
        {block.image && (
          <div
            className="relative my-2 cursor-zoom-in"
            data-anchor={a("image", 0)}
            onClick={() => onImageClick(block.image!.src)}
          >
            <img
              src={block.image.src}
              alt={block.image.alt}
              className="w-full rounded-lg"
            />
            <span className="absolute bottom-1 right-2 pointer-events-none text-[0.68rem] text-[var(--text-faint)]">
              click to expand
            </span>
          </div>
        )}

        {/* Table */}
        {block.table && (
          <div className="overflow-x-auto" data-anchor={a("table", 0)}>
            <table className="mb-3 w-full border-collapse">
              <thead>
                <tr>
                  {block.table.headers.map((h, i) => (
                    <th
                      key={i}
                      className={block.table!.alignRight?.includes(i) ? TH_R : TH}
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {block.table.rows.map((row, ri) => {
                  const isTotal = row[0]?.startsWith("__");
                  return (
                    <tr
                      key={ri}
                      className={isTotal ? "border-t-2 border-[var(--border)] font-semibold" : ""}
                    >
                      {row.map((cell, ci) => (
                        <td
                          key={ci}
                          className={block.table!.alignRight?.includes(ci) ? TD_R : TD}
                        >
                          {renderInline(cell)}
                        </td>
                      ))}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {/* Chart */}
        {block.chart && (
          <StaticChart
            type={block.chart.type}
            labels={block.chart.labels}
            datasets={block.chart.datasets}
            yLabel={block.chart.yLabel}
          />
        )}

        {/* Bullets */}
        {block.bullets && (
          <ul className="mb-3 list-disc space-y-1 pl-5 text-[0.95rem]" data-anchor={a("bullets", 0)}>
            {block.bullets.items.map((item, i) => (
              <li key={i}>{renderInline(item)}</li>
            ))}
          </ul>
        )}

        {/* Paragraphs */}
        {block.paragraphs && block.paragraphs.length > 0 && (
          block.paragraphsToggle ? (
            <details className="mt-3 border-t border-[var(--border)] pt-2">
              <summary className="cursor-pointer text-xs text-[var(--text-muted)] hover:text-[var(--text)]">
                {block.paragraphsToggleLabel || "關鍵觀察"}
              </summary>
              <div className="mt-2">
                {block.paragraphs.map((p, i) => (
                  <p key={i} className="mb-3 text-[0.95rem] leading-relaxed" data-anchor={a("paragraph", i)}>
                    {renderInline(p)}
                  </p>
                ))}
              </div>
            </details>
          ) : (
            block.paragraphs.map((p, i) => (
              <p key={i} className="mb-3 text-[0.95rem] leading-relaxed" data-anchor={a("paragraph", i)}>
                {renderInline(p)}
              </p>
            ))
          )
        )}

        {/* Footnotes + Sources toggle */}
        {(block.footnote || block.footnotes?.length || block.sources?.length) ? (
          <details className="mt-3 border-t border-[var(--border)] pt-2">
            <summary className="cursor-pointer text-xs text-[var(--text-muted)] hover:text-[var(--text)]">
              註釋 & Sources
            </summary>
            <div className="mt-2">
              {block.footnote && (
                <div className="mb-2 text-xs text-[var(--text-faint)]">{block.footnote}</div>
              )}
              {block.footnotes && block.footnotes.length > 0 && (
                <div className="mb-2 text-xs leading-relaxed text-[var(--text-muted)]">
                  {block.footnotes.map((fn) => (
                    <div key={fn.id} className="flex gap-1.5">
                      <sup className="mt-0.5 text-[0.6rem] text-[var(--primary)]">{fn.id}</sup>
                      <span>{fn.text}</span>
                    </div>
                  ))}
                </div>
              )}
              {block.sources && <Sources list={block.sources} />}
            </div>
          </details>
        ) : null}
      </ContentBox>
    </div>
  );
}

/* ================================================================
   Lightbox
   ================================================================ */
function LightboxModal({
  src,
  onClose,
}: {
  src: string | null;
  onClose: () => void;
}) {
  if (!src) return null;
  return (
    <div
      className="fixed inset-0 z-[9999] flex cursor-zoom-out items-center justify-center bg-[rgba(44,21,23,0.55)] backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="max-h-[90vh] w-[85vw] max-w-[1200px] cursor-default overflow-auto rounded-xl bg-[var(--bg-card)] p-8 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <img src={src} alt="Expanded view" className="w-full" />
      </div>
    </div>
  );
}

/* ================================================================
   Valuation Components
   ================================================================ */
const EPS_LABELS = ["悲觀估值", "中間估值", "樂觀估值", "TTM\n(剔除一次性)"] as const;

function PEGrid({
  v,
  peLabels,
  currentPrice,
}: {
  v: ValuationVersion;
  peLabels: string[];
  currentPrice?: number | null;
}) {
  const epsRows: { label: string; value: number }[] = [
    { label: "悲觀估值", value: v.eps.bear },
    { label: "中間估值", value: v.eps.base },
    { label: "樂觀估值", value: v.eps.bull },
    { label: "TTM (剔除一次性)", value: v.eps.ttm },
  ];

  // Find the two cells that bracket the current price (one ≤, one ≥)
  // If price is outside the range, only one cell flashes
  const breatheKeys = new Set<string>();
  if (currentPrice && currentPrice > 0) {
    const allCells: { key: string; price: number }[] = [];
    epsRows.forEach((row, ri) => {
      v.peRatios.forEach((pe, ci) => {
        allCells.push({ key: `${ri}-${ci}`, price: row.value * pe });
      });
    });

    // Sort by target price
    const sorted = [...allCells].sort((a, b) => a.price - b.price);

    // Find floor (highest price ≤ currentPrice) and ceiling (lowest price ≥ currentPrice)
    let floor: typeof sorted[0] | null = null;
    let ceiling: typeof sorted[0] | null = null;
    for (const c of sorted) {
      if (c.price <= currentPrice) floor = c;
    }
    for (const c of sorted) {
      if (c.price >= currentPrice && !ceiling) ceiling = c;
    }

    if (floor) breatheKeys.add(floor.key);
    if (ceiling && ceiling.key !== floor?.key) breatheKeys.add(ceiling.key);
    // If no floor (price below all), just ceiling; if no ceiling (price above all), just floor
    if (!floor && ceiling) breatheKeys.add(ceiling.key);
    if (!ceiling && floor) breatheKeys.add(floor.key);
  }

  const cell =
    "border border-[var(--border)] px-3 py-2 text-sm text-right tabular-nums";
  const hdr =
    "border border-[var(--border)] px-3 py-2 text-xs font-semibold text-center";

  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse">
        <thead>
          <tr>
            <th className={`${hdr} bg-[var(--bg-subtle)]`} colSpan={2}>
              {v.label}
            </th>
            <th className={`${hdr} bg-[var(--bg-subtle)]`} colSpan={4}>
              P/E Ratio
            </th>
          </tr>
          <tr>
            <th className={`${hdr} bg-[var(--bg-subtle)]`} colSpan={2}>
              全年 EPS
            </th>
            {peLabels.map((label, i) => (
              <th key={i} className={`${hdr} bg-[var(--bg-subtle)]`}>
                <div className="text-[0.7rem] text-[var(--text-muted)]">
                  {label}
                </div>
                <div className="mt-0.5 text-sm font-bold">
                  {v.peRatios[i].toFixed(2)}
                </div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {epsRows.map((row, ri) => (
            <tr key={ri}>
              <td
                className={`${cell} text-left font-medium ${ri === 3 ? "text-xs" : ""}`}
              >
                {row.label}
              </td>
              <td className={`${cell} font-semibold`}>{row.value.toFixed(2)}</td>
              {v.peRatios.map((pe, ci) => {
                const price = (row.value * pe).toFixed(1);
                const isBase = ri === 1 && ci === 2;
                const isBreathe = breatheKeys.has(`${ri}-${ci}`);
                return (
                  <td
                    key={ci}
                    className={`${cell} ${
                      isBase
                        ? "bg-[var(--bg-highlight)] font-bold text-[var(--primary)]"
                        : ""
                    }`}
                    style={
                      isBreathe
                        ? { animation: "breathe 2.5s ease-in-out infinite" }
                        : undefined
                    }
                  >
                    {price}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      {currentPrice && (
        <p className="mt-2 text-sm text-[var(--text-muted)]">
          現價 <span className="text-base font-bold text-[var(--primary)]">${currentPrice.toFixed(2)}</span>
        </p>
      )}
    </div>
  );
}

function QuarterlyEPS({ v }: { v: ValuationVersion }) {
  const total = {
    bear: v.quarterly.reduce((s, q) => s + q.bear, 0),
    base: v.quarterly.reduce((s, q) => s + q.base, 0),
    bull: v.quarterly.reduce((s, q) => s + q.bull, 0),
  };
  const cell =
    "border border-[var(--border)] px-3 py-2 text-sm text-right tabular-nums";
  const hdr =
    "border border-[var(--border)] px-3 py-2 text-xs font-semibold text-center bg-[var(--bg-subtle)]";

  const renderRow = (
    label: string,
    bear: number,
    base: number,
    bull: number,
    isActual: boolean,
    isBold = false,
  ) => (
    <tr key={label} className={isBold ? "font-semibold bg-[var(--bg-subtle)]" : ""}>
      <td
        className={`${cell} text-left ${isBold ? "font-semibold" : "font-medium"}`}
      >
        {label}
      </td>
      <td className={cell}>
        ${bear.toFixed(2)}
        {isActual && !isBold && (
          <span className="ml-1 text-[0.65rem] text-green-600">✓</span>
        )}
      </td>
      <td className={cell}>
        ${base.toFixed(2)}
        {isActual && !isBold && (
          <span className="ml-1 text-[0.65rem] text-green-600">✓</span>
        )}
      </td>
      <td className={cell}>
        ${bull.toFixed(2)}
        {isActual && !isBold && (
          <span className="ml-1 text-[0.65rem] text-green-600">✓</span>
        )}
      </td>
    </tr>
  );

  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse">
        <thead>
          <tr>
            <th className={hdr}>Quarter</th>
            <th className={hdr}>Bear</th>
            <th className={hdr}>Base</th>
            <th className={hdr}>Bull</th>
          </tr>
        </thead>
        <tbody>
          {v.quarterly.map((q) =>
            renderRow(q.label, q.bear, q.base, q.bull, q.isActual),
          )}
          {renderRow("Total", total.bear, total.base, total.bull, false, true)}
        </tbody>
      </table>
      <p className="mt-1 text-[0.65rem] text-[var(--text-faint)]">
        <span className="text-green-600">✓</span> = 已公布實際值
      </p>
    </div>
  );
}

function VersionHistory({
  versions,
  peLabels,
  openId,
  onToggle,
}: {
  versions: ValuationVersion[];
  peLabels: string[];
  openId: string | null;
  onToggle: (id: string | null) => void;
}) {

  return (
    <div className="space-y-2">
      {versions.map((v) => {
        const isOpen = openId === v.id;
        return (
          <div
            key={v.id}
            className="rounded-lg border border-[var(--border)] bg-[var(--bg-card)]"
          >
            <button
              className="flex w-full items-center justify-between px-4 py-3 text-left text-sm hover:bg-[var(--bg-subtle)]"
              onClick={() => onToggle(isOpen ? null : v.id)}
            >
              <div>
                <span className="mr-2 font-mono text-xs text-[var(--text-faint)]">
                  {v.id}
                </span>
                <span className="font-semibold">{v.label}</span>
                <span className="ml-2 text-xs text-[var(--text-muted)]">
                  {v.date}
                </span>
              </div>
              <span className="text-[var(--text-faint)]">
                {isOpen ? "▲" : "▼"}
              </span>
            </button>
            {isOpen && (
              <div className="border-t border-[var(--border)] px-4 pb-4 pt-3">
                <p className="mb-1 text-xs font-medium text-[var(--text-muted)]">
                  觸發事件：{v.trigger}
                </p>
                <p className="mb-4 text-xs text-[var(--text-faint)]">
                  {v.note}
                </p>
                <div className="grid gap-4 lg:grid-cols-2">
                  <div>
                    <p className="mb-1.5 text-xs font-semibold text-[var(--text-muted)]">
                      P/E 估值矩陣
                    </p>
                    <PEGrid v={v} peLabels={peLabels} />
                  </div>
                  <div>
                    <p className="mb-1.5 text-xs font-semibold text-[var(--text-muted)]">
                      每季 EPS 預估
                    </p>
                    <QuarterlyEPS v={v} />
                  </div>
                </div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function DetailsToggle({
  details,
  detailsTable,
}: {
  details: string[];
  detailsTable?: { headers: string[]; rows: string[][] };
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-6 border-t border-[var(--border)] pt-3">
      <button
        className="flex w-full items-center justify-between text-left text-[0.85rem] font-semibold hover:text-[var(--primary)]"
        onClick={() => setOpen(!open)}
      >
        估值邏輯
        <span className="text-xs text-[var(--text-faint)]">{open ? "▲" : "▼"}</span>
      </button>
      {open && (
        <div className="mt-3">
          {details.map((p, i) => (
            <p key={i} className="mb-3 text-[0.95rem] leading-relaxed">
              {renderInline(p)}
            </p>
          ))}
          {detailsTable && (
            <div className="mt-4 overflow-x-auto">
              <table className="w-auto text-[0.85rem] border-collapse">
                <thead>
                  <tr>
                    {detailsTable.headers.map((h, i) => (
                      <th
                        key={i}
                        className="border-b border-[var(--border)] px-4 py-1.5 text-left font-semibold text-[var(--text-muted)]"
                      >
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {detailsTable.rows.map((row, ri) => (
                    <tr key={ri}>
                      {row.map((cell, ci) => (
                        <td
                          key={ci}
                          className="border-b border-[var(--border-faint)] px-4 py-1.5"
                        >
                          {renderInline(cell)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function PEValuation({
  model,
  ticker,
  currentPrice,
}: {
  model: ValuationModel;
  ticker: string;
  currentPrice: number | null;
}) {
  const versions = model.versions || [];
  const peLabels = model.peLabels || [];
  const latest = versions[0];
  const [historyOpenId, setHistoryOpenId] = useState<string | null>(null);

  if (!latest) return null;

  return (
    <>
      <ContentBox title="最新估價">
        <div className="mb-4 text-sm text-[var(--text-muted)] space-y-0.5">
          <p>版本：<span className="font-mono">{latest.id}</span></p>
          <p>發布日期：{latest.date}</p>
          {latest.latestReport && <p>最新財報：{latest.latestReport}</p>}
        </div>
        <div className="grid gap-6 lg:grid-cols-5">
          <div className="lg:col-span-3">
            <p className="mb-1.5 text-xs font-semibold text-[var(--text-muted)]">
              P/E 估值矩陣（目標股價 = EPS × P/E）
            </p>
            <PEGrid
              v={latest}
              peLabels={peLabels}
              currentPrice={currentPrice}
            />
          </div>
          <div className="lg:col-span-2">
            <p className="mb-1.5 text-xs font-semibold text-[var(--text-muted)]">
              每季 EPS 預估
            </p>
            <QuarterlyEPS v={latest} />
          </div>
        </div>
        {latest.details && latest.details.length > 0 && (
          <DetailsToggle details={latest.details} detailsTable={latest.detailsTable} />
        )}
      </ContentBox>

      <ContentBox title="版本紀錄">
        <p className="mb-3 text-xs text-[var(--text-faint)]">
          每次財報公布或重大消息調整估價時，會新增一個版本。展開可查看當時的估價快照。
        </p>
        {versions.length > 1 ? (
          <VersionHistory
            versions={versions.slice(1)}
            peLabels={peLabels}
            openId={historyOpenId}
            onToggle={setHistoryOpenId}
          />
        ) : (
          <p className="py-4 text-center text-xs text-[var(--text-faint)]">尚無歷史版本</p>
        )}
      </ContentBox>
    </>
  );
}

function ChronicleCard({ chronicle }: { chronicle: Chronicle }) {
  return (
    <div className="mb-10">
      <SectionTitle>{chronicle.title}</SectionTitle>
      <a
        href={chronicle.href}
        target="_blank"
        rel="noopener"
        className="group block rounded-lg border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm transition-colors hover:border-[var(--primary-lt)]"
      >
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm text-[var(--text-muted)]">
              {chronicle.description}
            </p>
          </div>
          <span className="ml-4 shrink-0 rounded-md bg-[var(--tag-bg)] px-3 py-1.5 text-xs font-semibold text-[var(--primary)] transition-colors group-hover:bg-[var(--primary)] group-hover:text-white">
            {chronicle.linkLabel || "開啟"} ↗
          </span>
        </div>
      </a>
    </div>
  );
}

function ValuationChapter({
  valuations,
  ticker,
  chronicle,
}: {
  valuations: ValuationModel[];
  ticker: string;
  chronicle?: Chronicle;
}) {
  const [currentPrice, setCurrentPrice] = useState<number | null>(null);

  useEffect(() => {
    fetch(`/api/quote?ticker=${ticker}`)
      .then((r) => r.json())
      .then((d) => {
        if (d?.price) setCurrentPrice(d.price);
      })
      .catch(() => {});
  }, [ticker]);

  return (
    <>
      {chronicle && <ChronicleCard chronicle={chronicle} />}

      {valuations.map((model, i) => (
        <section key={i} className="mb-10">
          <SectionTitle>{model.title}</SectionTitle>

          {model.type === "pe" && (
            <PEValuation model={model} ticker={ticker} currentPrice={currentPrice} />
          )}

          {model.placeholder && model.type !== "pe" && (
            <ContentBox>
              <p className="p-4 text-center text-sm italic text-[var(--text-faint)]">
                {model.placeholder}
              </p>
            </ContentBox>
          )}
        </section>
      ))}
    </>
  );
}

/* ================================================================
   Main Report Component
   ================================================================ */
/* ================================================================
   Slide builder — flattens chapters/sections/blocks into snap slides
   ================================================================ */
interface Slide {
  key: string;
  isFirst: boolean; // first slide gets header
  chapterTitle?: { id: string; numeral: string; title: string };
  sectionTitle?: { id: string; title: string; toggle?: boolean; toggleLabel?: string };
  // Always-present breadcrumb for every slide
  breadcrumb?: { chapter: string; section: string };
  kvCards?: { cards: Section["kvCards"]; anchor: string };
  block?: { block: Block; anchorPrefix: string; index: number };
  allBlocks?: { block: Block; anchorPrefix: string; index: number }[];
  // Special slide types
  placeholder?: { chapterId: string; text: string };
  valuationChapter?: { valuations: ValuationModel[]; ticker: string; chronicle?: Chronicle; chapterId: string };
  footer?: boolean;
}

function buildSlides(chapters: Chapter[]): Slide[] {
  const slides: Slide[] = [];
  let isFirst = true;
  let currentChapterLabel = "";
  let currentSectionLabel = "";

  for (const ch of chapters) {
    currentChapterLabel = `${ch.numeral}. ${ch.title}`;
    // Track whether we've emitted the chapter title yet
    let chapterTitlePending: Slide["chapterTitle"] | undefined = {
      id: ch.id,
      numeral: ch.numeral,
      title: ch.title,
    };

    // Valuation chapter — gets its own slide with chapter title
    if (ch.valuations) {
      slides.push({
        key: `val-${ch.id}`,
        isFirst,
        chapterTitle: chapterTitlePending,
        valuationChapter: {
          valuations: ch.valuations,
          ticker: "", // filled at render time
          chronicle: ch.chronicle,
          chapterId: ch.id,
        },
      });
      isFirst = false;
      chapterTitlePending = undefined;
    }

    // Placeholder chapter (no sections, no valuations)
    if (ch.placeholder && ch.sections.length === 0 && !ch.valuations) {
      slides.push({
        key: `ph-${ch.id}`,
        isFirst,
        chapterTitle: chapterTitlePending,
        placeholder: { chapterId: ch.id, text: ch.placeholder },
      });
      isFirst = false;
      chapterTitlePending = undefined;
    }

    // Sections
    for (const sec of ch.sections) {
      currentSectionLabel = sec.title;
      let sectionTitlePending: Slide["sectionTitle"] | undefined = {
        id: sec.id,
        title: sec.title,
        toggle: sec.toggle,
        toggleLabel: sec.toggleLabel,
      };

      // If section has kvCards, they go with the first block (or alone if no blocks)
      const hasKvCards = sec.kvCards && sec.kvCards.length > 0;
      const kvCardsData = hasKvCards
        ? { cards: sec.kvCards, anchor: `${sec.id}-0-kvCards-0` }
        : undefined;

      if (sec.blocks.length === 0) {
        // Section with only kvCards or empty
        slides.push({
          key: `sec-${sec.id}`,
          isFirst,
          breadcrumb: { chapter: currentChapterLabel, section: currentSectionLabel },
          chapterTitle: chapterTitlePending,
          sectionTitle: sectionTitlePending,
          kvCards: kvCardsData,
        });
        isFirst = false;
        chapterTitlePending = undefined;
        sectionTitlePending = undefined;
        continue;
      }

      // Toggle sections (Archive): group ALL blocks into ONE slide
      if (sec.toggle) {
        const slide: Slide = {
          key: `toggle-${sec.id}`,
          isFirst,
          breadcrumb: { chapter: currentChapterLabel, section: currentSectionLabel },
          sectionTitle: sectionTitlePending,
          kvCards: kvCardsData,
          // Store all blocks — we'll use a new field
          allBlocks: sec.blocks.map((block, i) => ({
            block,
            anchorPrefix: `${sec.id}-${i}`,
            index: i,
          })),
        };
        if (chapterTitlePending) {
          slide.chapterTitle = chapterTitlePending;
          chapterTitlePending = undefined;
        }
        isFirst = false;
        sectionTitlePending = undefined;
        slides.push(slide);
        continue;
      }

      for (let i = 0; i < sec.blocks.length; i++) {
        const block = sec.blocks[i];
        const ap = `${sec.id}-${i}`;

        const slide: Slide = {
          key: `block-${ap}`,
          isFirst,
          breadcrumb: { chapter: currentChapterLabel, section: currentSectionLabel },
          block: { block, anchorPrefix: ap, index: i },
        };

        // Attach chapter title to the first block of the chapter's first section
        if (chapterTitlePending) {
          slide.chapterTitle = chapterTitlePending;
          chapterTitlePending = undefined;
        }

        // Attach section title to the first block of the section
        if (sectionTitlePending) {
          slide.sectionTitle = sectionTitlePending;
          sectionTitlePending = undefined;
        }

        // Attach kvCards to the first block of the section
        if (i === 0 && kvCardsData) {
          slide.kvCards = kvCardsData;
        }

        isFirst = false;
        slides.push(slide);
      }
    }

    // If chapter title was never consumed (e.g. chapter with only valuations handled above,
    // but no sections), it's already been emitted
  }

  // Footer slide
  slides.push({ key: "footer", isFirst: false, footer: true });

  return slides;
}

export default function Report({ data }: { data: ReportData }) {
  const { ticker, name, updated, chapters } = data;
  const scrollRef = useRef<HTMLDivElement>(null);

  // Build flat list of section IDs for scroll tracking
  const allIds: string[] = [];
  for (const ch of chapters) {
    allIds.push(ch.id);
    for (const sec of ch.sections) {
      allIds.push(sec.id);
    }
  }

  const [activeId, setActiveId] = useState(allIds[0] || "");
  const [showStickyHeader, setShowStickyHeader] = useState(false);
  const [lightboxImg, setLightboxImg] = useState<string | null>(null);
  const [panelOpen, setPanelOpen] = useState(false);

  // Derive current chapter + section from activeId for sticky headers
  const stickyHeaders = (() => {
    for (const ch of chapters) {
      if (ch.id === activeId) return { chapter: `${ch.numeral}. ${ch.title}`, section: "" };
      for (const sec of ch.sections) {
        if (sec.id === activeId) return { chapter: `${ch.numeral}. ${ch.title}`, section: sec.title };
      }
    }
    return { chapter: "", section: "" };
  })();

  // Scroll tracking — uses the snap scroll container instead of window
  useEffect(() => {
    const container = scrollRef.current;
    if (!container) return;

    const targets = allIds
      .map((id) => document.getElementById(id))
      .filter(Boolean) as HTMLElement[];

    function onScroll() {
      if (!container) return;
      const containerRect = container.getBoundingClientRect();
      const threshold = containerRect.top + 80; // 80px from top of scroll container
      let active = targets[0];
      for (const t of targets) {
        const rect = t.getBoundingClientRect();
        if (rect.top <= threshold) active = t;
      }
      if (active) setActiveId(active.id);
      setShowStickyHeader(container.scrollTop > container.clientHeight * 0.5);
    }

    container.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
    return () => container.removeEventListener("scroll", onScroll);
  }, []);

  const openLightbox = useCallback((src: string) => {
    setLightboxImg(src);
  }, []);

  // Build slides
  const slides = buildSlides(chapters);

  // Helper: render a block inside a slide
  const renderBlock = (block: Block, ap: string, i: number) => {
    if (block.type === "financial-chart") {
      return (
        <div className="mb-4 rounded-lg border border-[var(--border)] bg-[var(--bg-card)] p-6 shadow-sm" data-anchor={`${ap}-chart-0`}>
          {block.title && (
            <h3 className="mb-3 border-b border-[var(--bg-subtle)] pb-1.5 text-[0.95rem] font-semibold">
              {block.title}
            </h3>
          )}
          <RatioChart
            ticker={ticker}
            metrics={block.metrics}
            defaultSelected={block.defaultSelected}
            height={block.height}
            defaultView={block.defaultView}
          />
        </div>
      );
    }
    if (block.type === "financial-table") {
      return (
        <div className="mb-4 rounded-lg border border-[var(--border)] bg-[var(--bg-card)] p-6 shadow-sm" data-anchor={`${ap}-financial-table-0`}>
          {block.title && (
            <h3 className="mb-3 border-b border-[var(--bg-subtle)] pb-1.5 text-[0.95rem] font-semibold">
              {block.title}
            </h3>
          )}
          <FinancialTable
            ticker={ticker}
            statement={block.statement}
            metrics={block.metrics}
            maxPeriods={block.maxPeriods}
            defaultView={block.defaultView}
          />
        </div>
      );
    }
    if (block.type === "segment-table") {
      return (
        <div className="mb-4 rounded-lg border border-[var(--border)] bg-[var(--bg-card)] p-6 shadow-sm" data-anchor={`${ap}-segment-table-0`}>
          {block.title && (
            <h3 className="mb-3 border-b border-[var(--bg-subtle)] pb-1.5 text-[0.95rem] font-semibold">
              {block.title}
            </h3>
          )}
          <SegmentTable
            ticker={ticker}
            maxPeriods={block.maxPeriods}
            defaultView={block.defaultView}
            defaultCategory={block.defaultCategory}
          />
        </div>
      );
    }
    return <BlockRenderer block={block as ContentBoxBlock} onImageClick={openLightbox} anchorPrefix={ap} />;
  };

  return (
    <div
      ref={scrollRef}
      className="h-svh overflow-y-auto snap-y snap-mandatory"
    >
      {/* To-Do Panel */}
      <TodoPanel ticker={ticker} onToggle={setPanelOpen} />

      {/* Highlight styles for To-Do anchors */}
      <style jsx global>{`
        .todo-highlight {
          transition: all 0.3s ease;
        }
        /* Text elements: yellow background */
        p.todo-highlight,
        ul.todo-highlight,
        div[data-anchor].todo-highlight > div {
          background: rgba(250, 204, 21, 0.15);
          border-radius: 4px;
        }
        /* Tables: yellow border */
        div[data-anchor*="table"].todo-highlight {
          outline: 2px solid rgba(250, 204, 21, 0.6);
          outline-offset: 2px;
          border-radius: 8px;
        }
        /* Charts: yellow ring */
        div[data-anchor*="chart"].todo-highlight,
        div[data-anchor*="segment"].todo-highlight {
          outline: 2px solid rgba(250, 204, 21, 0.6);
          outline-offset: 2px;
          border-radius: 8px;
        }
        /* KV Cards: yellow ring */
        div[data-anchor*="kvCards"].todo-highlight {
          outline: 2px solid rgba(250, 204, 21, 0.6);
          outline-offset: 4px;
          border-radius: 8px;
        }
        /* Content-box: subtle highlight */
        div[data-anchor*="content-box"].todo-highlight > div {
          outline: 2px solid rgba(250, 204, 21, 0.4);
          outline-offset: 0px;
        }
        /* Toggle (details) section: yellow ring */
        details.todo-highlight {
          outline: 2px solid rgba(250, 204, 21, 0.6);
          outline-offset: 4px;
          border-radius: 8px;
        }
        /* Text fragment highlight */
        mark.todo-text-hl {
          background: rgba(250, 204, 21, 0.35);
          border-radius: 2px;
          padding: 1px 0;
        }
        /* Pick-mode: show clickable areas */
        body.todo-pick-mode [data-anchor] {
          cursor: crosshair !important;
          outline: 2px dashed rgba(250, 204, 21, 0.3);
          outline-offset: 2px;
          border-radius: 4px;
          transition: outline-color 0.15s;
        }
        body.todo-pick-mode [data-anchor]:hover {
          outline-color: rgba(250, 204, 21, 0.8);
          background: rgba(250, 204, 21, 0.08);
        }
      `}</style>

      {/* Side TOC */}
      <SideToc chapters={chapters} activeId={activeId} />

      {/* Sticky chapter + section headers — only show after scrolling past first slide */}
      {showStickyHeader && stickyHeaders.chapter && (
        <div className="pointer-events-none fixed top-0 left-0 right-0 z-30" style={{
          paddingLeft: panelOpen ? "340px" : "0",
          transition: "padding 0.3s",
        }}>
          <div className="pointer-events-auto bg-[var(--bg)]/95 backdrop-blur-sm border-b border-[var(--border)]">
            <div className="max-w-[1200px] mx-auto px-8">
              <div className="py-2 text-sm font-bold tracking-wide text-[var(--primary)]">
                {stickyHeaders.chapter}
              </div>
              {stickyHeaders.section && (
                <div className="pb-2 text-xs text-[var(--text-muted)] -mt-0.5">
                  {stickyHeaders.section}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Lightbox */}
      <LightboxModal src={lightboxImg} onClose={() => setLightboxImg(null)} />

      {/* Slides */}
      {slides.map((slide) => {
        // Footer slide
        if (slide.footer) {
          return (
            <div key={slide.key} className="snap-start min-h-[100svh] flex flex-col justify-end pb-8 px-8 max-w-[1200px]" style={{
              marginLeft: panelOpen ? "max(340px, calc((100vw - 1200px) / 2))" : "auto",
              marginRight: "auto",
            }}>
              <footer className="border-t border-[var(--border)] pt-4 text-xs text-[var(--text-faint)]">
                Equity Research · K-House
              </footer>
            </div>
          );
        }

        // First slide: header + first chapter + first section + first block
        if (slide.isFirst) {
          return (
            <div key={slide.key} className="snap-start min-h-[100svh] pt-12 px-8 max-w-[1200px] transition-[margin] duration-300 relative" style={{
              marginLeft: panelOpen ? "max(340px, calc((100vw - 1200px) / 2))" : "auto",
              marginRight: "auto",
            }}>
              {slide.chapterTitle && <div id={slide.chapterTitle.id} className="absolute top-0" />}
              {slide.sectionTitle && <div id={slide.sectionTitle.id} className="absolute top-0" />}
              <Link
                href="/equity-research"
                className="mb-3 inline-block text-sm font-semibold text-[var(--primary)] opacity-70 transition-opacity hover:opacity-100"
              >
                ← Equity Research
              </Link>

              <header className="mb-10 flex items-start justify-between border-b border-[var(--border)] pb-5">
                <div>
                  <h1 className="text-3xl font-bold tracking-wide">
                    <span className="text-[var(--primary)]">{ticker}</span> 個股研究
                  </h1>
                  <div className="mt-1 text-sm text-[var(--text-muted)]">
                    {name} · 最後更新：{updated}
                  </div>
                </div>
                <ThemeToggle />
              </header>

              {slide.chapterTitle && (
                <div className="mb-8 border-b-2 border-[var(--primary)] pb-2 text-xl font-bold tracking-wide">
                  <span className="text-[var(--primary)]">{slide.chapterTitle.numeral}.</span> {slide.chapterTitle.title}
                </div>
              )}

              {slide.sectionTitle && !slide.sectionTitle.toggle && (
                <div>
                  <SectionTitle>{slide.sectionTitle.title}</SectionTitle>
                </div>
              )}

              {slide.kvCards && (
                <div
                  className="mb-4 grid gap-4 grid-cols-[repeat(auto-fill,minmax(200px,1fr))]"
                  data-anchor={slide.kvCards.anchor}
                >
                  {slide.kvCards.cards!.map((kv, i) => (
                    <KvCard key={i} {...kv} />
                  ))}
                </div>
              )}

              {slide.block && renderBlock(slide.block.block, slide.block.anchorPrefix, slide.block.index)}

              {slide.placeholder && (
                <p className="p-4 text-center text-sm italic text-[var(--text-faint)]">
                  {slide.placeholder.text}
                </p>
              )}

              {slide.valuationChapter && (
                <ValuationChapter
                  valuations={slide.valuationChapter.valuations}
                  ticker={ticker}
                  chronicle={slide.valuationChapter.chronicle}
                />
              )}
            </div>
          );
        }

        // Regular slides
        // Wrap toggle sections — Archive: compact, no full-page snap
        if (slide.sectionTitle?.toggle) {
          return (
            <div key={slide.key} className="snap-start py-4 px-8 max-w-[1200px] transition-[margin] duration-300 relative" style={{
              marginLeft: panelOpen ? "max(340px, calc((100vw - 1200px) / 2))" : "auto",
              marginRight: "auto",
            }}>
              {slide.chapterTitle && <div id={slide.chapterTitle.id} className="absolute top-0" />}
              {slide.sectionTitle && <div id={slide.sectionTitle.id} className="absolute top-0" />}

              {slide.chapterTitle && (
                <div className="mb-8 border-b-2 border-[var(--primary)] pb-2 text-xl font-bold tracking-wide">
                  <span className="text-[var(--primary)]">{slide.chapterTitle.numeral}.</span> {slide.chapterTitle.title}
                </div>
              )}

              <details data-anchor={slide.sectionTitle!.id} className="group mb-4">
                <summary className="cursor-pointer list-none">
                  <div className="flex items-center gap-2">
                    <span className="text-[var(--primary)] transition-transform group-open:rotate-90">▶</span>
                    <SectionTitle>{slide.sectionTitle.toggleLabel || slide.sectionTitle.title}</SectionTitle>
                  </div>
                </summary>
                <div className="mt-2 border-l-2 border-[var(--border)] pl-4">
                  {slide.kvCards && (
                    <div
                      className="mb-4 grid gap-4 grid-cols-[repeat(auto-fill,minmax(200px,1fr))]"
                      data-anchor={slide.kvCards.anchor}
                    >
                      {slide.kvCards.cards!.map((kv, i) => (
                        <KvCard key={i} {...kv} />
                      ))}
                    </div>
                  )}
                  {(slide.allBlocks || (slide.block ? [slide.block] : [])).map((b) =>
                    <div key={b.anchorPrefix}>{renderBlock(b.block, b.anchorPrefix, b.index)}</div>
                  )}
                </div>
              </details>
            </div>
          );
        }

        return (
          <div key={slide.key} className="snap-start min-h-[100svh] flex flex-col justify-center px-8 max-w-[1200px] transition-[margin] duration-300 relative" style={{
            marginLeft: panelOpen ? "max(340px, calc((100vw - 1200px) / 2))" : "auto",
            marginRight: "auto",
          }}>
            {/* Invisible anchor at very top of slide for scroll tracking */}
            {slide.chapterTitle && <div id={slide.chapterTitle.id} className="absolute top-0" />}
            {slide.sectionTitle && <div id={slide.sectionTitle.id} className="absolute top-0" />}

            <div>
              {slide.chapterTitle && (
                <div className="mb-8 border-b-2 border-[var(--primary)] pb-2 text-xl font-bold tracking-wide">
                  <span className="text-[var(--primary)]">{slide.chapterTitle.numeral}.</span> {slide.chapterTitle.title}
                </div>
              )}

              {slide.sectionTitle && (
                <div>
                  <SectionTitle>{slide.sectionTitle.title}</SectionTitle>
                </div>
              )}

              {slide.kvCards && (
                <div
                  className="mb-4 grid gap-4 grid-cols-[repeat(auto-fill,minmax(200px,1fr))]"
                  data-anchor={slide.kvCards.anchor}
                >
                  {slide.kvCards.cards!.map((kv, i) => (
                    <KvCard key={i} {...kv} />
                  ))}
                </div>
              )}

              {slide.block && renderBlock(slide.block.block, slide.block.anchorPrefix, slide.block.index)}

              {slide.placeholder && (
                <p className="p-4 text-center text-sm italic text-[var(--text-faint)]">
                  {slide.placeholder.text}
                </p>
              )}

              {slide.valuationChapter && (
                <ValuationChapter
                  valuations={slide.valuationChapter.valuations}
                  ticker={ticker}
                  chronicle={slide.valuationChapter.chronicle}
                />
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
