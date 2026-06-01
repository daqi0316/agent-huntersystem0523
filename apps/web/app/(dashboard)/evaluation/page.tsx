"use client";

import { useState, useEffect } from "react";
import { Search, ChevronDown, ChevronUp, Loader2, Calendar, RefreshCw } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { ErrorAlert } from "@/components/common/error-alert";
import { toast } from "sonner";
import { api } from "@/lib/trpc";
import {
  RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis, ResponsiveContainer, Tooltip,
} from "recharts";

interface EvaluationItem {
  id: string;
  candidateId: string;
  jobId: string;
  name: string;
  title: string;
  company: string;
  skills: string[];
  status: string;
  summary: string;
  date: string;
  scores: { dimension: string; score: number }[];
  overall: number;
}

interface EvalApiResponse {
  success: boolean;
  items: {
    id: string;
    candidate_id: string;
    job_id: string;
    name: string;
    job_title: string;
    skills: string[];
    status: string;
    overall_score: number;
    scores: { name: string; score: number }[];
    summary: string;
    date: string;
  }[];
  total: number;
}

function scoreColor(s: number) {
  if (s >= 85) return "success";
  if (s >= 70) return "warning";
  return "destructive";
}

export default function EvaluationPage() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [evaluations, setEvaluations] = useState<EvaluationItem[]>([]);
  const [schedulingId, setSchedulingId] = useState<string | null>(null);

  const fetchEvaluations = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.get<EvalApiResponse>("/evaluations");
      const items = res.items ?? [];
      setEvaluations(
        items.map((item) => ({
          id: item.id,
          candidateId: item.candidate_id,
          jobId: item.job_id,
          name: item.name,
          title: item.job_title,
          company: "",
          skills: item.skills,
          status: item.status,
          summary: item.summary,
          date: item.date,
          scores: item.scores.map((s) => ({ dimension: s.name, score: s.score })),
          overall: item.overall_score,
        }))
      );
    } catch {
      setError("无法连接后端服务");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchEvaluations();
  }, []);

  const filtered = evaluations.filter(
    (e) => e.name.includes(search) || (e.title || "").includes(search)
  );

  const handleScheduleInterview = async (ev: EvaluationItem) => {
    setSchedulingId(ev.id);
    try {
      const result = await api.post<{ success: boolean; status?: string; approval?: Record<string, unknown> }>(
        "/human-loop/schedule",
        {
          action_type: "schedule_interview",
          params: {
            candidate_id: ev.candidateId,
            job_id: ev.jobId,
            candidate_name: ev.name,
            job_title: ev.title,
            evaluation_score: ev.overall,
            evaluation_summary: ev.summary,
          },
        }
      );
      if (result?.success) {
        toast.success(`已为 ${ev.name} 发起面试提议，等待审批`);
      } else {
        toast.error("面试提议创建失败");
      }
    } catch {
      toast.error("面试提议创建失败，请确认后端已启动");
    } finally {
      setSchedulingId(null);
    }
  };

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <h1 className="text-3xl font-bold">评估报告</h1>
        </div>
        <div className="space-y-4">
          {Array.from({ length: 3 }).map((_, i) => (
            <Card key={i}>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <Skeleton className="h-5 w-32" />
                  <Skeleton className="h-5 w-20" />
                </div>
              </CardHeader>
              <CardContent>
                <div className="grid gap-6 md:grid-cols-2">
                  <Skeleton className="h-48 w-full" />
                  <div className="space-y-3">
                    <div className="grid grid-cols-5 gap-2">
                      {Array.from({ length: 5 }).map((_, j) => (
                        <Skeleton key={j} className="h-12 w-full" />
                      ))}
                    </div>
                    <Skeleton className="h-20 w-full" />
                    <Skeleton className="h-9 w-32 ml-auto" />
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    );
  }

  if (error && evaluations.length === 0) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <h1 className="text-3xl font-bold">评估报告</h1>
        </div>
        <p className="text-muted-foreground">查看 AI 生成的候选人评估报告</p>
        <div className="flex flex-col items-center justify-center gap-4 rounded-lg border border-dashed py-16">
          <ErrorAlert message={error} />
          <Button onClick={fetchEvaluations}>
            <RefreshCw className="mr-2 h-4 w-4" />
            重新加载
          </Button>
        </div>
      </div>
    );
  }

  if (evaluations.length === 0) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <h1 className="text-3xl font-bold">评估报告</h1>
        </div>
        <p className="text-muted-foreground">查看 AI 生成的候选人评估报告</p>
        <div className="flex flex-col items-center justify-center gap-4 rounded-lg border border-dashed py-16">
          <Search className="h-12 w-12 text-muted-foreground" />
          <p className="text-lg font-medium">暂无评估数据</p>
          <p className="text-sm text-muted-foreground">
            完成候选人初筛后，AI 将自动生成评估报告
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold">评估报告</h1>
        {error && <ErrorAlert message={error} variant="warning" />}
      </div>
      <p className="text-muted-foreground">查看 AI 生成的候选人评估报告</p>

      {/* Search */}
      <div className="relative max-w-sm">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          placeholder="搜索候选人..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="pl-9"
        />
      </div>

      {/* Evaluation Cards */}
      <div className="space-y-4">
        {filtered.map((ev) => (
          <Card key={ev.id}>
            <CardHeader className="cursor-pointer" onClick={() => setExpandedId(expandedId === ev.id ? null : ev.id)}>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div>
                    <CardTitle className="text-base">{ev.name}</CardTitle>
                    <p className="text-sm text-muted-foreground">{ev.title || ev.company}</p>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <Badge variant={scoreColor(ev.overall) as "success" | "warning" | "destructive"}>
                    {ev.overall} 分
                  </Badge>
                  <Badge variant="outline">{ev.status}</Badge>
                  <span className="text-xs text-muted-foreground">{ev.date}</span>
                  {expandedId === ev.id ? (
                    <ChevronUp className="h-4 w-4 text-muted-foreground" />
                  ) : (
                    <ChevronDown className="h-4 w-4 text-muted-foreground" />
                  )}
                </div>
              </div>
            </CardHeader>
            {expandedId === ev.id && (
              <CardContent>
                <div className="grid gap-6 md:grid-cols-2">
                  {/* Radar Chart */}
                  <div className="h-64">
                    <ResponsiveContainer width="100%" height="100%">
                      <RadarChart data={ev.scores}>
                        <PolarGrid />
                        <PolarAngleAxis dataKey="dimension" tick={{ fontSize: 12 }} />
                        <PolarRadiusAxis domain={[0, 100]} tick={false} axisLine={false} />
                        <Radar
                          name="分数"
                          dataKey="score"
                          stroke="#3b82f6"
                          fill="#3b82f6"
                          fillOpacity={0.3}
                        />
                        <Tooltip />
                      </RadarChart>
                    </ResponsiveContainer>
                  </div>
                  {/* Summary */}
                  <div className="space-y-3">
                    <div className="grid grid-cols-5 gap-2">
                      {ev.scores.map((s) => (
                        <div key={s.dimension} className="text-center">
                          <p className="text-xs text-muted-foreground">{s.dimension}</p>
                          <p className="text-lg font-bold">{s.score}</p>
                        </div>
                      ))}
                    </div>
                    <div className="rounded-lg bg-muted/50 p-3">
                      <p className="text-sm leading-relaxed">{ev.summary}</p>
                    </div>
                    <div className="flex justify-end gap-2">
                      <Button variant="outline" size="sm">查看详情</Button>
                      <Button
                        size="sm"
                        disabled={schedulingId === ev.id}
                        onClick={() => handleScheduleInterview(ev)}
                      >
                        {schedulingId === ev.id ? (
                          <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                        ) : (
                          <Calendar className="mr-1 h-3 w-3" />
                        )}
                        安排面试
                      </Button>
                    </div>
                  </div>
                </div>
              </CardContent>
            )}
          </Card>
        ))}
        {filtered.length === 0 && (
          <div className="flex flex-col items-center justify-center gap-2 py-12">
            <Search className="h-8 w-8 text-muted-foreground" />
            <p className="text-muted-foreground">未找到匹配的评估报告</p>
          </div>
        )}
      </div>
    </div>
  );
}
