"use client";

import { useState, useEffect, useMemo } from "react";
import {
  FileText, AlertCircle, Filter, ChevronDown, ChevronRight,
  RefreshCw, Loader2, Shield,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorAlert } from "@/components/common/error-alert";
import { api } from "@/lib/trpc";

interface LogEntry {
  id: string;
  agent_name: string;
  action: string;
  status: string;
  error_category: string | null;
  input_summary: string | null;
  output_summary: string | null;
  error_message: string | null;
  duration_ms: number | null;
  created_at: string;
  updated_at: string;
}

interface AuditLogsResponse {
  items: LogEntry[];
  total: number;
}

const STATUS_COLORS: Record<string, string> = {
  pending: "bg-gray-100 text-gray-700",
  running: "bg-blue-100 text-blue-700",
  completed: "bg-green-100 text-green-700",
  failed: "bg-red-100 text-red-700",
  cancelled: "bg-yellow-100 text-yellow-700",
  awaiting_approval: "bg-purple-100 text-purple-700",
};

const ERROR_COLORS: Record<string, string> = {
  system: "bg-red-100 text-red-700 border-red-300",
  user: "bg-amber-100 text-amber-700 border-amber-300",
  business: "bg-slate-100 text-slate-700 border-slate-300",
};

const AGENT_OPTIONS = [
  "router", "orchestrator", "screening", "pipeline", "interview",
  "gen_eval", "aggregator", "human_loop", "single_agent",
];

const ERROR_CATEGORY_OPTIONS = ["system", "user", "business"];

function formatDuration(ms: number | null): string {
  if (ms === null) return "—";
  if (ms < 1000) return `${ms.toFixed(0)}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

function formatTime(iso: string): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleString("zh-CN", {
      month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit",
    });
  } catch {
    return iso;
  }
}

export default function AuditPanel() {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [agentFilter, setAgentFilter] = useState<string>("");
  const [errorFilter, setErrorFilter] = useState<string>("");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const queryString = useMemo(() => {
    const params = new URLSearchParams({ limit: "50" });
    if (agentFilter) params.set("agent_name", agentFilter);
    if (errorFilter) params.set("error_category", errorFilter);
    return params.toString();
  }, [agentFilter, errorFilter]);

  const load = async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    else setLoading(true);
    setError(null);
    try {
      const res = await api.get<AuditLogsResponse>(`/audit/logs?${queryString}`);
      setLogs(res?.items || []);
      setTotal(res?.total || 0);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载审计日志失败");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    load();
  }, [queryString]);

  const filtersActive = agentFilter !== "" || errorFilter !== "";

  return (
    <Card className="lg:col-span-3">
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2 text-base">
            <Shield className="h-4 w-4" />
            审计日志
            {total > 0 && (
              <span className="text-xs font-normal text-muted-foreground">({total})</span>
            )}
          </CardTitle>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => load(true)}
              disabled={refreshing}
            >
              {refreshing ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : (
                <RefreshCw className="h-3 w-3" />
              )}
            </Button>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2 pt-2">
          <Filter className="h-3 w-3 text-muted-foreground" />
          <select
            value={agentFilter}
            onChange={(e) => setAgentFilter(e.target.value)}
            className="rounded border border-input bg-background px-2 py-1 text-xs"
            aria-label="按 Agent 过滤"
          >
            <option value="">全部 Agent</option>
            {AGENT_OPTIONS.map((a) => (
              <option key={a} value={a}>{a}</option>
            ))}
          </select>

          <select
            value={errorFilter}
            onChange={(e) => setErrorFilter(e.target.value)}
            className="rounded border border-input bg-background px-2 py-1 text-xs"
            aria-label="按错误类别过滤"
          >
            <option value="">全部错误类别</option>
            {ERROR_CATEGORY_OPTIONS.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>

          {filtersActive && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => { setAgentFilter(""); setErrorFilter(""); }}
              className="h-6 px-2 text-xs"
            >
              清除
            </Button>
          )}
        </div>
      </CardHeader>

      <CardContent>
        {error && <ErrorAlert message={error} variant="error" />}

        {loading ? (
          <div className="space-y-2">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-10 w-full" />
            ))}
          </div>
        ) : logs.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
            <FileText className="mb-2 h-8 w-8 opacity-50" />
            <p className="text-sm">
              {filtersActive ? "当前过滤条件下无日志" : "暂无审计日志"}
            </p>
          </div>
        ) : (
          <div className="divide-y">
            {logs.map((log) => {
              const expanded = expandedId === log.id;
              return (
                <div key={log.id} className="py-2">
                  <button
                    onClick={() => setExpandedId(expanded ? null : log.id)}
                    className="flex w-full items-center justify-between gap-3 text-left text-sm hover:bg-muted/50"
                  >
                    <div className="flex min-w-0 flex-1 items-center gap-2">
                      {expanded ? (
                        <ChevronDown className="h-3 w-3 shrink-0" />
                      ) : (
                        <ChevronRight className="h-3 w-3 shrink-0" />
                      )}
                      <span className="font-mono text-xs text-muted-foreground">
                        {formatTime(log.created_at)}
                      </span>
                      <Badge variant="outline" className="font-mono text-xs">
                        {log.agent_name}
                      </Badge>
                      <span className="truncate font-mono text-xs">
                        {log.action}
                      </span>
                    </div>
                    <div className="flex shrink-0 items-center gap-1">
                      {log.error_category && (
                        <Badge
                          variant="outline"
                          className={`text-xs ${ERROR_COLORS[log.error_category] || ""}`}
                        >
                          {log.error_category}
                        </Badge>
                      )}
                      <Badge
                        variant="secondary"
                        className={`text-xs ${STATUS_COLORS[log.status] || ""}`}
                      >
                        {log.status}
                      </Badge>
                      <span className="ml-2 font-mono text-xs text-muted-foreground">
                        {formatDuration(log.duration_ms)}
                      </span>
                    </div>
                  </button>

                  {expanded && (
                    <div className="mt-2 ml-5 space-y-1 rounded bg-muted/30 p-3 text-xs">
                      {log.input_summary && (
                        <div>
                          <span className="text-muted-foreground">输入：</span>
                          <span className="font-mono">{log.input_summary}</span>
                        </div>
                      )}
                      {log.output_summary && (
                        <div>
                          <span className="text-muted-foreground">输出：</span>
                          <span className="font-mono">{log.output_summary}</span>
                        </div>
                      )}
                      {log.error_message && (
                        <div className="flex items-start gap-1 text-red-600">
                          <AlertCircle className="mt-0.5 h-3 w-3 shrink-0" />
                          <span className="font-mono">{log.error_message}</span>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
