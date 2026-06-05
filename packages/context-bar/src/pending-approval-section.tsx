"use client";

/**
 * PendingApprovalSection — 纯 UI 展示当前审批请求
 *
 * 工业级 / 全局规划：业务逻辑（调后端 api）从 UI 分离到 host 层。
 *  - 包内组件不直接依赖 @/lib/trpc，避免包内耦合 host 的 API client
 *  - host 通过 onApprove / onReject props 注入实际行为
 *  - 默认 no-op，host 不传也不报错（仅 UI 渲染）
 */

import { useState } from "react";
import { AlertCircle, Check, XCircle, Loader2 } from "lucide-react";
import { useAgentStore } from "@ai-recruitment/agent-store";

export interface PendingApprovalSectionProps {
  /** 批准回调；返回 summary 文案，失败时 throw */
  onApprove?: (approvalId: string) => Promise<string | void>;
  /** 拒绝回调 */
  onReject?: (approvalId: string) => Promise<void> | void;
}

export function PendingApprovalSection({
  onApprove,
  onReject,
}: PendingApprovalSectionProps = {}) {
  const approval = useAgentStore((s) => s.approval);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!approval.visible) return null;

  const handleAction = async (approve: boolean) => {
    if (!approval.approval_id || busy) return;
    setBusy(true);
    setError(null);
    try {
      if (approve && onApprove) {
        await onApprove(approval.approval_id);
      } else if (!approve && onReject) {
        await onReject(approval.approval_id);
      }
      useAgentStore.getState().resetApproval();
    } catch (err) {
      setError(err instanceof Error ? err.message : "操作失败");
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
          {error && (
            <p className="text-[10px] text-destructive mt-1">{error}</p>
          )}
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
