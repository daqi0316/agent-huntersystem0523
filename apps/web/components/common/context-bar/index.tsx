"use client";

/**
 * ContextBar — 右上角缩略按钮 + 抽屉（Phase 1 主交付）
 *
 * 行为：
 *  - 单个缩略按钮「📊 数据看板 · N 项」，徽章显示未读 dataCards 数
 *  - 点击展开右侧抽屉（z-40），按时间倒序展示所有 DataCard
 *  - 抽屉关闭不丢状态：缩略按钮常驻
 *  - MemoryPanel / OperationPanel / CommandPalette 仍由 /agent 页面独立控制
 *    （用户明确要求「共存」，不并入 ContextBar）
 *
 * 数据流：
 *  agent-store.dataCards → selectUnreadCardCount / selectLatestCards → ContextBar
 *  抽屉点击 DataCardItem → markCardRead
 */

import { useState, useMemo } from "react";
import {
  useAgentStore,
  selectUnreadCardCount,
  type DataCard,
} from "@/stores/agent-store";
import { ContextChip } from "./context-chip";
import { ContextDrawer } from "./context-drawer";
import { DataCardItem } from "./data-card-item";

export function ContextBar() {
  const cards = useAgentStore((s) => s.dataCards);
  const unreadCount = useAgentStore(selectUnreadCardCount);
  const [open, setOpen] = useState(false);
  const [activeId, setActiveId] = useState<string | null>(null);

  const sortedCards = useMemo(
    () => [...cards].sort((a, b) => b.createdAt.localeCompare(a.createdAt)),
    [cards]
  );

  const activeCard = useMemo<DataCard | null>(() => {
    if (!activeId) return null;
    return cards.find((c) => c.id === activeId) ?? null;
  }, [activeId, cards]);

  return (
    <>
      <ContextChip
        unreadCount={unreadCount}
        onClick={() => setOpen((v) => !v)}
        active={open}
      />
      <ContextDrawer
        open={open}
        onClose={() => setOpen(false)}
        title="数据看板"
        footer={
          cards.length > 0 ? (
            <button
              onClick={() => useAgentStore.getState().clearCards()}
              className="text-xs text-muted-foreground hover:text-destructive transition-colors"
            >
              清空全部
            </button>
          ) : null
        }
      >
        {sortedCards.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center text-muted-foreground">
            <p className="text-sm">暂无数据卡片</p>
            <p className="text-xs mt-1">
              在助手中询问「看板概览」「搜索候选人」等，会自动归档
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            {sortedCards.map((c) => (
              <DataCardItem
                key={c.id}
                card={c}
                active={c.id === activeId}
                onClick={() => {
                  setActiveId(c.id);
                  useAgentStore.getState().markCardRead(c.id);
                }}
                expanded={c.id === activeId}
              />
            ))}
          </div>
        )}
      </ContextDrawer>
      {activeCard && (
        <div className="hidden">{activeCard.id}</div>
      )}
    </>
  );
}
