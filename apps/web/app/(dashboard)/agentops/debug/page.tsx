"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { BugPlay, Search, AlertTriangle, CheckCircle, Clock, Activity } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorAlert } from "@/components/common/error-alert";
import { api } from "@/lib/trpc";

interface RecentRun {
  run_id: string;
  experiment_name: string;
  status: string;
  avg_score: number;
  total_items: number;
  passed_items: number;
  failed_items: number;
  duration_ms: number;
  started_at: string;
}

interface TraceEvent {
  id: string;
  event_type: string;
  name: string;
  entity_type: string;
  entity_id: string;
  created_at: string;
  offset_ms: number;
  domain_fields: Record<string, unknown>;
}

interface TraceDetail {
  trace_id: string;
  event_count: number;
  events: TraceEvent[];
}

export default function DebugConsole() {
  const [runs, setRuns] = useState<RecentRun[]>([]);
  const [runSearch, setRunSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Trace search state
  const [traceId, setTraceId] = useState("");
  const [traceResult, setTraceResult] = useState<TraceDetail | null>(null);
  const [traceLoading, setTraceLoading] = useState(false);
  const [traceError, setTraceError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const data = await api.get<RecentRun[]>("/dashboard/agentops/recent-runs?limit=50");
        setRuns(data || []);
      } catch (err) {
        setError(err instanceof Error ? err.message : "加载失败");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const handleTraceSearch = async () => {
    if (!traceId.trim()) return;
    setTraceLoading(true);
    setTraceError(null);
    setTraceResult(null);
    try {
      const data = await api.get<TraceDetail>(`/dashboard/agentops/traces/${traceId.trim()}`);
      setTraceResult(data);
    } catch (err) {
      setTraceError(err instanceof Error ? err.message : "Trace 未找到");
    } finally {
      setTraceLoading(false);
    }
  };

  const filtered = runs.filter((r) =>
    r.experiment_name.toLowerCase().includes(runSearch.toLowerCase()),
  );

  return (
    <div className="space-y-6 p-6">
      <nav className="flex gap-1 border-b pb-2 mb-2">
        <Link href="/agentops" className="px-3 py-1.5 text-sm rounded-md text-muted-foreground hover:bg-muted">概览</Link>
        <Link href="/agentops/debug" className="px-3 py-1.5 text-sm rounded-md bg-primary/10 text-primary font-medium">Debug</Link>
        <Link href="/agentops/cost" className="px-3 py-1.5 text-sm rounded-md text-muted-foreground hover:bg-muted">成本</Link>
        <Link href="/agentops/governance" className="px-3 py-1.5 text-sm rounded-md text-muted-foreground hover:bg-muted">治理</Link>
      </nav>

      <h1 className="text-2xl font-bold">Debug Console</h1>

      {/* Trace 搜索 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Trace 查询</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex gap-2">
            <input
              className="flex-1 px-3 py-2 text-sm border rounded-md font-mono"
              placeholder="输入 Trace ID..."
              value={traceId}
              onChange={(e) => setTraceId(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleTraceSearch()}
            />
            <button
              className="px-4 py-2 text-sm bg-primary text-primary-foreground rounded-md hover:bg-primary/90 disabled:opacity-50"
              onClick={handleTraceSearch}
              disabled={traceLoading || !traceId.trim()}
            >
              查询
            </button>
          </div>

          {traceError && <p className="mt-2 text-sm text-red-600">{traceError}</p>}

          {traceLoading && <Skeleton className="mt-2 h-24 w-full" />}

          {traceResult && (
            <div className="mt-4 space-y-1">
              <p className="text-sm text-muted-foreground">
                Trace {traceResult.trace_id} — {traceResult.event_count} 个事件
              </p>
              <div className="border rounded-md divide-y max-h-96 overflow-y-auto">
                {traceResult.events.map((ev, i) => (
                  <div key={ev.id} className="flex items-center gap-3 px-3 py-2 text-sm hover:bg-muted/50">
                    <span className="w-2 h-2 rounded-full bg-blue-500 shrink-0" />
                    <span className="w-32 font-mono text-xs text-muted-foreground shrink-0">
                      +{ev.offset_ms.toFixed(0)}ms
                    </span>
                    <span className="w-48 font-mono text-xs shrink-0">{ev.event_type}</span>
                    <span className="text-muted-foreground">{ev.entity_type}/{ev.entity_id}</span>
                    {ev.domain_fields && Object.keys(ev.domain_fields).length > 0 && (
                      <span className="text-xs text-muted-foreground truncate">
                        {JSON.stringify(ev.domain_fields).slice(0, 60)}...
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* 运行记录 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">运行记录</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="mb-3 relative w-64">
            <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
            <input
              className="w-full pl-8 pr-3 py-2 text-sm border rounded-md"
              placeholder="搜索实验名称..."
              value={runSearch}
              onChange={(e) => setRunSearch(e.target.value)}
            />
          </div>
          {loading ? (
            <Skeleton className="h-48 w-full" />
          ) : filtered.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-muted-foreground">
                    <th className="pb-2 font-medium">实验</th>
                    <th className="pb-2 font-medium">状态</th>
                    <th className="pb-2 font-medium">分数</th>
                    <th className="pb-2 font-medium">通过率</th>
                    <th className="pb-2 font-medium">耗时</th>
                    <th className="pb-2 font-medium">时间</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((run) => (
                    <tr key={run.run_id} className="border-b last:border-0 hover:bg-muted/50">
                      <td className="py-2 font-medium">{run.experiment_name}</td>
                      <td className="py-2">
                        <span className={`inline-flex items-center gap-1 ${
                          run.status === "completed" ? "text-green-600" : "text-yellow-600"
                        }`}>
                          {run.status === "completed"
                            ? <CheckCircle className="h-3 w-3" />
                            : <AlertTriangle className="h-3 w-3" />
                          }
                          {run.status}
                        </span>
                      </td>
                      <td className="py-2">{(run.avg_score * 100).toFixed(1)}</td>
                      <td className="py-2">
                        {run.total_items > 0
                          ? ((run.passed_items / run.total_items) * 100).toFixed(0) + "%"
                          : "-"}
                      </td>
                      <td className="py-2 flex items-center gap-1">
                        <Clock className="h-3 w-3 text-muted-foreground" />
                        {(run.duration_ms / 1000).toFixed(1)}s
                      </td>
                      <td className="py-2 text-muted-foreground">
                        {run.started_at ? new Date(run.started_at).toLocaleString() : "-"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              {runSearch ? "无匹配结果" : "暂无运行记录"}
            </p>
          )}
        </CardContent>
      </Card>

      {/* 评估器性能 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">评估器性能</CardTitle>
        </CardHeader>
        <CardContent>
          <EvaluatorTable />
        </CardContent>
      </Card>
    </div>
  );
}

function EvaluatorTable() {
  const [data, setData] = useState<Record<string, { avg_score: number; count: number }> | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get<Record<string, { avg_score: number; count: number }>>("/dashboard/agentops/evaluators")
      .then(setData)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <Skeleton className="h-24 w-full" />;
  if (!data || Object.keys(data).length === 0) return <p className="text-sm text-muted-foreground">暂无数据</p>;

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b text-left text-muted-foreground">
            <th className="pb-2 font-medium">评估器</th>
            <th className="pb-2 font-medium">平均分</th>
            <th className="pb-2 font-medium">使用次数</th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(data).map(([name, stats]) => (
            <tr key={name} className="border-b last:border-0">
              <td className="py-2 font-mono text-xs">{name}</td>
              <td className="py-2">{(stats.avg_score * 100).toFixed(1)}</td>
              <td className="py-2">{stats.count}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
