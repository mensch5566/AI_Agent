"use client";

import { useState } from "react";
import type { NewsItem, FeedbackTarget } from "./types";
import NewsFeedbackModal from "./NewsFeedbackModal";

interface NewsTableProps {
  items: NewsItem[];
}

export default function NewsTable({ items }: NewsTableProps) {
  const [feedbackTarget, setFeedbackTarget] = useState<FeedbackTarget | null>(null);
  const [dismissedNews, setDismissedNews] = useState<Set<number>>(new Set());

  const sortedItems = [...items].sort((a, b) => b.date.localeCompare(a.date));

  const cleanSummary = (text?: string) => {
    if (!text) return "";
    // Strip HTML tags, decode &nbsp; entities, collapse whitespace
    return text
      .replace(/<[^>]*>/g, "")
      .replace(/&nbsp;/g, " ")
      .replace(/&amp;/g, "&")
      .replace(/&lt;/g, "<")
      .replace(/&gt;/g, ">")
      .replace(/&quot;/g, '"')
      .replace(/&#39;/g, "'")
      .replace(/\s{2,}/g, " ")
      .trim();
  };

  const sentimentBadge = (s?: string) => {
    const label = s === "bullish" ? "利多" : s === "bearish" ? "利空" : "中立";
    const color = s === "bullish" ? "text-green-700 bg-green-50" : s === "bearish" ? "text-red-700 bg-red-50" : "text-[#7A5860] bg-[#F8F4F4]";
    return <span className={`inline-block px-1.5 py-0.5 rounded text-xs font-medium ${color}`}>{label}</span>;
  };

  const colGroup = (
    <colgroup>
      <col className="w-[90px]" />
      <col className="w-[60px]" />
      <col className="w-[160px]" />
      <col />
      <col className="w-[56px]" />
      <col className="w-[40px]" />
    </colgroup>
  );

  return (
    <>
      <div className="bg-[var(--bg-card)] border border-[var(--border)] rounded-lg p-5 shadow-[0_1px_3px_rgba(44,21,23,0.06)] relative">
        <table className="w-full border-collapse text-[0.88rem] table-fixed">
          {colGroup}
          <thead className="sticky top-0 z-10">
            <tr>
              <th className="px-3 py-2 bg-[var(--bg-subtle)] text-[var(--text-muted)] text-xs uppercase border-b border-[var(--border)] text-left">日期</th>
              <th className="px-3 py-2 bg-[var(--bg-subtle)] text-[var(--text-muted)] text-xs uppercase border-b border-[var(--border)] text-left">標的</th>
              <th className="px-3 py-2 bg-[var(--bg-subtle)] text-[var(--text-muted)] text-xs uppercase border-b border-[var(--border)] text-left">標題</th>
              <th className="px-3 py-2 bg-[var(--bg-subtle)] text-[var(--text-muted)] text-xs uppercase border-b border-[var(--border)] text-left">彙整</th>
              <th className="px-3 py-2 bg-[var(--bg-subtle)] text-[var(--text-muted)] text-xs uppercase border-b border-[var(--border)] text-center">情緒</th>
              <th className="px-3 py-2 bg-[var(--bg-subtle)] text-[var(--text-muted)] text-xs uppercase border-b border-[var(--border)] text-center"></th>
            </tr>
          </thead>
        </table>
        <div className="max-h-[480px] overflow-y-auto pr-2">
        <table className="w-full border-collapse text-[0.88rem] table-fixed">
          {colGroup}
          <tbody>
            {sortedItems.length > 0 ? (
              sortedItems.filter((_, i) => !dismissedNews.has(i)).map((item, i) => (
                <tr key={i} className="hover:bg-[var(--bg-subtle)] transition-colors">
                  <td className="px-3 py-2.5 border-b border-[var(--border)] align-top whitespace-nowrap text-[#B09898]">{item.date}</td>
                  <td className="px-3 py-2.5 border-b border-[var(--border)] align-top font-mono text-xs font-semibold text-[#5A3E42]">{item.ticker || "—"}</td>
                  <td className="px-3 py-2.5 border-b border-[var(--border)] align-top">
                    {item.url ? <a href={item.url} target="_blank" rel="noopener noreferrer" className="text-[#C02734] hover:underline">{item.headline}</a> : item.headline}
                  </td>
                  <td className="px-3 py-2.5 border-b border-[var(--border)] align-top break-words text-[0.82rem] leading-relaxed">
                    <span>{cleanSummary(item.summary)}</span>
                    {item.analysis && (
                      <span className="block mt-1.5 text-[0.78rem] text-[#7A5860] leading-snug border-l-2 border-[#C02734]/30 pl-2">
                        {item.analysis}
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2.5 border-b border-[var(--border)] align-top text-center">
                    {sentimentBadge(item.sentiment)}
                  </td>
                  <td className="px-3 py-2.5 border-b border-[var(--border)] align-top text-center">
                    <button
                      onClick={() => setFeedbackTarget({ index: i, headline: item.headline, url: item.url, ticker: item.ticker, sentiment: item.sentiment })}
                      className="text-[#B09898] hover:text-[#C02734] transition-colors text-lg leading-none"
                      title="標記此新聞不符需求"
                    >
                      &times;
                    </button>
                  </td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={6} className="text-center text-[#B09898] py-8">
                  目前無新聞
                </td>
              </tr>
            )}
          </tbody>
        </table>
        </div>
      </div>

      {feedbackTarget && (
        <NewsFeedbackModal
          target={feedbackTarget}
          onClose={() => setFeedbackTarget(null)}
          onSubmitted={(index) => {
            setDismissedNews((prev) => new Set(prev).add(index));
            setFeedbackTarget(null);
          }}
        />
      )}
    </>
  );
}
