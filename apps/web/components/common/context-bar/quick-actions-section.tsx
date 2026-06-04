"use client";

/**
 * QuickActionsSection — 抽屉底部快捷操作
 *
 * 设计：纯展示可点击 chip，用户能直接触发常用操作
 *  - 复制当前话题为查询（在助手页打开新消息）
 *  - 导出数据卡片为 JSON
 *  - 清空全部
 */

import { useState } from "react";
import { Copy, Download, Trash2, Check } from "lucide-react";
import { useAgentStore } from "@/stores/agent-store";

export function QuickActionsSection() {
  const context = useAgentStore((s) => s.currentContext);
  const cards = useAgentStore((s) => s.dataCards);
  const [copied, setCopied] = useState(false);

  const copyTopic = async () => {
    if (!context.recentTopic) return;
    try {
      await navigator.clipboard.writeText(context.recentTopic);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* noop */
    }
  };

  const exportCards = () => {
    if (cards.length === 0) return;
    const data = JSON.stringify(cards, null, 2);
    const blob = new Blob([data], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `context-cards-${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <section
      className="rounded-lg border bg-card/50 p-3 mb-3"
      aria-label="快捷操作"
    >
      <div className="flex flex-wrap gap-1.5">
        <button
          onClick={copyTopic}
          disabled={!context.recentTopic}
          className="flex items-center gap-1 rounded-md border bg-background px-2 py-1 text-[11px] hover:bg-accent transition-colors disabled:opacity-50"
          title="复制当前话题到剪贴板"
        >
          {copied ? <Check className="h-3 w-3 text-green-500" /> : <Copy className="h-3 w-3" />}
          {copied ? "已复制" : "复制话题"}
        </button>
        <button
          onClick={exportCards}
          disabled={cards.length === 0}
          className="flex items-center gap-1 rounded-md border bg-background px-2 py-1 text-[11px] hover:bg-accent transition-colors disabled:opacity-50"
          title="导出为 JSON"
        >
          <Download className="h-3 w-3" />
          导出 JSON
        </button>
        <button
          onClick={() => useAgentStore.getState().clearCards()}
          disabled={cards.length === 0}
          className="flex items-center gap-1 rounded-md border bg-background px-2 py-1 text-[11px] hover:bg-destructive/10 hover:text-destructive transition-colors disabled:opacity-50"
          title="清空所有数据卡片"
        >
          <Trash2 className="h-3 w-3" />
          清空
        </button>
      </div>
    </section>
  );
}
