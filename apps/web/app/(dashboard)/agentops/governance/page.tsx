"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { Shield, CheckCircle, XCircle, Clock, Users, Eye } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorAlert } from "@/components/common/error-alert";
import { api } from "@/lib/trpc";

interface Overview {
  total_experiments: number;
  total_runs: number;
  total_dataset_items: number;
  total_feedback: number;
}

interface FeedbackSummary {
  total: number;
  by_category: Record<string, { avg_score: number; count: number }>;
}

export default function GovernancePage() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [feedback, setFeedback] = useState<FeedbackSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const [ov, fb] = await Promise.all([
          api.get<Overview>("/dashboard/agentops/overview"),
          api.get<FeedbackSummary>("/dashboard/agentops/feedback"),
        ]);
        setOverview(ov);
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

  return (
    <div className="space-y-6 p-6">
      <nav className="flex gap-1 border-b pb-2 mb-2">
        <Link href="/agentops" className="px-3 py-1.5 text-sm rounded-md text-muted-foreground hover:bg-muted">概览</Link>
        <Link href="/agentops/debug" className="px-3 py-1.5 text-sm rounded-md text-muted-foreground hover:bg-muted">Debug</Link>
        <Link href="/agentops/cost" className="px-3 py-1.5 text-sm rounded-md text-muted-foreground hover:bg-muted">成本</Link>
        <Link href="/agentops/governance" className="px-3 py-1.5 text-sm rounded-md bg-primary/10 text-primary font-medium">治理</Link>
      </nav>

      <h1 className="text-2xl font-bold">治理后台</h1>

      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">实验数</CardTitle>
            <Shield className="h-4 w-4 text-blue-600" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{overview?.total_experiments || 0}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">运行数</CardTitle>
            <Clock className="h-4 w-4 text-green-600" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{overview?.total_runs || 0}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">数据集</CardTitle>
            <Users className="h-4 w-4 text-purple-600" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{overview?.total_dataset_items || 0}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">反馈</CardTitle>
            <Eye className="h-4 w-4 text-orange-600" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{overview?.total_feedback || 0}</div>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        {/* 采样规则摘要 */}
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">采样规则</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">默认采样率</span>
              <span className="font-mono">10%</span>
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">错误全采</span>
              <CheckCircle className="h-4 w-4 text-green-600" />
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">慢查询阈值</span>
              <span className="font-mono">5000ms</span>
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">Agent 覆盖</span>
              <span className="text-xs text-muted-foreground">screening: 100%</span>
            </div>
          </CardContent>
        </Card>

        {/* 隐私策略摘要 */}
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">隐私策略</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">简历全文</span>
              <span className="text-xs font-mono text-red-600">DROP</span>
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">邮箱/手机</span>
              <span className="text-xs font-mono text-yellow-600">HASH</span>
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">姓名/地址</span>
              <span className="text-xs font-mono text-yellow-600">MASK</span>
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">工具名/分数</span>
              <span className="text-xs font-mono text-green-600">ALLOW</span>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* 反馈分类分布 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">反馈分布</CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <Skeleton className="h-24 w-full" />
          ) : feedback && Object.keys(feedback.by_category).length > 0 ? (
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
            <p className="text-sm text-muted-foreground">暂无数据</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
