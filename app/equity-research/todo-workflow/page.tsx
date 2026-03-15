import type { Metadata } from "next";
import Link from "next/link";
import ThemeToggle from "@/app/components/ThemeToggle";

export const metadata: Metadata = {
  title: "To-Do Workflow — 待辦事項產生流程",
};

export default function TodoWorkflowPage() {
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
            <span className="text-[var(--primary)]">To-Do</span> Workflow
          </h1>
          <p className="mt-1 text-sm text-[var(--text-muted)]">
            從會議錄音到前端 To-Do Panel 的完整流程
          </p>
        </div>
        <ThemeToggle />
      </header>

      {/* Steps */}
      <section className="mb-10">
        <h2 className="mb-4 border-l-[3px] border-[var(--primary)] pl-3 text-lg font-semibold uppercase tracking-wide text-[var(--primary)]">
          流程步驟
        </h2>
        <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-card)] p-5 text-[0.9rem] leading-relaxed">
          <ol className="space-y-3 text-[var(--text)]">
            <StepCard
              number={1}
              title="上傳錄音"
              detail="將會議錄音上傳至 NotebookLM（work profile），作為 source 加入對應標的的 notebook"
            />
            <StepCard
              number={2}
              title="提取待辦事項"
              detail="請 Claude 從會議內容中萃取 action items（研究方向、數據待查、追蹤事項等）"
            />
            <StepCard
              number={3}
              title="查詢 NotebookLM"
              detail="Claude 針對每個 action item 查詢 NotebookLM，補充上下文與相關資訊"
            />
            <StepCard
              number={4}
              title="用戶確認"
              detail="Claude 列出所有待辦事項供用戶確認——確認內容正確、優先順序合理後才進入下一步"
              highlight
            />
            <StepCard
              number={5}
              title="寫入 Supabase"
              detail="確認後的事項寫入 Supabase research_todos table，每筆帶 anchor 資訊（blockId + subAnchor + textFragment + textOffset）"
            />
            <StepCard
              number={6}
              title="前端顯示"
              detail="個股報告頁的 To-Do Panel 即時讀取並顯示待辦事項，支援 anchor 定位與錯誤檢測"
            />
          </ol>
        </div>
      </section>

      {/* Anchor Integrity */}
      <section className="mb-10">
        <h2 className="mb-4 border-l-[3px] border-[var(--primary)] pl-3 text-lg font-semibold uppercase tracking-wide text-[var(--primary)]">
          Anchor 完整性檢查
        </h2>
        <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-card)] p-5 text-[0.88rem] leading-relaxed">
          <p className="text-[var(--text-muted)]">
            報告內容更動後，anchor 可能偏移或失效。兩層防護機制：
          </p>
          <div className="mt-4 space-y-3">
            <div className="rounded border border-[var(--border)] bg-[var(--bg-subtle)] px-4 py-3">
              <p className="font-semibold text-[var(--text)]">事後檢查（CLI）</p>
              <div className="mt-2 font-mono text-[0.82rem] text-[var(--text-muted)]">
                <p>
                  <span className="text-[var(--primary)]">python3</span>{" "}
                  Tools/research-tools/anchor-checker/check_anchors.py [TICKER]
                </p>
                <p className="mt-1">
                  <span className="text-[var(--primary)]">python3</span>{" "}
                  Tools/research-tools/anchor-checker/check_anchors.py --fix [TICKER]
                </p>
              </div>
              <p className="mt-2 text-xs text-[var(--text-faint)]">
                --fix 可自動修正 offset 偏移；block/element 消失則僅報告
              </p>
            </div>
            <div className="rounded border border-[var(--border)] bg-[var(--bg-subtle)] px-4 py-3">
              <p className="font-semibold text-[var(--text)]">前端即時提示</p>
              <p className="mt-1 text-[0.83rem] text-[var(--text-muted)]">
                anchor 指向的 DOM 不存在或 textOffset 不匹配 → pin 變紅 → todo item 紅框 → session header 顯示 error 數量
              </p>
            </div>
          </div>
        </div>
      </section>

      <footer className="border-t border-[var(--border)] pt-4 text-xs text-[var(--text-faint)]">
        Last updated: 2026-03-15
      </footer>
    </div>
  );
}

/* ── Sub-component ─────────────────────────────────────────── */

function StepCard({
  number,
  title,
  detail,
  highlight,
}: {
  number: number;
  title: string;
  detail: string;
  highlight?: boolean;
}) {
  return (
    <li
      className={`rounded border px-4 py-3 ${
        highlight
          ? "border-[var(--primary)] bg-[var(--primary)]/5"
          : "border-[var(--border)] bg-[var(--bg-subtle)]"
      }`}
    >
      <div className="flex items-center gap-2">
        <span
          className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[0.65rem] font-bold text-white ${
            highlight ? "bg-[var(--primary)]" : "bg-[var(--text-muted)]"
          }`}
        >
          {number}
        </span>
        <span className="text-[0.85rem] font-semibold text-[var(--text)]">
          {title}
        </span>
      </div>
      <p className="mt-1.5 pl-7 text-[0.83rem] text-[var(--text-muted)]">
        {detail}
      </p>
    </li>
  );
}
