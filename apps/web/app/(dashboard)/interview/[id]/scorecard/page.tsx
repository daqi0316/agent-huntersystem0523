"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/trpc";

interface ScorecardAnchor {
  score: number;
  anchor_text: string;
}

interface ScorecardDimension {
  id: string;
  name: string;
  weight: number;
  description?: string | null;
  required: boolean;
  anchors: ScorecardAnchor[];
}

interface ScorecardTemplate {
  id: string;
  job_profile_id?: string | null;
  profile_version_id?: string | null;
  name: string;
  round_type: string;
  status: string;
  dimensions: ScorecardDimension[];
}

export default function InterviewScorecardPage() {
  const params = useParams<{ id: string }>();
  const interviewId = params.id;
  const [template, setTemplate] = useState<ScorecardTemplate | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [scores, setScores] = useState<Record<string, string>>({});
  const [evidence, setEvidence] = useState<Record<string, string>>({});
  const [summary, setSummary] = useState("");
  const [riskFlags, setRiskFlags] = useState("");

  const overallScore = useMemo(() => {
    if (!template) return 0;
    return template.dimensions.reduce((total, dimension) => {
      const score = Number(scores[dimension.id] || 0);
      return total + score * dimension.weight;
    }, 0);
  }, [template, scores]);

  useEffect(() => {
    async function loadScorecard() {
      setLoading(true);
      try {
        const data = await api.get<ScorecardTemplate>(`/scorecards/interviews/${interviewId}/scorecard`);
        setTemplate(data);
      } catch {
        toast.error("暂无可用评分卡，请先为岗位绑定并激活评分卡模板");
      } finally {
        setLoading(false);
      }
    }
    void loadScorecard();
  }, [interviewId]);

  const submit = async () => {
    if (!template) return;
    const dimensionScores = template.dimensions.map((dimension) => ({
      dimension_id: dimension.id,
      score: Number(scores[dimension.id] || 0),
      evidence: evidence[dimension.id] || "",
    }));
    if (dimensionScores.some((item) => item.score < 1 || item.score > 5 || !item.evidence.trim())) {
      toast.error("每个维度都需要 1-5 分和行为证据");
      return;
    }
    setSubmitting(true);
    try {
      await api.post(`/scorecards/interviews/${interviewId}/submissions`, {
        scorecard_template_id: template.id,
        verdict: overallScore >= 4 ? "hire" : overallScore < 3 ? "pass" : "consider",
        summary,
        risk_flags: riskFlags.split("\n").map((item) => item.trim()).filter(Boolean),
        dimension_scores: dimensionScores,
      });
      toast.success("评分卡已提交");
      setScores({});
      setEvidence({});
      setSummary("");
      setRiskFlags("");
    } catch {
      toast.error("提交评分卡失败");
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  if (!template) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>面试评分卡</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">暂无可用评分卡。</CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">面试评分卡</h1>
        <p className="text-sm text-muted-foreground">面试 ID：{interviewId}</p>
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-start justify-between gap-3">
            <div>
              <CardTitle>{template.name}</CardTitle>
              <p className="mt-1 text-sm text-muted-foreground">{template.round_type}</p>
            </div>
            <Badge variant="outline">{template.status}</Badge>
          </div>
        </CardHeader>
        <CardContent className="space-y-2 text-sm text-muted-foreground">
          <div>岗位画像：{template.job_profile_id || "未绑定"}</div>
          <div>画像版本：{template.profile_version_id || "未绑定"}</div>
          <div>当前加权分：{overallScore.toFixed(2)}</div>
        </CardContent>
      </Card>

      {template.dimensions.map((dimension) => (
        <Card key={dimension.id}>
          <CardHeader>
            <div className="flex items-start justify-between gap-3">
              <div>
                <CardTitle className="text-base">{dimension.name}</CardTitle>
                <p className="mt-1 text-sm text-muted-foreground">权重 {Math.round(dimension.weight * 100)}%</p>
              </div>
              {dimension.required ? <Badge>必填</Badge> : null}
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            {dimension.description ? <p className="text-sm text-muted-foreground">{dimension.description}</p> : null}
            <div className="grid gap-2 md:grid-cols-3">
              {dimension.anchors.map((anchor) => (
                <div key={anchor.score} className="rounded-lg border p-2 text-xs">
                  <div className="font-medium">{anchor.score} 分锚定</div>
                  <div className="mt-1 text-muted-foreground">{anchor.anchor_text}</div>
                </div>
              ))}
            </div>
            <Input
              type="number"
              min={1}
              max={5}
              value={scores[dimension.id] || ""}
              onChange={(event) => setScores((prev) => ({ ...prev, [dimension.id]: event.target.value }))}
              placeholder="1-5 分"
            />
            <Textarea
              value={evidence[dimension.id] || ""}
              onChange={(event) => setEvidence((prev) => ({ ...prev, [dimension.id]: event.target.value }))}
              placeholder="填写行为证据：候选人说了什么、做过什么、无法回答什么"
            />
          </CardContent>
        </Card>
      ))}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">总体结论</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <Textarea value={summary} onChange={(event) => setSummary(event.target.value)} placeholder="总体评价" />
          <Textarea value={riskFlags} onChange={(event) => setRiskFlags(event.target.value)} placeholder="风险点，每行一个" />
          <Button onClick={submit} disabled={submitting}>{submitting ? "提交中..." : "提交评分卡"}</Button>
        </CardContent>
      </Card>
    </div>
  );
}
