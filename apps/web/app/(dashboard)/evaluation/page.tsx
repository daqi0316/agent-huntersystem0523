"use client";

import { useState, useEffect } from "react";
import { Search, ChevronDown, ChevronUp, Loader2, AlertCircle, Calendar } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
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

const mockEvaluations: EvaluationItem[] = [
  {
    id: "1",
    candidateId: "cand-1",
    jobId: "job-1",
    name: "张明",
    title: "高级前端工程师",
    company: "",
    skills: ["Vue", "React", "TypeScript"],
    status: "已评估",
    date: "2026-05-20",
    scores: [
      { dimension: "专业技能", score: 92 },
      { dimension: "沟通能力", score: 85 },
      { dimension: "经验匹配", score: 88 },
      { dimension: "文化契合", score: 80 },
      { dimension: "学习能力", score: 90 },
    ],
    summary: "技术栈扎实，Vue 和 React 均有丰富经验，沟通表达清晰，团队协作能力强。建议进入下一轮面试。",
    overall: 87,
  },
  {
    id: "2",
    candidateId: "cand-2",
    jobId: "job-2",
    name: "李华",
    title: "后端架构师",
    company: "",
    skills: ["Java", "K8s", "Microservices"],
    status: "已评估",
    date: "2026-05-19",
    scores: [
      { dimension: "专业技能", score: 90 },
      { dimension: "沟通能力", score: 70 },
      { dimension: "经验匹配", score: 92 },
      { dimension: "文化契合", score: 75 },
      { dimension: "学习能力", score: 85 },
    ],
    summary: "系统设计能力强，分布式经验丰富，微服务架构理解深入。但沟通风格较直接，需关注团队协作。",
    overall: 82,
  },
  {
    id: "3",
    candidateId: "cand-3",
    jobId: "job-3",
    name: "王芳",
    title: "产品经理",
    company: "",
    skills: ["Product Design", "Data Analysis", "A/B Testing"],
    status: "已评估",
    date: "2026-05-18",
    scores: [
      { dimension: "专业技能", score: 88 },
      { dimension: "沟通能力", score: 92 },
      { dimension: "经验匹配", score: 90 },
      { dimension: "文化契合", score: 95 },
      { dimension: "学习能力", score: 93 },
    ],
    summary: "产品思维成熟，数据分析驱动决策，用户洞察深刻。拥有 3 个完整产品周期的经验。",
    overall: 91,
  },
  {
    id: "4",
    candidateId: "cand-4",
    jobId: "job-4",
    name: "陈静",
    title: "UI/UX 设计师",
    company: "",
    skills: ["Figma", "User Research", "Motion Design"],
    status: "初筛中",
    date: "2026-05-22",
    scores: [
      { dimension: "专业技能", score: 85 },
      { dimension: "沟通能力", score: 80 },
      { dimension: "经验匹配", score: 72 },
      { dimension: "文化契合", score: 82 },
      { dimension: "学习能力", score: 78 },
    ],
    summary: "设计作品集出色，用户研究能力强，动效设计经验丰富。B 端设计经验略显不足。",
    overall: 78,
  },
  {
    id: "5",
    candidateId: "cand-5",
    jobId: "job-5",
    name: "赵岩",
    title: "DevOps 工程师",
    company: "",
    skills: ["K8s", "CI/CD", "AWS", "GCP"],
    status: "已评估",
    date: "2026-05-17",
    scores: [
      { dimension: "专业技能", score: 90 },
      { dimension: "沟通能力", score: 78 },
      { dimension: "经验匹配", score: 92 },
      { dimension: "文化契合", score: 80 },
      { dimension: "学习能力", score: 82 },
    ],
    summary: "K8s 和 CI/CD 实践经验丰富，自动化意识强。云服务（AWS/GCP）经验 5 年+。",
    overall: 85,
  },
];

export default function EvaluationPage() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [evaluations, setEvaluations] = useState<EvaluationItem[]>(mockEvaluations);
  const [schedulingId, setSchedulingId] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const res = await api.get<EvalApiResponse>("/evaluations");
        const items = res.items ?? [];
        if (items.length > 0) {
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
        } else {
          setError("暂无评估数据，展示模拟数据");
        }
      } catch {
        setError("后端暂未连接，展示模拟数据");
      } finally {
        setLoading(false);
      }
    })();
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
      <div className="flex h-96 items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold">评估报告</h1>
        {error && (
          <Badge variant="warning" className="gap-1">
            <AlertCircle className="h-3 w-3" />
            {error}
          </Badge>
        )}
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
          <p className="py-12 text-center text-muted-foreground">未找到匹配的评估报告</p>
        )}
      </div>
    </div>
  );
}
