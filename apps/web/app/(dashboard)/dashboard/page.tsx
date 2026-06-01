"use client";

import { useState, useEffect } from "react";
import {
  TrendingUp, Users, Briefcase, Activity, ArrowUpRight,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { ErrorAlert } from "@/components/common/error-alert";
import RecommendationSection from "@/components/features/recommendations/recommendation-section";
import OperationFeed from "@/components/features/operations/operation-feed";
import AIHealth from "@/components/features/monitoring/ai-health";
import { api } from "@/lib/trpc";
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from "recharts";

interface KpiItem {
  label: string;
  value: number;
  key: string;
}

interface TrendPoint {
  date: string;
  count: number;
}

interface ActivityItem {
  time: string;
  text: string;
  type: string;
}

interface DashboardStats {
  kpis: KpiItem[];
  trend: TrendPoint[];
  recent_activities: ActivityItem[];
}

const fallbackStats: DashboardStats = {
  kpis: [
    { label: "候选人总数", value: 128, key: "candidates" },
    { label: "招聘职位", value: 8, key: "jobs" },
    { label: "进行中面试", value: 14, key: "interviews" },
    { label: "本月入职", value: 3, key: "onboards" },
  ],
  trend: [
    { date: "05-01", count: 12 }, { date: "05-03", count: 8 },
    { date: "05-05", count: 15 }, { date: "05-07", count: 10 },
    { date: "05-09", count: 20 }, { date: "05-11", count: 18 },
    { date: "05-13", count: 25 }, { date: "05-15", count: 22 },
    { date: "05-17", count: 30 }, { date: "05-19", count: 28 },
    { date: "05-21", count: 35 }, { date: "05-23", count: 32 },
  ],
  recent_activities: [
    { time: "09:45", text: "王芳 完成 AI 初筛评估（得分 87）", type: "eval" },
    { time: "10:12", text: "张明 的面试已确认 — 明天 14:00", type: "interview" },
    { time: "11:00", text: "新增候选人 陈静 投递「高级前端工程师」", type: "apply" },
    { time: "13:30", text: "李华 的评估报告已生成", type: "eval" },
    { time: "14:15", text: "赵岩 收到 Offer（后端架构师）", type: "offer" },
    { time: "15:00", text: "系统完成对 12 份简历的初筛", type: "system" },
  ],
};

const iconMap: Record<string, { icon: typeof Users; color: string }> = {
  candidates: { icon: Users, color: "text-blue-600" },
  jobs: { icon: Briefcase, color: "text-violet-600" },
  interviews: { icon: Activity, color: "text-amber-600" },
  onboards: { icon: TrendingUp, color: "text-green-600" },
};

export default function DashboardPage() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [stats, setStats] = useState<DashboardStats>(fallbackStats);

  useEffect(() => {
    (async () => {
      try {
        const res = await api.get<DashboardStats>("/dashboard/stats");
        if (res) {
          setStats({
            kpis: res.kpis || fallbackStats.kpis,
            trend: res.trend || fallbackStats.trend,
            recent_activities: res.recent_activities || fallbackStats.recent_activities,
          });
        }
      } catch {
        setError("无法连接后端服务，展示模拟数据");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  if (loading) {
    return (
      <div className="space-y-6 p-6">
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Card key={i}>
              <CardHeader className="pb-2">
                <Skeleton className="h-4 w-24" />
              </CardHeader>
              <CardContent>
                <Skeleton className="h-8 w-16" />
              </CardContent>
            </Card>
          ))}
        </div>
        <div className="grid gap-6 lg:grid-cols-3">
          <Card className="lg:col-span-2">
            <CardHeader><Skeleton className="h-5 w-40" /></CardHeader>
            <CardContent><Skeleton className="h-72 w-full" /></CardContent>
          </Card>
          <Card>
            <CardHeader><Skeleton className="h-5 w-24" /></CardHeader>
            <CardContent className="space-y-3">
              {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-10 w-full" />)}
            </CardContent>
          </Card>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">数据看板</h1>
          <p className="text-muted-foreground">招聘数据总览与核心指标</p>
        </div>
        {error && <ErrorAlert message={error} variant="warning" />}
      </div>

      {/* KPI Cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {stats.kpis.map((k) => {
          const cfg = iconMap[k.key] || { icon: Users, color: "text-muted-foreground" };
          const Icon = cfg.icon;
          return (
            <Card key={k.key}>
              <CardHeader className="flex flex-row items-center justify-between pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground">
                  {k.label}
                </CardTitle>
                <Icon className={`h-4 w-4 ${cfg.color}`} />
              </CardHeader>
              <CardContent>
                <div className="flex items-baseline gap-2">
                  <span className="text-3xl font-bold">{k.value}</span>
                  <ArrowUpRight className={`h-4 w-4 ${cfg.color}`} />
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* AI Health */}
        <AIHealth />

        {/* Trend Chart */}
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="text-base">近 30 天候选人趋势</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={stats.trend}>
                  <defs>
                    <linearGradient id="trendFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#3b82f6" stopOpacity={0.2} />
                      <stop offset="100%" stopColor="#3b82f6" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                  <XAxis dataKey="date" tick={{ fontSize: 12 }} stroke="#94a3b8" />
                  <YAxis tick={{ fontSize: 12 }} stroke="#94a3b8" />
                  <Tooltip />
                  <Area
                    type="monotone"
                    dataKey="count"
                    stroke="#3b82f6"
                    strokeWidth={2}
                    fill="url(#trendFill)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>

        <OperationFeed />
      </div>
    </div>
  );
}
