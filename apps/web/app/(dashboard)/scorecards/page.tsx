"use client";

import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/trpc";

interface ScorecardDimension {
  id: string;
  name: string;
  weight: number;
  description?: string;
  required: boolean;
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

interface ListResponse<T> {
  items: T[];
  total: number;
}

export default function ScorecardsPage() {
  const [templates, setTemplates] = useState<ScorecardTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [interviewId, setInterviewId] = useState("");
  const [profileId, setProfileId] = useState("");
  const [selectedTemplateId, setSelectedTemplateId] = useState("");
  const [scores, setScores] = useState<Record<string, string>>({});
  const [evidence, setEvidence] = useState<Record<string, string>>({});
  const [summary, setSummary] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [creatingTemplate, setCreatingTemplate] = useState(false);

  const selectedTemplate = useMemo(
    () =>
      templates.find((item) => item.id === selectedTemplateId) || templates[0],
    [selectedTemplateId, templates],
  );

  useEffect(() => {
    void fetchTemplates();
  }, []);

  const fetchTemplates = async () => {
    setLoading(true);
    try {
      const res = await api.get<ListResponse<ScorecardTemplate>>(
        "/scorecards/templates?limit=50",
      );
      setTemplates(res.items || []);
      if (res.items?.[0]) setSelectedTemplateId(res.items[0].id);
    } catch {
      toast.error("加载评分卡失败");
    } finally {
      setLoading(false);
    }
  };

  const createTemplateFromProfile = async () => {
    if (!profileId.trim()) {
      toast.error("请填写岗位画像 ID");
      return;
    }
    setCreatingTemplate(true);
    try {
      const template = await api.post<ScorecardTemplate>(
        `/scorecards/templates/from-job-profile/${profileId}`,
        {
          round_type: "technical",
          status: "active",
        },
      );
      toast.success("已从岗位画像生成 active 评分卡");
      setTemplates((prev) => [template, ...prev]);
      setSelectedTemplateId(template.id);
      setProfileId("");
    } catch {
      toast.error("生成评分卡失败");
    } finally {
      setCreatingTemplate(false);
    }
  };

  const submitScorecard = async () => {
    if (!interviewId || !selectedTemplate) {
      toast.error("请填写面试 ID 并选择评分卡");
      return;
    }
    const dimensionScores = selectedTemplate.dimensions.map((dimension) => ({
      dimension_id: dimension.id,
      score: Number(scores[dimension.id] || 0),
      evidence: evidence[dimension.id] || "",
    }));
    if (
      dimensionScores.some(
        (item) => item.score < 1 || item.score > 5 || !item.evidence.trim(),
      )
    ) {
      toast.error("每个维度都需要 1-5 分和证据");
      return;
    }
    setSubmitting(true);
    try {
      await api.post(`/scorecards/interviews/${interviewId}/submissions`, {
        scorecard_template_id: selectedTemplate.id,
        verdict: "consider",
        summary,
        risk_flags: [],
        dimension_scores: dimensionScores,
      });
      toast.success("评分卡已提交");
      setSummary("");
      setScores({});
      setEvidence({});
    } catch {
      toast.error("提交评分卡失败");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">面试评分卡</h1>
        <p className="text-sm text-muted-foreground">
          结构化记录面试维度分、行为证据和推荐结论。
        </p>
      </div>

      <div className="grid gap-4 lg:grid-cols-[1fr_1.2fr]">
        <Card>
          <CardHeader>
            <CardTitle>评分卡模板</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="space-y-2 rounded-lg border p-3">
              <label className="text-sm font-medium">岗位画像 ID</label>
              <Input
                value={profileId}
                onChange={(event) => setProfileId(event.target.value)}
                placeholder="job profile uuid"
              />
              <Button
                className="w-full"
                onClick={createTemplateFromProfile}
                disabled={creatingTemplate}
              >
                {creatingTemplate ? "生成中..." : "从画像生成技术面评分卡"}
              </Button>
            </div>
            {loading ? (
              <p className="text-sm text-muted-foreground">加载中...</p>
            ) : null}
            {!loading && templates.length === 0 ? (
              <p className="text-sm text-muted-foreground">暂无评分卡模板。</p>
            ) : null}
            {templates.map((template) => (
              <button
                key={template.id}
                className={`w-full rounded-lg border p-3 text-left transition hover:bg-muted ${selectedTemplate?.id === template.id ? "border-primary" : ""}`}
                onClick={() => setSelectedTemplateId(template.id)}
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="font-medium">{template.name}</div>
                  <Badge variant="outline">{template.status}</Badge>
                </div>
                <div className="mt-1 text-xs text-muted-foreground">
                  {template.round_type} · {template.dimensions.length} 个维度
                </div>
                {template.profile_version_id ? (
                  <div className="mt-1 truncate text-xs text-muted-foreground">
                    画像版本：{template.profile_version_id}
                  </div>
                ) : null}
              </button>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>提交面试评分</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <label className="text-sm font-medium">面试 ID</label>
              <Input
                value={interviewId}
                onChange={(event) => setInterviewId(event.target.value)}
                placeholder="interview uuid"
              />
            </div>

            {selectedTemplate ? (
              <div className="space-y-4">
                <div className="rounded-lg border bg-muted/40 p-3">
                  <div className="font-medium">{selectedTemplate.name}</div>
                  <div className="text-xs text-muted-foreground">
                    {selectedTemplate.round_type}
                  </div>
                </div>
                {selectedTemplate.dimensions.map((dimension) => (
                  <div
                    key={dimension.id}
                    className="space-y-2 rounded-lg border p-3"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div>
                        <div className="font-medium">{dimension.name}</div>
                        <div className="text-xs text-muted-foreground">
                          权重 {Math.round(dimension.weight * 100)}%
                        </div>
                      </div>
                      {dimension.required ? <Badge>必填</Badge> : null}
                    </div>
                    {dimension.description ? (
                      <p className="text-sm text-muted-foreground">
                        {dimension.description}
                      </p>
                    ) : null}
                    <Input
                      type="number"
                      min={1}
                      max={5}
                      value={scores[dimension.id] || ""}
                      onChange={(event) =>
                        setScores((prev) => ({
                          ...prev,
                          [dimension.id]: event.target.value,
                        }))
                      }
                      placeholder="1-5 分"
                    />
                    <Textarea
                      value={evidence[dimension.id] || ""}
                      onChange={(event) =>
                        setEvidence((prev) => ({
                          ...prev,
                          [dimension.id]: event.target.value,
                        }))
                      }
                      placeholder="填写行为证据"
                    />
                  </div>
                ))}
                <Textarea
                  value={summary}
                  onChange={(event) => setSummary(event.target.value)}
                  placeholder="总体评价"
                />
                <Button onClick={submitScorecard} disabled={submitting}>
                  {submitting ? "提交中..." : "提交评分卡"}
                </Button>
              </div>
            ) : null}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
