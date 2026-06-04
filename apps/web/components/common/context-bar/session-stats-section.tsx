"use client";

/**
 * SessionStatsSection — 抽屉内的"本次会话统计"插槽
 *
 * 设计目的：证明 ContextBar 插槽模式可扩展
 * 数据源：agent-store.sessionStats（由 useChatStream 增量更新）
 * 零 props：完全自包含，可直接挂载
 *
 * 展示：
 *  - 消息数 / 工具调用次数 / 数据卡片数
 *  - 时长（首条消息至今）
 *  - 用过的工具列表（去重）
 */

import { useEffect, useState } from "react";
import { Activity, MessageSquare, Wrench, BarChart3, Clock } from "lucide-react";
import { useAgentStore } from "@/stores/agent-store";

function formatDuration(ms: number): string {
  if (ms < 1000) return "刚刚";
  if (ms < 60_000) return `${Math.floor(ms / 1000)}秒`;
  if (ms < 3_600_000) return `${Math.floor(ms / 60_000)}分钟`;
  return `${Math.floor(ms / 3_600_000)}小时`;
}

export function SessionStatsSection() {
  const stats = useAgentStore((s) => s.sessionStats);
  const cardCount = useAgentStore((s) => s.dataCards.length);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!stats.startedAt) return;
    const id = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(id);
  }, [stats.startedAt]);

  if (stats.messageCount === 0) return null;

  const duration = stats.startedAt
    ? formatDuration(now - new Date(stats.startedAt).getTime())
    : "—";

  const usedTools = Array.from(new Set(stats.usedTools));

  return (
    <section
      className="rounded-lg border bg-card/50 p-3 mb-3 space-y-3"
      aria-label="本次会话统计"
    >
      <div className="flex items-center gap-1.5">
        <Activity className="h-3.5 w-3.5 text-primary" />
        <p className="text-xs font-semibold text-foreground">本次会话</p>
      </div>

      <div className="grid grid-cols-3 gap-2">
        <div className="rounded-md bg-muted px-2 py-1.5 text-center">
          <MessageSquare className="h-3 w-3 mx-auto text-muted-foreground" />
          <div className="text-sm font-semibold mt-0.5">
            {stats.messageCount}
          </div>
          <div className="text-[10px] text-muted-foreground">消息</div>
        </div>
        <div className="rounded-md bg-muted px-2 py-1.5 text-center">
          <Wrench className="h-3 w-3 mx-auto text-muted-foreground" />
          <div className="text-sm font-semibold mt-0.5">
            {stats.toolCallCount}
          </div>
          <div className="text-[10px] text-muted-foreground">工具</div>
        </div>
        <div className="rounded-md bg-muted px-2 py-1.5 text-center">
          <BarChart3 className="h-3 w-3 mx-auto text-muted-foreground" />
          <div className="text-sm font-semibold mt-0.5">{cardCount}</div>
          <div className="text-[10px] text-muted-foreground">卡片</div>
        </div>
      </div>

      <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
        <Clock className="h-3 w-3 shrink-0" />
        <span>时长 {duration}</span>
        {usedTools.length > 0 && (
          <>
            <span className="text-muted-foreground/40">·</span>
            <span className="truncate" title={usedTools.join(", ")}>
              {usedTools.slice(0, 3).join("、")}
              {usedTools.length > 3 && ` +${usedTools.length - 3}`}
            </span>
          </>
        )}
      </div>
    </section>
  );
}
