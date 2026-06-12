"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity, BarChart3, CheckCircle, Database, FlaskConical, MessageSquare,
  TrendingUp, AlertTriangle, BugPlay, DollarSign, Shield,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorAlert } from "@/components/common/error-alert";
import { api } from "@/lib/trpc";
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  BarChart, Bar, PieChart, Pie, Cell, Legend,
} from "recharts";

const SUB_NAV = [
  { href: "/agentops", label: "概览", icon: BarChart3 },
  { href: "/agentops/debug", label: "Debug", icon: BugPlay },
  { href: "/agentops/cost", label: "成本", icon: DollarSign },
  { href: "/agentops/governance", label: "治理", icon: Shield },
];

function AgentOpsNav() {
  const pathname = usePathname();
  return (
    <nav className="flex gap-1 border-b pb-2 mb-6">
      {SUB_NAV.map((item) => {
        const active = pathname === item.href || (item.href !== "/agentops" && pathname.startsWith(item.href));
        return (
          <Link
            key={item.href}
            href={item.href}
            className={`flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-md transition-colors ${
              active
                ? "bg-primary/10 text-primary font-medium"
                : "text-muted-foreground hover:bg-muted"
            }`}
          >
            <item.icon className="h-4 w-4" />
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}

interface Overview {
  total_experiments: number;
  total_runs: number;
  total_dataset_items: number;
  total_feedback: number;
}

interface CategoryScore {
  [key: string]: number;
}

interface QualitySummary {
  avg_score: number;
  pass_rate: number;
  total_runs: number;
  total_items: number;
  completed_experiments: number;
  category_scores: CategoryScore;
  passed_items?: number;
  failed_items?: number;
}

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

interface FeedbackSummary {
  total: number;
  by_category: Record<string, { avg_score: number; count: number }>;
}

const COLORS = ["#10b981", "#3b82f6", "#f59e0b", "#ef4444", "#8b5cf6", "#ec4899"];

export default function AgentOpsDashboard() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [quality, setQuality] = useState<QualitySummary | null>(null);
  const [recentRuns, setRecentRuns] = useState<RecentRun[]>([]);
  const [feedback, setFeedback] = useState<FeedbackSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const [ov, ql, rr, fb] = await Promise.all([
          api.get<Overview>("/dashboard/agentops/overview"),
          api.get<QualitySummary>("/dashboard/agentops/quality"),
          api.get<RecentRun[]>("/dashboard/agentops/recent-runs?limit=10"),
          api.get<FeedbackSummary>("/dashboard/agentops/feedback"),
        ]);
        setOverview(ov);
        setQuality(ql);
        setRecentRuns(rr || []);
        setFeedback(fb);
      } catch (err) {
        setError(err instanceof Error ? err.message : "加载失败");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  if (error) return <ErrorAlert message={error} />;

  // ── KPI 卡片 ──
  const kpis = overview
    ? [
        { label: "实验次数", value: overview.total_experiments, icon: FlaskConical, color: "text-blue-600" },
        { label: "运行次数", value: overview.total_runs, icon: Activity, color: "text-green-600" },
        { label: "数据集项", value: overview.total_dataset_items, icon: Database, color: "text-purple-600" },
        { label: "反馈总数", value: overview.total_feedback, icon: MessageSquare, color: "text-orange-600" },
      ]
    : [];

  // ── 质量分数图表 ──
  const qualityChartData = quality
    ? Object.entries(quality.category_scores).map(([name, score]) => ({
        name,
        score: +(score * 100).toFixed(1),
      }))
    : [];

  // ── 通过率饼图 ──
  const passPieData = quality
    ? [
        { name: "通过", value: quality.passed_items ?? (quality.total_items - (quality.total_items * (1 - quality.pass_rate))) },
        { name: "失败", value: quality.failed_items ?? (quality.total_items * (1 - quality.pass_rate)) },
      ]
    : [];

  return (
    <div className="space-y-6 p-6">
      <AgentOpsNav />
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">AgentOps 监控</h1>
        <span className="text-sm text-muted-foreground">
          {loading ? "加载中..." : `更新于 ${new Date().toLocaleTimeString()}`}
        </span>
      </div>

      {/* KPI 卡片 */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {loading
          ? Array.from({ length: 4 }).map((_, i) => (
              <Card key={i}>
                <CardHeader className="flex flex-row items-center justify-between pb-2">
                  <Skeleton className="h-4 w-24" />
                  <Skeleton className="h-4 w-4" />
                </CardHeader>
                <CardContent>
                  <Skeleton className="h-8 w-16" />
                </CardContent>
              </Card>
            ))
          : kpis.map((kpi) => (
              <Card key={kpi.label}>
                <CardHeader className="flex flex-row items-center justify-between pb-2">
                  <CardTitle className="text-sm font-medium">{kpi.label}</CardTitle>
                  <kpi.icon className={`h-4 w-4 ${kpi.color}`} />
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold">{kpi.value}</div>
                </CardContent>
              </Card>
            ))}
      </div>

      {/* 质量概览 */}
      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">质量分数</CardTitle>
          </CardHeader>
          <CardContent>
            {loading ? (
              <Skeleton className="h-64 w-full" />
            ) : qualityChartData.length > 0 ? (
              <ResponsiveContainer width="100%" height={250}>
                <BarChart data={qualityChartData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="name" />
                  <YAxis domain={[0, 100]} />
                  <Tooltip />
                  <Bar dataKey="score" fill="#3b82f6" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <p className="text-sm text-muted-foreground">暂无数据</p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-lg">通过率</CardTitle>
          </CardHeader>
          <CardContent>
            {loading ? (
              <Skeleton className="h-64 w-full" />
            ) : quality ? (
              <div className="space-y-4">
                <div className="flex items-center justify-center">
                  <span className="text-4xl font-bold">{(quality.pass_rate * 100).toFixed(1)}%</span>
                </div>
                <div className="grid grid-cols-2 gap-2 text-center text-sm">
                  <div>
                    <span className="text-muted-foreground">总分</span>
                    <p className="text-lg font-semibold">{(quality.avg_score * 100).toFixed(1)}</p>
                  </div>
                  <div>
                    <span className="text-muted-foreground">实验数</span>
                    <p className="text-lg font-semibold">{quality.completed_experiments}</p>
                  </div>
                  <div>
                    <span className="text-muted-foreground">运行次数</span>
                    <p className="text-lg font-semibold">{quality.total_runs}</p>
                  </div>
                  <div>
                    <span className="text-muted-foreground">总用例</span>
                    <p className="text-lg font-semibold">{quality.total_items}</p>
                  </div>
                </div>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">暂无数据</p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* 最近运行 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">最近实验运行</CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <Skeleton className="h-32 w-full" />
          ) : recentRuns.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-muted-foreground">
                    <th className="pb-2 font-medium">实验名称</th>
                    <th className="pb-2 font-medium">状态</th>
                    <th className="pb-2 font-medium">平均分</th>
                    <th className="pb-2 font-medium">通过率</th>
                    <th className="pb-2 font-medium">耗时</th>
                  </tr>
                </thead>
                <tbody>
                  {recentRuns.map((run) => (
                    <tr key={run.run_id} className="border-b last:border-0">
                      <td className="py-2">{run.experiment_name}</td>
                      <td className="py-2">
                        <span className={`inline-flex items-center gap-1 ${
                          run.status === "completed" ? "text-green-600" : "text-yellow-600"
                        }`}>
                          {run.status === "completed" ? <CheckCircle className="h-3 w-3" /> : <AlertTriangle className="h-3 w-3" />}
                          {run.status}
                        </span>
                      </td>
                      <td className="py-2">{(run.avg_score * 100).toFixed(1)}</td>
                      <td className="py-2">
                        {run.total_items > 0
                          ? ((run.passed_items / run.total_items) * 100).toFixed(0) + "%"
                          : "-"}
                      </td>
                      <td className="py-2">{(run.duration_ms / 1000).toFixed(1)}s</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">暂无运行记录</p>
          )}
        </CardContent>
      </Card>

      {/* 反馈汇总 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">反馈汇总</CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <Skeleton className="h-24 w-full" />
          ) : feedback ? (
            <div className="space-y-2">
              <p className="text-sm text-muted-foreground">共 {feedback.total} 条反馈</p>
              {feedback.by_category && Object.keys(feedback.by_category).length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b text-left text-muted-foreground">
                        <th className="pb-2 font-medium">分类</th>
                        <th className="pb-2 font-medium">条数</th>
                        <th className="pb-2 font-medium">平均分</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(feedback.by_category).map(([cat, stats]) => (
                        <tr key={cat} className="border-b last:border-0">
                          <td className="py-2">{cat}</td>
                          <td className="py-2">{stats.count}</td>
                          <td className="py-2">{(stats.avg_score * 100).toFixed(1)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">暂无分类数据</p>
              )}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">暂无数据</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
