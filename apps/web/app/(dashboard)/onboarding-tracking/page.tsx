"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/trpc";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { UserCheck, AlertTriangle, Users, BarChart3 } from "lucide-react";

interface OnboardingTracking {
  id: string;
  candidate_id: string;
  application_id: string | null;
  offer_id: string | null;
  hire_date: string | null;
  department: string | null;
  manager_id: string | null;
  mentor_id: string | null;
  status: string;
  risk_level: string;
  created_at: string;
  updated_at: string;
}

interface Checkpoint {
  checkpoint: {
    id: string;
    onboarding_id: string;
    checkpoint_type: string;
    due_at: string;
    completed_at: string | null;
    status: string;
    summary: string | null;
    risk_flags: string[];
  };
}

interface ProbationFeedback {
  id: string;
  onboarding_id: string;
  checkpoint_id: string | null;
  reviewer_id: string | null;
  performance_score: number | null;
  culture_fit_score: number | null;
  ramp_up_score: number | null;
  communication_score: number | null;
  retention_risk: string | null;
  feedback_text: string | null;
  pass_probation: boolean | null;
}

interface TrackingDetail extends OnboardingTracking {
  checkpoints: Checkpoint[];
  feedbacks: ProbationFeedback[];
}

const STATUS_MAP: Record<string, { label: string; color: "default" | "secondary" | "destructive" | "outline" }> = {
  preboarding: { label: "待入职", color: "outline" },
  onboarded: { label: "已入职", color: "default" },
  probation: { label: "试用期", color: "secondary" },
  probation_passed: { label: "试用通过", color: "default" },
  probation_failed: { label: "试用未过", color: "destructive" },
  resigned: { label: "已离职", color: "destructive" },
};

const RISK_MAP: Record<string, { label: string; color: "default" | "secondary" | "destructive" | "outline" }> = {
  low: { label: "低", color: "default" },
  medium: { label: "中", color: "secondary" },
  high: { label: "高", color: "destructive" },
  critical: { label: "严重", color: "destructive" },
};

const CP_TYPE_LABEL: Record<string, string> = {
  day_1: "入职首日",
  day_7: "首周",
  month_1: "1个月",
  month_3: "3个月",
  month_6: "6个月",
};

export default function OnboardingTrackingPage() {
  const [trackings, setTrackings] = useState<OnboardingTracking[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<TrackingDetail | null>(null);
  const [candidateFilter, setCandidateFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");

  // pass rate analytics
  const [passRate, setPassRate] = useState<{ total_feedbacks: number; passed: number; pass_rate: number } | null>(null);

  useEffect(() => {
    void loadTrackings();
    void loadPassRate();
  }, []);

  const loadTrackings = async () => {
    setLoading(true);
    try {
      const qs = new URLSearchParams();
      if (candidateFilter) qs.set("candidate_id", candidateFilter);
      if (statusFilter) qs.set("status", statusFilter);
      const res = await api.get<{ data: { items: OnboardingTracking[]; total: number } }>(`/onboarding-trackings?${qs.toString()}`);
      setTrackings(res.data?.items || []);
    } finally {
      setLoading(false);
    }
  };

  const loadPassRate = async () => {
    try {
      const res = await api.get<{ data: any }>("/onboarding-analytics/probation-pass-rate");
      setPassRate(res.data || null);
    } catch { /* ignore */ }
  };

  const viewDetail = async (id: string) => {
    const res = await api.get<{ data: TrackingDetail }>(`/onboarding-trackings/${id}`);
    setSelected(res.data || null);
  };

  const closeDetail = () => setSelected(null);

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center gap-2">
        <UserCheck className="h-7 w-7" />
        <div>
          <h1 className="text-3xl font-bold">入职后跟踪</h1>
          <p className="text-muted-foreground">候选人入职管理 · 试用期跟踪 · 检查点看板</p>
        </div>
      </div>

      {/* Analytics */}
      {passRate && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Card>
            <CardHeader><CardTitle className="flex items-center gap-2"><Users className="h-4 w-4" />试用期反馈总数</CardTitle></CardHeader>
            <CardContent><p className="text-3xl font-bold">{passRate.total_feedbacks}</p></CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle className="flex items-center gap-2"><BarChart3 className="h-4 w-4" />通过数</CardTitle></CardHeader>
            <CardContent><p className="text-3xl font-bold text-green-600">{passRate.passed}</p></CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle className="flex items-center gap-2"><AlertTriangle className="h-4 w-4" />通过率</CardTitle></CardHeader>
            <CardContent><p className="text-3xl font-bold text-blue-600">{passRate.pass_rate}%</p></CardContent>
          </Card>
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-wrap gap-3 items-center">
        <Input placeholder="候选人 ID" value={candidateFilter} onChange={e => setCandidateFilter(e.target.value)} className="w-64" />
        <select
          className="h-10 rounded-md border border-input bg-background px-3 text-sm"
          value={statusFilter}
          onChange={e => setStatusFilter(e.target.value)}
        >
          <option value="">全部状态</option>
          <option value="preboarding">待入职</option>
          <option value="onboarded">已入职</option>
          <option value="probation">试用期</option>
          <option value="probation_passed">试用通过</option>
          <option value="probation_failed">试用未过</option>
          <option value="resigned">已离职</option>
        </select>
        <Button onClick={loadTrackings} disabled={loading}>查询</Button>
      </div>

      {/* List */}
      {loading ? (
        <p className="text-muted-foreground">加载中...</p>
      ) : trackings.length === 0 ? (
        <p className="text-muted-foreground">暂无入职跟踪记录</p>
      ) : (
        <Card>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-muted-foreground">
                    <th className="p-3 font-medium">状态</th>
                    <th className="p-3 font-medium">风险</th>
                    <th className="p-3 font-medium">部门</th>
                    <th className="p-3 font-medium">入职日期</th>
                    <th className="p-3 font-medium">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {trackings.map(t => {
                    const st = STATUS_MAP[t.status] || { label: t.status, color: "outline" };
                    const rk = RISK_MAP[t.risk_level] || { label: t.risk_level, color: "outline" };
                    return (
                      <tr key={t.id} className="border-b last:border-0 hover:bg-muted/50">
                        <td className="p-3"><Badge variant={st.color}>{st.label}</Badge></td>
                        <td className="p-3"><Badge variant={rk.color}>{rk.label}</Badge></td>
                        <td className="p-3">{t.department || "-"}</td>
                        <td className="p-3">{t.hire_date || "-"}</td>
                        <td className="p-3">
                          <Button variant="outline" size="sm" onClick={() => viewDetail(t.id)}>详情</Button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Detail Dialog */}
      {selected && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-start justify-center pt-10" onClick={closeDetail}>
          <div className="bg-background rounded-lg w-full max-w-3xl max-h-[80vh] overflow-y-auto m-4" onClick={e => e.stopPropagation()}>
            <div className="sticky top-0 bg-background border-b px-6 py-4 flex items-center justify-between">
              <h2 className="text-lg font-semibold">入职跟踪详情</h2>
              <Button variant="ghost" size="sm" onClick={closeDetail}>关闭</Button>
            </div>
            <div className="p-6 space-y-6">
              {/* Basic Info */}
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div><span className="text-muted-foreground">候选人 ID：</span>{selected.candidate_id}</div>
                <div><span className="text-muted-foreground">状态：</span>{STATUS_MAP[selected.status]?.label || selected.status}</div>
                <div><span className="text-muted-foreground">部门：</span>{selected.department || "-"}</div>
                <div><span className="text-muted-foreground">入职日期：</span>{selected.hire_date || "-"}</div>
                <div><span className="text-muted-foreground">风险等级：</span>{RISK_MAP[selected.risk_level]?.label || selected.risk_level}</div>
              </div>

              {/* Checkpoints */}
              <div>
                <h3 className="font-medium mb-3">检查点</h3>
                {selected.checkpoints?.length === 0 ? (
                  <p className="text-sm text-muted-foreground">暂无检查点</p>
                ) : (
                  <div className="space-y-2">
                    {selected.checkpoints?.map(({ checkpoint: cp }) => {
                      const cpStatus = cp.status === "completed" ? "✅" : cp.status === "overdue" ? "⚠️" : "⏳";
                      return (
                        <div key={cp.id} className="flex items-center justify-between rounded border p-3 text-sm">
                          <div>
                            <span className="font-medium">{CP_TYPE_LABEL[cp.checkpoint_type] || cp.checkpoint_type}</span>
                            <span className="text-muted-foreground ml-2">
                              {new Date(cp.due_at).toLocaleDateString("zh-CN")}
                            </span>
                          </div>
                          <span>{cpStatus} {cp.status}</span>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>

              {/* Probation Feedbacks */}
              <div>
                <h3 className="font-medium mb-3">试用期反馈</h3>
                {selected.feedbacks?.length === 0 ? (
                  <p className="text-sm text-muted-foreground">暂无试用期反馈</p>
                ) : (
                  <div className="space-y-3">
                    {selected.feedbacks?.map(fb => (
                      <div key={fb.id} className="rounded border p-3 text-sm space-y-2">
                        <div className="flex gap-4">
                          <span>业务能力：{fb.performance_score ?? "-"}</span>
                          <span>文化融入：{fb.culture_fit_score ?? "-"}</span>
                          <span>上手速度：{fb.ramp_up_score ?? "-"}</span>
                          <span>沟通协作：{fb.communication_score ?? "-"}</span>
                        </div>
                        <div className="text-muted-foreground">{fb.feedback_text || "-"}</div>
                        <div>
                          留任风险：<Badge variant={fb.retention_risk === "high" ? "destructive" : "outline"}>{fb.retention_risk || "低"}</Badge>
                          {fb.pass_probation !== null && (
                            <span className="ml-4">是否通过试用期：{fb.pass_probation ? "✅" : "❌"}</span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
