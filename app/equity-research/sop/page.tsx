import type { Metadata } from "next";
import Link from "next/link";
import ThemeToggle from "@/app/components/ThemeToggle";

export const metadata: Metadata = {
  title: "Research SOP — 個股研究流程",
};

export default function SOPPage() {
  return (
    <div className="mx-auto max-w-[820px] px-6 py-12 pb-16">
      <Link
        href="/equity-research"
        className="mb-3 inline-block text-sm font-semibold text-[var(--primary)] opacity-70 transition-opacity hover:opacity-100"
      >
        ← Equity Research
      </Link>

      <header className="mb-10 flex items-start justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-wide">
            <span className="text-[var(--primary)]">Research</span> SOP
          </h1>
          <p className="mt-1 text-sm text-[var(--text-muted)]">
            新標的研究流程 — 從零到建立 Mental Model
          </p>
        </div>
        <ThemeToggle />
      </header>

      {/* Overview */}
      <section className="mb-10">
        <h2 className="mb-4 border-l-[3px] border-[var(--primary)] pl-3 text-lg font-semibold uppercase tracking-wide text-[var(--primary)]">
          目標
        </h2>
        <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-card)] p-5 text-[0.9rem] leading-relaxed text-[var(--text)]">
          <p>
            快速建立一間公司的 <strong>mental model</strong>：靠什麼賺錢、技術護城河在哪、關鍵術語是什麼意思。
          </p>
          <p className="mt-2 text-[var(--text-muted)]">
            不是「讀完所有財報」，而是用結構化提問在 1-2 小時內掌握 80% 的 context。
          </p>
        </div>
      </section>

      {/* Phase 1 */}
      <Phase
        number={1}
        title="素材準備"
        description="把原始資料放進 NotebookLM"
        items={[
          "SEC 10-K（最近 1-2 年）",
          "SEC 10-Q（最近 2-3 季）",
          "Earnings Call Transcripts（最近 2-3 季）",
          "公司官方 Investor Presentation（如有）",
        ]}
        note="每個標的建一個獨立的 NotebookLM notebook，命名格式：{Company Name} - {TICKER}"
      />

      {/* Phase 2 */}
      <Phase
        number={2}
        title="結構化提問"
        description="用固定問題模板向 NotebookLM 提問，從財報和 transcript 中萃取關鍵資訊"
      >
        <div className="mt-4 space-y-3">
          <QuestionCard
            number={1}
            title="業務拆解"
            question="公司有哪幾個業務線（segment）？各自營收佔比多少？哪些在成長、哪些在衰退？最近一季各 segment 的 YoY 和 QoQ 變化？"
          />
          <QuestionCard
            number={2}
            title="產品與技術棧"
            question="公司的核心產品是什麼？製造流程或技術架構是什麼？有哪些世代演進（如製程節點、產品代號）？目前最新一代是什麼？"
          />
          <QuestionCard
            number={3}
            title="術語清單"
            question="管理層在最近 2-3 季的 earnings call 中反覆提到哪些技術術語和產品代號？請列出每個術語並用一句話解釋其含義和重要性。"
          />
          <QuestionCard
            number={4}
            title="競爭格局"
            question="管理層怎麼描述競爭對手和市場格局？公司的差異化優勢在哪？市佔率大約多少？主要競品是誰？"
          />
          <QuestionCard
            number={5}
            title="成長驅動力與風險"
            question="管理層認為未來 1-2 年的成長來自哪裡？有哪些明確提到的 tailwind 和 headwind？資本支出計畫是什麼？"
          />
        </div>
      </Phase>

      {/* Phase 3 */}
      <Phase
        number={3}
        title="技術深潛"
        description="針對 Phase 2 產出的術語清單，用 Perplexity 補充底層技術原理"
      >
        <div className="mt-3 rounded border border-dashed border-[var(--border)] bg-[var(--bg-subtle)] p-4 text-[0.85rem]">
          <p className="font-semibold text-[var(--text)]">範例：SNDK 的術語深潛</p>
          <ul className="mt-2 space-y-1 text-[var(--text-muted)]">
            <li>• <strong>NAND Flash</strong> → 浮閘 vs 電荷捕捉的儲存原理</li>
            <li>• <strong>TLC / QLC</strong> → 每 cell 儲存 3 vs 4 bits，容量與耐久性的 trade-off</li>
            <li>• <strong>BiCS8</strong> → 第 8 代 3D NAND 堆疊技術，層數與良率的關係</li>
            <li>• <strong>eSSD</strong> → Enterprise SSD，數據中心用的高性能儲存裝置</li>
          </ul>
          <p className="mt-3 text-xs text-[var(--text-faint)]">
            重點：先建立 big picture（Phase 2），遇到看不懂的再查。不要一開始就鑽進技術細節。
          </p>
        </div>
      </Phase>

      {/* Phase 4 */}
      <Phase
        number={4}
        title="輸出 Company Primer"
        description="將 Phase 2 + 3 的結果整理為 Equity Research 報告的第一個 section"
        items={[
          "公司概覽：一段話描述公司做什麼",
          "業務線拆解：segment 營收佔比表格",
          "核心技術：關鍵術語解釋（附技術深潛結果）",
          "競爭格局：市佔率與主要競品",
          "成長與風險：管理層觀點 + 自己的判斷",
        ]}
        note="輸出格式對齊 Equity Research JSON schema 的 content-box block type"
      />

      <footer className="border-t border-[var(--border)] pt-4 text-xs text-[var(--text-faint)]">
        Last updated: 2026-03-12
      </footer>
    </div>
  );
}

/* ── Sub-components ─────────────────────────────────────────── */

function Phase({
  number,
  title,
  description,
  items,
  note,
  children,
}: {
  number: number;
  title: string;
  description: string;
  items?: string[];
  note?: string;
  children?: React.ReactNode;
}) {
  return (
    <section className="mb-10">
      <h2 className="mb-4 border-l-[3px] border-[var(--primary)] pl-3 text-lg font-semibold uppercase tracking-wide text-[var(--primary)]">
        Phase {number}：{title}
      </h2>
      <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-card)] p-5 text-[0.9rem] leading-relaxed">
        <p className="text-[var(--text-muted)]">{description}</p>
        {items && (
          <ul className="mt-3 space-y-1.5 text-[var(--text)]">
            {items.map((item) => (
              <li key={item} className="flex gap-2">
                <span className="text-[var(--primary)]">•</span>
                {item}
              </li>
            ))}
          </ul>
        )}
        {note && (
          <p className="mt-3 text-xs text-[var(--text-faint)]">※ {note}</p>
        )}
        {children}
      </div>
    </section>
  );
}

function QuestionCard({
  number,
  title,
  question,
}: {
  number: number;
  title: string;
  question: string;
}) {
  return (
    <div className="rounded border border-[var(--border)] bg-[var(--bg-subtle)] px-4 py-3">
      <div className="flex items-center gap-2">
        <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[var(--primary)] text-[0.65rem] font-bold text-white">
          {number}
        </span>
        <span className="text-[0.85rem] font-semibold text-[var(--text)]">
          {title}
        </span>
      </div>
      <p className="mt-1.5 pl-7 text-[0.83rem] text-[var(--text-muted)]">
        {question}
      </p>
    </div>
  );
}
