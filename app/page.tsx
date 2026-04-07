import Image from "next/image";
import Link from "next/link";
import ThemeToggle from "./components/ThemeToggle";

const featured = [
  {
    href: "/command-center",
    icon: "📊",
    nameEn: "Command Center",
    name: "投資戰情室",
    desc: "總體指標、市場即時數據、thesis-driven 新聞情報，整合為單一決策支援平台。",
    tags: ["即時更新"],
  },
  {
    href: "/alphadash",
    icon: "💹",
    nameEn: "AlphaDash",
    name: "財務儀表板",
    desc: "個股財務數據儀表板，快速掌握關鍵財務指標與趨勢。",
    tags: ["Dashboard"],
  },
];

const research = [
  {
    href: "/weekly",
    icon: "📈",
    nameEn: "Stock Weekly",
    name: "個股週報",
    desc: "個股技術面、籌碼面、基本面綜合週報。",
    tags: ["每週更新"],
  },
  {
    href: "/financials",
    icon: "🗂️",
    nameEn: "Financials Viewer",
    name: "財務報表瀏覽器",
    desc: "三表（損益、資產負債、現金流）及財務比率的時序瀏覽，支援多標的切換。",
    tags: ["SNDK", "MU", "LEU"],
  },
  {
    href: "/equity-research",
    icon: "🔬",
    nameEn: "Equity Research",
    name: "個股研究報告",
    desc: "美股與台股個股深度研究報告，含質性分析與量化估值。",
    tags: ["US", "TW"],
  },
  {
    href: "/monthly-report",
    icon: "📊",
    nameEn: "Performance Calculator",
    name: "月報漲跌幅計算器",
    desc: "選擇時間範圍，快速對比多個市場標的的漲跌幅表現。",
    tags: ["SPY", "QQQ", "DIA"],
  },
];

function ToolCard({
  href,
  icon,
  nameEn,
  name,
  desc,
  tags,
}: {
  href: string;
  icon: string;
  nameEn: string;
  name: string;
  desc: string;
  tags: string[];
}) {
  return (
    <Link
      href={href}
      className="group block rounded-[var(--radius)] border border-[var(--border)] bg-[var(--bg-card)] p-6 no-underline shadow-[0_1px_4px_rgba(44,21,23,0.05)] transition-all hover:-translate-y-0.5 hover:border-[var(--primary)] hover:shadow-[0_4px_16px_rgba(192,39,52,0.12)] active:translate-y-0"
    >
      <div className="text-[1.6rem] leading-none">{icon}</div>
      <div className="mt-2 text-[0.72rem] font-semibold uppercase tracking-[0.06em] text-[var(--primary)]">
        {nameEn}
      </div>
      <div className="mt-1 text-base font-bold text-[var(--text)]">{name}</div>
      <div className="mt-1 flex-1 text-[0.82rem] text-[var(--text-muted)]">
        {desc}
      </div>
      <div className="mt-2 flex flex-wrap gap-1">
        {tags.map((tag) => (
          <span
            key={tag}
            className="inline-block rounded-full bg-[var(--tag-bg)] px-2 py-0.5 text-[0.68rem] font-semibold tracking-[0.03em] text-[var(--primary-dk)]"
          >
            {tag}
          </span>
        ))}
      </div>
      <div className="mt-2 text-right text-[0.8rem] text-[var(--text-faint)] group-hover:text-[var(--primary)]">
        開啟 →
      </div>
    </Link>
  );
}

export default function Portal() {
  return (
    <div className="min-h-screen bg-[var(--bg-page)]">
      {/* Header */}
      <header className="flex items-center gap-4 border-b-2 border-[var(--primary)] bg-[var(--bg-card)] px-8 py-5">
        <Image
          src="/images/khouse_LOGO_text.png"
          alt="K-House Logo"
          width={160}
          height={40}
          className="h-10 w-auto"
        />
        <div className="h-8 w-px bg-[var(--border)]" />
        <div className="text-[0.9rem] tracking-[0.04em] text-[var(--text-muted)]">
          研究工具入口
        </div>
        <div className="ml-auto">
          <ThemeToggle />
        </div>
      </header>

      {/* Main */}
      <main className="mx-auto max-w-[960px] px-6 pb-16 pt-12">
        <div className="mb-4 text-[0.72rem] font-bold uppercase tracking-[0.1em] text-[var(--text-faint)]">
          FEATURED
        </div>
        <div className="mb-10 grid grid-cols-[repeat(auto-fill,minmax(260px,1fr))] gap-4">
          {featured.map((item) => (
            <ToolCard key={item.nameEn} {...item} />
          ))}
        </div>

        <div className="mb-4 text-[0.72rem] font-bold uppercase tracking-[0.1em] text-[var(--text-faint)]">
          個股研究
        </div>
        <div className="mb-10 grid grid-cols-[repeat(auto-fill,minmax(260px,1fr))] gap-4">
          {research.map((item) => (
            <ToolCard key={item.nameEn} {...item} />
          ))}
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-[var(--border)] px-8 py-5 text-center text-[0.75rem] text-[var(--text-faint)]">
        K-House Research · Internal Use Only
      </footer>
    </div>
  );
}
