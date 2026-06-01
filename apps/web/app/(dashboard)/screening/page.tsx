"use client";

import { useState, useRef, useEffect } from "react";
import {
  Sparkles, Loader2, CheckCircle2, AlertCircle, ThumbsUp, ThumbsDown,
  Send, Calendar, BarChart3, MessageSquare, Bot, User,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { StepIndicator } from "@/components/features/screening/step-indicator";
import { api } from "@/lib/trpc";

interface ScreeningPipelineResult {
  success: boolean;
  pipeline_id: string;
  candidate_id: string;
  job_id: string;
  overall_score: number;
  dimensions: Record<string, unknown>;
  parsed_resume: Record<string, unknown>;
  gate_passed: boolean;
  needs_human_review: boolean;
  strengths: string[];
  weaknesses: string[];
  recommendation: string;
  summary: string;
  steps: Record<string, unknown>[];
  report: Record<string, unknown> | null;
  candidate_status: string;
}

interface MultiEvaluateResult {
  success: boolean;
  dimension_results: { dimension: string; score: number; analysis: string }[];
  consensus: Record<string, unknown>;
  total_dimensions: number;
}

interface HumanLoopResult {
  success: boolean;
  status: string;
  approval: { id?: string; action_type?: string; params?: Record<string, unknown> };
}

export default function ScreeningPage() {
  // --- Pipeline tab ---
  const [candidateId, setCandidateId] = useState("");
  const [jobId, setJobId] = useState("");
  const [applicationId, setApplicationId] = useState("");
  const [resumeText, setResumeText] = useState("");
  const [jobReqs, setJobReqs] = useState("");
  const [pipelineLoading, setPipelineLoading] = useState(false);
  const [pipelineResult, setPipelineResult] = useState<ScreeningPipelineResult | null>(null);
  const [pipelineError, setPipelineError] = useState<string | null>(null);
  const [pipelineTaskId, setPipelineTaskId] = useState<string | null>(null);

  // --- Multi-Evaluate tab ---
  const [candidateInfo, setCandidateInfo] = useState("");
  const [evalDimensions, setEvalDimensions] = useState("technical, behavioral, experience");
  const [evalLoading, setEvalLoading] = useState(false);
  const [evalResult, setEvalResult] = useState<MultiEvaluateResult | null>(null);
  const [evalError, setEvalError] = useState<string | null>(null);

  // --- Multi-turn Screening Chat ---
  const [chatSessionId, setChatSessionId] = useState<string | null>(null);
  const [chatMessages, setChatMessages] = useState<{ role: string; content: string }[]>([]);
  const [chatInput, setChatInput] = useState("");
  const [chatLoading, setChatLoading] = useState(false);
  const [chatCandidateId, setChatCandidateId] = useState("");
  const [chatJobId, setChatJobId] = useState("");
  const chatEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chatMessages]);

  const handleStartChat = async () => {
    if (!chatCandidateId || !chatJobId) return;
    try {
      const session = await api.post<{ id: string }>("/conversation/session", {
        title: `初筛: ${chatCandidateId}`,
      });
      setChatSessionId(session.id);
      setChatMessages([]);
    } catch {
      alert("创建对话失败");
    }
  };

  const handleSendChat = async () => {
    if (!chatInput.trim() || !chatSessionId || !chatCandidateId || !chatJobId) return;
    const userMsg = chatInput.trim();
    setChatInput("");
    setChatMessages((prev) => [...prev, { role: "user", content: userMsg }]);
    setChatLoading(true);
    try {
      const res = await api.post<{ reply: string }>(
        `/conversation/session/${chatSessionId}/screen`,
        {
          session_id: chatSessionId,
          message: userMsg,
          candidate_id: chatCandidateId,
          job_id: chatJobId,
        },
      );
      setChatMessages((prev) => [...prev, { role: "assistant", content: res.reply }]);
    } catch {
      setChatMessages((prev) => [...prev, { role: "assistant", content: "抱歉，评估请求失败，请稍后重试。" }]);
    } finally {
      setChatLoading(false);
    }
  };

  // --- Human-in-Loop ---
  const [hlLoading, setHlLoading] = useState(false);
  const [hlResult, setHlResult] = useState<HumanLoopResult | null>(null);
  const [approvalId, setApprovalId] = useState<string | null>(null);
  const [hlError, setHlError] = useState<string | null>(null);

  const handlePipelineSubmit = async () => {
    if (!candidateId || !jobId || !resumeText || !jobReqs) return;
    // Generate a local taskId for SSE progress visualization before the POST completes
    const taskId = crypto.randomUUID();
    setPipelineTaskId(taskId);
    setPipelineLoading(true);
    setPipelineResult(null);
    setPipelineError(null);
    try {
      const result = await api.post<ScreeningPipelineResult>("/pipeline/screen-resume", {
        candidate_id: candidateId,
        job_id: jobId,
        resume_text: resumeText,
        job_requirements: jobReqs,
        pipeline_task_id: taskId,
        application_id: applicationId || undefined,
      });
      setPipelineResult(result);
    } catch (err) {
      setPipelineError(err instanceof Error ? err.message : "初筛请求失败");
    } finally {
      setPipelineLoading(false);
    }
  };

  const handleEvaluateSubmit = async () => {
    if (!candidateInfo) return;
    setEvalLoading(true);
    setEvalResult(null);
    setEvalError(null);
    try {
      const dims = evalDimensions.split(",").map((d) => d.trim()).filter(Boolean);
      const result = await api.post<MultiEvaluateResult>("/parallel/multi-evaluate", {
        candidate_info: candidateInfo,
        dimensions: dims,
      });
      setEvalResult(result);
    } catch (err) {
      setEvalError(err instanceof Error ? err.message : "评估请求失败");
    } finally {
      setEvalLoading(false);
    }
  };

  const handleScheduleInterview = async () => {
    setHlLoading(true);
    setHlError(null);
    try {
      const result = await api.post<HumanLoopResult>("/human-loop/schedule", {
        action_type: "schedule_interview",
        params: {
          candidate_id: candidateId || pipelineResult?.candidate_id,
          job_id: jobId || pipelineResult?.job_id,
        },
      });
      setHlResult(result);
      setApprovalId(result.approval?.id ?? null);
    } catch (err) {
      setHlError(err instanceof Error ? err.message : "安排面试失败");
    } finally {
      setHlLoading(false);
    }
  };

  const handleApprove = async (approved: boolean) => {
    if (!approvalId) return;
    setHlLoading(true);
    try {
      const result = await api.post<HumanLoopResult>("/human-loop/approve", {
        approval_id: approvalId,
        approved,
        action_type: "schedule_interview",
        params: {},
      });
      setHlResult(result);
    } catch (err) {
      setHlError(err instanceof Error ? err.message : "操作失败");
    } finally {
      setHlLoading(false);
    }
  };

  const scoreColor = (score: number) => {
    if (score >= 80) return "text-green-600";
    if (score >= 60) return "text-yellow-600";
    return "text-red-600";
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">AI初筛</h1>
          <p className="text-muted-foreground">
            AI驱动的简历智能筛选流水线（图2 Pipeline + 图4 Aggregator）
          </p>
        </div>
      </div>

      <Tabs defaultValue="pipeline">
        <TabsList>
          <TabsTrigger value="pipeline">初筛流水线</TabsTrigger>
          <TabsTrigger value="evaluate">聚合评估</TabsTrigger>
          <TabsTrigger value="chat">多轮对话式初筛</TabsTrigger>
        </TabsList>

        {/* --- Pipeline Tab --- */}
        <TabsContent value="pipeline" className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Sparkles className="h-5 w-5 text-blue-500" />
                简历初筛
              </CardTitle>
              <CardDescription>输入候选人信息和职位要求，启动AI初筛流水线</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="mb-1 block text-sm font-medium">候选人 ID</label>
                  <Input value={candidateId} onChange={(e) => setCandidateId(e.target.value)} placeholder="cand_001" />
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium">职位 ID</label>
                  <Input value={jobId} onChange={(e) => setJobId(e.target.value)} placeholder="job_001" />
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium">
                    申请 ID <span className="text-xs text-muted-foreground">(可选)</span>
                  </label>
                  <Input value={applicationId} onChange={(e) => setApplicationId(e.target.value)} placeholder="app_001" />
                </div>
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium">简历文本</label>
                <textarea
                  className="w-full rounded-lg border bg-transparent p-3 text-sm outline-none focus:ring-2 focus:ring-blue-500"
                  rows={6}
                  value={resumeText}
                  onChange={(e) => setResumeText(e.target.value)}
                  placeholder="粘贴简历文本..."
                />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium">职位要求</label>
                <textarea
                  className="w-full rounded-lg border bg-transparent p-3 text-sm outline-none focus:ring-2 focus:ring-blue-500"
                  rows={6}
                  value={jobReqs}
                  onChange={(e) => setJobReqs(e.target.value)}
                  placeholder="粘贴职位描述和任职要求..."
                />
              </div>
              <Button onClick={handlePipelineSubmit} disabled={pipelineLoading}>
                {pipelineLoading ? (
                  <><Loader2 className="mr-2 h-4 w-4 animate-spin" /> 筛选中...</>
                ) : (
                  <><Sparkles className="mr-2 h-4 w-4" /> 开始初筛</>
                )}
              </Button>

              {pipelineError && (
                <div className="flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
                  <AlertCircle className="h-4 w-4" /> {pipelineError}
                </div>
              )}

              {pipelineTaskId && (
                <div className="mb-4">
                  <StepIndicator taskId={pipelineTaskId} />
                </div>
              )}

              {pipelineResult && (
                <div className="space-y-4">
                  <Separator />
                  <h3 className="font-semibold">筛选结果</h3>

                  <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
                    <Card>
                      <CardContent className="p-4 text-center">
                        <p className="text-xs text-muted-foreground">综合评分</p>
                        <p className={`text-3xl font-bold ${scoreColor(pipelineResult.overall_score)}`}>
                          {pipelineResult.overall_score}
                        </p>
                      </CardContent>
                    </Card>
                    <Card>
                      <CardContent className="p-4 text-center">
                        <p className="text-xs text-muted-foreground">初筛结果</p>
                        {pipelineResult.gate_passed ? (
                          <Badge className="mt-1 bg-green-500">已通过</Badge>
                        ) : (
                          <Badge className="mt-1 bg-red-500">未通过</Badge>
                        )}
                      </CardContent>
                    </Card>
                    <Card>
                      <CardContent className="p-4 text-center">
                        <p className="text-xs text-muted-foreground">候选人状态</p>
                        <Badge className="mt-1" variant="outline">
                          {pipelineResult.candidate_status}
                        </Badge>
                      </CardContent>
                    </Card>
                    <Card>
                      <CardContent className="p-4 text-center">
                        <p className="text-xs text-muted-foreground">人工复核</p>
                        {pipelineResult.needs_human_review ? (
                          <Badge className="mt-1 bg-yellow-500">需要</Badge>
                        ) : (
                          <Badge className="mt-1 bg-gray-500">不需要</Badge>
                        )}
                      </CardContent>
                    </Card>
                    <Card>
                      <CardContent className="p-4 text-center">
                        <p className="text-xs text-muted-foreground">流水线</p>
                        <p className="mt-1 text-sm font-mono">{pipelineResult.pipeline_id.slice(0, 12)}...</p>
                      </CardContent>
                    </Card>
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <Card>
                      <CardHeader className="pb-2">
                        <CardTitle className="text-sm">优势</CardTitle>
                      </CardHeader>
                      <CardContent>
                        {pipelineResult.strengths.length > 0 ? (
                          <ul className="list-inside list-disc space-y-1 text-sm">
                            {pipelineResult.strengths.map((s, i) => (
                              <li key={i}>{s}</li>
                            ))}
                          </ul>
                        ) : (
                          <p className="text-sm text-muted-foreground">暂无</p>
                        )}
                      </CardContent>
                    </Card>
                    <Card>
                      <CardHeader className="pb-2">
                        <CardTitle className="text-sm">不足</CardTitle>
                      </CardHeader>
                      <CardContent>
                        {pipelineResult.weaknesses.length > 0 ? (
                          <ul className="list-inside list-disc space-y-1 text-sm">
                            {pipelineResult.weaknesses.map((w, i) => (
                              <li key={i}>{w}</li>
                            ))}
                          </ul>
                        ) : (
                          <p className="text-sm text-muted-foreground">暂无</p>
                        )}
                      </CardContent>
                    </Card>
                  </div>

                  <div className="rounded-lg border p-4">
                    <p className="text-sm font-medium">推荐建议</p>
                    <p className="mt-1 text-sm text-muted-foreground">{pipelineResult.recommendation || "暂无"}</p>
                  </div>

                  <div className="rounded-lg border p-4">
                    <p className="text-sm font-medium">摘要</p>
                    <p className="mt-1 text-sm text-muted-foreground">{pipelineResult.summary || "暂无"}</p>
                  </div>

                  {pipelineResult.report && (
                    <div className="rounded-lg border p-4">
                      <p className="text-sm font-medium">评估报告</p>
                      <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap text-xs text-muted-foreground">
                        {JSON.stringify(pipelineResult.report, null, 2)}
                      </pre>
                    </div>
                  )}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="chat" className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <MessageSquare className="h-5 w-5 text-emerald-500" />
                多轮对话式初筛
              </CardTitle>
              <CardDescription>通过自然语言多轮对话深入了解候选人，AI会根据对话历史和候选人信息持续评估</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {!chatSessionId ? (
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="mb-1 block text-sm font-medium">候选人 ID</label>
                    <Input value={chatCandidateId} onChange={(e) => setChatCandidateId(e.target.value)} placeholder="cand_001" />
                  </div>
                  <div>
                    <label className="mb-1 block text-sm font-medium">职位 ID</label>
                    <Input value={chatJobId} onChange={(e) => setChatJobId(e.target.value)} placeholder="job_001" />
                  </div>
                  <div className="col-span-2">
                    <Button onClick={handleStartChat} className="w-full bg-emerald-600 hover:bg-emerald-700">
                      <MessageSquare className="mr-2 h-4 w-4" /> 开始对话式初筛
                    </Button>
                  </div>
                </div>
              ) : (
                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <p className="text-xs text-muted-foreground">对话 ID: {chatSessionId.slice(0, 12)}...</p>
                    <Button variant="ghost" size="sm" onClick={() => { setChatSessionId(null); setChatMessages([]); }}>
                      结束对话
                    </Button>
                  </div>
                  <div className="flex h-[400px] flex-col overflow-y-auto rounded-lg border p-4">
                    {chatMessages.length === 0 && (
                      <div className="flex flex-1 items-center justify-center text-sm text-muted-foreground">
                        输入消息开始评估候选人
                      </div>
                    )}
                    {chatMessages.map((msg, i) => (
                      <div key={i} className={`mb-3 flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
                        <div className={`flex max-w-[80%] gap-2 ${msg.role === "user" ? "flex-row-reverse" : ""}`}>
                          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-muted">
                            {msg.role === "user" ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4 text-emerald-500" />}
                          </div>
                          <div className={`rounded-lg px-3 py-2 text-sm ${
                            msg.role === "user"
                              ? "bg-emerald-500 text-white"
                              : "bg-muted"
                          }`}>
                            {msg.content}
                          </div>
                        </div>
                      </div>
                    ))}
                    {chatLoading && (
                      <div className="mb-3 flex justify-start">
                        <div className="flex max-w-[80%] gap-2">
                          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-muted">
                            <Bot className="h-4 w-4 text-emerald-500" />
                          </div>
                          <div className="rounded-lg bg-muted px-3 py-2 text-sm text-muted-foreground">
                            <Loader2 className="mr-2 inline h-3 w-3 animate-spin" /> 思考中...
                          </div>
                        </div>
                      </div>
                    )}
                    <div ref={chatEndRef} />
                  </div>
                  <div className="flex gap-2">
                    <Input
                      value={chatInput}
                      onChange={(e) => setChatInput(e.target.value)}
                      onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && (e.preventDefault(), handleSendChat())}
                      placeholder="询问关于候选人的问题..."
                      disabled={chatLoading}
                    />
                    <Button onClick={handleSendChat} disabled={chatLoading || !chatInput.trim()} className="bg-emerald-600 hover:bg-emerald-700">
                      {chatLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                    </Button>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* --- Evaluate Tab --- */}
        <TabsContent value="evaluate" className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <BarChart3 className="h-5 w-5 text-purple-500" />
                多维度并行评估
              </CardTitle>
              <CardDescription>AI同时从多个维度评估候选人，自动汇聚共识评分</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <label className="mb-1 block text-sm font-medium">候选人信息</label>
                <textarea
                  className="w-full rounded-lg border bg-transparent p-3 text-sm outline-none focus:ring-2 focus:ring-purple-500"
                  rows={8}
                  value={candidateInfo}
                  onChange={(e) => setCandidateInfo(e.target.value)}
                  placeholder="粘贴候选人完整信息（姓名、经历、技能、项目经验等）..."
                />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium">评估维度（逗号分隔）</label>
                <Input
                  value={evalDimensions}
                  onChange={(e) => setEvalDimensions(e.target.value)}
                />
              </div>
              <Button onClick={handleEvaluateSubmit} disabled={evalLoading} className="bg-purple-600 hover:bg-purple-700">
                {evalLoading ? (
                  <><Loader2 className="mr-2 h-4 w-4 animate-spin" /> 评估中...</>
                ) : (
                  <><BarChart3 className="mr-2 h-4 w-4" /> 开始评估</>
                )}
              </Button>

              {evalError && (
                <div className="flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
                  <AlertCircle className="h-4 w-4" /> {evalError}
                </div>
              )}

              {evalResult && (
                <div className="space-y-4">
                  <Separator />
                  <h3 className="font-semibold">评估结果（{evalResult.total_dimensions} 个维度）</h3>
                  {evalResult.dimension_results.map((dim, i) => (
                    <Card key={i}>
                      <CardHeader className="pb-2">
                        <div className="flex items-center justify-between">
                          <CardTitle className="text-sm capitalize">{dim.dimension}</CardTitle>
                          <span className={`text-lg font-bold ${scoreColor(dim.score)}`}>
                            {dim.score}
                          </span>
                        </div>
                      </CardHeader>
                      <CardContent>
                        <p className="text-sm text-muted-foreground">{dim.analysis}</p>
                      </CardContent>
                    </Card>
                  ))}
                  {evalResult.consensus && Object.keys(evalResult.consensus).length > 0 && (
                    <Card className="border-purple-200 bg-purple-50">
                      <CardHeader className="pb-2">
                        <CardTitle className="text-sm">共识总结</CardTitle>
                      </CardHeader>
                      <CardContent>
                        <p className="text-sm">{JSON.stringify(evalResult.consensus, null, 2)}</p>
                      </CardContent>
                    </Card>
                  )}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* --- Human-in-Loop Section --- */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Calendar className="h-5 w-5 text-orange-500" />
            面试安排（Human-in-Loop）
          </CardTitle>
          <CardDescription>AI生成面试建议，人工确认后执行</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {!approvalId ? (
            <Button onClick={handleScheduleInterview} disabled={hlLoading} variant="outline">
              {hlLoading ? (
                <><Loader2 className="mr-2 h-4 w-4 animate-spin" /> 生成建议...</>
              ) : (
                <><Send className="mr-2 h-4 w-4" /> 安排面试</>
              )}
            </Button>
          ) : (
            <div className="space-y-3">
              <p className="text-sm text-muted-foreground">面试建议已生成，等待审批</p>
              <div className="flex gap-2">
                <Button onClick={() => handleApprove(true)} className="bg-green-600 hover:bg-green-700">
                  <ThumbsUp className="mr-2 h-4 w-4" /> 批准
                </Button>
                <Button onClick={() => handleApprove(false)} variant="destructive">
                  <ThumbsDown className="mr-2 h-4 w-4" /> 拒绝
                </Button>
              </div>
            </div>
          )}

          {hlError && (
            <div className="flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
              <AlertCircle className="h-4 w-4" /> {hlError}
            </div>
          )}

          {hlResult && hlResult.status === "confirmed" && (
            <div className="flex items-center gap-2 rounded-lg border border-green-200 bg-green-50 p-3 text-sm text-green-700">
              <CheckCircle2 className="h-4 w-4" /> 操作已确认
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
