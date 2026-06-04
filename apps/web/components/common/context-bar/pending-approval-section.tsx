"use client";

/**
 * PendingApprovalSection — 当前审批请求抽屉内展示
 *
 * 价值：让审批状态跨页面可见
 *  - /agent 页面有 banner 提示
 *  - 其它 dashboard 页面（如 /candidates）只能从抽屉看到
 *
 * 数据源：agent-store.approval
 */

import { useState } from "react";
import { AlertCircle, Check, XCircle, Loader2 } from "lucide-react";
import { useAgentStore } from "@/stores/agent-store";
import { api } from "@/lib/trpc";

export function PendingApprovalSection() {
  const approval = useAgentStore((s) => s.approval);
  const [busy, setBusy] = useState(false);

  if (!approval.visible) return null;

  const handleAction = async (approve: boolean) => {
    if (!approval.approval_id || busy) return;
    setBusy(true);
    try {
      await api.post("/human-loop/approve", {
        action_type: "schedule_interview",
        approval_id: approval.approval_id,
        approved: approve,
      });
      if (approve) {
        const resume = await api.post<{
          success: boolean;
          data?: { status: string; summary: string };
        }>("/human-loop/resume", { approval_id: approval.approval_id });
        if (resume.success && resume.data) {
          useAgentStore.getState().addMessage({
            role: "assistant",
            content: `✅ 审批通过，编排继续执行。\n\n${resume.data.summary}`,
          });
        }
      }
      useAgentStore.getState().resetApproval();
    } catch (err) {
      useAgentStore.getState().addMessage({
        role: "assistant",
        content: (err as Error).message || "审批处理失败",
        error: true,
      });
    } finally {
      setBusy(false);
    }
  };

  return (
    <section
      className="rounded-lg border border-amber-500/40 bg-amber-50/50 dark:bg-amber-950/20 p-3 mb-3 space-y-2"
      aria-label="待审批"
    >
      <div className="flex items-start gap-2">
        <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-amber-100 dark:bg-amber-900">
          <AlertCircle className="h-3.5 w-3.5 text-amber-600 dark:text-amber-400" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-xs font-semibold text-amber-900 dark:text-amber-200">
            待审批
          </p>
          <p className="text-[11px] text-amber-800 dark:text-amber-300 line-clamp-2 mt-0.5">
            {approval.summary}
          </p>
        </div>
      </div>
      <div className="flex gap-1.5">
        <button
          onClick={() => handleAction(false)}
          disabled={busy}
          className="flex-1 flex items-center justify-center gap-1 rounded-md border bg-background px-2 py-1 text-[11px] font-medium hover:bg-accent transition-colors disabled:opacity-50"
        >
          <XCircle className="h-3 w-3" />
          拒绝
        </button>
        <button
          onClick={() => handleAction(true)}
          disabled={busy}
          className="flex-1 flex items-center justify-center gap-1 rounded-md bg-amber-600 px-2 py-1 text-[11px] font-medium text-white hover:bg-amber-700 transition-colors disabled:opacity-50"
        >
          {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : <Check className="h-3 w-3" />}
          批准
        </button>
      </div>
    </section>
  );
}
