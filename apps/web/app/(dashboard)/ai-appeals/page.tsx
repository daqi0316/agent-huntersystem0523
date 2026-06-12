"use client";

import { useEffect, useState } from "react";
import { CheckCircle, XCircle, Loader2, Inbox } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ErrorAlert } from "@/components/common/error-alert";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
const TOKEN_KEY = "ai-recruitment-token";

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
}

interface Appeal {
  id: string;
  target_type: string;
  target_id: string;
  status: string;
  reason: string;
  resolution: string | null;
  resolved_by: string | null;
  resolved_at: string | null;
  due_at: string;
  sla_days_left: number | null;
  overdue: boolean;
  created_at: string;
}

const STATUS_COLORS: Record<string, string> = {
  pending: "bg-yellow-100 text-yellow-700 border-yellow-300",
  in_review: "bg-blue-100 text-blue-700 border-blue-300",
  resolved_accepted: "bg-green-100 text-green-700 border-green-300",
  resolved_rejected: "bg-gray-100 text-gray-700 border-gray-300",
  cancelled: "bg-gray-100 text-gray-500 border-gray-200",
};

const STATUS_LABELS: Record<string, string> = {
  pending: "待处理",
  in_review: "处理中",
  resolved_accepted: "已支持",
  resolved_rejected: "已驳回",
  cancelled: "已撤回",
};

export default function AppealsListPage() {
  const [appeals, setAppeals] = useState<Appeal[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<string>("pending");
  const [actionInProgress, setActionInProgress] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const token = getToken();
      if (!token) { setError("未登录"); return; }
      const url = filter
        ? `${API_BASE}/ai-compliance/appeals?status=${filter}`
        : `${API_BASE}/ai-compliance/appeals`;
      const res = await fetch(url, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const j = await res.json();
      setAppeals(j.data || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [filter]);

  const handleResolve = async (id: string, accept: boolean) => {
    const resolution = window.prompt(
      `${accept ? "支持申诉" : "驳回申诉"} - 写 resolution (≥10 字符):`,
    );
    if (!resolution || resolution.length < 10) {
      if (resolution !== null) alert("resolution 至少 10 字符");
      return;
    }
    setActionInProgress(id);
    setError(null);
    try {
      const token = getToken();
      const res = await fetch(`${API_BASE}/ai-compliance/appeals/${id}/resolve`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ resolution, accept }),
      });
      const j = await res.json();
      if (!res.ok || !j.success) throw new Error(j.error || "处理失败");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "处理失败");
    } finally {
      setActionInProgress(null);
    }
  };

  return (
    <div className="space-y-6 p-6">
      <div>
        <h1 className="text-3xl font-bold">
          AI 评分申诉
        </h1>
        <p className="text-muted-foreground">处理用户的 AI 评分申诉 (7 天 SLA)</p>
      </div>

      {error && <ErrorAlert message={error} variant="error" />}

      <div className="flex items-center gap-2">
        {["pending", "in_review", "resolved_accepted", "resolved_rejected", ""].map((s) => (
          <Button
            key={s || "all"}
            variant={filter === s ? "default" : "outline"}
            size="sm"
            onClick={() => setFilter(s)}
          >
            {s ? STATUS_LABELS[s] : "全部"}
          </Button>
        ))}
      </div>

      {loading ? (
        <div className="flex items-center justify-center p-12 text-muted-foreground">
          <Loader2 className="mr-2 h-4 w-4 animate-spin" /> 加载...
        </div>
      ) : appeals.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12 text-muted-foreground">
            <Inbox className="mb-2 h-8 w-8 opacity-50" />
            <p className="text-sm">暂无{STATUS_LABELS[filter] || ""}的申诉</p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {appeals.map((a) => (
            <Card key={a.id}>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle className="flex items-center gap-2 text-base">
                    <Badge variant="outline" className={STATUS_COLORS[a.status] || ""}>
                      {STATUS_LABELS[a.status] || a.status}
                    </Badge>
                    <span className="font-mono text-xs text-muted-foreground">{a.id.slice(0, 12)}…</span>
                  </CardTitle>
                  {a.overdue && (
                    <Badge variant="destructive" className="text-xs">⚠ SLA 超时</Badge>
                  )}
                </div>
              </CardHeader>
              <CardContent className="space-y-3 text-sm">
                <div>
                  <span className="text-muted-foreground">对象: </span>
                  <code className="rounded bg-muted px-1 py-0.5 text-xs">
                    {a.target_type}:{a.target_id.slice(0, 8)}…
                  </code>
                </div>
                <div>
                  <span className="text-muted-foreground">原因: </span>
                  <p className="mt-1 whitespace-pre-wrap rounded bg-muted/30 p-2 text-xs">{a.reason}</p>
                </div>
                {a.resolution && (
                  <div>
                    <span className="text-muted-foreground">处理结果: </span>
                    <p className="mt-1 whitespace-pre-wrap rounded bg-green-50 p-2 text-xs">{a.resolution}</p>
                  </div>
                )}
                <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
                  <span>提交: {new Date(a.created_at).toLocaleString("zh-CN")}</span>
                  <span>到期: {new Date(a.due_at).toLocaleString("zh-CN")}</span>
                  {a.sla_days_left !== null && a.status === "pending" && (
                    <span>剩余: <strong>{a.sla_days_left}</strong> 天</span>
                  )}
                </div>
                {(a.status === "pending" || a.status === "in_review") && (
                  <div className="flex gap-2 pt-2">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => handleResolve(a.id, true)}
                      disabled={actionInProgress === a.id}
                    >
                      {actionInProgress === a.id ? <Loader2 className="mr-1 h-3 w-3 animate-spin" /> : <CheckCircle className="mr-1 h-3 w-3" />}
                      支持申诉
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => handleResolve(a.id, false)}
                      disabled={actionInProgress === a.id}
                    >
                      <XCircle className="mr-1 h-3 w-3" /> 驳回
                    </Button>
                  </div>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
