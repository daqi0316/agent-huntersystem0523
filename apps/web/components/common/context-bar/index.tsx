"use client";

/**
 * ContextBar — 右上角缩略按钮 + 抽屉
 *
 * Phase 1: 单个缩略按钮 + 抽屉 + DataCardItem
 * Phase 2: 接入 currentContext，显示"正在讨论 X" + 上次工具
 *
 * 行为：
 *  - 缩略按钮「📊 数据看板 · N 项」徽章显示未读 dataCards 数
 *  - tooltip 显示 currentContext.recentTopic（最近讨论话题）
 *  - 抽屉头部显示 currentTopic + lastToolUsed
 *  - 抽屉关闭不丢状态：缩略按钮常驻
 *  - MemoryPanel / OperationPanel / CommandPalette 仍由 /agent 页面独立控制
 *    （用户明确要求「共存」，不并入 ContextBar）
 *
 * 数据流：
 *  agent-store.dataCards       → 缩略按钮徽章
 *  agent-store.currentContext  → 话题指示
 *  抽屉点击 DataCardItem        → markCardRead
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

export function ContextBar() {
  const cards = useAgentStore((s) => s.dataCards);
  const unreadCount = useAgentStore(selectUnreadCardCount);
  const context = useAgentStore((s) => s.currentContext);
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

  return (
    <>
      <ContextChip
        unreadCount={unreadCount}
        onClick={() => setOpen((v) => !v)}
        active={open}
        title={chipTitle}
        subtitle={context.recentTopic}
      />
      <ContextDrawer
        open={open}
        onClose={() => setOpen(false)}
        title="数据看板"
        subtitle={drawerSubtitle}
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
      {activeCard && <div className="hidden">{activeCard.id}</div>}
    </>
  );
}
