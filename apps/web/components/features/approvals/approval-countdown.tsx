"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import {
  Clock, CheckCircle2, XCircle, AlertTriangle, Loader2, Inbox,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorAlert } from "@/components/common/error-alert";
import { api, withErrorHandling } from "@/lib/trpc";

interface PendingApproval {
  approval_id: string;
  action_type: string;
  status: string;
  proposal: Record<string, unknown>;
  params?: Record<string, unknown>;
  candidate_email?: string;
  created_at: string;
  expires_at: string;
}

interface HistoryEntry {
  approval_id: string;
  action_type: string;
  status: string;
  resolution?: string;
  created_at: string;
  resolved_at: string;
}

const REFRESH_INTERVAL_MS = 60_000;
const URGENT_THRESHOLD_HOURS = 6;

function timeUntilExpiry(iso: string): { ms: number; label: string; urgent: boolean } {
  if (!iso) return { ms: 0, label: "—", urgent: false };
  const ms = new Date(iso).getTime() - Date.now();
  if (ms <= 0) return { ms, label: "已过期", urgent: true };
  const hours = ms / (1000 * 60 * 60);
  if (hours < 1) {
    const mins = Math.floor(ms / (1000 * 60));
    return { ms, label: `${mins} 分钟`, urgent: true };
  }
  if (hours < 24) {
    return {
      ms,
      label: `${hours.toFixed(1)} 小时`,
      urgent: hours < URGENT_THRESHOLD_HOURS,
    };
  }
  const days = Math.floor(hours / 24);
  return { ms, label: `${days} 天`, urgent: false };
}

export default function ApprovalCountdown() {
  const [pending, setPending] = useState<PendingApproval[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [resolvingId, setResolvingId] = useState<string | null>(null);
  const [now, setNow] = useState(Date.now());

  const load = useCallback(async () => {
    try {
      const res = await api.get<{ data?: PendingApproval[] } | PendingApproval[]>(
        "/human_loop/pending"
      );
      const items = Array.isArray(res) ? res : (res?.data || []);
      setPending(items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载待审批失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const refreshTimer = setInterval(load, REFRESH_INTERVAL_MS);
    const tickTimer = setInterval(() => setNow(Date.now()), 30_000);
    return () => {
      clearInterval(refreshTimer);
      clearInterval(tickTimer);
    };
  }, [load]);

  const sorted = useMemo(() => {
    void now; // re-render when tick updates
    return [...pending].sort((a, b) => {
      const ea = new Date(a.expires_at).getTime();
      const eb = new Date(b.expires_at).getTime();
      return ea - eb;
    });
  }, [pending, now]);

  const handleResolve = async (approvalId: string, approved: boolean) => {
    setResolvingId(approvalId);
    const result = await withErrorHandling(
      () => api.post<HistoryEntry>("/human_loop/approve", {
        approval_id: approvalId,
        approved,
      }),
      {
        success: approved ? "已批准" : "已拒绝",
        error: "操作失败",
      }
    );
    if (result) {
      setPending((prev) => prev.filter((p) => p.approval_id !== approvalId));
    }
    setResolvingId(null);
  };

  const urgentCount = sorted.filter((p) => {
    const { urgent } = timeUntilExpiry(p.expires_at);
    return urgent;
  }).length;

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center justify-between text-base">
          <span className="flex items-center gap-2">
            <Clock className="h-4 w-4" />
            待审批
            {sorted.length > 0 && (
              <Badge variant="secondary" className="ml-1">
                {sorted.length}
              </Badge>
            )}
          </span>
          {urgentCount > 0 && (
            <Badge variant="destructive" className="text-xs">
              <AlertTriangle className="mr-1 h-3 w-3" />
              {urgentCount} 紧急
            </Badge>
          )}
        </CardTitle>
      </CardHeader>

      <CardContent>
        {error && <ErrorAlert message={error} variant="error" />}

        {loading ? (
          <div className="space-y-2">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-16 w-full" />
            ))}
          </div>
        ) : sorted.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
            <Inbox className="mb-2 h-6 w-6 opacity-50" />
            <p className="text-sm">无待审批</p>
          </div>
        ) : (
          <div className="space-y-2 max-h-96 overflow-y-auto">
            {sorted.map((p) => {
              const { label, urgent } = timeUntilExpiry(p.expires_at);
              const proposalText = JSON.stringify(p.proposal || {}).slice(0, 80);
              const isResolving = resolvingId === p.approval_id;
              return (
                <div
                  key={p.approval_id}
                  className={`rounded border p-2 ${
                    urgent ? "border-red-200 bg-red-50/50" : "border-border bg-card"
                  }`}
                >
                  <div className="mb-1 flex items-center justify-between gap-2">
                    <Badge variant="outline" className="font-mono text-xs">
                      {p.action_type}
                    </Badge>
                    <span
                      className={`font-mono text-xs ${
                        urgent ? "font-semibold text-red-600" : "text-muted-foreground"
                      }`}
                    >
                      {urgent && <AlertTriangle className="mr-0.5 inline h-3 w-3" />}
                      {label}
                    </span>
                  </div>
                  {p.candidate_email && (
                    <p className="truncate text-xs text-muted-foreground">
                      {p.candidate_email}
                    </p>
                  )}
                  <p className="line-clamp-1 font-mono text-xs text-muted-foreground">
                    {proposalText}
                  </p>
                  <div className="mt-2 flex gap-1">
                    <Button
                      size="sm"
                      variant="default"
                      className="h-6 flex-1 px-2 text-xs"
                      onClick={() => handleResolve(p.approval_id, true)}
                      disabled={isResolving}
                    >
                      {isResolving ? (
                        <Loader2 className="h-3 w-3 animate-spin" />
                      ) : (
                        <CheckCircle2 className="h-3 w-3" />
                      )}
                      <span className="ml-1">批准</span>
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      className="h-6 flex-1 px-2 text-xs"
                      onClick={() => handleResolve(p.approval_id, false)}
                      disabled={isResolving}
                    >
                      <XCircle className="h-3 w-3" />
                      <span className="ml-1">拒绝</span>
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
