"use client";

import { useEffect, useState, useMemo } from "react";
import {
  FileText, Filter, RefreshCw, Loader2, Shield, X, Download, ChevronLeft, ChevronRight,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorAlert } from "@/components/common/error-alert";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
const TOKEN_KEY = "ai-recruitment-token";

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
}

interface AuditLog {
  id: string;
  org_id: string;
  actor_user_id: string | null;
  action: string;
  target_user_id: string | null;
  meta: Record<string, unknown> | null;
  ip_address: string | null;
  user_agent: string | null;
  created_at: string;
}

interface AuditLogsResponse {
  items: AuditLog[];
  total: number;
}

const ACTION_OPTIONS = [
  { value: "", label: "全部" },
  { value: "org_switch", label: "切换 Org" },
  { value: "invite_accept", label: "接受邀请" },
  { value: "membership_add", label: "添加成员" },
  { value: "membership_remove", label: "移除成员" },
  { value: "membership_role_change", label: "角色变更" },
  { value: "wechat_login", label: "微信登录" },
  { value: "wechat_bind", label: "微信绑定" },
];

const ACTION_COLORS: Record<string, string> = {
  org_switch: "bg-blue-100 text-blue-700 border-blue-300",
  invite_accept: "bg-green-100 text-green-700 border-green-300",
  membership_add: "bg-emerald-100 text-emerald-700 border-emerald-300",
  membership_remove: "bg-orange-100 text-orange-700 border-orange-300",
  membership_role_change: "bg-purple-100 text-purple-700 border-purple-300",
  wechat_login: "bg-cyan-100 text-cyan-700 border-cyan-300",
  wechat_bind: "bg-teal-100 text-teal-700 border-teal-300",
};

function formatTime(iso: string): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("zh-CN", {
      year: "numeric", month: "2-digit", day: "2-digit",
      hour: "2-digit", minute: "2-digit", second: "2-digit",
    });
  } catch { return iso; }
}

function exportToCSV(items: AuditLog[]): void {
  const headers = ["时间", "动作", "操作人", "目标", "IP", "元数据"];
  const rows = items.map((log) => [
    formatTime(log.created_at),
    log.action,
    log.actor_user_id || "",
    log.target_user_id || "",
    log.ip_address || "",
    JSON.stringify(log.meta || {}),
  ]);
  const csv = [headers, ...rows]
    .map((row) => row.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(","))
    .join("\n");
  const blob = new Blob(["\ufeff" + csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `audit_logs_${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

export default function AuditLogPanel() {
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actionFilter, setActionFilter] = useState<string>("");
  const [fromDate, setFromDate] = useState<string>("");
  const [toDate, setToDate] = useState<string>("");
  const [skip, setSkip] = useState(0);
  const [detail, setDetail] = useState<AuditLog | null>(null);
  const limit = 50;

  const queryString = useMemo(() => {
    const params = new URLSearchParams({ limit: String(limit), offset: String(skip) });
    if (actionFilter) params.set("action", actionFilter);
    return params.toString();
  }, [actionFilter, skip]);

  const load = async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    else setLoading(true);
    setError(null);
    try {
      const token = getToken();
      if (!token) {
        setError("未登录");
        return;
      }
      const res = await fetch(`${API_BASE}/audit-logs?${queryString}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: AuditLogsResponse = await res.json();
      let items = data.items || [];
      if (fromDate || toDate) {
        items = items.filter((log) => {
          const t = new Date(log.created_at).getTime();
          if (fromDate && t < new Date(fromDate).getTime()) return false;
          if (toDate && t > new Date(toDate).getTime() + 86400000) return false;
          return true;
        });
      }
      setLogs(items);
      setTotal(data.total || 0);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载审计日志失败");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => { load(); }, [queryString]);

  const filtersActive = actionFilter !== "" || fromDate !== "" || toDate !== "";
  const hasNext = skip + limit < total;
  const hasPrev = skip > 0;

  return (
    <>
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="flex items-center gap-2 text-base">
              <Shield className="h-4 w-4" />
              审计日志
              {total > 0 && (
                <span className="text-xs font-normal text-muted-foreground">({total} 总计)</span>
              )}
            </CardTitle>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => exportToCSV(logs)}
                disabled={logs.length === 0}
              >
                <Download className="mr-1 h-3 w-3" />
                导出 CSV
              </Button>
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

          <div className="flex flex-wrap items-center gap-2 pt-3">
            <Filter className="h-3 w-3 text-muted-foreground" />
            <select
              value={actionFilter}
              onChange={(e) => { setActionFilter(e.target.value); setSkip(0); }}
              className="rounded border border-input bg-background px-2 py-1 text-xs"
              aria-label="按动作过滤"
            >
              {ACTION_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>

            <span className="text-xs text-muted-foreground">从</span>
            <input
              type="date"
              value={fromDate}
              onChange={(e) => { setFromDate(e.target.value); setSkip(0); }}
              className="rounded border border-input bg-background px-2 py-1 text-xs"
            />

            <span className="text-xs text-muted-foreground">至</span>
            <input
              type="date"
              value={toDate}
              onChange={(e) => { setToDate(e.target.value); setSkip(0); }}
              className="rounded border border-input bg-background px-2 py-1 text-xs"
            />

            {filtersActive && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => { setActionFilter(""); setFromDate(""); setToDate(""); setSkip(0); }}
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
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="border-b text-left text-xs text-muted-foreground">
                  <tr>
                    <th className="px-2 py-2 font-medium">时间</th>
                    <th className="px-2 py-2 font-medium">动作</th>
                    <th className="px-2 py-2 font-medium">操作人</th>
                    <th className="px-2 py-2 font-medium">目标</th>
                    <th className="px-2 py-2 font-medium">IP</th>
                    <th className="px-2 py-2 font-medium text-right">详情</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {logs.map((log) => (
                    <tr key={log.id} className="hover:bg-muted/30">
                      <td className="px-2 py-2 font-mono text-xs">
                        {formatTime(log.created_at)}
                      </td>
                      <td className="px-2 py-2">
                        <Badge variant="outline" className={`text-xs ${ACTION_COLORS[log.action] || ""}`}>
                          {log.action}
                        </Badge>
                      </td>
                      <td className="px-2 py-2 font-mono text-xs text-muted-foreground">
                        {log.actor_user_id ? log.actor_user_id.slice(0, 8) + "..." : "—"}
                      </td>
                      <td className="px-2 py-2 font-mono text-xs text-muted-foreground">
                        {log.target_user_id ? log.target_user_id.slice(0, 8) + "..." : "—"}
                      </td>
                      <td className="px-2 py-2 font-mono text-xs text-muted-foreground">
                        {log.ip_address || "—"}
                      </td>
                      <td className="px-2 py-2 text-right">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setDetail(log)}
                          className="h-6 px-2 text-xs"
                        >
                          查看
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {!loading && logs.length > 0 && (
            <div className="mt-4 flex items-center justify-between text-xs text-muted-foreground">
              <span>
                显示 {skip + 1}-{Math.min(skip + limit, total)} 共 {total}
              </span>
              <div className="flex items-center gap-1">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setSkip(Math.max(0, skip - limit))}
                  disabled={!hasPrev}
                >
                  <ChevronLeft className="h-3 w-3" />
                  上一页
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setSkip(skip + limit)}
                  disabled={!hasNext}
                >
                  下一页
                  <ChevronRight className="h-3 w-3" />
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {detail && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
          onClick={() => setDetail(null)}
        >
          <div
            className="max-h-[80vh] w-full max-w-2xl overflow-y-auto rounded-lg bg-white p-6"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-lg font-semibold">审计日志详情</h2>
              <button
                onClick={() => setDetail(null)}
                className="text-muted-foreground hover:text-foreground"
                aria-label="关闭"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <dl className="space-y-2 text-sm">
              <div>
                <dt className="text-xs text-muted-foreground">ID</dt>
                <dd className="font-mono text-xs">{detail.id}</dd>
              </div>
              <div>
                <dt className="text-xs text-muted-foreground">时间</dt>
                <dd className="font-mono text-xs">{formatTime(detail.created_at)}</dd>
              </div>
              <div>
                <dt className="text-xs text-muted-foreground">动作</dt>
                <dd>
                  <Badge variant="outline" className={ACTION_COLORS[detail.action] || ""}>
                    {detail.action}
                  </Badge>
                </dd>
              </div>
              <div>
                <dt className="text-xs text-muted-foreground">Org ID</dt>
                <dd className="font-mono text-xs">{detail.org_id}</dd>
              </div>
              <div>
                <dt className="text-xs text-muted-foreground">操作人</dt>
                <dd className="font-mono text-xs">{detail.actor_user_id || "—"}</dd>
              </div>
              <div>
                <dt className="text-xs text-muted-foreground">目标</dt>
                <dd className="font-mono text-xs">{detail.target_user_id || "—"}</dd>
              </div>
              <div>
                <dt className="text-xs text-muted-foreground">IP</dt>
                <dd className="font-mono text-xs">{detail.ip_address || "—"}</dd>
              </div>
              <div>
                <dt className="text-xs text-muted-foreground">User Agent</dt>
                <dd className="font-mono text-xs break-all">{detail.user_agent || "—"}</dd>
              </div>
              <div>
                <dt className="text-xs text-muted-foreground">元数据 (raw JSON)</dt>
                <dd className="overflow-x-auto rounded bg-muted/30 p-3 font-mono text-xs">
                  <pre>{JSON.stringify(detail.meta || {}, null, 2)}</pre>
                </dd>
              </div>
            </dl>

            <div className="mt-4 flex justify-end">
              <Button variant="outline" onClick={() => setDetail(null)}>
                关闭
              </Button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
