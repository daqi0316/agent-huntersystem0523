"use client";

import { useState, useEffect } from "react";
import {
  Activity, CheckCircle2, XCircle, AlertCircle, Clock,
  TrendingUp, AlertTriangle,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/separator";
import { api } from "@/lib/trpc";

interface AgentSummary {
  agent_name: string;
  total_ops: number;
  success_count: number;
  fail_count: number;
  system_error_count: number;
  success_rate: number;
  avg_duration_ms: number;
}

interface OverallSummary {
  total_ops: number;
  success_rate: number;
  system_errors: number;
  period_hours: number;
}

interface SummaryResponse {
  success: boolean;
  data: {
    overall: OverallSummary;
    agents: AgentSummary[];
  };
}

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

export default function AIHealth() {
  const [summary, setSummary] = useState<SummaryResponse["data"] | null>(null);
  const [loading, setLoading] = useState(true);
  const [warning, setWarning] = useState<string | null>(null);

  useEffect(() => {
    api.get<SummaryResponse>("/dashboard/operations/summary")
      .then((res) => {
        if (res?.success) {
          setSummary(res.data);
          if (res.data.overall.system_errors > 0) {
            setWarning(`${res.data.overall.system_errors} 次系统级错误`);
          }
          const lowRate = res.data.agents.find((a) => a.success_rate < 60 && a.total_ops > 5);
          if (lowRate) {
            setWarning((prev) => [prev, `${lowRate.agent_name} 成功率 ${lowRate.success_rate}%`].filter(Boolean).join("；"));
          }
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <Card>
        <CardHeader className="pb-3">
          <Skeleton className="h-5 w-32" />
        </CardHeader>
        <CardContent className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-12 w-full" />
          ))}
        </CardContent>
      </Card>
    );
  }

  if (!summary || summary.overall.total_ops === 0) return null;

  const { overall, agents } = summary;
  const rateColor = overall.success_rate >= 80 ? "text-green-600" : overall.success_rate >= 60 ? "text-amber-600" : "text-red-600";

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Activity className="h-4 w-4 text-muted-foreground" />
            <CardTitle className="text-base">AI 健康</CardTitle>
            <Badge variant="outline" className="text-[10px]">最近 24h</Badge>
          </div>
          {warning && (
            <Badge variant="destructive" className="text-[10px] animate-pulse">
              <AlertTriangle className="mr-1 h-3 w-3" /> {warning}
            </Badge>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-3 gap-3 text-center">
          <div className="rounded-lg bg-muted/50 p-2">
            <p className="text-2xl font-bold">{overall.total_ops}</p>
            <p className="text-[10px] text-muted-foreground">操作总数</p>
          </div>
          <div className="rounded-lg bg-muted/50 p-2">
            <p className={`text-2xl font-bold ${rateColor}`}>{overall.success_rate}%</p>
            <p className="text-[10px] text-muted-foreground">成功率</p>
          </div>
          <div className="rounded-lg bg-muted/50 p-2">
            <p className={`text-2xl font-bold ${overall.system_errors > 0 ? "text-red-600" : "text-green-600"}`}>
              {overall.system_errors}
            </p>
            <p className="text-[10px] text-muted-foreground">系统错误</p>
          </div>
        </div>

        <Separator />

        <div className="space-y-2">
          {agents.map((agent) => {
            const color = agentColors[agent.agent_name] || "border-l-gray-400";
            const agentRateColor = agent.success_rate >= 80 ? "text-green-600" : agent.success_rate >= 60 ? "text-amber-600" : "text-red-600";
            return (
              <div key={agent.agent_name} className={`border-l-2 ${color} flex items-center justify-between pl-3`}>
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">{agent.agent_name}</p>
                  <p className="text-[10px] text-muted-foreground">
                    {agent.total_ops} 次操作 · {agent.avg_duration_ms}ms
                  </p>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  {agent.system_error_count > 0 && (
                    <AlertCircle className="h-3.5 w-3.5 text-red-500" />
                  )}
                  <span className={`text-sm font-bold ${agentRateColor}`}>{agent.success_rate}%</span>
                </div>
              </div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}
