"use client";

import { useState, useEffect } from "react";
import { Search, UserCheck, Loader2, Briefcase, GraduationCap, X } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { ErrorAlert } from "@/components/common/error-alert";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/trpc";
import {
  RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis, ResponsiveContainer,
} from "recharts";

interface CandidateItem {
  id: string;
  name: string;
  email: string;
  phone?: string;
  summary?: string;
  skills: string[];
  experience_years?: number;
  current_company?: string;
  current_title?: string;
  education?: string;
  status: string;
  created_at: string;
}

interface ApiResponse {
  success: boolean;
  data?: { items: CandidateItem[]; total: number };
  items?: CandidateItem[];
  total?: number;
}

interface EvalSummary {
  id: string;
  name: string;
  overall_score: number;
  skills: string[];
  scores: { name: string; score: number }[];
  summary: string;
  status: string;
  date: string;
}

const mockCandidates: CandidateItem[] = [
  { id: "m1", name: "张明", email: "zhangming@example.com", summary: "5 年前端开发经验，精通 React/Vue/TypeScript，参与过多个大型 B 端项目。", skills: ["React", "Vue", "TypeScript", "Webpack", "Node.js", "CSS"], experience_years: 5, current_company: "字节跳动", current_title: "高级前端工程师", education: "本科 - 计算机科学与技术", status: "active", created_at: "2026-05-20" },
  { id: "m2", name: "李华", email: "lihua@example.com", summary: "8 年后端开发经验，专注于分布式系统与微服务架构设计。", skills: ["Java", "Spring Boot", "Kubernetes", "Docker", "PostgreSQL", "Kafka"], experience_years: 8, current_company: "阿里巴巴", current_title: "后端架构师", education: "硕士 - 软件工程", status: "active", created_at: "2026-05-19" },
  { id: "m3", name: "王芳", email: "wangfang@example.com", summary: "6 年产品经验，从 0 到 1 打造过 3 款 SaaS 产品。", skills: ["产品策略", "数据分析", "用户研究", "A/B 测试", "PRD", "敏捷管理"], experience_years: 6, current_company: "腾讯", current_title: "资深产品经理", education: "MBA", status: "active", created_at: "2026-05-18" },
  { id: "m4", name: "陈静", email: "chenjing@example.com", summary: "4 年 UI/UX 设计经验，擅长用户研究与交互设计。", skills: ["Figma", "用户研究", "交互设计", "设计系统", "动效设计", "Sketch"], experience_years: 4, current_company: "美团", current_title: "UI/UX 设计师", education: "本科 - 视觉传达", status: "active", created_at: "2026-05-22" },
];

const mockJobFits = [
  { job: "高级前端工程师", fit: 92 },
  { job: "全栈开发工程师", fit: 85 },
  { job: "技术主管", fit: 72 },
];

const statusBadge: Record<string, "success" | "warning" | "default" | "destructive"> = {
  active: "success",
  reviewing: "warning",
  archived: "default",
  blacklisted: "destructive",
};

function getInitials(name: string) {
  return name.charAt(0);
}

function getRadarData(skills: string[]) {
  const top = skills.slice(0, 6);
  return top.map((s) => ({ skill: s, score: 75 + Math.floor(Math.random() * 20) }));
}

export default function TalentProfilePage() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [candidates, setCandidates] = useState<CandidateItem[]>(mockCandidates);
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<CandidateItem | null>(null);
  const [evalData, setEvalData] = useState<EvalSummary | null>(null);
  const [evalLoading, setEvalLoading] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const res = await api.get<ApiResponse>("/candidates?limit=20");
        const items = res.data?.items ?? res.items ?? [];
        if (items.length > 0) {
          setCandidates(items.slice(0, 20));
        }
      } catch {
        setError("使用模拟数据展示");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const filtered = candidates.filter(
    (c) => c.name.includes(search) || c.current_title?.includes(search)
  );

  if (loading) {
    return (
      <div className="space-y-6 p-6">
        <Skeleton className="h-8 w-32" />
        <Skeleton className="h-4 w-64" />
        <div className="grid gap-6 lg:grid-cols-[320px_1fr]">
          <Card>
            <CardHeader><Skeleton className="h-10 w-full" /></CardHeader>
            <CardContent className="space-y-2">
              {Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="flex items-center gap-3">
                  <Skeleton className="h-10 w-10 rounded-full" />
                  <div className="flex-1 space-y-1">
                    <Skeleton className="h-4 w-24" />
                    <Skeleton className="h-3 w-32" />
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>
          <Card>
            <CardContent className="flex items-center justify-center h-64">
              <Skeleton className="h-48 w-48 rounded-full" />
            </CardContent>
          </Card>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold">人才档案</h1>
        {error && <ErrorAlert message={error} variant="warning" />}
      </div>
      <p className="text-muted-foreground">查看候选人详细档案与多维评估</p>

      <div className="grid gap-6 lg:grid-cols-[320px_1fr]">
        <Card>
          <CardHeader>
            <div className="relative">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input placeholder="搜索候选人..." value={search} onChange={(e) => setSearch(e.target.value)} className="pl-9" />
            </div>
          </CardHeader>
          <CardContent className="space-y-1">
            {filtered.map((c) => (
                <button
                  key={c.id}
                  onClick={() => {
                    setSelected(c);
                    setEvalData(null);
                    (async () => {
                      setEvalLoading(true);
                      try {
                        const res = await api.get<EvalSummary>(`/evaluations/${c.id}`);
                        setEvalData(res);
                      } catch {
                        /* fall back to skills-only radar */
                      } finally {
                        setEvalLoading(false);
                      }
                    })();
                  }}
                className={`w-full rounded-lg p-3 text-left transition-colors hover:bg-muted/50 ${selected?.id === c.id ? "bg-muted" : ""}`}
              >
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-primary/10 text-sm font-bold text-primary">
                    {getInitials(c.name)}
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium">{c.name}</p>
                    <p className="truncate text-xs text-muted-foreground">{c.current_title || "—"} · {c.current_company || "—"}</p>
                  </div>
                  <Badge variant={statusBadge[c.status] || "outline"}>{c.experience_years || "?"}年</Badge>
                </div>
              </button>
            ))}
            {filtered.length === 0 && (
              <p className="py-8 text-center text-sm text-muted-foreground">未找到匹配</p>
            )}
          </CardContent>
        </Card>

        {selected ? (
          <div className="space-y-6">
            <Card>
              <CardHeader>
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-4">
                    <div className="flex h-16 w-16 items-center justify-center rounded-full bg-primary/10 text-2xl font-bold text-primary">
                      {getInitials(selected.name)}
                    </div>
                    <div>
                      <CardTitle className="text-xl">{selected.name}</CardTitle>
                      <p className="text-sm text-muted-foreground">{selected.current_title} · {selected.current_company}</p>
                      <p className="text-xs text-muted-foreground">{selected.education || "—"} · {selected.email}</p>
                    </div>
                  </div>
                  <Badge variant={statusBadge[selected.status] || "outline"}>
                    {selected.status === "active" ? "活跃" : selected.status}
                  </Badge>
                </div>
              </CardHeader>
              <CardContent>
                <p className="text-sm leading-relaxed text-muted-foreground">{selected.summary || "暂无简介"}</p>
              </CardContent>
            </Card>

            <div className="grid gap-6 md:grid-cols-2">
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">
                    {evalData ? "评估雷达" : "技能雷达"}
                    {evalLoading && <Loader2 className="ml-2 inline h-3 w-3 animate-spin" />}
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="h-64">
                    <ResponsiveContainer width="100%" height="100%">
                      <RadarChart data={evalData ? evalData.scores.map((s) => ({ skill: s.name, score: s.score })) : getRadarData(selected.skills)}>
                        <PolarGrid />
                        <PolarAngleAxis dataKey="skill" tick={{ fontSize: 11 }} />
                        <PolarRadiusAxis domain={[0, 100]} tick={false} axisLine={false} />
                        <Radar name="熟练度" dataKey="score" stroke="#3b82f6" fill="#3b82f6" fillOpacity={0.3} />
                      </RadarChart>
                    </ResponsiveContainer>
                  </div>
                  {evalData && evalData.summary && (
                    <div className="mt-3 rounded-lg bg-muted/50 p-3">
                      <p className="text-xs font-medium text-muted-foreground mb-1">评估摘要</p>
                      <p className="text-sm leading-relaxed">{evalData.summary}</p>
                    </div>
                  )}
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle className="text-base">推荐岗位匹配</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  {mockJobFits.map((jf) => (
                    <div key={jf.job} className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <Briefcase className="h-4 w-4 text-muted-foreground" />
                        <span className="text-sm">{jf.job}</span>
                      </div>
                      <Badge variant={jf.fit >= 85 ? "success" : jf.fit >= 70 ? "warning" : "destructive"}>{jf.fit}%</Badge>
                    </div>
                  ))}
                  <div className="pt-2">
                    <Button variant="outline" size="sm" className="w-full gap-1">
                      <GraduationCap className="h-4 w-4" />
                      生成更多推荐
                    </Button>
                  </div>
                </CardContent>
              </Card>
            </div>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">技能标签</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex flex-wrap gap-2">
                  {selected.skills.map((s) => (
                    <Badge key={s} variant="secondary">{s}</Badge>
                  ))}
                </div>
              </CardContent>
            </Card>
          </div>
        ) : (
          <div className="flex h-96 flex-col items-center justify-center rounded-lg border text-center">
            <UserCheck className="mb-4 h-12 w-12 text-muted-foreground/50" />
            <p className="text-lg font-medium text-muted-foreground">请选择候选人</p>
            <p className="text-sm text-muted-foreground/60">从左侧列表中点击候选人查看详细信息</p>
          </div>
        )}
      </div>
    </div>
  );
}
