"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { RefreshCw, AlertCircle, CheckCircle2, Clock, FileText, Users, BarChart3 } from "lucide-react";

type ImportRecord = {
  id: string;
  entity_type: string;
  status: string;
  file_name: string | null;
  total: number | null;
  imported: number | null;
  failed: number | null;
  started_at: string | null;
  completed_at: string | null;
};

type HealthScore = {
  org_id: string;
  total_score: number;
  risk_level: string;
  breakdown: { login: number; feature: number; support: number; referral: number };
  metrics: Record<string, number> | null;
  computed_at: string;
};

const STATUS_MAP: Record<string, { label: string; color: "default" | "secondary" | "destructive" | "outline" }> = {
  completed: { label: "已完成", color: "default" },
  partial: { label: "部分成功", color: "secondary" },
  failed: { label: "失败", color: "destructive" },
  processing: { label: "处理中", color: "outline" },
};

const ENTITY_LABEL: Record<string, string> = {
  candidate: "候选人",
  job_position: "职位",
};

const RISK_MAP: Record<string, { label: string; color: "default" | "secondary" | "destructive" | "outline" }> = {
  healthy: { label: "健康", color: "default" },
  at_risk: { label: "需关注", color: "secondary" },
  high_risk: { label: "高风险", color: "destructive" },
};

export default function OnboardingDashboardPage() {
  const [imports, setImports] = useState<ImportRecord[]>([]);
  const [healthScore, setHealthScore] = useState<HealthScore | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  async function loadData() {
    setLoading(true);
    try {
      const [importRes, healthRes] = await Promise.all([
        api.get<{ data: ImportRecord[] }>("/onboarding/imports?limit=50"),
        api.get<{ data: HealthScore }>("/onboarding/health-score"),
      ]);
      setImports(importRes.data || []);
      setHealthScore(healthRes.data || null);
    } finally {
      setLoading(false);
    }
  }

  async function refreshHealthScore() {
    setRefreshing(true);
    try {
      const res = await api.post<{ data: HealthScore }>("/onboarding/health-score/refresh", {});
      setHealthScore(res.data || null);
    } finally {
      setRefreshing(false);
    }
  }

  useEffect(() => {
    loadData();
  }, []);

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">
            客户导入中心
          </h1>
          <p className="text-muted-foreground">
            批量导入记录 · 客户健康度看板
          </p>
        </div>
      </div>

      {/* 健康度卡片 */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card className="md:col-span-3">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">健康度评分</CardTitle>
            <Button variant="outline" size="sm" onClick={refreshHealthScore} disabled={refreshing}>
              <RefreshCw className={`h-3 w-3 mr-1 ${refreshing ? "animate-spin" : ""}`} />
              刷新
            </Button>
          </CardHeader>
          <CardContent>
            {loading && !healthScore ? (
              <p className="text-sm text-muted-foreground">加载中...</p>
            ) : healthScore ? (
              <div className="space-y-4">
                <div className="flex items-center gap-4">
                  <div className="text-4xl font-bold">{Math.round(healthScore.total_score)}</div>
                  <Badge variant={RISK_MAP[healthScore.risk_level]?.color || "outline"}>
                    {RISK_MAP[healthScore.risk_level]?.label || healthScore.risk_level}
                  </Badge>
                </div>
                <div className="grid grid-cols-4 gap-4 text-sm">
                  <div>
                    <p className="text-muted-foreground">登录频次 (40%)</p>
                    <p className="font-medium">{Math.round(healthScore.breakdown.login)}</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">功能使用 (30%)</p>
                    <p className="font-medium">{Math.round(healthScore.breakdown.feature)}</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">支持评分 (20%)</p>
                    <p className="font-medium">{Math.round(healthScore.breakdown.support)}</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">推荐行为 (10%)</p>
                    <p className="font-medium">{Math.round(healthScore.breakdown.referral)}</p>
                  </div>
                </div>
                {healthScore.metrics && (
                  <div className="text-xs text-muted-foreground">
                    用户: {healthScore.metrics.total_users ?? "?"} · 
                    7d 活跃: {healthScore.metrics.active_users_7d ?? "?"} · 
                    审计事件: {healthScore.metrics.audit_events_7d ?? "?"} · 
                    邀请: {healthScore.metrics.invites_30d ?? "?"}
                  </div>
                )}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">暂无数据，请先导入数据</p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">导入概览</CardTitle>
          </CardHeader>
          <CardContent>
            {loading ? (
              <p className="text-sm text-muted-foreground">加载中...</p>
            ) : (
              <div className="space-y-3 text-sm">
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">总导入</span>
                  <span className="font-medium">{imports.length}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">成功</span>
                  <span className="font-medium text-green-600">
                    {imports.filter(i => i.status === "completed").length}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">部分成功</span>
                  <span className="font-medium text-yellow-600">
                    {imports.filter(i => i.status === "partial").length}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">失败</span>
                  <span className="font-medium text-red-600">
                    {imports.filter(i => i.status === "failed").length}
                  </span>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* 导入历史表 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-medium">导入历史</CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <p className="text-sm text-muted-foreground">加载中...</p>
          ) : imports.length === 0 ? (
            <p className="text-sm text-muted-foreground">暂无导入记录</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-muted-foreground">
                    <th className="pb-2 pr-4 font-medium">类型</th>
                    <th className="pb-2 pr-4 font-medium">状态</th>
                    <th className="pb-2 pr-4 font-medium">总计</th>
                    <th className="pb-2 pr-4 font-medium">成功</th>
                    <th className="pb-2 pr-4 font-medium">失败</th>
                    <th className="pb-2 pr-4 font-medium">开始时间</th>
                  </tr>
                </thead>
                <tbody>
                  {imports.map((row) => {
                    const st = STATUS_MAP[row.status] || { label: row.status, color: "outline" };
                    return (
                      <tr key={row.id} className="border-b last:border-0 hover:bg-muted/50">
                        <td className="py-2 pr-4">
                          <div className="flex items-center gap-1">
                            {row.entity_type === "candidate" ? (
                              <Users className="h-3 w-3" />
                            ) : (
                              <FileText className="h-3 w-3" />
                            )}
                            {ENTITY_LABEL[row.entity_type] || row.entity_type}
                          </div>
                        </td>
                        <td className="py-2 pr-4">
                          <Badge variant={st.color}>{st.label}</Badge>
                        </td>
                        <td className="py-2 pr-4">{row.total ?? "-"}</td>
                        <td className="py-2 pr-4 text-green-600">{row.imported ?? "-"}</td>
                        <td className="py-2 pr-4 text-red-600">{row.failed ?? "-"}</td>
                        <td className="py-2 pr-4 text-muted-foreground">
                          {row.started_at ? new Date(row.started_at).toLocaleString("zh-CN") : "-"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
