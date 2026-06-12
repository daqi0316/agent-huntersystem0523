"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/trpc";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Search, TrendingUp, AlertTriangle, BarChart3 } from "lucide-react";

interface Benchmark {
  id: string;
  city: string;
  job_family: string;
  job_title: string;
  level: string;
  base_min: number | null;
  base_p50: number | null;
  base_max: number | null;
  total_min: number | null;
  total_p50: number | null;
  total_max: number | null;
  currency: string;
  company_type: string | null;
  data_source: string | null;
  confidence: number | null;
  sample_size: number | null;
}

interface CandidateCompensation {
  id: string;
  candidate_id: string;
  current_base: number | null;
  current_total: number | null;
  expected_base: number | null;
  expected_total: number | null;
  minimum_acceptable: number | null;
  notice_period: string | null;
  competing_offers: string[];
  notes: string | null;
}

interface OfferRecord {
  id: string;
  candidate_id: string;
  expected_total: number | null;
  first_offer_total: number | null;
  final_offer_total: number | null;
  market_p50: number | null;
  budget_min: number | null;
  budget_max: number | null;
  negotiation_status: string;
  accepted: boolean | null;
  reject_reason: string | null;
}

function formatCurrency(val: number | null | undefined): string {
  if (val == null) return "-";
  return `${(val / 10000).toFixed(0)}万`;
}

export default function CompensationPage() {
  // benchmark search
  const [benchmarks, setBenchmarks] = useState<Benchmark[]>([]);
  const [searchParams, setSearchParams] = useState({ city: "", level: "", job_title: "", job_family: "" });
  const [loadingBenchmarks, setLoadingBenchmarks] = useState(false);

  // candidate compensation lookup
  const [candidateId, setCandidateId] = useState("");
  const [candComp, setCandComp] = useState<{ expectations: CandidateCompensation[]; offers: OfferRecord[]; risk: any } | null>(null);
  const [loadingCandidate, setLoadingCandidate] = useState(false);

  // analytics
  const [analytics, setAnalytics] = useState<{ total_rejected: number; salary_rejected: number; salary_rejection_ratio: number } | null>(null);

  useEffect(() => {
    void fetchBenchmarks();
    void fetchAnalytics();
  }, []);

  const fetchBenchmarks = async (params?: typeof searchParams) => {
    setLoadingBenchmarks(true);
    try {
      const p = params || searchParams;
      const qs = new URLSearchParams();
      if (p.city) qs.set("city", p.city);
      if (p.level) qs.set("level", p.level);
      if (p.job_title) qs.set("job_title", p.job_title);
      if (p.job_family) qs.set("job_family", p.job_family);
      const res = await api.get<{ data: { items: Benchmark[]; total: number } }>(`/compensation/benchmarks?${qs.toString()}`);
      setBenchmarks(res.data?.items || []);
    } finally {
      setLoadingBenchmarks(false);
    }
  };

  const fetchCandidateCompensation = async () => {
    if (!candidateId.trim()) return;
    setLoadingCandidate(true);
    try {
      const res = await api.get<{ data: any }>(`/candidates/${candidateId}/compensation`);
      setCandComp(res.data || null);
    } finally {
      setLoadingCandidate(false);
    }
  };

  const fetchAnalytics = async () => {
    try {
      const res = await api.get<{ data: any }>("/compensation/analytics/salary-loss");
      setAnalytics(res.data || null);
    } catch { /* ignore */ }
  };

  const riskBadge = (label: string) => {
    const map: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
      low: "default",
      medium: "secondary",
      high: "destructive",
    };
    return <Badge variant={map[label] || "outline"}>{label === "low" ? "低" : label === "medium" ? "中" : "高"}</Badge>;
  };

  return (
    <div className="space-y-6 p-6">
      <div>
        <h1 className="text-3xl font-bold">薪酬数据库</h1>
        <p className="text-muted-foreground">市场薪酬基准 · 候选人期望 · Offer 谈判分析</p>
      </div>

      <Tabs defaultValue="benchmarks">
        <TabsList>
          <TabsTrigger value="benchmarks"><Search className="h-4 w-4 mr-1" />薪酬查询</TabsTrigger>
          <TabsTrigger value="candidate"><TrendingUp className="h-4 w-4 mr-1" />候选人薪酬</TabsTrigger>
          <TabsTrigger value="analytics"><BarChart3 className="h-4 w-4 mr-1" />统计分析</TabsTrigger>
        </TabsList>

        {/* Tab 1：薪酬查询 */}
        <TabsContent value="benchmarks" className="space-y-4">
          <Card>
            <CardHeader><CardTitle>查询条件</CardTitle></CardHeader>
            <CardContent>
              <div className="flex flex-wrap gap-3">
                <Input placeholder="城市" value={searchParams.city} onChange={e => setSearchParams(p => ({ ...p, city: e.target.value }))} className="w-36" />
                <Input placeholder="职级" value={searchParams.level} onChange={e => setSearchParams(p => ({ ...p, level: e.target.value }))} className="w-36" />
                <Input placeholder="岗位名称" value={searchParams.job_title} onChange={e => setSearchParams(p => ({ ...p, job_title: e.target.value }))} className="w-48" />
                <Input placeholder="职能族" value={searchParams.job_family} onChange={e => setSearchParams(p => ({ ...p, job_family: e.target.value }))} className="w-36" />
                <Button onClick={() => fetchBenchmarks(searchParams)} disabled={loadingBenchmarks}>
                  <Search className="h-4 w-4 mr-1" />查询
                </Button>
              </div>
            </CardContent>
          </Card>

          {loadingBenchmarks ? (
            <p className="text-muted-foreground">加载中...</p>
          ) : benchmarks.length === 0 ? (
            <p className="text-muted-foreground">暂无数据，请调整查询条件</p>
          ) : (
            <Card>
              <CardContent className="p-0">
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b text-left text-muted-foreground">
                        <th className="p-3 font-medium">城市</th>
                        <th className="p-3 font-medium">岗位</th>
                        <th className="p-3 font-medium">职级</th>
                        <th className="p-3 font-medium">公司类型</th>
                        <th className="p-3 font-medium">月薪 P50</th>
                        <th className="p-3 font-medium">年薪范围</th>
                        <th className="p-3 font-medium">样本量</th>
                      </tr>
                    </thead>
                    <tbody>
                      {benchmarks.map(b => (
                        <tr key={b.id} className="border-b last:border-0 hover:bg-muted/50">
                          <td className="p-3">{b.city}</td>
                          <td className="p-3">{b.job_title}</td>
                          <td className="p-3">{b.level}</td>
                          <td className="p-3">{b.company_type || "-"}</td>
                          <td className="p-3 font-medium">{formatCurrency(b.base_p50)}</td>
                          <td className="p-3">{formatCurrency(b.total_min)} ~ {formatCurrency(b.total_max)}</td>
                          <td className="p-3">{b.sample_size ?? "-"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          )}
        </TabsContent>

        {/* Tab 2：候选人薪酬 */}
        <TabsContent value="candidate" className="space-y-4">
          <Card>
            <CardHeader><CardTitle>查询候选人薪酬</CardTitle></CardHeader>
            <CardContent>
              <div className="flex gap-3">
                <Input placeholder="候选人 ID" value={candidateId} onChange={e => setCandidateId(e.target.value)} className="w-80" />
                <Button onClick={fetchCandidateCompensation} disabled={loadingCandidate}>
                  <Search className="h-4 w-4 mr-1" />查询
                </Button>
              </div>
            </CardContent>
          </Card>

          {candComp && (
            <>
              {/* 薪酬风险标签 */}
              {candComp.risk && (
                <Card>
                  <CardHeader><CardTitle className="flex items-center gap-2"><AlertTriangle className="h-5 w-5" />薪酬风险</CardTitle></CardHeader>
                  <CardContent>
                    <div className="flex items-center gap-3 mb-3">
                      {riskBadge(candComp.risk.risk_label)}
                      <span className="text-sm">风险分：{candComp.risk.risk_score}</span>
                    </div>
                    {candComp.risk.reasons?.length > 0 && (
                      <ul className="text-sm space-y-1">
                        {candComp.risk.reasons.map((r: string, i: number) => (
                          <li key={i} className="text-muted-foreground">• {r}</li>
                        ))}
                      </ul>
                    )}
                    <div className="grid grid-cols-3 gap-4 mt-3 text-sm">
                      <div><span className="text-muted-foreground">期望总额：</span>{formatCurrency(candComp.risk.expected_total)}</div>
                      <div><span className="text-muted-foreground">市场 P50：</span>{formatCurrency(candComp.risk.market_p50)}</div>
                      <div><span className="text-muted-foreground">预算范围：</span>{formatCurrency(candComp.risk.budget_min)} ~ {formatCurrency(candComp.risk.budget_max)}</div>
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* 期望薪酬记录 */}
              {candComp.expectations?.length > 0 && (
                <Card>
                  <CardHeader><CardTitle>期望薪酬记录</CardTitle></CardHeader>
                  <CardContent className="p-0">
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b text-left text-muted-foreground">
                            <th className="p-3 font-medium">当前底薪</th>
                            <th className="p-3 font-medium">当前总包</th>
                            <th className="p-3 font-medium">期望底薪</th>
                            <th className="p-3 font-medium">期望总包</th>
                            <th className="p-3 font-medium">最低可接受</th>
                            <th className="p-3 font-medium">竞品 Offer</th>
                          </tr>
                        </thead>
                        <tbody>
                          {candComp.expectations.map((e: CandidateCompensation) => (
                            <tr key={e.id} className="border-b last:border-0 hover:bg-muted/50">
                              <td className="p-3">{formatCurrency(e.current_base)}</td>
                              <td className="p-3">{formatCurrency(e.current_total)}</td>
                              <td className="p-3">{formatCurrency(e.expected_base)}</td>
                              <td className="p-3 font-medium">{formatCurrency(e.expected_total)}</td>
                              <td className="p-3">{formatCurrency(e.minimum_acceptable)}</td>
                              <td className="p-3">{e.competing_offers?.length ? e.competing_offers.join(", ") : "-"}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Offer 谈判记录 */}
              {candComp.offers?.length > 0 && (
                <Card>
                  <CardHeader><CardTitle>Offer 谈判记录</CardTitle></CardHeader>
                  <CardContent className="p-0">
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b text-left text-muted-foreground">
                            <th className="p-3 font-medium">状态</th>
                            <th className="p-3 font-medium">期望总包</th>
                            <th className="p-3 font-medium">首次出价</th>
                            <th className="p-3 font-medium">最终出价</th>
                            <th className="p-3 font-medium">市场 P50</th>
                            <th className="p-3 font-medium">预算范围</th>
                            <th className="p-3 font-medium">是否接受</th>
                          </tr>
                        </thead>
                        <tbody>
                          {candComp.offers.map((o: OfferRecord) => (
                            <tr key={o.id} className="border-b last:border-0 hover:bg-muted/50">
                              <td className="p-3"><Badge variant="outline">{o.negotiation_status}</Badge></td>
                              <td className="p-3">{formatCurrency(o.expected_total)}</td>
                              <td className="p-3">{formatCurrency(o.first_offer_total)}</td>
                              <td className="p-3 font-medium">{formatCurrency(o.final_offer_total)}</td>
                              <td className="p-3">{formatCurrency(o.market_p50)}</td>
                              <td className="p-3">{formatCurrency(o.budget_min)} ~ {formatCurrency(o.budget_max)}</td>
                              <td className="p-3">{o.accepted === true ? "✅" : o.accepted === false ? "❌" : "-"}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </CardContent>
                </Card>
              )}
            </>
          )}
        </TabsContent>

        {/* Tab 3：统计分析 */}
        <TabsContent value="analytics" className="space-y-4">
          {analytics ? (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <Card>
                <CardHeader><CardTitle>总拒绝数</CardTitle></CardHeader>
                <CardContent><p className="text-3xl font-bold">{analytics.total_rejected}</p></CardContent>
              </Card>
              <Card>
                <CardHeader><CardTitle>薪资相关拒绝</CardTitle></CardHeader>
                <CardContent><p className="text-3xl font-bold text-orange-600">{analytics.salary_rejected}</p></CardContent>
              </Card>
              <Card>
                <CardHeader><CardTitle>薪资流失占比</CardTitle></CardHeader>
                <CardContent>
                  <p className="text-3xl font-bold text-red-600">{analytics.salary_rejection_ratio}%</p>
                </CardContent>
              </Card>
            </div>
          ) : (
            <p className="text-muted-foreground">暂无数据</p>
          )}
          <p className="text-xs text-muted-foreground">基于 Offer 谈判记录中 reject_reason 包含"薪"的数据统计</p>
        </TabsContent>
      </Tabs>
    </div>
  );
}
