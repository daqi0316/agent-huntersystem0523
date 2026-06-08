"use client";

/**
 * 候选人详情页 — /candidates/[id]
 *
 * 工业级实施要点：
 *  - 数据：api.get<{success: true; data: CandidateRead}>(`/candidates/${id}`) — 走
 *    tRPC 统一封装（自动 token + 错误处理 + 200 unwrap）
 *  - 加载态：useEffect 异步加载，本地 loading state + Skeleton
 *  - 错误兜底：ErrorAlert 组件 + 重试按钮（不为端点崩溃制造新 Failed to fetch）
 *  - 404：候选人/职位不存在时调 notFound() 触发 Next.js not-found 页面
 *  - 布局：左 2/3 主信息 + 右 1/3 metadata + 返回链接（context-bar 跳转后能回退）
 *  - a11y：<main aria-labelledby> + <h1> + 字段 <dt>/<dd>
 *
 * T2 配套：CurrentContextSection chip 跳 /candidates/{id} 进入本页面。
 */

import { useEffect, useState, use } from "react";
import Link from "next/link";
import { notFound, useRouter } from "next/navigation";
import {
  ArrowLeft,
  Mail,
  Phone,
  Briefcase,
  GraduationCap,
  Clock,
  User,
  RefreshCw,
  Sparkles,
  GitBranch,
  ClipboardList,
  AlertTriangle,
} from "lucide-react";

import { api, ApiError } from "@/lib/trpc";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorAlert } from "@/components/common/error-alert";

interface CandidateRead {
  id: string;
  name: string;
  email: string;
  phone: string | null;
  summary: string | null;
  skills: string[];
  experience_years: number | null;
  education: string | null;
  current_company: string | null;
  current_title: string | null;
  status: string;
  created_at: string;
  updated_at: string;
}

interface DecisionChainStateHistoryItem {
  id: string;
  from_state: string | null;
  to_state: string;
  reason: string;
  operator_id: string;
  triggered_actions: Array<Record<string, unknown>>;
  created_at: string | null;
}

interface DecisionChainJobProfileSummary {
  id: string;
  code: string;
  title: string;
  level: string;
  hard_requirements: string[];
  soft_requirements: string[];
  evaluation_dimensions: Array<Record<string, unknown>>;
  interview_focus: string[];
}

interface DecisionChainRejectionSummary {
  id: string;
  reason_code: string;
  reason_category: string;
  primary_reason: string;
  stage: string;
  evidence: string;
  suggested_action: string | null;
  created_at: string | null;
}

interface DecisionChainApplicationSummary {
  id: string;
  job_id: string | null;
  job_title: string | null;
  status: string;
  match_score: number | null;
  ai_summary: string | null;
  created_at: string | null;
}

interface DecisionChainInterviewSummary {
  id: string;
  application_id: string | null;
  type: string;
  status: string;
  scheduled_at: string | null;
  feedback: string | null;
}

interface DecisionChainInterviewFeedbackSummary {
  id: string;
  interview_id: string;
  round: string;
  overall_score: number | null;
  verdict: string;
  dimensions: string | null;
  key_observations: string | null;
  red_flags: string | null;
  feedback: string | null;
  created_at: string | null;
}

interface CandidateDecisionChainRead {
  candidate: {
    id: string;
    name: string;
    status: string;
    recruitment_state: string;
  };
  state_history: DecisionChainStateHistoryItem[];
  job_profiles: DecisionChainJobProfileSummary[];
  applications: DecisionChainApplicationSummary[];
  interviews: DecisionChainInterviewSummary[];
  interview_feedback: DecisionChainInterviewFeedbackSummary[];
  rejections: DecisionChainRejectionSummary[];
  missing_sections: string[];
}

const STATUS_VARIANT: Record<
  string,
  "default" | "secondary" | "destructive" | "outline"
> = {
  active: "default",
  archived: "outline",
  hired: "secondary",
  rejected: "destructive",
};

interface PageProps {
  params: Promise<{ id: string }>;
}

export default function CandidateDetailPage({ params }: PageProps) {
  const { id } = use(params);
  const router = useRouter();
  const [candidate, setCandidate] = useState<CandidateRead | null>(null);
  const [decisionChain, setDecisionChain] =
    useState<CandidateDecisionChainRead | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [data, chain] = await Promise.all([
        api.get<CandidateRead>(`/candidates/${id}`),
        api.get<CandidateDecisionChainRead>(`/candidates/${id}/decision-chain`),
      ]);
      setCandidate(data);
      setDecisionChain(chain);
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) {
        notFound();
      } else {
        setError(e instanceof Error ? e.message : "加载候选人失败");
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (id) void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  if (loading) {
    return (
      <main
        className="container mx-auto p-6"
        aria-labelledby="page-title-loading"
      >
        <h1 id="page-title-loading" className="sr-only">
          加载候选人详情中
        </h1>
        <div className="mb-4 flex items-center gap-2">
          <Skeleton className="h-9 w-9" />
          <Skeleton className="h-6 w-48" />
        </div>
        <div className="grid gap-4 md:grid-cols-3">
          <Skeleton className="h-96 md:col-span-2" />
          <Skeleton className="h-96" />
        </div>
      </main>
    );
  }

  if (error) {
    return (
      <main
        className="container mx-auto p-6"
        aria-labelledby="page-title-error"
      >
        <h1 id="page-title-error" className="sr-only">
          加载候选人失败
        </h1>
        <div className="mb-4">
          <Button variant="ghost" size="sm" onClick={() => router.back()}>
            <ArrowLeft className="mr-1 h-4 w-4" />
            返回
          </Button>
        </div>
        <ErrorAlert message={error} variant="error" />
        <div className="mt-4">
          <Button variant="outline" onClick={load}>
            <RefreshCw className="mr-1 h-4 w-4" />
            重试
          </Button>
        </div>
      </main>
    );
  }

  if (!candidate) {
    return null;
  }

  const createdAtLocal = new Date(candidate.created_at).toLocaleString("zh-CN");
  const updatedAtLocal = new Date(candidate.updated_at).toLocaleString("zh-CN");
  const recruitmentState =
    decisionChain?.candidate.recruitment_state ?? "未采集";
  const stateHistory = decisionChain?.state_history ?? [];
  const jobProfiles = decisionChain?.job_profiles ?? [];
  const applications = decisionChain?.applications ?? [];
  const interviews = decisionChain?.interviews ?? [];
  const interviewFeedback = decisionChain?.interview_feedback ?? [];
  const rejections = decisionChain?.rejections ?? [];

  return (
    <main
      className="container mx-auto p-6 space-y-4"
      aria-labelledby="page-title"
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={() => router.back()}>
            <ArrowLeft className="mr-1 h-4 w-4" />
            返回
          </Button>
          <h1
            id="page-title"
            className="text-2xl font-bold flex items-center gap-2"
          >
            <User className="h-6 w-6" />
            {candidate.name}
          </h1>
          <Badge variant={STATUS_VARIANT[candidate.status] || "outline"}>
            {candidate.status}
          </Badge>
        </div>
        <Link href={`/agent?focus=msg_candidate_${candidate.id}`}>
          <Button variant="outline" size="sm">
            <Sparkles className="mr-1 h-4 w-4" />
            在助手中讨论
          </Button>
        </Link>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        {/* 主信息卡片 — 左 2/3 */}
        <Card className="md:col-span-2">
          <CardHeader>
            <CardTitle>个人信息</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <dl className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div className="flex items-start gap-2">
                <Mail
                  className="h-4 w-4 mt-0.5 text-muted-foreground shrink-0"
                  aria-hidden
                />
                <div className="min-w-0">
                  <dt className="text-xs text-muted-foreground">邮箱</dt>
                  <dd className="text-sm">
                    <a
                      href={`mailto:${candidate.email}`}
                      className="hover:underline"
                    >
                      {candidate.email}
                    </a>
                  </dd>
                </div>
              </div>

              {candidate.phone && (
                <div className="flex items-start gap-2">
                  <Phone
                    className="h-4 w-4 mt-0.5 text-muted-foreground shrink-0"
                    aria-hidden
                  />
                  <div className="min-w-0">
                    <dt className="text-xs text-muted-foreground">电话</dt>
                    <dd className="text-sm">{candidate.phone}</dd>
                  </div>
                </div>
              )}

              {candidate.current_title && (
                <div className="flex items-start gap-2">
                  <Briefcase
                    className="h-4 w-4 mt-0.5 text-muted-foreground shrink-0"
                    aria-hidden
                  />
                  <div className="min-w-0">
                    <dt className="text-xs text-muted-foreground">当前职位</dt>
                    <dd className="text-sm">
                      {candidate.current_title}
                      {candidate.current_company && (
                        <span className="text-muted-foreground">
                          {" "}
                          · {candidate.current_company}
                        </span>
                      )}
                    </dd>
                  </div>
                </div>
              )}

              {candidate.experience_years !== null && (
                <div className="flex items-start gap-2">
                  <Clock
                    className="h-4 w-4 mt-0.5 text-muted-foreground shrink-0"
                    aria-hidden
                  />
                  <div className="min-w-0">
                    <dt className="text-xs text-muted-foreground">工作年限</dt>
                    <dd className="text-sm">{candidate.experience_years} 年</dd>
                  </div>
                </div>
              )}

              {candidate.education && (
                <div className="flex items-start gap-2 sm:col-span-2">
                  <GraduationCap
                    className="h-4 w-4 mt-0.5 text-muted-foreground shrink-0"
                    aria-hidden
                  />
                  <div className="min-w-0">
                    <dt className="text-xs text-muted-foreground">教育背景</dt>
                    <dd className="text-sm">{candidate.education}</dd>
                  </div>
                </div>
              )}
            </dl>

            {candidate.summary && (
              <div>
                <h2 className="mb-1 text-sm font-semibold">简介</h2>
                <p className="text-sm text-muted-foreground whitespace-pre-wrap">
                  {candidate.summary}
                </p>
              </div>
            )}

            {candidate.skills.length > 0 && (
              <div>
                <h2 className="mb-2 text-sm font-semibold">技能</h2>
                <div className="flex flex-wrap gap-1.5">
                  {candidate.skills.map((skill) => (
                    <Badge key={skill} variant="secondary">
                      {skill}
                    </Badge>
                  ))}
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        {/* 元数据卡片 — 右 1/3 */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">元数据</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-xs">
            <div>
              <dt className="text-muted-foreground">候选人 ID</dt>
              <dd className="font-mono break-all">{candidate.id}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">创建时间</dt>
              <dd>{createdAtLocal}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">更新时间</dt>
              <dd>{updatedAtLocal}</dd>
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <GitBranch className="h-4 w-4" />
              招聘决策链
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm text-muted-foreground">
                当前招聘状态
              </span>
              <Badge variant="outline">{recruitmentState}</Badge>
            </div>

            {stateHistory.length > 0 ? (
              <div className="space-y-3">
                {stateHistory.map((item) => (
                  <div key={item.id} className="rounded-lg border p-3">
                    <div className="flex flex-wrap items-center gap-2 text-sm font-medium">
                      <Badge variant="secondary">
                        {item.from_state ?? "起点"}
                      </Badge>
                      <span>→</span>
                      <Badge>{item.to_state}</Badge>
                    </div>
                    <p className="mt-2 text-sm text-muted-foreground">
                      {item.reason}
                    </p>
                    <div className="mt-2 text-xs text-muted-foreground">
                      {item.created_at
                        ? new Date(item.created_at).toLocaleString("zh-CN")
                        : "时间未采集"}
                      <span className="mx-2">·</span>
                      操作人 {item.operator_id || "未采集"}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
                状态历史未采集
              </p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <ClipboardList className="h-4 w-4" />
              岗位画像
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {jobProfiles.length > 0 ? (
              jobProfiles.map((profile) => (
                <div
                  key={profile.id}
                  className="space-y-3 rounded-lg border p-3"
                >
                  <div>
                    <div className="text-sm font-medium">{profile.title}</div>
                    <div className="text-xs text-muted-foreground">
                      {profile.code} · {profile.level}
                    </div>
                  </div>
                  <div>
                    <div className="mb-1 text-xs text-muted-foreground">
                      硬性要求
                    </div>
                    <div className="flex flex-wrap gap-1">
                      {profile.hard_requirements.length > 0 ? (
                        profile.hard_requirements.map((item) => (
                          <Badge key={item} variant="outline">
                            {item}
                          </Badge>
                        ))
                      ) : (
                        <span className="text-xs text-muted-foreground">
                          未采集
                        </span>
                      )}
                    </div>
                  </div>
                  <div>
                    <div className="mb-1 text-xs text-muted-foreground">
                      面试重点
                    </div>
                    <div className="space-y-1 text-xs">
                      {profile.interview_focus.length > 0 ? (
                        profile.interview_focus.map((item) => (
                          <div key={item}>· {item}</div>
                        ))
                      ) : (
                        <span className="text-muted-foreground">未采集</span>
                      )}
                    </div>
                  </div>
                </div>
              ))
            ) : (
              <p className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
                岗位画像未采集
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Briefcase className="h-4 w-4" />
              投递记录
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {applications.length > 0 ? (
              applications.map((item) => (
                <div key={item.id} className="rounded-lg border p-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="outline">{item.status}</Badge>
                    {item.match_score !== null && (
                      <Badge variant="secondary">匹配 {item.match_score}</Badge>
                    )}
                  </div>
                  <div className="mt-2 text-sm font-medium">
                    {item.job_title || "职位未采集"}
                  </div>
                  <p className="mt-1 text-sm text-muted-foreground">
                    {item.ai_summary || "AI 摘要未采集"}
                  </p>
                  <p className="mt-2 text-xs text-muted-foreground">
                    {item.created_at
                      ? new Date(item.created_at).toLocaleString("zh-CN")
                      : "时间未采集"}
                  </p>
                </div>
              ))
            ) : (
              <p className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
                投递记录未采集
              </p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Clock className="h-4 w-4" />
              面试记录
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {interviews.length > 0 ? (
              interviews.map((item) => (
                <div key={item.id} className="rounded-lg border p-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="outline">{item.type}</Badge>
                    <Badge variant="secondary">{item.status}</Badge>
                  </div>
                  <p className="mt-2 text-sm text-muted-foreground">
                    {item.feedback || "面试备注未采集"}
                  </p>
                  <p className="mt-2 text-xs text-muted-foreground">
                    {item.scheduled_at
                      ? new Date(item.scheduled_at).toLocaleString("zh-CN")
                      : "时间未采集"}
                  </p>
                </div>
              ))
            ) : (
              <p className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
                面试记录未采集
              </p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <ClipboardList className="h-4 w-4" />
              面试反馈
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {interviewFeedback.length > 0 ? (
              interviewFeedback.map((item) => (
                <div key={item.id} className="rounded-lg border p-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="outline">{item.round}</Badge>
                    <Badge>{item.verdict}</Badge>
                    {item.overall_score !== null && (
                      <Badge variant="secondary">{item.overall_score}</Badge>
                    )}
                  </div>
                  <p className="mt-2 text-sm text-muted-foreground">
                    {item.key_observations || item.feedback || "反馈内容未采集"}
                  </p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    红旗：{item.red_flags || "未采集"}
                  </p>
                </div>
              ))
            ) : (
              <p className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
                面试反馈未采集
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <AlertTriangle className="h-4 w-4" />
            结构化淘汰原因
          </CardTitle>
        </CardHeader>
        <CardContent>
          {rejections.length > 0 ? (
            <div className="grid gap-3 md:grid-cols-2">
              {rejections.map((item) => (
                <div key={item.id} className="rounded-lg border p-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="destructive">{item.reason_category}</Badge>
                    <Badge variant="outline">{item.stage}</Badge>
                  </div>
                  <div className="mt-2 text-sm font-medium">
                    {item.primary_reason}
                  </div>
                  <p className="mt-1 text-sm text-muted-foreground">
                    证据：{item.evidence}
                  </p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    建议：{item.suggested_action || "未采集"}
                  </p>
                  <p className="mt-2 text-xs text-muted-foreground">
                    {item.created_at
                      ? new Date(item.created_at).toLocaleString("zh-CN")
                      : "时间未采集"}
                  </p>
                </div>
              ))}
            </div>
          ) : (
            <p className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
              结构化淘汰原因未采集
            </p>
          )}
        </CardContent>
      </Card>
    </main>
  );
}
