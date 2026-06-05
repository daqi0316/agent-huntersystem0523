"use client";

/**
 * ContextBar — 右上角缩略按钮 + 抽屉
 *
 * Phase 1: 单个缩略按钮 + 抽屉 + DataCardItem
 * Phase 2: 接入 currentContext，显示"正在讨论 X" + 上次工具
 * Phase 3: ⌘K / Ctrl+K 全局快捷键 + Esc 关闭 + 焦点管理 + a11y
 *
 * 行为：
 *  - ⌘K (Mac) / Ctrl+K (Win/Linux) 全局打开抽屉
 *  - Esc 关闭抽屉
 *  - 打开时 focus 移到关闭按钮；关闭时还原 focus
 *  - 抽屉关闭不丢状态：缩略按钮常驻
 *  - MemoryPanel / OperationPanel / CommandPalette 仍由 /agent 页面独立控制
 *    （用户明确要求「共存」，不并入 ContextBar）
 *
 * 数据流：
 *  agent-store.dataCards       → 缩略按钮徽章
 *  agent-store.currentContext  → 话题指示
 *  抽屉点击 DataCardItem        → markCardRead
 */

import { useState, useMemo, useRef, useEffect, useCallback } from "react";
import {
  useAgentStore,
  selectUnreadCardCount,
  getTelemetryQueue,
  type DataCard,
  type DataCardType,
} from "@ai-recruitment/agent-store";
import { useGlobalShortcut } from "./use-global-shortcut";
import { useCardOrderHash, applyHashOrder } from "./use-card-order-hash";
import { useCardKeyboardNav } from "./use-card-keyboard-nav";
import { buildExportPayload, downloadJson } from "./export-cards";
import { ContextChip } from "./context-chip";
import { ContextDrawer } from "./context-drawer";
import { DataCardItem } from "./data-card-item";
import { CurrentContextSection } from "./current-context-section";
import { SessionStatsSection } from "./session-stats-section";
import { RecentActivitySection } from "./recent-activity-section";
import { PendingApprovalSection } from "./pending-approval-section";
import { QuickActionsSection } from "./quick-actions-section";
import { SearchBar, filterCards, EMPTY_FILTERS } from "./search-bar";
import { NotificationsSection } from "./notifications/notifications-section";

const TOOL_LABELS: Record<string, string> = {
  get_dashboard_stats: "看板数据",
  search_candidates: "搜索候选人",
  screen_resume: "简历评估",
  generate_jd: "生成 JD",
  schedule_interview: "安排面试",
  get_schedule: "查询日程",
  get_upcoming_interviews: "即将面试",
  create_candidate: "创建候选人",
  update_candidate: "更新候选人",
  archive_candidate: "归档候选人",
  create_job: "创建职位",
  update_job: "更新职位",
  close_job: "关闭职位",
  cancel_interview: "取消面试",
  reschedule_interview: "改期面试",
  save_evaluation: "保存评估",
};

function toolLabel(name: string | undefined): string {
  if (!name) return "";
  return TOOL_LABELS[name] || name;
}

export interface ContextBarProps {
  onApprovalApprove?: (approvalId: string) => Promise<string | void>;
  onApprovalReject?: (approvalId: string) => Promise<void> | void;
}

export function ContextBar({
  onApprovalApprove,
  onApprovalReject,
}: ContextBarProps = {}) {
  const cards = useAgentStore((s) => s.dataCards);
  const unreadCount = useAgentStore(selectUnreadCardCount);
  const context = useAgentStore((s) => s.currentContext);
  const [open, setOpen] = useState(false);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [activeTypes, setActiveTypes] = useState<DataCardType[]>([]);
  const [keyboardIndex, setKeyboardIndex] = useState(0);

  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const lastFocusedRef = useRef<HTMLElement | null>(null);

  // T5: URL hash ↔ sort order 同步（跨 tab 共享 sort 顺序）
  const { hashOrder, setOrder, clearOrder } = useCardOrderHash();

  const sortedCards = useMemo(
    () => applyHashOrder(cards, hashOrder),
    [cards, hashOrder]
  );

  const filteredCards = useMemo(
    () => filterCards(sortedCards, { query, types: activeTypes }),
    [sortedCards, query, activeTypes]
  );

  const activeCard = useMemo<DataCard | null>(() => {
    if (!activeId) return null;
    return cards.find((c) => c.id === activeId) ?? null;
  }, [activeId, cards]);

  // T5: 拖拽后写 URL hash（仅当顺序真变化时）
  const handleDrop = useCallback(
    (targetId: string) => (e: React.DragEvent) => {
      e.preventDefault();
      const sourceId = e.dataTransfer.getData("text/plain");
      if (!sourceId || sourceId === targetId) {
        setDraggingId(null);
        setDragOverId(null);
        return;
      }
      const next = [...sortedCards];
      const srcIdx = next.findIndex((c) => c.id === sourceId);
      const dstIdx = next.findIndex((c) => c.id === targetId);
      if (srcIdx < 0 || dstIdx < 0) return;
      const [moved] = next.splice(srcIdx, 1);
      next.splice(dstIdx, 0, moved);
      useAgentStore.setState({ dataCards: next });
      setOrder(next.map((c) => c.id));
      setDraggingId(null);
      setDragOverId(null);
      getTelemetryQueue().track("drag_drop", {
        card_type: moved.type,
        success: true,
      });
      getTelemetryQueue().track("hash_order_change", {
        card_type: moved.type,
        success: true,
      });
    },
    [sortedCards, setOrder]
  );

  // T5: 拖到 body 外部 = 不更新 order（即回滚；React 不触发 onDrop）
  // 已通过 React 行为天然处理；显式 dragend 清理视觉状态
  const handleDragEnd = useCallback(() => {
    setDraggingId(null);
    setDragOverId(null);
  }, []);

  // T5: ⌘↑/↓ 键盘上下选 + Enter 展开
  useCardKeyboardNav({
    enabled: open && (query.length > 0 || activeTypes.length > 0),
    cards: filteredCards,
    activeIndex: keyboardIndex,
    onActiveIndexChange: setKeyboardIndex,
    onActivate: (id) => {
      const card = cards.find((c) => c.id === id);
      if (card) {
        useAgentStore.getState().markCardRead(card.id);
        setActiveId(card.id);
        getTelemetryQueue().track("keyboard_nav", {
          card_type: card.type,
          success: true,
        });
      }
    },
  });

  // T5: 导出 JSON
  const handleExport = useCallback(() => {
    const payload = buildExportPayload(
      filteredCards,
      sortedCards.map((c) => c.id),
      { query, types: activeTypes }
    );
    downloadJson(payload);
    getTelemetryQueue().track("card_export", {
      card_type: filteredCards[0]?.type ?? "none",
      result_count: filteredCards.length,
      success: true,
    });
  }, [filteredCards, sortedCards, query, activeTypes]);

  const chipTitle = context.recentTopic
    ? `数据看板 · ${unreadCount} 项未读 · 当前讨论：${context.recentTopic}`
    : `数据看板 · ${unreadCount} 项未读`;

  const drawerSubtitle = useMemo(() => {
    const parts: string[] = [];
    if (context.recentTopic) parts.push(context.recentTopic);
    if (context.lastToolUsed) parts.push(`上次：${toolLabel(context.lastToolUsed)}`);
    if (context.currentCandidateIds.length > 0) {
      parts.push(`${context.currentCandidateIds.length} 候选人`);
    }
    if (context.currentJobIds.length > 0) {
      parts.push(`${context.currentJobIds.length} 职位`);
    }
    return parts.join(" · ");
  }, [context]);

  const openDrawer = useCallback(() => {
    if (open) return;
    lastFocusedRef.current = document.activeElement as HTMLElement | null;
    setOpen(true);
  }, [open]);

  useEffect(() => {
    if (!open) {
      setQuery("");
      setActiveTypes([]);
    }
  }, [open]);

  const [draggingId, setDraggingId] = useState<string | null>(null);
  const [dragOverId, setDragOverId] = useState<string | null>(null);

  const handleDragStart = useCallback((id: string) => (e: React.DragEvent) => {
    setDraggingId(id);
    e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.setData("text/plain", id);
  }, []);

  const handleDragOver = useCallback((id: string) => (e: React.DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    setDragOverId(id);
  }, []);

  const closeDrawer = useCallback(() => {
    if (!open) return;
    setOpen(false);
    setActiveId(null);
    requestAnimationFrame(() => {
      lastFocusedRef.current?.focus();
    });
  }, [open]);

  useGlobalShortcut("k", openDrawer, { mod: true });
  useGlobalShortcut("escape", closeDrawer);

  useEffect(() => {
    if (open) {
      getTelemetryQueue().track("drawer_open", { source: "chip" });
    }
  }, [open]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const start = window.performance.now();
    return () => {
      if (!open) return;
      const duration = Math.round(window.performance.now() - start);
      getTelemetryQueue().track("drawer_close", { duration_ms: duration });
    };
  }, [open]);

  useEffect(() => {
    if (!query && activeTypes.length === 0) return;
    getTelemetryQueue().track("search_use", {
      result_count: filteredCards.length,
      source: activeTypes.length > 0 ? "filter" : "query",
    });
  }, [query, activeTypes, filteredCards.length]);

  useEffect(() => {
    if (open) {
      requestAnimationFrame(() => {
        closeButtonRef.current?.focus();
      });
      useAgentStore.getState().markAllCardsRead();
    }
  }, [open]);

  return (
    <>
      <ContextChip
        unreadCount={unreadCount}
        onClick={openDrawer}
        active={open}
        title={chipTitle}
        subtitle={context.recentTopic}
      />
      <ContextDrawer
        open={open}
        onClose={closeDrawer}
        title="数据看板"
        subtitle={drawerSubtitle}
        closeButtonRef={closeButtonRef}
        footer={
          cards.length > 0 ? (
            <div className="flex items-center justify-between w-full">
              <button
                onClick={handleExport}
                className="text-xs text-muted-foreground hover:text-foreground transition-colors"
                aria-label="导出 JSON"
              >
                导出 JSON
              </button>
              <button
                onClick={() => useAgentStore.getState().clearCards()}
                className="text-xs text-muted-foreground hover:text-destructive transition-colors"
              >
                清空全部
              </button>
            </div>
          ) : null
        }
      >
        <CurrentContextSection context={context} />
        <NotificationsSection />
        <PendingApprovalSection
          onApprove={onApprovalApprove}
          onReject={onApprovalReject}
        />
        <SessionStatsSection />
        <RecentActivitySection />
        <QuickActionsSection />
        {sortedCards.length > 0 && (
          <SearchBar
            query={query}
            onQueryChange={setQuery}
            activeTypes={activeTypes}
            onActiveTypesChange={setActiveTypes}
            resultCount={filteredCards.length}
            totalCount={sortedCards.length}
          />
        )}
        {sortedCards.length === 0 && !context.recentTopic ? (
          <div className="flex flex-col items-center justify-center h-full text-center text-muted-foreground">
            <p className="text-sm">暂无数据卡片</p>
            <p className="text-xs mt-1">
              在助手中询问「看板概览」「搜索候选人」等，会自动归档
            </p>
            <p className="text-[10px] mt-3 text-muted-foreground/60">
              快捷键：⌘K 打开 · Esc 关闭
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            {filteredCards.map((c) => (
              <DataCardItem
                key={c.id}
                card={c}
                active={c.id === activeId}
                onClick={() => {
                  setActiveId(c.id);
                  useAgentStore.getState().markCardRead(c.id);
                }}
                expanded={c.id === activeId}
                draggable
                onDragStart={handleDragStart(c.id)}
                onDragOver={handleDragOver(c.id)}
                onDrop={handleDrop(c.id)}
                onDragEnd={handleDragEnd}
                isDragOver={dragOverId === c.id && draggingId !== c.id}
              />
            ))}
            {filteredCards.length === 0 && sortedCards.length > 0 && (
              <div className="text-center text-xs text-muted-foreground py-4">
                没有匹配的卡片
              </div>
            )}
            {sortedCards.length === 0 && context.recentTopic && (
              <div className="text-center text-xs text-muted-foreground py-4">
                本轮对话尚未产生数据卡片
              </div>
            )}
          </div>
        )}
      </ContextDrawer>
      {activeCard && <div className="hidden">{activeCard.id}</div>}
    </>
  );
}
