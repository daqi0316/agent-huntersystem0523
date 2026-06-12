"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import {
  DollarSign, TrendingUp, Cpu, BarChart3, Users,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorAlert } from "@/components/common/error-alert";
import { api } from "@/lib/trpc";
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Legend, PieChart, Pie, Cell,
} from "recharts";

/* ── 类型定义 ── */

interface Summary {
  total_cost: number;
  total_tokens: number;
  total_calls: number;
  avg_duration_ms: number;
  today_cost: number;
  today_tokens: number;
  today_calls: number;
  model_count: number;
  currency: string;
}

interface DailyPoint {
  date: string;
  calls: number;
  total_tokens: number;
  prompt_tokens: number;
  completion_tokens: number;
  cost: number;
  avg_duration_ms: number;
}

interface Timeseries {
  daily: DailyPoint[];
  summary: {
    total_cost: number;
    total_tokens: number;
    total_calls: number;
    currency: string;
  };
}

interface ModelStat {
  model: string;
  calls: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  cost: number;
  avg_duration_ms: number;
}

interface UserStat {
  user_id: string;
  calls: number;
  total_tokens: number;
  cost: number;
}

interface ModelPricing {
  model: string;
  input_token_cost_per_1k: number;
  output_token_cost_per_1k: number;
  currency: string;
}

const COLORS = ["#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#ec4899", "#14b8a6", "#f97316"];

function fmtCost(v: number): string {
  if (v >= 1) return `$${v.toFixed(2)}`;
  if (v >= 0.001) return `$${(v * 1000).toFixed(2)}m`;
  return `$${(v * 1000000).toFixed(2)}µ`;
}

function fmtTokens(v: number): string {
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000) return `${(v / 1_000).toFixed(1)}K`;
  return String(v);
}

export default function CostDashboard() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [timeseries, setTimeseries] = useState<Timeseries | null>(null);
  const [byModel, setByModel] = useState<ModelStat[]>([]);
  const [byUser, setByUser] = useState<UserStat[]>([]);
  const [pricing, setPricing] = useState<ModelPricing[]>([]);
  const [days, setDays] = useState(30);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const [s, ts, bm, bu, pr] = await Promise.all([
          api.get<Summary>(`/dashboard/agentops/cost/summary?days=${days}`),
          api.get<Timeseries>(`/dashboard/agentops/cost/timeseries?days=${days}`),
          api.get<ModelStat[]>(`/dashboard/agentops/cost/by-model?days=${days}`),
          api.get<UserStat[]>(`/dashboard/agentops/cost/by-user?days=${days}`),
          api.get<{models: ModelPricing[]}>("/dashboard/agentops/cost/model-pricing"),
        ]);
        setSummary(s);
        setTimeseries(ts);
        setByModel(bm);
        setByUser(bu);
        setPricing(pr.models);
      } catch (err) {
        setError(err instanceof Error ? err.message : "加载失败");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [days]);

  if (error) return <ErrorAlert message={error} />;

  const costByModelChart = byModel.slice(0, 8).map((m) => ({
    name: m.model.length > 20 ? m.model.slice(0, 20) + "…" : m.model,
    cost: m.cost,
    tokens: m.total_tokens,
    calls: m.calls,
  }));

  return (
    <div className="space-y-6 p-6">
      {/* Nav */}
      <nav className="flex gap-1 border-b pb-2 mb-2">
        <Link href="/agentops" className="px-3 py-1.5 text-sm rounded-md text-muted-foreground hover:bg-muted">概览</Link>
        <Link href="/agentops/debug" className="px-3 py-1.5 text-sm rounded-md text-muted-foreground hover:bg-muted">Debug</Link>
        <Link href="/agentops/cost" className="px-3 py-1.5 text-sm rounded-md bg-primary/10 text-primary font-medium">成本</Link>
        <Link href="/agentops/governance" className="px-3 py-1.5 text-sm rounded-md text-muted-foreground hover:bg-muted">治理</Link>
      </nav>

      <h1 className="text-2xl font-bold">LLM 成本看板</h1>

      {/* ── Summary Cards ── */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">今日成本</CardTitle>
            <DollarSign className="h-4 w-4 text-green-600" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{loading ? "—" : fmtCost(summary?.today_cost ?? 0)}</div>
            <p className="text-xs text-muted-foreground">{fmtTokens(summary?.today_tokens ?? 0)} tokens / {summary?.today_calls ?? 0} 次调用</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">近 {days} 天总成本</CardTitle>
            <TrendingUp className="h-4 w-4 text-blue-600" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{loading ? "—" : fmtCost(summary?.total_cost ?? 0)}</div>
            <p className="text-xs text-muted-foreground">{fmtTokens(summary?.total_tokens ?? 0)} tokens / {summary?.total_calls ?? 0} 次调用</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">模型数</CardTitle>
            <Cpu className="h-4 w-4 text-purple-600" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{loading ? "—" : summary?.model_count ?? 0}</div>
            <p className="text-xs text-muted-foreground">已使用的不同模型</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">平均耗时</CardTitle>
            <BarChart3 className="h-4 w-4 text-orange-600" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{loading ? "—" : `${(summary?.avg_duration_ms ?? 0).toFixed(0)}ms`}</div>
            <p className="text-xs text-muted-foreground">每次 LLM 调用</p>
          </CardContent>
        </Card>
      </div>

      {/* ── Day Range Selector ── */}
      <div className="flex gap-1">
        {[7, 14, 30, 90].map((d) => (
          <button
            key={d}
            className={`px-3 py-1.5 text-sm rounded-md ${
              days === d ? "bg-primary text-primary-foreground" : "bg-muted hover:bg-muted/80"
            }`}
            onClick={() => setDays(d)}
          >
            {d} 天
          </button>
        ))}
      </div>

      {/* ── Cost Trend ── */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">成本趋势</CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <Skeleton className="h-64 w-full" />
          ) : timeseries && timeseries.daily.length > 0 ? (
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={timeseries.daily}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="date" tick={{ fontSize: 12 }} />
                <YAxis tickFormatter={(v: number) => fmtCost(v)} />
                <Tooltip formatter={(value: number, name: string) => {
                  if (name === "cost") return [fmtCost(value), "成本"];
                  if (name === "total_tokens") return [fmtTokens(value), "Tokens"];
                  return [value, name];
                }} />
                <Legend />
                <Line type="monotone" dataKey="cost" stroke="#10b981" name="成本" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="total_tokens" stroke="#3b82f6" name="Tokens" strokeWidth={2} dot={false} yAxisId={0} />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <p className="text-sm text-muted-foreground">暂无趋势数据（LLM 调用后将自动记录）</p>
          )}
        </CardContent>
      </Card>

      {/* ── Token Trend ── */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Token 消耗趋势</CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <Skeleton className="h-48 w-full" />
          ) : timeseries && timeseries.daily.length > 0 ? (
            <ResponsiveContainer width="100%" height={250}>
              <BarChart data={timeseries.daily}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="date" tick={{ fontSize: 12 }} />
                <YAxis tickFormatter={fmtTokens} />
                <Tooltip />
                <Legend />
                <Bar dataKey="prompt_tokens" stackId="tokens" fill="#3b82f6" name="Prompt Tokens" radius={[0, 0, 0, 0]} />
                <Bar dataKey="completion_tokens" stackId="tokens" fill="#10b981" name="Completion Tokens" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <p className="text-sm text-muted-foreground">暂无 token 数据</p>
          )}
        </CardContent>
      </Card>

      {/* ── Cost by Model ── */}
      <div className="grid gap-6 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">按模型成本</CardTitle>
          </CardHeader>
          <CardContent>
            {loading ? (
              <Skeleton className="h-64 w-full" />
            ) : costByModelChart.length > 0 ? (
              <ResponsiveContainer width="100%" height={300}>
                <PieChart>
                  <Pie
                    data={costByModelChart}
                    dataKey="cost"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    outerRadius={90}
                    label={({ name, percent }: { name: string; percent: number }) =>
                      `${name} ${(percent * 100).toFixed(0)}%`
                    }
                  >
                    {costByModelChart.map((_, idx) => (
                      <Cell key={idx} fill={COLORS[idx % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(value: number) => fmtCost(value)} />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <p className="text-sm text-muted-foreground">暂无数据</p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-lg">模型成本排行</CardTitle>
          </CardHeader>
          <CardContent>
            {loading ? (
              <Skeleton className="h-64 w-full" />
            ) : byModel.length > 0 ? (
              <div className="space-y-2">
                {byModel.slice(0, 10).map((m, idx) => (
                  <div key={m.model} className="flex items-center justify-between text-sm">
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="text-muted-foreground w-4 shrink-0">#{idx + 1}</span>
                      <span className="truncate max-w-[180px]" title={m.model}>{m.model}</span>
                    </div>
                    <div className="flex gap-4 shrink-0">
                      <span className="text-muted-foreground w-16 text-right">{fmtTokens(m.total_tokens)}</span>
                      <span className="font-medium w-20 text-right">{fmtCost(m.cost)}</span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">暂无数据</p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* ── Top Users ── */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">用户成本排行</CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <Skeleton className="h-48 w-full" />
          ) : byUser.length > 0 ? (
            <div className="space-y-2">
              {byUser.map((u, idx) => (
                <div key={u.user_id} className="flex items-center justify-between text-sm">
                  <div className="flex items-center gap-2">
                    <Users className="h-3.5 w-3.5 text-muted-foreground" />
                    <span>{u.user_id.length > 24 ? `${u.user_id.slice(0, 24)}…` : u.user_id}</span>
                  </div>
                  <div className="flex gap-4">
                    <span className="text-muted-foreground w-20 text-right">{u.calls} 次调用</span>
                    <span className="text-muted-foreground w-16 text-right">{fmtTokens(u.total_tokens)}</span>
                    <span className="font-medium w-20 text-right">{fmtCost(u.cost)}</span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">暂无数据</p>
          )}
        </CardContent>
      </Card>

      {/* ── Model Pricing Table ── */}
      {pricing.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">模型定价参考</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b">
                    <th className="text-left py-2 px-2">模型</th>
                    <th className="text-right py-2 px-2">输入 ($/1K tokens)</th>
                    <th className="text-right py-2 px-2">输出 ($/1K tokens)</th>
                  </tr>
                </thead>
                <tbody>
                  {pricing.map((p) => (
                    <tr key={p.model} className="border-b last:border-0 hover:bg-muted/50">
                      <td className="py-1.5 px-2">{p.model}</td>
                      <td className="text-right py-1.5 px-2">{p.input_token_cost_per_1k.toFixed(6)}</td>
                      <td className="text-right py-1.5 px-2">{p.output_token_cost_per_1k.toFixed(6)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
