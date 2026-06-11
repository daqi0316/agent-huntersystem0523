"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, ExternalLink, Globe, MapPin, DollarSign, Briefcase, GraduationCap, Building2, ChevronLeft, ChevronRight, Sparkles, Brain, AlertTriangle, TrendingUp, Layers } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useCandidateDetail, useAnalyzeCandidate, type AiAnalysis, type MatchScore } from "@/hooks/use-sourcing";

const COMPARE_FIELDS = [
  { key: "name", label: "姓名" },
  { key: "title", label: "职位" },
  { key: "company", label: "公司" },
  { key: "location", label: "地点" },
  { key: "salary", label: "薪资" },
  { key: "experience_years", label: "经验" },
  { key: "education", label: "学历" },
  { key: "skills", label: "技能" },
];

function extractField(data: Record<string, any>, fieldKey: string): string {
  if (fieldKey === "skills") {
    const s = data.skills || data.skill_tags || [];
    return Array.isArray(s) ? s.join(", ") : String(s || "");
  }
  const val = data[fieldKey] ?? data[`current_${fieldKey}`] ?? "";
  return val != null ? String(val) : "";
}

function MultiSourceCompareCard({ rawData }: { rawData: Record<string, any> }) {
  const platforms = Object.keys(rawData);
  const rows = COMPARE_FIELDS.map(({ key, label }) => {
    const values = platforms.map((p) => extractField(rawData[p] || {}, key));
    const unique = new Set(values.map((v) => v.trim().toLowerCase()));
    const hasDiff = unique.size > 1;
    return { label, values, hasDiff };
  });

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <Layers className="h-4 w-4 text-blue-500" />
          <CardTitle className="text-base">多源对比</CardTitle>
        </div>
      </CardHeader>
      <CardContent className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b">
              <th className="text-left py-1.5 pr-3 font-medium text-muted-foreground w-16">字段</th>
              {platforms.map((p) => (
                <th key={p} className="text-left py-1.5 px-2 font-medium">{sourceBadge(p)}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map(({ label, values, hasDiff }) => (
              <tr key={label} className="border-b last:border-0">
                <td className="py-1.5 pr-3 text-muted-foreground whitespace-nowrap">{label}</td>
                {values.map((v, i) => (
                  <td
                    key={i}
                    className={`py-1.5 px-2 ${hasDiff ? "bg-yellow-50 dark:bg-yellow-950/20" : ""}`}
                  >
                    <span className={`${hasDiff ? "font-medium" : ""} ${!v ? "text-muted-foreground italic" : ""}`}>
                      {v || "-"}
                    </span>
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </CardContent>
    </Card>
  );
}

const platformColor: Record<string, string> = {
  boss_zhipin: "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400",
  linkedin: "bg-sky-100 text-sky-800 dark:bg-sky-900/30 dark:text-sky-400",
  lagou: "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400",
  maimai: "bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-400",
  zhilian: "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400",
};

function sourceBadge(platform: string) {
  return (
    <Badge className={platformColor[platform] || "bg-gray-100 text-gray-800"}>
      {platform}
    </Badge>
  );
}

function ScoreBar({ value, label }: { value?: number; label: string }) {
  if (value == null) return null;
  const pct = Math.round(value * 100);
  const color = pct >= 80 ? "bg-green-500" : pct >= 60 ? "bg-yellow-500" : "bg-red-500";
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-xs">
        <span className="text-muted-foreground">{label}</span>
        <span className="font-medium">{pct}%</span>
      </div>
      <div className="h-1.5 w-full rounded-full bg-muted">
        <div className={`h-full rounded-full ${color} transition-all`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function ConfidenceBadge({ confidence }: { confidence?: number }) {
  if (confidence == null) return null;
  const label = confidence >= 0.7 ? "AI分析" : confidence >= 0.3 ? "AI推测" : "AI低置信度";
  const color = confidence >= 0.7
    ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400"
    : "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400";
  return <Badge className={color}>{label}</Badge>;
}

function AiAnalysisCard({ analysis, matchScore, isAnalyzing, onAnalyze }: {
  analysis?: AiAnalysis;
  matchScore?: MatchScore;
  isAnalyzing: boolean;
  onAnalyze: () => void;
}) {
  const hasAnalysis = analysis?.skills_extracted && analysis.skills_extracted.length > 0;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Brain className="h-4 w-4 text-purple-500" />
            <CardTitle className="text-base">AI 分析</CardTitle>
          </div>
          <div className="flex items-center gap-2">
            <ConfidenceBadge confidence={analysis?.confidence} />
            <Button size="sm" variant={hasAnalysis ? "outline" : "default"} onClick={onAnalyze} disabled={isAnalyzing}>
              <Sparkles className="h-3.5 w-3.5 mr-1" />
              {isAnalyzing ? "分析中..." : hasAnalysis ? "重新分析" : "开始分析"}
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {!hasAnalysis && !isAnalyzing && (
          <p className="text-sm text-muted-foreground">点击"开始分析"使用 AI 提取技能、分析职业轨迹并生成摘要。</p>
        )}

        {isAnalyzing && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground py-4">
            <Sparkles className="h-4 w-4 animate-pulse" />
            AI 分析中...
          </div>
        )}

        {hasAnalysis && (
          <div className="space-y-5">
            {analysis.summary?.one_liner && (
              <div>
                <p className="text-sm font-medium">{analysis.summary.one_liner}</p>
              </div>
            )}

            {analysis.skills_extracted && analysis.skills_extracted.length > 0 && (
              <div>
                <h4 className="text-xs font-medium text-muted-foreground mb-1.5 flex items-center gap-1">
                  <Layers className="h-3 w-3" /> 技能提取
                </h4>
                <div className="flex flex-wrap gap-1.5">
                  {analysis.skills_extracted.map((s: string) => (
                    <Badge key={s} variant="outline" className="text-xs">{s}</Badge>
                  ))}
                </div>
              </div>
            )}

            {analysis.skill_categories && Object.keys(analysis.skill_categories).length > 0 && (
              <div className="grid grid-cols-2 gap-3">
                {Object.entries(analysis.skill_categories).map(([cat, skills]) =>
                  skills && skills.length > 0 ? (
                    <div key={cat}>
                      <h4 className="text-xs font-medium text-muted-foreground mb-1">{cat}</h4>
                      <div className="flex flex-wrap gap-1">
                        {skills.map((s: string) => (
                          <Badge key={s} variant="secondary" className="text-xs">{s}</Badge>
                        ))}
                      </div>
                    </div>
                  ) : null
                )}
              </div>
            )}

            {analysis.career_trajectory && (
              <div>
                <h4 className="text-xs font-medium text-muted-foreground mb-1.5 flex items-center gap-1">
                  <TrendingUp className="h-3 w-3" /> 职业轨迹
                </h4>
                <div className="text-sm space-y-0.5">
                  {analysis.career_trajectory.direction && (
                    <p><span className="text-muted-foreground">方向：</span>{analysis.career_trajectory.direction}</p>
                  )}
                  {analysis.career_trajectory.stability && (
                    <p><span className="text-muted-foreground">稳定性：</span>
                      <Badge variant="outline" className="text-xs ml-0.5">{analysis.career_trajectory.stability}</Badge>
                    </p>
                  )}
                  {analysis.career_trajectory.avg_tenure_years != null && (
                    <p><span className="text-muted-foreground">平均在职：</span>{analysis.career_trajectory.avg_tenure_years} 年</p>
                  )}
                </div>
              </div>
            )}

            <div className="grid grid-cols-2 gap-4">
              {analysis.summary?.strengths && analysis.summary.strengths.length > 0 && (
                <div>
                  <h4 className="text-xs font-medium text-green-600 dark:text-green-400 mb-1">优势</h4>
                  <ul className="space-y-0.5">
                    {analysis.summary.strengths.map((s: string, i: number) => (
                      <li key={i} className="text-xs text-muted-foreground flex items-start gap-1">
                        <span className="text-green-500 mt-0.5">•</span>{s}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {analysis.summary?.risks && analysis.summary.risks.length > 0 && (
                <div>
                  <h4 className="text-xs font-medium text-red-600 dark:text-red-400 mb-1 flex items-center gap-1">
                    <AlertTriangle className="h-3 w-3" /> 风险
                  </h4>
                  <ul className="space-y-0.5">
                    {analysis.summary.risks.map((s: string, i: number) => (
                      <li key={i} className="text-xs text-muted-foreground flex items-start gap-1">
                        <span className="text-red-500 mt-0.5">•</span>{s}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>

            {matchScore && matchScore.overall_score != null && (
              <div className="rounded-md border p-3 space-y-2">
                <h4 className="text-xs font-medium text-muted-foreground flex items-center gap-1">
                  <Sparkles className="h-3 w-3" /> JD 匹配度
                </h4>
                <ScoreBar value={matchScore.overall_score} label="综合匹配" />
                {matchScore.dimensions && (
                  <div className="space-y-1.5 pt-1">
                    <ScoreBar value={matchScore.dimensions.skills_match?.score} label="技能匹配" />
                    <ScoreBar value={matchScore.dimensions.experience_match?.score} label="经验匹配" />
                    <ScoreBar value={matchScore.dimensions.industry_match?.score} label="行业匹配" />
                  </div>
                )}
                {matchScore.summary && (
                  <p className="text-xs text-muted-foreground pt-1">{matchScore.summary}</p>
                )}
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default function SourcingCandidateDetail() {
  const params = useParams();
  const candidateId = params.candidateId as string;
  const [page, setPage] = useState(1);

  const { data, isLoading } = useCandidateDetail(candidateId);
  const analyzeMutation = useAnalyzeCandidate();

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-40 w-full" />
        <Skeleton className="h-60 w-full" />
      </div>
    );
  }

  if (!data?.data) {
    return (
      <div className="text-center py-12">
        <p className="text-muted-foreground">候选人不存在</p>
        <Link href="/sourcing/candidates">
          <Button variant="link">返回列表</Button>
        </Link>
      </div>
    );
  }

  const c = data.data;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <Link
          href="/sourcing/candidates"
          className="text-sm text-muted-foreground hover:text-primary flex items-center gap-1 mb-2"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          返回候选人列表
        </Link>
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-2xl font-bold tracking-tight">{c.name}</h1>
            <p className="text-sm text-muted-foreground mt-1">
              {c.current_title}{c.current_title && c.current_company ? " · " : ""}{c.current_company}
            </p>
          </div>
          <div className="flex items-center gap-2">
            {c.source_platforms?.map(sourceBadge)}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {c.current_title && (
          <Card>
            <CardContent className="pt-4">
              <div className="flex items-center gap-2 text-sm">
                <Briefcase className="h-4 w-4 text-muted-foreground" />
                <span className="text-muted-foreground">职位</span>
              </div>
              <p className="text-sm font-medium mt-1">{c.current_title}</p>
            </CardContent>
          </Card>
        )}
        {c.current_company && (
          <Card>
            <CardContent className="pt-4">
              <div className="flex items-center gap-2 text-sm">
                <Building2 className="h-4 w-4 text-muted-foreground" />
                <span className="text-muted-foreground">公司</span>
              </div>
              <p className="text-sm font-medium mt-1">{c.current_company}</p>
            </CardContent>
          </Card>
        )}
        {c.location && (
          <Card>
            <CardContent className="pt-4">
              <div className="flex items-center gap-2 text-sm">
                <MapPin className="h-4 w-4 text-muted-foreground" />
                <span className="text-muted-foreground">地点</span>
              </div>
              <p className="text-sm font-medium mt-1">{c.location}</p>
            </CardContent>
          </Card>
        )}
        {c.salary && (
          <Card>
            <CardContent className="pt-4">
              <div className="flex items-center gap-2 text-sm">
                <DollarSign className="h-4 w-4 text-muted-foreground" />
                <span className="text-muted-foreground">薪资</span>
              </div>
              <p className="text-sm font-medium mt-1">{c.salary}</p>
            </CardContent>
          </Card>
        )}
        {c.experience_years != null && (
          <Card>
            <CardContent className="pt-4">
              <div className="flex items-center gap-2 text-sm">
                <GraduationCap className="h-4 w-4 text-muted-foreground" />
                <span className="text-muted-foreground">经验</span>
              </div>
              <p className="text-sm font-medium mt-1">{c.experience_years} 年</p>
            </CardContent>
          </Card>
        )}
        {c.education && (
          <Card>
            <CardContent className="pt-4">
              <div className="flex items-center gap-2 text-sm">
                <GraduationCap className="h-4 w-4 text-muted-foreground" />
                <span className="text-muted-foreground">学历</span>
              </div>
              <p className="text-sm font-medium mt-1">{c.education}</p>
            </CardContent>
          </Card>
        )}
      </div>

      {c.skills && c.skills.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">技能标签</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-1.5">
              {c.skills.map((s: string) => (
                <Badge key={s} variant="secondary">{s}</Badge>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* AI 分析 */}
      <AiAnalysisCard
        analysis={c.ai_analysis}
        matchScore={(() => {
          if (!c.match_scores) return undefined;
          if (typeof c.match_scores === "object" && "overall_score" in c.match_scores) return c.match_scores as import("@/hooks/use-sourcing").MatchScore;
          const scores = c.match_scores as Record<string, import("@/hooks/use-sourcing").MatchScore>;
          return Object.values(scores)[0];
        })()}
        isAnalyzing={analyzeMutation.isPending}
        onAnalyze={() => analyzeMutation.mutate({ candidateId })}
      />

      {/* 多源对比 */}
      {c.raw_data && Object.keys(c.raw_data).length >= 2 && (
        <MultiSourceCompareCard rawData={c.raw_data as Record<string, any>} />
      )}

      {c.source_urls && Object.keys(c.source_urls).length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">多源数据</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {Object.entries(c.source_urls as Record<string, string>).map(([platform, url]) => (
                <div key={platform} className="flex items-center justify-between rounded-md border p-2.5">
                  <div className="flex items-center gap-2">
                    {sourceBadge(platform)}
                    <span className="text-xs text-muted-foreground truncate max-w-[300px]">{url}</span>
                  </div>
                  <a href={url} target="_blank" rel="noopener noreferrer">
                    <Button size="sm" variant="ghost">
                      <ExternalLink className="h-3.5 w-3.5" />
                    </Button>
                  </a>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {c.raw_data && Object.keys(c.raw_data).length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">原始数据</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {Object.entries(c.raw_data as Record<string, any>).slice((page - 1) * 3, page * 3).map(([platform, data]) => (
                <div key={platform} className="rounded-md border p-3">
                  <div className="flex items-center gap-2 mb-2">
                    {sourceBadge(platform)}
                  </div>
                  <pre className="text-xs text-muted-foreground overflow-auto max-h-40 whitespace-pre-wrap">
                    {JSON.stringify(data, null, 2)}
                  </pre>
                </div>
              ))}
              {Object.keys(c.raw_data).length > 3 && (
                <div className="flex items-center justify-between pt-2">
                  <span className="text-xs text-muted-foreground">
                    第 {page}/{Math.ceil(Object.keys(c.raw_data).length / 3)} 页
                  </span>
                  <div className="flex gap-1">
                    <Button size="sm" variant="outline" className="h-7 text-xs" disabled={page <= 1} onClick={() => setPage(p => Math.max(1, p - 1))}>
                      <ChevronLeft className="h-3 w-3" />
                    </Button>
                    <Button size="sm" variant="outline" className="h-7 text-xs" disabled={page * 3 >= Object.keys(c.raw_data).length} onClick={() => setPage(p => p + 1)}>
                      <ChevronRight className="h-3 w-3" />
                    </Button>
                  </div>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
