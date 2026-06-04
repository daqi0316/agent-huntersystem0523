"use client";

/**
 * MemoryPanel — 提取自 agent/page.tsx（原 line 175-266）
 * 行为完全保留：展示用户的结构化记忆事实（PG memory_facts 表）。
 * 共存：与其他 panel 独立，不进缩略按钮。
 */

import { useState, useEffect } from "react";
import { Brain, X, Loader2 } from "lucide-react";
import { api } from "@/lib/trpc";
import type { MemoryFact } from "@/types/chat";

const FACT_TYPE_LABELS: Record<string, string> = {
  candidate_action: "候选人操作",
  decision: "决策",
  preference: "偏好设置",
  workflow_state: "流程状态",
  agent_action: "系统操作",
};

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "刚刚";
  if (mins < 60) return `${mins}分钟前`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}小时前`;
  return `${Math.floor(hrs / 24)}天前`;
}

export function MemoryPanel({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const [facts, setFacts] = useState<MemoryFact[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    api
      .post<{ success: boolean; facts: MemoryFact[] }>("/memory/facts", {
        user_id: "default",
        limit: 50,
      })
      .then((data) => setFacts(data.facts || []))
      .catch(() => setFacts([]))
      .finally(() => setLoading(false));
  }, [open]);

  const grouped = facts.reduce<Record<string, MemoryFact[]>>((acc, f) => {
    const key = f.fact_type || "other";
    if (!acc[key]) acc[key] = [];
    acc[key].push(f);
    return acc;
  }, {});

  return (
    <div
      className={`fixed inset-y-0 right-0 z-50 w-80 bg-background border-l shadow-xl transform transition-transform ${
        open ? "translate-x-0" : "translate-x-full"
      }`}
    >
      <div className="flex items-center justify-between border-b px-4 py-3">
        <div className="flex items-center gap-2">
          <Brain className="h-4 w-4 text-primary" />
          <h2 className="text-sm font-semibold">结构化记忆</h2>
        </div>
        <button
          onClick={onClose}
          className="rounded-md p-1 hover:bg-accent transition-colors"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
      <div className="overflow-y-auto h-[calc(100vh-4rem)] p-4 space-y-4">
        {loading && (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        )}
        {!loading && facts.length === 0 && (
          <p className="text-sm text-muted-foreground text-center py-8">
            暂无记忆
          </p>
        )}
        {!loading &&
          Object.entries(grouped).map(([type, items]) => (
            <div key={type}>
              <h3 className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-2">
                {FACT_TYPE_LABELS[type] || type}
              </h3>
              <div className="space-y-2">
                {items.map((f) => (
                  <div
                    key={f.id}
                    className="rounded-lg border p-3 text-xs space-y-1"
                  >
                    <p className="font-medium text-foreground">{f.verb}</p>
                    {f.object_value &&
                      Object.entries(f.object_value)
                        .slice(0, 3)
                        .map(([k, v]) => (
                          <p key={k} className="text-muted-foreground">
                            {k}:{" "}
                            {typeof v === "object"
                              ? JSON.stringify(v)
                              : String(v)}
                          </p>
                        ))}
                    <p className="text-[10px] text-muted-foreground/60">
                      {timeAgo(f.created_at)}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          ))}
      </div>
    </div>
  );
}
