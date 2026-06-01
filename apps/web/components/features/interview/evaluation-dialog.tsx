"use client";

import { useState, useEffect } from "react";
import { Loader2, X, Sparkles, AlertCircle, CheckCircle2, FileText } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { api } from "@/lib/trpc";

/* ── Types ── */

interface DimensionScore {
  name: string;
  score: number;
}

interface EvaluationResponse {
  id: string;
  round: string;
  overall_score: number | null;
  verdict: string;
  dimensions: Record<string, number> | null;
  key_observations: string;
  red_flags: string;
  feedback: string;
  created_at: string;
}

interface GenerateFormResult {
  interview_id: string;
  evaluation_form: Record<string, unknown>;
}

/* ── Props ── */

interface Props {
  open: boolean;
  onClose: () => void;
  interviewId: string;
  candidateName: string;
  candidateBackground?: string;
  onSaved?: () => void;
}

/* ── Constants ── */

const VERDICT_OPTIONS = [
  { value: "strong_hire", label: "强烈推荐", color: "bg-green-100 text-green-700 border-green-200" },
  { value: "hire", label: "建议录用", color: "bg-blue-100 text-blue-700 border-blue-200" },
  { value: "consider", label: "有待观察", color: "bg-yellow-100 text-yellow-700 border-yellow-200" },
  { value: "pass", label: "不予通过", color: "bg-red-100 text-red-700 border-red-200" },
] as const;

const ROUND_OPTIONS = ["R1", "R2", "R3", "R4"] as const;

const DEFAULT_DIMENSIONS = [
  "专业技能",
  "沟通表达",
  "逻辑思维",
  "团队协作",
  "学习能力",
  "文化契合",
];

/* ── Component ── */

export default function EvaluationDialog({
  open, onClose, interviewId, candidateName, candidateBackground, onSaved,
}: Props) {
  /* ---- form state ---- */
  const [round, setRound] = useState<string>("R1");
  const [overallScore, setOverallScore] = useState<number>(7);
  const [verdict, setVerdict] = useState<string>("consider");
  const [scores, setScores] = useState<Record<string, number>>({});
  const [observations, setObservations] = useState("");
  const [redFlags, setRedFlags] = useState("");
  const [feedback, setFeedback] = useState("");

  /* ---- ui state ---- */
  const [activeTab, setActiveTab] = useState<"form" | "ai" | "history">("form");
  const [saving, setSaving] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [summarizing, setSummarizing] = useState(false);
  const [errors, setErrors] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [existingEvals, setExistingEvals] = useState<EvaluationResponse[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(false);

  /* ---- fetch existing evaluations when opened ---- */
  useEffect(() => {
    if (!open) return;
    setActiveTab("form");
    setErrors(null);
    setSuccess(null);
    setRound("R1");
    setOverallScore(7);
    setVerdict("consider");
    setScores({});
    setObservations("");
    setRedFlags("");
    setFeedback("");

    // Initialize dimension scores
    const init: Record<string, number> = {};
    for (const d of DEFAULT_DIMENSIONS) init[d] = 5;
    setScores(init);

    // Fetch existing evaluations
    (async () => {
      setLoadingHistory(true);
      try {
        const evals = await api.get<EvaluationResponse[]>(`/interviews/${interviewId}/evaluation`);
        setExistingEvals(Array.isArray(evals) ? evals : []);
      } catch {
        setExistingEvals([]);
      } finally {
        setLoadingHistory(false);
      }
    })();
  }, [open, interviewId]);

  /* ---- helpers ---- */
  const setScore = (dim: string, val: number) => {
    setScores((p) => ({ ...p, [dim]: Math.max(0, Math.min(10, val)) }));
  };

  const clearMessages = () => { setErrors(null); setSuccess(null); };

  /* ---- save evaluation ---- */
  const handleSave = async () => {
    clearMessages();
    setSaving(true);
    try {
      await api.post(`/interviews/${interviewId}/evaluation`, {
        round,
        overall_score: overallScore,
        verdict,
        dimensions: scores,
        key_observations: observations,
        red_flags: redFlags,
        feedback,
      });
      setSuccess("评估已保存");
      onSaved?.();
      // Refresh existing
      const evals = await api.get<EvaluationResponse[]>(`/interviews/${interviewId}/evaluation`);
      setExistingEvals(Array.isArray(evals) ? evals : []);
    } catch (e) {
      setErrors(e instanceof Error ? e.message : "保存失败");
    } finally {
      setSaving(false);
    }
  };

  /* ---- generate form via AI ---- */
  const handleGenerate = async () => {
    clearMessages();
    setGenerating(true);
    try {
      const result = await api.post<GenerateFormResult>(
        `/interviews/${interviewId}/evaluation/generate`,
        {
          candidate_name: candidateName,
          candidate_background: candidateBackground || "",
          round_id: round,
        }
      );
      if (result.evaluation_form) {
        const form = result.evaluation_form as Record<string, unknown>;
        if (typeof form.overall_score === "number") setOverallScore(form.overall_score);
        if (typeof form.verdict === "string") setVerdict(form.verdict);
        if (typeof form.observations === "string") setObservations(form.observations);
        if (typeof form.feedback === "string") setFeedback(form.feedback);
        if (typeof form.red_flags === "string") setRedFlags(form.red_flags);
        if (form.dimensions && typeof form.dimensions === "object") {
          const dims = form.dimensions as Record<string, number>;
          setScores((prev) => ({ ...prev, ...dims }));
        }
        setSuccess("AI 评估表单已生成，请审核后保存");
      }
    } catch (e) {
      setErrors(e instanceof Error ? e.message : "生成失败");
    } finally {
      setGenerating(false);
    }
  };

  /* ---- summarize feedback ---- */
  const handleSummarize = async () => {
    clearMessages();
    setSummarizing(true);
    try {
      const existingEvalList = existingEvals.map((ev) => ({
        round: ev.round,
        verdict: ev.verdict,
        score: ev.overall_score,
        feedback: ev.feedback,
      }));
      const result = await api.post<{ summary: string }>(
        `/interviews/${interviewId}/evaluation/summarize`,
        {
          candidate_name: candidateName,
          evaluations: existingEvalList,
        }
      );
      if (result.summary) {
        setFeedback((prev) => prev + (prev ? "\n\n" : "") + `【AI 汇总】${result.summary}`);
        setSuccess("反馈汇总已生成，已追加到反馈文本框");
      }
    } catch (e) {
      setErrors(e instanceof Error ? e.message : "汇总失败");
    } finally {
      setSummarizing(false);
    }
  };

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      onClick={onClose}
    >
      <div
        className="mx-4 flex max-h-[90vh] w-full max-w-3xl flex-col rounded-xl bg-white shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* ── Header ── */}
        <div className="flex items-center justify-between border-b px-6 py-4">
          <div>
            <h2 className="text-lg font-semibold">面试评估</h2>
            <p className="text-sm text-muted-foreground">{candidateName}</p>
          </div>
          <button onClick={onClose} className="rounded-full p-1 hover:bg-muted">
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* ── Messages ── */}
        {errors && (
          <div className="mx-6 mt-4 flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            <AlertCircle className="h-4 w-4 shrink-0" />
            <span className="flex-1">{errors}</span>
            <button onClick={() => setErrors(null)}><X className="h-4 w-4" /></button>
          </div>
        )}
        {success && (
          <div className="mx-6 mt-4 flex items-center gap-2 rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-700">
            <CheckCircle2 className="h-4 w-4 shrink-0" />
            <span className="flex-1">{success}</span>
            <button onClick={() => setSuccess(null)}><X className="h-4 w-4" /></button>
          </div>
        )}

        {/* ── Body ── */}
        <div className="flex-1 overflow-y-auto p-6">
          {/* Tab bar */}
          <div className="mb-6 flex gap-2 border-b pb-2">
            <button
              className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                activeTab === "form" ? "bg-primary text-primary-foreground" : "hover:bg-muted"
              }`}
              onClick={() => setActiveTab("form")}
            >
              评估表单
            </button>
            <button
              className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                activeTab === "ai" ? "bg-primary text-primary-foreground" : "hover:bg-muted"
              }`}
              onClick={() => setActiveTab("ai")}
            >
              AI 辅助
            </button>
            <button
              className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                activeTab === "history" ? "bg-primary text-primary-foreground" : "hover:bg-muted"
              }`}
              onClick={() => setActiveTab("history")}
            >
              评估记录
            </button>
          </div>

          {/* Tab: Form */}
          {activeTab === "form" && (
            <div className="space-y-5">
              {/* Round + Verdict row */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="mb-1 block text-sm font-medium">面试轮次</label>
                  <div className="flex gap-2">
                    {ROUND_OPTIONS.map((r) => (
                      <button
                        key={r}
                        className={`rounded-md border px-3 py-1.5 text-sm transition-colors ${
                          round === r
                            ? "border-primary bg-primary/10 text-primary font-medium"
                            : "hover:bg-muted"
                        }`}
                        onClick={() => setRound(r)}
                      >
                        {r}
                      </button>
                    ))}
                  </div>
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium">综合评分 (0-10)</label>
                  <div className="flex items-center gap-3">
                    <input
                      type="range"
                      min={0}
                      max={10}
                      step={0.5}
                      value={overallScore}
                      onChange={(e) => setOverallScore(Number(e.target.value))}
                      className="flex-1"
                    />
                    <span className="min-w-[3ch] text-right text-lg font-bold tabular-nums">
                      {overallScore.toFixed(1)}
                    </span>
                  </div>
                </div>
              </div>

              {/* Verdict */}
              <div>
                <label className="mb-1 block text-sm font-medium">面试结论</label>
                <div className="flex flex-wrap gap-2">
                  {VERDICT_OPTIONS.map((v) => (
                    <button
                      key={v.value}
                      className={`rounded-md border px-3 py-1.5 text-sm transition-colors ${
                        verdict === v.value
                          ? "border-primary ring-2 ring-primary/20 font-medium"
                          : "hover:bg-muted"
                      } ${v.color}`}
                      onClick={() => setVerdict(v.value)}
                    >
                      {v.label}
                    </button>
                  ))}
                </div>
              </div>

              <Separator />

              {/* Dimension scores */}
              <div>
                <label className="mb-2 block text-sm font-medium">维度评分</label>
                <div className="grid grid-cols-2 gap-x-6 gap-y-3">
                  {DEFAULT_DIMENSIONS.map((dim) => (
                    <div key={dim} className="flex items-center gap-2">
                      <span className="w-24 shrink-0 text-sm text-muted-foreground">{dim}</span>
                      <input
                        type="range"
                        min={0}
                        max={10}
                        step={0.5}
                        value={scores[dim] ?? 5}
                        onChange={(e) => setScore(dim, Number(e.target.value))}
                        className="flex-1"
                      />
                      <span className="w-6 text-right text-sm font-medium tabular-nums">
                        {scores[dim]?.toFixed(1) ?? "5.0"}
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              <Separator />

              {/* Text areas */}
              <div>
                <label className="mb-1 block text-sm font-medium">关键观察</label>
                <textarea
                  className="w-full rounded-lg border p-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
                  rows={3}
                  placeholder="面试中的亮点和关键表现..."
                  value={observations}
                  onChange={(e) => setObservations(e.target.value)}
                />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium">危险信号</label>
                <textarea
                  className="w-full rounded-lg border p-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
                  rows={2}
                  placeholder="面试中发现的潜在问题..."
                  value={redFlags}
                  onChange={(e) => setRedFlags(e.target.value)}
                />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium">综合反馈</label>
                <textarea
                  className="w-full rounded-lg border p-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
                  rows={3}
                  placeholder="整体评价和录用建议..."
                  value={feedback}
                  onChange={(e) => setFeedback(e.target.value)}
                />
              </div>

              {/* Save button */}
              <div className="flex justify-end gap-2 pt-2">
                <Button variant="outline" onClick={onClose}>取消</Button>
                <Button onClick={handleSave} disabled={saving}>
                  {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                  保存评估
                </Button>
              </div>
            </div>
          )}

          {/* Tab: AI */}
          {activeTab === "ai" && (
            <div className="space-y-4">
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="flex items-center gap-2 text-base">
                    <Sparkles className="h-4 w-4 text-amber-500" />
                    AI 评估表单生成
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <p className="text-sm text-muted-foreground">
                    基于候选人信息自动生成评估表单，包含维度评分、面试结论和反馈建议。
                  </p>
                  <Button
                    variant="outline"
                    className="w-full"
                    onClick={handleGenerate}
                    disabled={generating}
                  >
                    {generating ? (
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    ) : (
                      <Sparkles className="mr-2 h-4 w-4" />
                    )}
                    {generating ? "生成中..." : "生成评估表单"}
                  </Button>
                </CardContent>
              </Card>

              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="flex items-center gap-2 text-base">
                    <FileText className="h-4 w-4 text-blue-500" />
                    AI 反馈汇总
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <p className="text-sm text-muted-foreground">
                    汇总当前面试的所有轮次评估记录，生成统一的候选人评价摘要。
                  </p>
                  <Button
                    variant="outline"
                    className="w-full"
                    onClick={handleSummarize}
                    disabled={summarizing || existingEvals.length === 0}
                  >
                    {summarizing ? (
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    ) : (
                      <FileText className="mr-2 h-4 w-4" />
                    )}
                    {summarizing
                      ? "汇总中..."
                      : existingEvals.length === 0
                        ? "暂无评估记录可汇总"
                        : `汇总 ${existingEvals.length} 条评估记录`}
                  </Button>
                </CardContent>
              </Card>
            </div>
          )}

          {/* Tab: History */}
          {activeTab === "history" && (
            <div>
              {loadingHistory ? (
                <div className="flex items-center justify-center py-12">
                  <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                </div>
              ) : existingEvals.length === 0 ? (
                <div className="flex flex-col items-center justify-center gap-2 py-12 text-muted-foreground">
                  <FileText className="h-8 w-8" />
                  <p className="text-sm">暂无评估记录</p>
                  <p className="text-xs">完成面试后在此记录评估结果</p>
                </div>
              ) : (
                <div className="space-y-4">
                  {existingEvals.map((ev) => (
                    <Card key={ev.id}>
                      <CardHeader className="pb-2">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <Badge variant="outline">{ev.round}</Badge>
                            <span className="text-sm font-medium">
                              {VERDICT_OPTIONS.find((v) => v.value === ev.verdict)?.label ?? ev.verdict}
                            </span>
                          </div>
                          {ev.overall_score != null && (
                            <span className="text-lg font-bold tabular-nums">
                              {ev.overall_score.toFixed(1)}
                            </span>
                          )}
                        </div>
                      </CardHeader>
                      <CardContent className="space-y-2 text-sm">
                        {ev.dimensions && Object.keys(ev.dimensions).length > 0 && (
                          <div className="flex flex-wrap gap-2">
                            {Object.entries(ev.dimensions).map(([name, score]) => (
                              <div
                                key={name}
                                className="rounded-md bg-muted px-2 py-1 text-xs"
                              >
                                {name}: <span className="font-medium">{score.toFixed(1)}</span>
                              </div>
                            ))}
                          </div>
                        )}
                        {ev.key_observations && (
                          <p className="text-muted-foreground">
                            <span className="font-medium text-foreground">观察: </span>
                            {ev.key_observations}
                          </p>
                        )}
                        {ev.red_flags && (
                          <p className="text-red-600">
                            <span className="font-medium">风险: </span>
                            {ev.red_flags}
                          </p>
                        )}
                        {ev.feedback && (
                          <p className="text-muted-foreground">{ev.feedback}</p>
                        )}
                        <p className="text-xs text-muted-foreground">
                          {new Date(ev.created_at).toLocaleString("zh-CN")}
                        </p>
                      </CardContent>
                    </Card>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
