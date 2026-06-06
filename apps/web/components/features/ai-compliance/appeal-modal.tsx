"use client";

import { useState } from "react";
import { Loader2, Clock } from "lucide-react";
import { Button } from "@/components/ui/button";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
const TOKEN_KEY = "ai-recruitment-token";

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
}

interface AppealModalProps {
  open: boolean;
  onClose: () => void;
  onSuccess: () => void;
  targetType: "recommendation" | "interview_evaluation";
  targetId: string;
  targetLabel?: string;
}

export function AppealModal({ open, onClose, onSuccess, targetType, targetId, targetLabel }: AppealModalProps) {
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!open) return null;

  const handleSubmit = async () => {
    if (reason.length < 10) {
      setError("申诉原因至少 10 个字符");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const token = getToken();
      const res = await fetch(`${API_BASE}/ai-compliance/appeals`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ target_type: targetType, target_id: targetId, reason }),
      });
      const j = await res.json();
      if (!res.ok || !j.success) throw new Error(j.error || "申诉失败");
      onSuccess();
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "申诉失败");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-lg bg-white p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center gap-2">
          <Clock className="h-5 w-5 text-blue-600" />
          <h2 className="text-lg font-semibold">AI 评分申诉</h2>
        </div>

        <div className="space-y-4">
          {targetLabel && (
            <div>
              <label className="text-sm text-muted-foreground">对象</label>
              <p className="text-sm font-mono">{targetLabel}</p>
            </div>
          )}

          <div>
            <label className="text-sm font-medium" htmlFor="appeal-reason">
              申诉原因 (≥10 字符, 7 天内必回复)
            </label>
            <textarea
              id="appeal-reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="详细说明为何认为该 AI 评分不合理, 如: 工作经验未充分考虑 / 评分标准不符合岗位要求"
              rows={4}
              className="mt-1 w-full rounded border border-input bg-background px-3 py-2 text-sm"
            />
          </div>

          {error && (
            <p className="text-sm text-destructive">{error}</p>
          )}

          <div className="rounded border border-blue-200 bg-blue-50 p-2 text-xs text-blue-800">
            提交后管理员将在 7 天内回复, 处理结果落 audit_log。期间 AI 评分仍生效, 不会立即变更。
          </div>
        </div>

        <div className="mt-4 flex justify-end gap-2">
          <Button variant="outline" onClick={onClose} disabled={submitting}>
            取消
          </Button>
          <Button onClick={handleSubmit} disabled={submitting}>
            {submitting ? <Loader2 className="mr-1 h-3 w-3 animate-spin" /> : null}
            提交申诉
          </Button>
        </div>
      </div>
    </div>
  );
}
