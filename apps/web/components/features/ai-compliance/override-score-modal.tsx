"use client";

import { useState } from "react";
import { Loader2, AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
const TOKEN_KEY = "ai-recruitment-token";

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
}

interface OverrideScoreModalProps {
  open: boolean;
  onClose: () => void;
  onSuccess: () => void;
  recommendationId: string;
  originalScore: number;
}

export function OverrideScoreModal({ open, onClose, onSuccess, recommendationId, originalScore }: OverrideScoreModalProps) {
  const [newScore, setNewScore] = useState(originalScore);
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!open) return null;

  const handleSubmit = async () => {
    if (newScore === originalScore) {
      setError("新评分与原评分相同, 无需改写");
      return;
    }
    if (reason.length < 5) {
      setError("原因至少 5 个字符");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const token = getToken();
      const res = await fetch(`${API_BASE}/ai-compliance/recommendations/${recommendationId}/override-score`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ new_score: newScore, reason }),
      });
      const j = await res.json();
      if (!res.ok || !j.success) throw new Error(j.error || "改写失败");
      onSuccess();
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "改写失败");
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
          <AlertTriangle className="h-5 w-5 text-amber-600" />
          <h2 className="text-lg font-semibold">人工改写 AI 评分</h2>
        </div>

        <div className="space-y-4">
          <div>
            <label className="text-sm text-muted-foreground">原 AI 评分</label>
            <p className="text-2xl font-bold">{originalScore}</p>
          </div>

          <div>
            <label className="text-sm font-medium" htmlFor="new-score">新评分 (0-100)</label>
            <input
              id="new-score"
              type="range"
              min="0"
              max="100"
              value={newScore}
              onChange={(e) => setNewScore(parseInt(e.target.value, 10))}
              className="mt-2 w-full"
            />
            <div className="mt-1 flex items-center justify-between">
              <span className="text-xs text-muted-foreground">0</span>
              <span className="text-xl font-bold">{newScore}</span>
              <span className="text-xs text-muted-foreground">100</span>
            </div>
          </div>

          <div>
            <label className="text-sm font-medium" htmlFor="reason">改写原因 (≥5 字符, 落 audit)</label>
            <textarea
              id="reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="如: 候选人 5 年 React 经验被低估, 项目复杂度与职位匹配"
              rows={3}
              className="mt-1 w-full rounded border border-input bg-background px-3 py-2 text-sm"
            />
          </div>

          {error && (
            <p className="text-sm text-destructive">{error}</p>
          )}

          <div className="rounded border border-amber-200 bg-amber-50 p-2 text-xs text-amber-800">
            改写后此评分将标记为 "人工", AI 评分仅作历史参考。改写操作落 audit_log。
          </div>
        </div>

        <div className="mt-4 flex justify-end gap-2">
          <Button variant="outline" onClick={onClose} disabled={submitting}>
            取消
          </Button>
          <Button onClick={handleSubmit} disabled={submitting}>
            {submitting ? <Loader2 className="mr-1 h-3 w-3 animate-spin" /> : null}
            确认改写
          </Button>
        </div>
      </div>
    </div>
  );
}
