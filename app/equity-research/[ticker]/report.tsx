"use client";

import { useState, useEffect, useCallback, type ReactNode } from "react";
import Link from "next/link";
import dynamic from "next/dynamic";
import ThemeToggle from "@/app/components/ThemeToggle";
import TodoPanel from "@/app/components/TodoPanel";

const RatioChart = dynamic(() => import("@/app/components/financials/RatioChart"), { ssr: false });
const FinancialTable = dynamic(() => import("@/app/components/financials/FinancialTable"), { ssr: false });
const SegmentTable = dynamic(() => import("@/app/components/financials/SegmentTable"), { ssr: false });

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

interface ContentBoxBlock {
  type: "content-box";
  id?: string;
  title?: string;
  paragraphs?: string[];
  table?: TableData;
  image?: ImageData;
  bullets?: BulletList;
  footnote?: string;
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
  const items: { id: string; label: string; isChapter: boolean }[] = [];
  for (const ch of chapters) {
    items.push({ id: ch.id, label: `${ch.numeral}. ${ch.title}`, isChapter: true });
    if (ch.id !== "ch-archive") {
      for (const sec of ch.sections) {
        items.push({ id: sec.id, label: sec.title.replace(/^\d+\s*·\s*/, ""), isChapter: false });
      }
    }
  }

  return (
    <nav
      className="fixed top-1/2 z-50 hidden w-[180px] -translate-y-1/2 text-xs leading-relaxed min-[1440px]:block"
      style={{ right: "calc((100vw - 1200px) / 2 - 200px)" }}
    >
      <ul className="border-l-2 border-[var(--border)]">
        {items.map((s) => {
          const isActive = activeId === s.id;
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
                className={`transition-colors ${
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
    </nav>
  );
}

/* ================================================================
   Inline Markdown — minimal bold / italic / bold-italic support
   ================================================================ */
function renderInline(text: string): ReactNode {
  // Split by **bold**, __underline-bold__, *italic*
  const parts = text.split(/(\*\*[^*]+\*\*|__[^_]+__)/g);
  return parts.map((part, i) => {
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
    // Handle \n line breaks
    if (part.includes("\n")) {
      return part.split("\n").map((line, j, arr) => (
        <span key={`${i}-${j}`}>
          {line}
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

        {/* Bullets */}
        {block.bullets && (
          <ul className="mb-3 list-disc space-y-1 pl-5 text-[0.95rem]" data-anchor={a("bullets", 0)}>
            {block.bullets.items.map((item, i) => (
              <li key={i}>{renderInline(item)}</li>
            ))}
          </ul>
        )}

        {/* Paragraphs */}
        {block.paragraphs?.map((p, i) => (
          <p key={i} className="mb-3 text-[0.95rem] leading-relaxed" data-anchor={a("paragraph", i)}>
            {renderInline(p)}
          </p>
        ))}

        {/* Footnote */}
        {block.footnote && (
          <div className="text-xs text-[var(--text-faint)]">{block.footnote}</div>
        )}

        {/* Sources */}
        {block.sources && <Sources list={block.sources} />}
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

function DetailsToggle({ details }: { details: string[] }) {
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
          <DetailsToggle details={latest.details} />
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
export default function Report({ data }: { data: ReportData }) {
  const { ticker, name, updated, chapters } = data;

  // Build flat list of section IDs for scroll tracking
  const allIds: string[] = [];
  for (const ch of chapters) {
    allIds.push(ch.id);
    for (const sec of ch.sections) {
      allIds.push(sec.id);
    }
  }

  const [activeId, setActiveId] = useState(allIds[0] || "");
  const [lightboxImg, setLightboxImg] = useState<string | null>(null);

  useEffect(() => {
    const targets = allIds
      .map((id) => document.getElementById(id))
      .filter(Boolean) as HTMLElement[];

    function onScroll() {
      const offset = window.scrollY + window.innerHeight * 0.25;
      let active = targets[0];
      for (const t of targets) {
        if (t.offsetTop <= offset) active = t;
      }
      if (active) setActiveId(active.id);
    }

    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  const openLightbox = useCallback((src: string) => {
    setLightboxImg(src);
  }, []);

  return (
    <div className="mx-auto max-w-[1200px] px-8 py-8 pb-16">
      {/* To-Do Panel */}
      <TodoPanel ticker={ticker} />

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

      <Link
        href="/equity-research"
        className="mb-3 inline-block text-sm font-semibold text-[var(--primary)] opacity-70 transition-opacity hover:opacity-100"
      >
        ← Equity Research
      </Link>

      {/* Header */}
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

      {/* Side TOC */}
      <SideToc chapters={chapters} activeId={activeId} />

      {/* Lightbox */}
      <LightboxModal src={lightboxImg} onClose={() => setLightboxImg(null)} />

      {/* Chapters */}
      {chapters.map((ch) => (
        <div key={ch.id} className="mb-16" id={ch.id}>
          <div className="mb-8 border-b-2 border-[var(--primary)] pb-2 text-xl font-bold tracking-wide">
            <span className="text-[var(--primary)]">{ch.numeral}.</span> {ch.title}
          </div>

          {ch.valuations && <ValuationChapter valuations={ch.valuations} ticker={ticker} chronicle={ch.chronicle} />}

          {ch.placeholder && ch.sections.length === 0 && !ch.valuations && (
            <p className="p-4 text-center text-sm italic text-[var(--text-faint)]">
              {ch.placeholder}
            </p>
          )}

          {ch.sections.map((sec) => {
            const sectionInner = (
              <>
                {!sec.toggle && <SectionTitle>{sec.title}</SectionTitle>}

                {/* KV Cards */}
                {sec.kvCards && sec.kvCards.length > 0 && (
                  <div
                    className="mb-4 grid gap-4 grid-cols-[repeat(auto-fill,minmax(200px,1fr))]"
                    data-anchor={`${sec.id}-0-kvCards-0`}
                  >
                    {sec.kvCards.map((kv, i) => (
                      <KvCard key={i} {...kv} />
                    ))}
                  </div>
                )}

                {/* Blocks */}
                {sec.blocks.map((block, i) => {
                  const ap = `${sec.id}-${i}`;
                  if (block.type === "financial-chart") {
                    return (
                      <div key={i} className="mb-4 rounded-lg border border-[var(--border)] bg-[var(--bg-card)] p-6 shadow-sm" data-anchor={`${ap}-chart-0`}>
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
                      <div key={i} className="mb-4 rounded-lg border border-[var(--border)] bg-[var(--bg-card)] p-6 shadow-sm" data-anchor={`${ap}-financial-table-0`}>
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
                      <div key={i} className="mb-4 rounded-lg border border-[var(--border)] bg-[var(--bg-card)] p-6 shadow-sm" data-anchor={`${ap}-segment-table-0`}>
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
                  return <BlockRenderer key={i} block={block as ContentBoxBlock} onImageClick={openLightbox} anchorPrefix={ap} />;
                })}
              </>
            );

            if (sec.toggle) {
              return (
                <details key={sec.id} id={sec.id} data-anchor={sec.id} className="group mb-10">
                  <summary className="cursor-pointer list-none">
                    <div className="flex items-center gap-2">
                      <span className="text-[var(--primary)] transition-transform group-open:rotate-90">▶</span>
                      <SectionTitle>{sec.toggleLabel || sec.title}</SectionTitle>
                    </div>
                  </summary>
                  <div className="mt-2 border-l-2 border-[var(--border)] pl-4">
                    {sectionInner}
                  </div>
                </details>
              );
            }

            return (
              <section key={sec.id} id={sec.id} className="mb-10">
                {sectionInner}
              </section>
            );
          })}
        </div>
      ))}

      <footer className="border-t border-[var(--border)] pt-4 text-xs text-[var(--text-faint)]">
        Equity Research · K-House
      </footer>
    </div>
  );
}
