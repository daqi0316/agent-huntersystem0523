"use client";

/**
 * RecentActivitySection — 抽屉内"最近活动"时间线插槽
 *
 * 数据源：agent-store 变化历史
 *  - 派生自：addCard 触发 + recordMessage / recordToolCall 触发
 *  - 保留最近 N 条活动
 *
 * 展示：垂直时间线（最新在上）
 *  - 💬 发送消息
 *  - 🔧 工具调用（get_dashboard_stats 等）
 *  - 📊 数据卡片产生
 *
 * 设计：纯展示，不交互（避免与 DataCardItem 重复）
 */

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { History, MessageSquare, Wrench, BarChart3 } from "lucide-react";
import { useAgentStore } from "@ai-recruitment/agent-store";
import { TOOL_LABELS, toolLabel } from "@ai-recruitment/agent-store/tool-labels";

const MAX_ITEMS = 8;

function formatRelative(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  if (diff < 60_000) return "刚刚";
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}分钟前`;
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}小时前`;
  return `${Math.floor(diff / 86_400_000)}天前`;
}

interface ActivityItem {
  id: string;
  kind: "message" | "tool" | "card";
  label: string;
  detail?: string;
  at: string;
  focusKey?: string;
}

export function RecentActivitySection() {
  const cards = useAgentStore((s) => s.dataCards);
  const stats = useAgentStore((s) => s.sessionStats);
  const router = useRouter();
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 60_000);
    return () => clearInterval(id);
  }, []);

  const handleItemClick = (item: ActivityItem) => {
    if (!item.focusKey) return;
    router.push(`/agent?focus=${encodeURIComponent(item.focusKey)}`);
  };

  if (stats.messageCount === 0) return null;

  const items: ActivityItem[] = [];

  for (const c of cards.slice(0, MAX_ITEMS)) {
    items.push({
      id: `card-${c.id}`,
      kind: "card",
      label: c.title || "数据卡片",
      detail: c.toolName ? toolLabel(c.toolName) : undefined,
      at: c.createdAt,
      focusKey: c.messageId || `card-${c.id}`,
    });
  }

  if (stats.startedAt) {
    items.push({
      id: "session-start",
      kind: "message",
      label: "会话开始",
      at: stats.startedAt,
    });
  }

  items.sort((a, b) => b.at.localeCompare(a.at));
  const display = items.slice(0, MAX_ITEMS);

  return (
    <section
      className="rounded-lg border bg-card/50 p-3 mb-3"
      aria-label="最近活动"
    >
      <div className="flex items-center gap-1.5 mb-2">
        <History className="h-3.5 w-3.5 text-primary" />
        <p className="text-xs font-semibold text-foreground">最近活动</p>
      </div>

      <ul className="space-y-1.5">
        {display.map((item) => {
          const clickable = Boolean(item.focusKey);
          const ButtonTag = clickable ? "button" : "div";
          return (
            <li
              key={item.id}
              data-now={now}
            >
              <ButtonTag
                type={clickable ? "button" : undefined}
                onClick={clickable ? () => handleItemClick(item) : undefined}
                aria-label={clickable ? `跳转到 ${item.label}` : item.label}
                className={
                  clickable
                    ? "flex w-full items-start gap-2 rounded text-left text-[11px] px-1 py-0.5 hover:bg-muted/60 transition-colors"
                    : "flex w-full items-start gap-2 text-[11px] px-1 py-0.5"
                }
              >
                <div className="mt-0.5 shrink-0">
                  {item.kind === "message" && (
                    <MessageSquare className="h-3 w-3 text-muted-foreground" />
                  )}
                  {item.kind === "tool" && (
                    <Wrench className="h-3 w-3 text-muted-foreground" />
                  )}
                  {item.kind === "card" && (
                    <BarChart3 className="h-3 w-3 text-primary" />
                  )}
                </div>
                <div className="flex-1 min-w-0 flex items-center justify-between gap-2">
                  <div className="min-w-0 truncate">
                    <span className="text-foreground">{item.label}</span>
                    {item.detail && (
                      <span className="text-muted-foreground ml-1">
                        · {item.detail}
                      </span>
                    )}
                  </div>
                  <span className="text-[10px] text-muted-foreground/70 shrink-0">
                    {formatRelative(item.at)}
                  </span>
                </div>
              </ButtonTag>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
