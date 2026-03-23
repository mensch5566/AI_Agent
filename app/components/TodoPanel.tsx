"use client";

import { useState, useEffect, useCallback } from "react";
import { createPortal } from "react-dom";

/* ----------------------------------------------------------------
   Types
   ---------------------------------------------------------------- */
interface AnchorPoint {
  blockId?: string;          // preferred: content-level ID (survives moves)
  sectionId?: string;        // fallback: positional
  boxIndex?: number;
  elementType?: string;
  elementIndex?: number;
  subAnchor?: string;        // e.g. "table-0" within a blockId
  textFragment?: string;
  textOffset?: number;        // char offset within element's textContent (disambiguates duplicate fragments)
  label?: string;
}

interface TodoItem {
  id: string;
  ticker: string;
  session_date: string;
  session_label: string | null;
  category: string | null;
  title: string;
  content: string | null;
  status: "open" | "done" | "archived";
  response: string | null;
  anchor: AnchorPoint[] | null;
  anchor_locked: boolean;
  created_at: string;
  updated_at: string;
}

/* ----------------------------------------------------------------
   Highlight helpers
   ---------------------------------------------------------------- */
function clearAllHighlights() {
  document.querySelectorAll(".todo-highlight").forEach((el) => {
    el.classList.remove("todo-highlight");
  });
  document.querySelectorAll("mark.todo-text-hl").forEach((mark) => {
    const parent = mark.parentNode;
    if (parent) {
      parent.replaceChild(
        document.createTextNode(mark.textContent || ""),
        mark,
      );
      parent.normalize();
    }
  });
}

function highlightTextInElement(el: Element, fragment: string, textOffset?: number) {
  const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
  let node: Text | null;
  let charsSoFar = 0; // running offset within el.textContent

  while ((node = walker.nextNode() as Text | null)) {
    const nodeLen = node.textContent?.length ?? 0;

    // If we have a precise offset, use it to skip to the right text node
    if (textOffset != null) {
      if (charsSoFar + nodeLen <= textOffset) {
        charsSoFar += nodeLen;
        continue;
      }
      const localIdx = textOffset - charsSoFar;
      if (node.textContent?.substring(localIdx, localIdx + fragment.length) === fragment) {
        const range = document.createRange();
        range.setStart(node, localIdx);
        range.setEnd(node, localIdx + fragment.length);
        const mark = document.createElement("mark");
        mark.className = "todo-text-hl";
        range.surroundContents(mark);
        return true;
      }
      charsSoFar += nodeLen;
      continue;
    }

    // Fallback: no offset, match first occurrence
    const idx = node.textContent?.indexOf(fragment) ?? -1;
    if (idx === -1) continue;
    const range = document.createRange();
    range.setStart(node, idx);
    range.setEnd(node, idx + fragment.length);
    const mark = document.createElement("mark");
    mark.className = "todo-text-hl";
    range.surroundContents(mark);
    return true;
  }
  return false;
}

function resolveAnchorSelector(anchor: AnchorPoint): string | null {
  // If sub-anchor within a block (e.g. specific table inside a content-box)
  if (anchor.blockId && anchor.subAnchor) {
    return `${anchor.blockId}--${anchor.subAnchor}`;
  }
  // Block-level anchor
  if (anchor.blockId) {
    return anchor.blockId;
  }
  // Positional fallback
  if (anchor.sectionId != null && anchor.boxIndex != null && anchor.elementType && anchor.elementIndex != null) {
    return `${anchor.sectionId}-${anchor.boxIndex}-${anchor.elementType}-${anchor.elementIndex}`;
  }
  return null;
}

function scrollToAnchor(anchor: AnchorPoint) {
  const selector = resolveAnchorSelector(anchor);
  if (!selector) return;
  const el = document.querySelector(`[data-anchor="${selector}"]`);
  if (!el) return;

  // Auto-open the element itself (if <details>) and any parent <details>
  if (el.tagName === "DETAILS" && !(el as HTMLDetailsElement).open) {
    (el as HTMLDetailsElement).open = true;
  }
  let parent = el.parentElement;
  while (parent) {
    if (parent.tagName === "DETAILS" && !(parent as HTMLDetailsElement).open) {
      (parent as HTMLDetailsElement).open = true;
    }
    parent = parent.parentElement;
  }

  el.classList.add("todo-highlight");
  if (anchor.textFragment) {
    highlightTextInElement(el, anchor.textFragment, anchor.textOffset);
  }
  el.scrollIntoView({ behavior: "smooth", block: "center" });
}

function parseAnchorId(
  anchorId: string,
): { sectionId: string; boxIndex: number; elementType: string; elementIndex: number } | null {
  // Format: sectionId-boxIndex-elementType-elementIndex
  // sectionId can contain hyphens (e.g. "sec-market-share")
  // We split from the right: last part = elementIndex, second-last = elementType, third-last = boxIndex
  const parts = anchorId.split("-");
  if (parts.length < 4) return null;
  const elementIndex = parseInt(parts[parts.length - 1], 10);
  const elementType = parts[parts.length - 2];
  const boxIndex = parseInt(parts[parts.length - 3], 10);
  const sectionId = parts.slice(0, parts.length - 3).join("-");
  if (isNaN(elementIndex) || isNaN(boxIndex)) return null;
  return { sectionId, boxIndex, elementType, elementIndex };
}

/* ----------------------------------------------------------------
   Status icon
   ---------------------------------------------------------------- */
function StatusIcon({ status }: { status: string }) {
  switch (status) {
    case "done":
      return <span className="text-green-500">&#10003;</span>;
    case "archived":
      return <span className="text-[var(--text-faint)]">&#9744;</span>;
    default:
      return <span className="text-amber-500">&#9634;</span>;
  }
}

/* ----------------------------------------------------------------
   Category badge
   ---------------------------------------------------------------- */
const CATEGORY_COLORS: Record<string, string> = {
  技術比較: "bg-blue-50 text-blue-600 border-blue-200 dark:bg-blue-950/40 dark:text-blue-400 dark:border-blue-800",
  財務釐清: "bg-amber-50 text-amber-600 border-amber-200 dark:bg-amber-950/40 dark:text-amber-400 dark:border-amber-800",
  估值: "bg-purple-50 text-purple-600 border-purple-200 dark:bg-purple-950/40 dark:text-purple-400 dark:border-purple-800",
};

function CategoryBadge({ category }: { category: string | null }) {
  if (!category) return null;
  const color =
    CATEGORY_COLORS[category] ||
    "bg-gray-50 text-gray-500 border-gray-200 dark:bg-gray-900 dark:text-gray-400 dark:border-gray-700";
  return (
    <span
      className={`inline-block rounded-md border px-1.5 py-0.5 text-[0.7rem] leading-tight font-medium ${color}`}
    >
      {category}
    </span>
  );
}

/* ----------------------------------------------------------------
   Tooltip — portal to body so transform parent doesn't clip it
   ---------------------------------------------------------------- */
function Tooltip({
  text,
  children,
}: {
  text: string | null;
  children: React.ReactNode;
}) {
  const [show, setShow] = useState(false);
  const [pos, setPos] = useState({ x: 0, y: 0 });

  if (!text) return <>{children}</>;

  return (
    <div
      onMouseEnter={(e) => {
        const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
        setPos({ x: rect.right + 8, y: rect.top });
        setShow(true);
      }}
      onMouseLeave={() => setShow(false)}
    >
      {children}
      {show &&
        createPortal(
          <div
            className="pointer-events-none fixed z-[9999] w-[320px] rounded-lg border border-[var(--border)] bg-[var(--bg-card)] px-3.5 py-2.5 text-xs leading-relaxed text-[var(--text)] shadow-lg"
            style={{ left: pos.x, top: pos.y }}
          >
            {text}
          </div>,
          document.body,
        )}
    </div>
  );
}

/* ----------------------------------------------------------------
   TodoPanel Component
   ---------------------------------------------------------------- */
export default function TodoPanel({ ticker, onToggle }: { ticker: string; onToggle?: (open: boolean) => void }) {
  const [isOpen, setIsOpen] = useState(false);
  const [todos, setTodos] = useState<TodoItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [openSessions, setOpenSessions] = useState<Set<string>>(new Set());
  const [activeItemId, setActiveItemId] = useState<string | null>(null);
  const [pickingAnchorForId, setPickingAnchorForId] = useState<string | null>(null);
  const lockedItems: Set<string> = new Set(todos.filter(t => t.anchor_locked).map(t => t.id));
  // Track broken anchors: key = "todoId-anchorIdx"
  const [brokenAnchors, setBrokenAnchors] = useState<Set<string>>(new Set());

  // Validate all anchors against the DOM (element existence + textFragment/textOffset)
  const validateAnchors = useCallback(() => {
    const broken = new Set<string>();
    for (const todo of todos) {
      if (!todo.anchor) continue;
      todo.anchor.forEach((a, idx) => {
        const selector = resolveAnchorSelector(a);
        if (!selector) { broken.add(`${todo.id}-${idx}`); return; }
        const el = document.querySelector(`[data-anchor="${selector}"]`);
        if (!el) { broken.add(`${todo.id}-${idx}`); return; }
        // Check textFragment + textOffset precision
        if (a.textFragment && a.textOffset != null) {
          const text = el.textContent || "";
          const actual = text.substring(a.textOffset, a.textOffset + a.textFragment.length);
          if (actual !== a.textFragment) {
            broken.add(`${todo.id}-${idx}`);
          }
        }
      });
    }
    setBrokenAnchors(broken);
  }, [todos]);

  // Re-validate when todos change or panel opens
  useEffect(() => {
    if (isOpen && todos.length > 0) {
      // Small delay to ensure DOM is rendered
      const timer = setTimeout(validateAnchors, 300);
      return () => clearTimeout(timer);
    }
  }, [isOpen, todos, validateAnchors]);

  // Fetch todos
  const fetchTodos = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`/api/research-todos?ticker=${ticker}`);
      const data = await res.json();
      if (Array.isArray(data)) setTodos(data);
    } catch {
      // silently fail
    } finally {
      setLoading(false);
    }
  }, [ticker]);

  useEffect(() => {
    if (isOpen) fetchTodos();
  }, [isOpen, fetchTodos]);

  // Clean up highlights when panel closes
  useEffect(() => {
    if (!isOpen) {
      clearAllHighlights();
      setActiveItemId(null);
      setPickingAnchorForId(null);
    }
  }, [isOpen]);

  // Anchor picking mode — click on any data-anchor element to add anchor
  useEffect(() => {
    if (!pickingAnchorForId) {
      document.body.classList.remove("todo-pick-mode");
      return;
    }
    document.body.classList.add("todo-pick-mode");

    // In pick mode, open all <details> so inner content is clickable,
    // and prevent <summary> clicks from toggling them closed
    const allDetails = document.querySelectorAll("details");
    const previousState = new Map<HTMLDetailsElement, boolean>();
    allDetails.forEach((d) => {
      previousState.set(d, d.open);
      d.open = true;
    });

    const preventToggle = (e: MouseEvent) => {
      const summary = (e.target as HTMLElement).closest("summary");
      if (summary) {
        e.preventDefault();
      }
    };
    document.addEventListener("click", preventToggle, true);

    const handler = (e: MouseEvent) => {
      // Ignore clicks inside the panel itself
      const panel = (e.target as HTMLElement).closest("[data-todo-panel]");
      if (panel) return;

      // Determine target: prefer selection's position for precision, fallback to e.target
      let target: Element | null = null;
      let textFragment: string | undefined;

      const sel = window.getSelection();
      if (sel && sel.rangeCount > 0 && !sel.isCollapsed) {
        const selected = sel.toString().trim();
        if (selected.length > 0) {
          textFragment = selected;
          // Use selection start to find the most specific anchor element
          const startNode = sel.getRangeAt(0).startContainer;
          const startEl = startNode.nodeType === Node.TEXT_NODE
            ? startNode.parentElement
            : (startNode as HTMLElement);
          target = startEl?.closest("[data-anchor]") || null;
        }
      }

      // Fallback to click target if no text was selected
      if (!target) {
        target = (e.target as HTMLElement).closest("[data-anchor]");
      }

      if (!target) return;
      const anchorId = target.getAttribute("data-anchor");
      if (!anchorId) return;

      e.preventDefault();

      // Determine if this is a blockId anchor or a positional anchor
      const isSubAnchor = anchorId.includes("--");

      let anchorData: Partial<AnchorPoint>;
      // Try positional parse first; if it fails, treat as blockId
      const parsed = !anchorId.startsWith("blk-") && !isSubAnchor ? parseAnchorId(anchorId) : null;
      if (parsed) {
        anchorData = parsed;
      } else if (isSubAnchor) {
        const [bid, ...subParts] = anchorId.split("--");
        anchorData = { blockId: bid, subAnchor: subParts.join("--") };
      } else {
        // Section-level or blk- anchor — store as blockId
        anchorData = { blockId: anchorId };
      }

      // Compute textOffset: char position of the selection within the anchor element's textContent
      let textOffset: number | undefined;
      if (textFragment && target) {
        const sel2 = window.getSelection();
        if (sel2 && sel2.rangeCount > 0) {
          const range = sel2.getRangeAt(0);
          // Create a range from start of anchor element to start of selection
          const preRange = document.createRange();
          preRange.setStart(target, 0);
          preRange.setEnd(range.startContainer, range.startOffset);
          textOffset = preRange.toString().length;
        }
      }
      if (textOffset != null) {
        anchorData.textOffset = textOffset;
      }

      // Derive label: selected text > element's own text > parent box h3 > section title > elementType
      let label = "";
      if (textFragment) {
        label = textFragment.length > 25
          ? textFragment.slice(0, 25) + "..."
          : textFragment;
      }
      if (!label) {
        const summary = target.querySelector("summary");
        if (summary) label = summary.textContent?.trim().replace(/^▶\s*/, "").slice(0, 30) || "";
      }
      if (!label) {
        const innerH3 = target.querySelector("h3");
        if (innerH3) label = innerH3.textContent?.slice(0, 30) || "";
      }
      if (!label) {
        const tag = target.tagName?.toLowerCase();
        if (["p", "li", "ul", "div"].includes(tag)) {
          const text = target.textContent?.trim() || "";
          if (text.length > 0 && text.length < 200) {
            label = text.slice(0, 25) + (text.length > 25 ? "..." : "");
          }
        }
      }
      if (!label) {
        const parentBox = target.closest("[data-anchor^='blk-']") || target.closest("[data-anchor*='content-box']") || target.closest(".mb-4");
        const boxH3 = parentBox?.querySelector("h3");
        if (boxH3) label = boxH3.textContent?.slice(0, 30) || "";
      }
      if (!label) {
        const section = target.closest("section");
        const sectionTitle = section?.querySelector("[class*='border-l-']");
        if (sectionTitle) label = sectionTitle.textContent?.slice(0, 30) || "";
      }
      if (!label) label = anchorData.blockId || anchorData.elementType || "anchor";

      const newAnchor: AnchorPoint = { ...anchorData, label, ...(textFragment ? { textFragment } : {}) } as AnchorPoint;

      // Update local state
      setTodos((prev) =>
        prev.map((t) => {
          if (t.id !== pickingAnchorForId) return t;
          const existing = t.anchor || [];
          // Avoid duplicate
          const newSel = resolveAnchorSelector(newAnchor);
          const dupe = existing.some(
            (a) => resolveAnchorSelector(a) === newSel,
          );
          if (dupe) return t;
          return { ...t, anchor: [...existing, newAnchor] };
        }),
      );

      // Save to API
      const todo = todos.find((t) => t.id === pickingAnchorForId);
      const existing = todo?.anchor || [];
      const updatedAnchors = [
        ...existing,
        newAnchor,
      ];

      fetch("/api/research-todos", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          id: pickingAnchorForId,
          anchor: updatedAnchors,
        }),
      });

      // Flash the picked element
      clearAllHighlights();
      target.classList.add("todo-highlight");
      setTimeout(() => target.classList.remove("todo-highlight"), 1500);

      setPickingAnchorForId(null);
    };

    // Use mouseup so text selection completes before we read it
    document.addEventListener("mouseup", handler, true);
    return () => {
      document.removeEventListener("mouseup", handler, true);
      document.removeEventListener("click", preventToggle, true);
      // Restore <details> to their previous state
      previousState.forEach((wasOpen, d) => {
        if (d.isConnected) d.open = wasOpen;
      });
    };
  }, [pickingAnchorForId, todos]);

  // Group by session_date
  const sessions = todos.reduce<
    Record<string, { label: string; items: TodoItem[] }>
  >((acc, todo) => {
    const key = todo.session_date;
    if (!acc[key]) {
      acc[key] = { label: todo.session_label || key, items: [] };
    }
    acc[key].items.push(todo);
    return acc;
  }, {});

  const sessionDates = Object.keys(sessions).sort((a, b) =>
    b.localeCompare(a),
  );

  // Auto-open first session
  useEffect(() => {
    if (sessionDates.length > 0 && openSessions.size === 0) {
      setOpenSessions(new Set([sessionDates[0]]));
    }
  }, [sessionDates.length]);

  const toggleSession = (date: string) => {
    setOpenSessions((prev) => {
      const next = new Set(prev);
      if (next.has(date)) next.delete(date);
      else next.add(date);
      return next;
    });
  };

  const handleItemClick = (item: TodoItem) => {
    clearAllHighlights();
    if (!item.anchor || item.anchor.length === 0) return;
    setActiveItemId(item.id);
    item.anchor.forEach((a) => scrollToAnchor(a));
    scrollToAnchor(item.anchor[0]);
  };

  const handleAnchorClick = (anchor: AnchorPoint) => {
    clearAllHighlights();
    scrollToAnchor(anchor);
  };

  const handleRemoveAnchor = async (itemId: string, anchorIdx: number) => {
    const todo = todos.find((t) => t.id === itemId);
    if (!todo?.anchor) return;
    const updated = todo.anchor.filter((_, i) => i !== anchorIdx);
    setTodos((prev) =>
      prev.map((t) =>
        t.id === itemId ? { ...t, anchor: updated.length > 0 ? updated : null } : t,
      ),
    );
    await fetch("/api/research-todos", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: itemId, anchor: updated.length > 0 ? updated : null }),
    });
  };

  // Check if a todo item has any broken anchors
  const itemHasBrokenAnchor = useCallback((item: TodoItem) => {
    if (!item.anchor) return false;
    return item.anchor.some((_, idx) => brokenAnchors.has(`${item.id}-${idx}`));
  }, [brokenAnchors]);

  // Stats
  const openCount = todos.filter((t) => t.status === "open").length;
  const doneCount = todos.filter((t) => t.status === "done").length;

  return (
    <>
      {/* Pick-mode overlay hint */}
      {pickingAnchorForId && (
        <div className="fixed inset-x-0 top-0 z-[70] flex items-center justify-center gap-3 bg-amber-500 px-4 py-2 text-sm font-medium text-white shadow-lg">
          <span>
            點擊元素設定 anchor · 或先選取文字再點擊，可標記特定片段
          </span>
          <button
            onClick={() => setPickingAnchorForId(null)}
            className="rounded bg-white/20 px-2 py-0.5 text-xs hover:bg-white/30"
          >
            取消
          </button>
        </div>
      )}

      {/* Toggle tab */}
      <button
        onClick={() => { const next = !isOpen; setIsOpen(next); onToggle?.(next); }}
        className="fixed left-0 top-1/2 z-[60] -translate-y-1/2 rounded-r-lg border border-l-0 border-[var(--border)] bg-[var(--bg-card)] px-1.5 py-4 shadow-md transition-all hover:bg-[var(--bg-subtle)]"
        title={isOpen ? "關閉 To-Do Panel" : "開啟 To-Do Panel"}
      >
        <div className="flex flex-col items-center gap-1.5">
          <span className="text-sm">{isOpen ? "\u25C0" : "\u25B6"}</span>
          <span
            className="text-[0.6rem] font-bold tracking-widest text-[var(--text-muted)]"
            style={{ writingMode: "vertical-rl" }}
          >
            TO-DO
          </span>
          {!isOpen && openCount > 0 && (
            <span className="mt-1 flex h-4 w-4 items-center justify-center rounded-full bg-amber-500 text-[0.55rem] font-bold text-white">
              {openCount}
            </span>
          )}
        </div>
      </button>

      {/* Panel */}
      <div
        data-todo-panel
        className={`fixed left-0 top-0 z-50 h-full border-r border-[var(--border)] bg-[var(--bg)] shadow-xl transition-transform duration-300 ${
          isOpen ? "translate-x-0" : "-translate-x-full"
        }`}
        style={{ width: "340px" }}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-[var(--border)] px-4 py-3">
          <div>
            <h2 className="text-sm font-bold">To-Do Panel</h2>
            <p className="text-[0.65rem] text-[var(--text-muted)]">
              {ticker} · {openCount} open · {doneCount} done
            </p>
          </div>
          <button
            onClick={() => setIsOpen(false)}
            className="rounded p-1 text-[var(--text-muted)] hover:bg-[var(--bg-subtle)] hover:text-[var(--text)]"
          >
            &#10005;
          </button>
        </div>

        {/* Content */}
        <div className="h-[calc(100%-56px)] overflow-y-auto px-3 py-3">
          {loading && (
            <p className="py-8 text-center text-xs text-[var(--text-faint)]">
              載入中...
            </p>
          )}

          {!loading && todos.length === 0 && (
            <p className="py-8 text-center text-xs text-[var(--text-faint)]">
              尚無待辦事項
            </p>
          )}

          {sessionDates.map((date) => {
            const session = sessions[date];
            const isSessionOpen = openSessions.has(date);
            const sessionOpenCount = session.items.filter(
              (t) => t.status === "open",
            ).length;
            const sessionErrorCount = session.items.filter(
              (t) => itemHasBrokenAnchor(t),
            ).length;

            return (
              <div key={date} className="mb-3">
                {/* Session header */}
                <button
                  onClick={() => toggleSession(date)}
                  className="flex w-full items-center justify-between rounded-md px-2 py-2 text-left hover:bg-[var(--bg-subtle)]"
                >
                  <div className="flex items-center gap-2">
                    <span className="text-[0.65rem] text-[var(--text-faint)]">
                      {isSessionOpen ? "\u25BC" : "\u25B6"}
                    </span>
                    <span className="text-xs font-semibold">{date}</span>
                  </div>
                  <div className="flex items-center gap-1.5 text-[0.6rem]">
                    {sessionErrorCount > 0 && (
                      <span className="rounded bg-red-50 border border-red-200 px-1.5 py-0.5 font-medium text-red-600 dark:bg-red-950/40 dark:text-red-400 dark:border-red-800">
                        {sessionErrorCount} error{sessionErrorCount > 1 ? "s" : ""}
                      </span>
                    )}
                    {sessionOpenCount > 0 && (
                      <span className="rounded bg-amber-50 border border-amber-200 px-1.5 py-0.5 font-medium text-amber-600 dark:bg-amber-950/40 dark:text-amber-400 dark:border-amber-800">
                        {sessionOpenCount} open
                      </span>
                    )}
                    <span className="text-[var(--text-faint)]">
                      {session.items.length} total
                    </span>
                  </div>
                </button>

                {/* Items */}
                {isSessionOpen && (
                  <div className="ml-2 mt-1 space-y-1 border-l-2 border-[var(--border)] pl-3">
                    {session.items.map((item) => {
                      const hasAnchor =
                        item.anchor && item.anchor.length > 0;
                      const isActive = activeItemId === item.id;
                      const isPicking = pickingAnchorForId === item.id;
                      const hasBroken = itemHasBrokenAnchor(item);

                      return (
                        <div
                          key={item.id}
                          className={`rounded-md border px-3 py-2 transition-colors ${
                            hasBroken
                              ? "border-red-300 bg-red-50/50 dark:border-red-800 dark:bg-red-950/20"
                              : isPicking
                                ? "border-amber-400 bg-amber-50/50 dark:bg-amber-950/20"
                                : isActive
                                  ? "border-[var(--primary)] bg-[var(--bg-highlight)]"
                                  : "border-transparent hover:bg-[var(--bg-subtle)]"
                          } ${hasAnchor ? "cursor-pointer" : "cursor-default"}`}
                          onClick={() =>
                            hasAnchor && !isPicking && handleItemClick(item)
                          }
                        >
                          <div className="flex items-start gap-2">
                            <button
                              className="mt-0.5 shrink-0 hover:opacity-70"
                              title={item.status === "done" ? "標記為未完成" : "標記為完成"}
                              onClick={(e) => {
                                e.stopPropagation();
                                const newStatus = item.status === "done" ? "open" : "done";
                                setTodos((prev) =>
                                  prev.map((t) =>
                                    t.id === item.id ? { ...t, status: newStatus } : t
                                  )
                                );
                                fetch("/api/research-todos", {
                                  method: "PATCH",
                                  headers: { "Content-Type": "application/json" },
                                  body: JSON.stringify({ id: item.id, status: newStatus }),
                                });
                              }}
                            >
                              <StatusIcon status={item.status} />
                            </button>
                            <div className="min-w-0 flex-1">
                              {/* Title with tooltip */}
                              <Tooltip text={item.content}>
                                <span
                                  className={`text-xs font-medium ${
                                    hasBroken
                                      ? "text-red-600 dark:text-red-400"
                                      : item.status === "done"
                                        ? "text-[var(--text-muted)] line-through"
                                        : item.status === "archived"
                                          ? "text-[var(--text-faint)]"
                                          : ""
                                  }`}
                                >
                                  {item.title}
                                </span>
                              </Tooltip>

                              <div className="mt-1 flex items-center gap-1.5">
                                <CategoryBadge category={item.category} />
                                {hasAnchor && (
                                  <span className="text-[0.6rem] text-[var(--text-faint)]">
                                    {item.anchor!.length} anchor
                                    {item.anchor!.length > 1 ? "s" : ""}
                                  </span>
                                )}
                                {/* Add anchor button */}
                                {!lockedItems.has(item.id) && (
                                  <button
                                    className="ml-auto rounded px-1 py-0.5 text-[0.6rem] text-[var(--text-faint)] hover:bg-[var(--bg-subtle)] hover:text-[var(--primary)]"
                                    title="新增 anchor（點擊後在頁面上選取元素）"
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      setPickingAnchorForId(
                                        isPicking ? null : item.id,
                                      );
                                    }}
                                  >
                                    {isPicking ? "選取中..." : "+ anchor"}
                                  </button>
                                )}
                              </div>

                              {/* Anchors list */}
                              {isActive &&
                                item.anchor &&
                                item.anchor.length > 0 && (
                                  <div className="mt-1.5 space-y-0.5">
                                    {/* Lock toggle */}
                                    {item.anchor.length > 0 && (
                                      <button
                                        className="mb-0.5 flex items-center gap-1 rounded px-1.5 py-0.5 text-[0.6rem] text-[var(--text-faint)] hover:text-[var(--text-muted)]"
                                        title={lockedItems.has(item.id) ? "解鎖 anchor（允許刪除）" : "鎖定 anchor（防止誤刪）"}
                                        onClick={(e) => {
                                          e.stopPropagation();
                                          const newLocked = !item.anchor_locked;
                                          setTodos((prev) =>
                                            prev.map((t) =>
                                              t.id === item.id ? { ...t, anchor_locked: newLocked } : t
                                            )
                                          );
                                          fetch("/api/research-todos", {
                                            method: "PATCH",
                                            headers: { "Content-Type": "application/json" },
                                            body: JSON.stringify({ id: item.id, anchor_locked: newLocked }),
                                          });
                                        }}
                                      >
                                        <span>{lockedItems.has(item.id) ? "\uD83D\uDD12" : "\uD83D\uDD13"}</span>
                                        <span>{lockedItems.has(item.id) ? "已鎖定" : "未鎖定"}</span>
                                      </button>
                                    )}
                                    {item.anchor.map((a, ai) => {
                                      const isBroken = brokenAnchors.has(`${item.id}-${ai}`);
                                      const brokenTooltip = isBroken
                                        ? `⚠️ 找不到目標元素\n原始標記：${a.textFragment || a.label || "N/A"}\nanchor: ${resolveAnchorSelector(a) || "unknown"}`
                                        : null;
                                      return (
                                      <div
                                        key={ai}
                                        className="group flex items-center gap-1"
                                      >
                                        <Tooltip text={isBroken ? brokenTooltip : null}>
                                        <button
                                          className={`flex flex-1 items-center gap-1.5 rounded px-1.5 py-0.5 text-left text-[0.65rem] ${
                                            isBroken
                                              ? "border border-red-300 bg-red-50 text-red-600 dark:border-red-800 dark:bg-red-950 dark:text-red-400"
                                              : "text-[var(--text-muted)] hover:bg-[var(--bg-subtle)] hover:text-[var(--primary)]"
                                          }`}
                                          onClick={(e) => {
                                            e.stopPropagation();
                                            if (!isBroken) handleAnchorClick(a);
                                          }}
                                        >
                                          <span>{isBroken ? "\u26A0\uFE0F" : "\uD83D\uDCCD"}</span>
                                          <span>
                                            {a.label ||
                                              `\u00A7${a.sectionId} · ${a.elementType}`}
                                          </span>
                                        </button>
                                        </Tooltip>
                                        {lockedItems.has(item.id) ? (
                                          <span className="px-1 text-[0.6rem] text-[var(--text-faint)]">
                                            &#128274;
                                          </span>
                                        ) : (
                                          <button
                                            className="hidden rounded px-1 text-[0.6rem] text-[var(--text-faint)] hover:text-red-500 group-hover:block"
                                            title="移除此 anchor"
                                            onClick={(e) => {
                                              e.stopPropagation();
                                              handleRemoveAnchor(item.id, ai);
                                            }}
                                          >
                                            &#10005;
                                          </button>
                                        )}
                                      </div>
                                      );
                                    })}
                                  </div>
                                )}

                              {/* Response preview for done/archived */}
                              {item.response && isActive && (
                                <p className="mt-1.5 text-[0.65rem] leading-relaxed text-[var(--text-muted)]">
                                  {item.response.length > 120
                                    ? item.response.slice(0, 120) + "..."
                                    : item.response}
                                </p>
                              )}
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </>
  );
}
