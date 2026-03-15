import type { Metadata } from "next";
import Link from "next/link";
import ThemeToggle from "@/app/components/ThemeToggle";

export const metadata: Metadata = {
  title: "Equity Research — 個股研究報告",
};

const US_TICKERS = [
  {
    symbol: "SNDK",
    name: "Sandisk Corp",
    tags: [
      { label: "WIP", status: "wip" as const },
      { label: "NAND Flash", status: "default" as const },
    ],
  },
];

const TAG_STYLE: Record<string, string> = {
  wip: "bg-yellow-100 text-yellow-800",
  ready: "bg-green-100 text-green-800",
  default: "bg-[var(--bg-subtle)] text-[var(--text-muted)]",
};

export default function EquityResearchPage() {
  return (
    <div className="mx-auto max-w-[720px] px-6 py-12 pb-16">
      <Link
        href="/"
        className="mb-3 inline-block text-sm font-semibold text-[var(--primary)] opacity-70 transition-opacity hover:opacity-100"
      >
        ← Portal
      </Link>

      <header className="mb-10 flex items-start justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-wide">
            <span className="text-[var(--primary)]">Equity</span> Research
          </h1>
          <p className="mt-1 text-sm text-[var(--text-muted)]">
            個股基本面研究報告
          </p>
        </div>
        <ThemeToggle />
      </header>

      {/* US Stocks */}
      <div className="mb-8">
        <div className="mb-3 text-xs font-semibold uppercase tracking-widest text-[var(--text-muted)]">
          US Stocks
        </div>
        <div className="grid gap-3 grid-cols-[repeat(auto-fill,minmax(180px,1fr))]">
          {US_TICKERS.map((t) => (
            <Link
              key={t.symbol}
              href={`/equity-research/${t.symbol}`}
              className="rounded-lg border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm transition-all hover:border-[var(--primary)] hover:shadow-md"
            >
              <div className="text-xl font-bold text-[var(--primary)]">
                {t.symbol}
              </div>
              <div className="mt-0.5 text-xs text-[#6B5E60]">{t.name}</div>
              <div className="mt-2 flex gap-1.5">
                {t.tags.map((tag) => (
                  <span
                    key={tag.label}
                    className={`rounded px-2 py-0.5 text-[0.68rem] ${TAG_STYLE[tag.status]}`}
                  >
                    {tag.label}
                  </span>
                ))}
              </div>
            </Link>
          ))}
        </div>
      </div>

      {/* TW Stocks */}
      <div className="mb-8">
        <div className="mb-3 text-xs font-semibold uppercase tracking-widest text-[var(--text-muted)]">
          TW Stocks
        </div>
        <p className="p-2 text-sm italic text-[var(--text-faint)]">尚無標的</p>
      </div>

      {/* SOP */}
      <div className="mb-8">
        <div className="mb-3 text-xs font-semibold uppercase tracking-widest text-[var(--text-muted)]">
          SOPs
        </div>
        <div className="grid gap-3 grid-cols-[repeat(auto-fill,minmax(180px,1fr))]">
          <Link
            href="/equity-research/sop"
            className="rounded-lg border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm transition-all hover:border-[var(--primary)] hover:shadow-md"
          >
            <div className="text-lg font-bold text-[var(--primary)]">
              Research SOP
            </div>
            <div className="mt-0.5 text-xs text-[#6B5E60]">新標的研究流程</div>
          </Link>
          <Link
            href="/equity-research/todo-workflow"
            className="rounded-lg border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm transition-all hover:border-[var(--primary)] hover:shadow-md"
          >
            <div className="text-lg font-bold text-[var(--primary)]">
              To-Do Workflow
            </div>
            <div className="mt-0.5 text-xs text-[#6B5E60]">待辦事項產生流程</div>
          </Link>
        </div>
      </div>

      <footer className="border-t border-[var(--border)] pt-4 text-xs text-[var(--text-faint)]">
        Equity Research Portal
      </footer>
    </div>
  );
}
