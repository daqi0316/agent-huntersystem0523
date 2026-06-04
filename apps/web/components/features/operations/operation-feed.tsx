"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import {
  Activity, CheckCircle2, XCircle, Clock, Loader2,
  AlertCircle, Play, RotateCcw,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/trpc";
import { useEventSource } from "@/hooks/use-event-source";

interface OperationEvent {
  operation_id: string;
  agent_name: string;
  action: string;
  status: string;
  output_summary?: string;
  error_message?: string;
  duration_ms?: number;
  timestamp: string;
}

const statusConfig: Record<string, { label: string; color: string; icon: typeof Clock }> = {
  pending: { label: "排队中", color: "bg-gray-100 text-gray-600", icon: Clock },
  running: { label: "运行中", color: "bg-blue-100 text-blue-600", icon: Loader2 },
  completed: { label: "已完成", color: "bg-green-100 text-green-600", icon: CheckCircle2 },
  failed: { label: "失败", color: "bg-red-100 text-red-600", icon: XCircle },
  cancelled: { label: "已取消", color: "bg-yellow-100 text-yellow-600", icon: AlertCircle },
  awaiting_approval: { label: "待审批", color: "bg-purple-100 text-purple-600", icon: AlertCircle },
};

const agentColors: Record<string, string> = {
  screening: "border-l-blue-500",
  pipeline: "border-l-blue-500",
  orchestrator: "border-l-purple-500",
  human_loop: "border-l-orange-500",
  aggregator: "border-l-green-500",
  router: "border-l-yellow-500",
  gen_eval: "border-l-pink-500",
  single_agent: "border-l-gray-500",
  interview: "border-l-teal-500",
};

export default function OperationFeed() {
  const [events, setEvents] = useState<OperationEvent[]>([]);
  const [history, setHistory] = useState<OperationEvent[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(true);
  const [filter, setFilter] = useState<string>("all");
  const feedRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api
      .get<{ data?: { items?: OperationEvent[] } }>("/operations?limit=20")
      .then((res) => {
        setHistory(res?.data?.items || []);
      })
      .catch(() => {
        void 0;
      })
      .finally(() => setLoadingHistory(false));
  }, []);

  const { connected, subscribe } = useEventSource("/operations/stream");

  useEffect(() => {
    const unsub = subscribe("operation", (data) => {
      const ev = data as OperationEvent;
      if (!ev?.operation_id) return;
      setEvents((prev) => [ev, ...prev].slice(0, 100));
    });
    return unsub;
  }, [subscribe]);

  useEffect(() => {
    if (feedRef.current) {
      feedRef.current.scrollTop = 0;
    }
  });

  const filtered = filter === "all"
    ? events
    : events.filter((e) => e.status === filter);

  const allItems = [...filtered, ...history.filter(
    (h) => !events.find((e) => e.operation_id === h.operation_id),
  )].slice(0, 50);

  if (!connected && events.length === 0 && history.length === 0) {
    return (
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center gap-2">
            <Activity className="h-4 w-4 text-muted-foreground" />
            <CardTitle className="text-base">Agent 操作记录</CardTitle>
          </div>
        </CardHeader>
        <CardContent>
          {loadingHistory ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : (
            <p className="py-4 text-center text-sm text-muted-foreground">暂无操作记录</p>
          )}
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Activity className="h-4 w-4 text-muted-foreground" />
            <CardTitle className="text-base">Agent 操作记录</CardTitle>
            <Badge variant={connected ? "default" : "secondary"} className="ml-1 text-[10px]">
              {connected ? "实时" : "离线"}
            </Badge>
          </div>
          <div className="flex items-center gap-1">
            <select
              className="h-7 rounded border bg-transparent px-2 text-xs outline-none"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
            >
              <option value="all">全部</option>
              <option value="running">运行中</option>
              <option value="completed">已完成</option>
              <option value="failed">失败</option>
              <option value="awaiting_approval">待审批</option>
            </select>
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7"
              onClick={() => { setEvents([]); setHistory([]); setLoadingHistory(true); }}
            >
              <RotateCcw className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="p-0">
        <div ref={feedRef} className="max-h-[400px] overflow-y-auto">
          {allItems.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">暂无操作</p>
          ) : (
            <div className="divide-y">
              {allItems.map((ev) => {
                const sc = statusConfig[ev.status] || statusConfig.pending;
                const StatusIcon = sc.icon;
                const agentColor = agentColors[ev.agent_name] || "border-l-gray-400";
                return (
                  <div key={ev.operation_id} className={`border-l-2 ${agentColor} px-4 py-3 transition-colors hover:bg-accent/30`}>
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2 min-w-0">
                        <StatusIcon className={`h-3.5 w-3.5 shrink-0 ${ev.status === "running" ? "animate-spin" : ""}`} />
                        <span className="truncate text-sm font-medium">{ev.action}</span>
                        <Badge variant="outline" className="text-[10px] shrink-0">{ev.agent_name}</Badge>
                      </div>
                      <Badge className={`shrink-0 text-[10px] ${sc.color}`}>{sc.label}</Badge>
                    </div>
                    {ev.output_summary && ev.status === "completed" && (
                      <p className="mt-1 truncate text-xs text-muted-foreground">{ev.output_summary}</p>
                    )}
                    {ev.error_message && ev.status === "failed" && (
                      <p className="mt-1 truncate text-xs text-red-500">{ev.error_message}</p>
                    )}
                    <div className="mt-1 flex items-center gap-2 text-[10px] text-muted-foreground/60">
                      <span>{ev.timestamp ? new Date(ev.timestamp).toLocaleTimeString("zh-CN") : ""}</span>
                      {ev.duration_ms != null && <span>{ev.duration_ms.toFixed(0)}ms</span>}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
