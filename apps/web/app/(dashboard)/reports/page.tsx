"use client";

import { useState, useEffect } from "react";
import { Loader2, AlertCircle, TrendingUp, Users, Briefcase, UserCheck } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/trpc";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend,
  AreaChart, Area,
} from "recharts";

interface ApiResponse {
  success: boolean;
  data?: { total: number };
  total?: number;
}

const funnelData = [
  { stage: "简历收到", count: 120 },
  { stage: "初筛通过", count: 85 },
  { stage: "面试邀约", count: 52 },
  { stage: "面试完成", count: 38 },
  { stage: "发放Offer", count: 15 },
  { stage: "已入职", count: 8 },
];

const sourceData = [
  { name: "内部推荐", value: 35, color: "#3b82f6" },
  { name: "招聘网站", value: 30, color: "#8b5cf6" },
  { name: "校园招聘", value: 15, color: "#06b6d4" },
  { name: "社交媒体", value: 12, color: "#22c55e" },
  { name: "猎头", value: 8, color: "#f59e0b" },
];

const monthlyTrend = [
  { month: "12月", hires: 3 },
  { month: "1月", hires: 5 },
  { month: "2月", hires: 2 },
  { month: "3月", hires: 7 },
  { month: "4月", hires: 4 },
  { month: "5月", hires: 6 },
];

interface KpiItem {
  label: string; key: string; icon: typeof Users; color: string; value: number;
}

const defaultKpis: KpiItem[] = [
  { label: "总候选人", key: "candidates", icon: Users, color: "text-blue-600", value: 128 },
  { label: "活跃职位", key: "jobs", icon: Briefcase, color: "text-violet-600", value: 8 },
  { label: "面试中", key: "interviewing", icon: TrendingUp, color: "text-amber-600", value: 14 },
  { label: "已录用", key: "hired", icon: UserCheck, color: "text-green-600", value: 6 },
];

function sourceColor(name: string): string {
  const colors: Record<string, string> = {
    "内部推荐": "#3b82f6", "招聘网站": "#8b5cf6", "校园招聘": "#06b6d4",
    "社交媒体": "#22c55e", "猎头": "#f59e0b", "主动投递": "#ef4444",
    "猎头推荐": "#f59e0b",
  };
  return colors[name] || "#6b7280";
}

export default function ReportsPage() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [kpis, setKpis] = useState<KpiItem[]>(defaultKpis);

  useEffect(() => {
    (async () => {
      try {
        const [candRes, jobRes, reportRes] = await Promise.allSettled([
          api.get<ApiResponse>("/candidates"),
          api.get<ApiResponse>("/jobs"),
          api.get<{ success: boolean; data: { funnel: { stage: string; count: number }[]; sources: { name: string; count: number }[]; trend: { date: string; count: number }[] } }>("/dashboard/reports"),
        ]);
        const candTotal = candRes.status === "fulfilled" ? candRes.value.data?.total ?? candRes.value.total ?? 128 : 128;
        const jobTotal = jobRes.status === "fulfilled" ? jobRes.value.data?.total ?? jobRes.value.total ?? 8 : 8;

        if (reportRes.status === "fulfilled" && reportRes.value.success) {
          const r = reportRes.value.data;
          if (r) {
            funnelData.length = 0;
            funnelData.push(...r.funnel.map((f) => ({ stage: f.stage, count: f.count })));
            sourceData.length = 0;
            sourceData.push(...r.sources.map((s) => ({ name: s.name, value: s.count, color: sourceColor(s.name) })));
            monthlyTrend.length = 0;
            monthlyTrend.push(...r.trend.map((t) => ({ month: t.date, hires: t.count })));
          }
        }

        setKpis([
          { label: "总候选人", key: "candidates", icon: Users, color: "text-blue-600", value: candTotal },
          { label: "活跃职位", key: "jobs", icon: Briefcase, color: "text-violet-600", value: jobTotal },
          { label: "面试中", key: "interviewing", icon: TrendingUp, color: "text-amber-600", value: 14 },
          { label: "已录用", key: "hired", icon: UserCheck, color: "text-green-600", value: 6 },
        ] as KpiItem[]);
      } catch {
        setError("使用模拟数据展示");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  if (loading) {
    return (
      <div className="flex h-96 items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">数据报表</h1>
          <p className="text-muted-foreground">招聘数据统计与趋势分析</p>
        </div>
        {error && (
          <Badge variant="warning" className="gap-1">
            <AlertCircle className="h-3 w-3" />
            {error}
          </Badge>
        )}
      </div>

      <div className="grid gap-4 md:grid-cols-4">
        {kpis.map((k) => {
          const Icon = k.icon;
          return (
            <Card key={k.key}>
              <CardHeader className="flex flex-row items-center justify-between pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground">{k.label}</CardTitle>
                <Icon className={`h-4 w-4 ${k.color}`} />
              </CardHeader>
              <CardContent>
                <p className="text-3xl font-bold">{k.value}</p>
              </CardContent>
            </Card>
          );
        })}
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">招聘漏斗</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={funnelData} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                  <XAxis type="number" tick={{ fontSize: 12 }} stroke="#94a3b8" />
                  <YAxis dataKey="stage" type="category" tick={{ fontSize: 12 }} stroke="#94a3b8" width={90} />
                  <Tooltip />
                  <Bar dataKey="count" fill="#3b82f6" radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">候选人来源</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={sourceData} cx="50%" cy="50%" innerRadius={60} outerRadius={100} dataKey="value" label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}>
                    {sourceData.map((entry, i) => <Cell key={i} fill={entry.color} />)}
                  </Pie>
                  <Tooltip />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">月度录用趋势</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={monthlyTrend}>
                <defs>
                  <linearGradient id="hireFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#22c55e" stopOpacity={0.2} />
                    <stop offset="100%" stopColor="#22c55e" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                <XAxis dataKey="month" tick={{ fontSize: 12 }} stroke="#94a3b8" />
                <YAxis tick={{ fontSize: 12 }} stroke="#94a3b8" />
                <Tooltip />
                <Area type="monotone" dataKey="hires" stroke="#22c55e" strokeWidth={2} fill="url(#hireFill)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
