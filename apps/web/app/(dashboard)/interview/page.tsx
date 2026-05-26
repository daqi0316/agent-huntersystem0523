"use client";

import { useState, useEffect } from "react";
import {
  Calendar, Clock, Users, Plus, Loader2, X, AlertCircle,
  Check, Ban, FileText, History, ChevronDown, ChevronUp, ThumbsUp, ThumbsDown,
} from "lucide-react";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { DataTable } from "@/components/common/data-table";
import { api } from "@/lib/trpc";

function isSameDay(a: Date, b: Date) {
  return a.getFullYear() === b.getFullYear()
    && a.getMonth() === b.getMonth()
    && a.getDate() === b.getDate();
}

interface BackendInterview {
  id: string;
  candidate_id: string;
  application_id: string;
  type: string;
  status: string;
  scheduled_at: string;
  duration_minutes: number;
  location: string;
  notes: string;
  feedback: string;
  created_at: string;
  updated_at: string;
}

interface InterviewRow {
  id: string;
  candidate: string;
  job: string;
  time: string;
  rawDate?: string;
  interviewer: string;
  status: "pending" | "confirmed" | "completed" | "cancelled";
  notes?: string;
}

const STATUS_MAP: Record<string, { label: string; color: "warning" | "default" | "success" | "destructive" }> = {
  pending: { label: "待确认", color: "warning" },
  confirmed: { label: "已确认", color: "default" },
  completed: { label: "已完成", color: "success" },
  cancelled: { label: "已取消", color: "destructive" },
};

function mapStatus(backendStatus: string): InterviewRow["status"] {
  if (backendStatus === "scheduled" || backendStatus === "no_show") return "pending";
  return backendStatus as InterviewRow["status"];
}

function toDisplay(b: BackendInterview): InterviewRow {
  const d = b.scheduled_at ? new Date(b.scheduled_at) : null;
  return {
    id: b.id,
    candidate: b.candidate_id.slice(0, 8) || "—",
    job: b.type || "—",
    time: d ? d.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }) : "待安排",
    rawDate: d?.toISOString(),
    interviewer: b.location || "待分配",
    status: mapStatus(b.status),
    notes: b.notes,
  };
}

interface InterviewProposal {
  recommended_slot: string;
  alternatives?: string[];
  duration_minutes?: number;
  interview_type?: string;
  suggested_interviewers?: string[];
  invitation_draft?: string;
}

interface PendingProposal {
  approval_id: string;
  action_type: string;
  proposal: InterviewProposal;
  params: Record<string, string>;
  status: string;
  created_at: string;
  expires_at: string;
}

interface ApprovalHistoryItem {
  approval_id: string;
  action_type: string;
  proposal: InterviewProposal;
  status: string;
  created_at: string;
  confirmed_at?: string;
  feedback?: string;
}

export default function InterviewPage() {
  const [interviews, setInterviews] = useState<InterviewRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [form, setForm] = useState({ candidate: "", job: "", time: "", interviewer: "", notes: "" });
  const [pendingProposals, setPendingProposals] = useState<PendingProposal[]>([]);
  const [approvingId, setApprovingId] = useState<string | null>(null);

  // Reject feedback dialog
  const [rejectDialog, setRejectDialog] = useState<{ open: boolean; approval_id: string }>({ open: false, approval_id: "" });
  const [rejectFeedback, setRejectFeedback] = useState("");

  // Approval history
  const [showHistory, setShowHistory] = useState(false);
  const [historyItems, setHistoryItems] = useState<ApprovalHistoryItem[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);

  // Full proposal detail
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const fetchPending = async () => {
    try {
      const res = await api.get<{ success: boolean; items: PendingProposal[] }>("/human-loop/pending");
      setPendingProposals(res.items ?? []);
    } catch {
      // silent
    }
  };

  const fetchHistory = async () => {
    setHistoryLoading(true);
    try {
      const res = await api.get<{ success: boolean; items: ApprovalHistoryItem[] }>("/human-loop/history?limit=50");
      setHistoryItems(res.items ?? []);
    } catch {
      toast.error("加载审批历史失败");
    } finally {
      setHistoryLoading(false);
    }
  };

  const handleApprove = async (approval_id: string) => {
    setApprovingId(approval_id);
    try {
      // 1. Approve the HumanLoop proposal
      const approveResult = await api.post<{ success: boolean; status: string; approval: Record<string, unknown> }>("/human-loop/approve", {
        approval_id,
        approved: true,
        action_type: "schedule_interview",
        params: {},
      });

      if (!approveResult.success) {
        toast.error("审批操作失败");
        return;
      }

      const proposalItem = pendingProposals.find(p => p.approval_id === approval_id);
      const { proposal, params: proposalParams } = proposalItem || {};
      const candidateId = proposalParams?.candidate_id || "";
      const jobId = proposalParams?.job_id || "";

      if (proposal && candidateId && jobId) {
        try {
          const created = await api.post<BackendInterview>("/interviews/from-proposal", {
            candidate_id: candidateId,
            job_id: jobId,
            scheduled_at: proposal.recommended_slot || new Date().toISOString(),
            type: proposal.interview_type || "video",
            duration_minutes: proposal.duration_minutes || 60,
            notes: [proposal.interview_type || "面试", proposal.invitation_draft?.slice(0, 100)].filter(Boolean).join(" | "),
          });
          setInterviews(prev => [toDisplay(created), ...prev]);
        } catch {
          toast.error("面试创建失败");
        }
      } else {
        toast.error("提案缺少候选人或职位信息");
      }

      toast.success("提案已批准，面试已安排");
      setPendingProposals(prev => prev.filter(p => p.approval_id !== approval_id));
    } catch {
      toast.error("审批操作失败");
    } finally {
      setApprovingId(null);
    }
  };

  const openRejectDialog = (approval_id: string) => {
    setRejectDialog({ open: true, approval_id });
    setRejectFeedback("");
  };

  const handleRejectConfirm = async () => {
    const { approval_id } = rejectDialog;
    setApprovingId(approval_id);
    try {
      await api.post<{ success: boolean }>("/human-loop/approve", {
        approval_id,
        approved: false,
        action_type: "schedule_interview",
        params: {},
        feedback: rejectFeedback,
      });
      toast.success(rejectFeedback ? "提案已拒绝（附反馈）" : "提案已拒绝");
      setPendingProposals(prev => prev.filter(p => p.approval_id !== approval_id));
      setRejectDialog({ open: false, approval_id: "" });
    } catch {
      toast.error("审批操作失败");
    } finally {
      setApprovingId(null);
    }
  };

  useEffect(() => {
    (async () => {
      try {
        const res = await api.get<{ success: boolean; items: BackendInterview[]; total: number }>(
          "/interviews?skip=0&limit=100"
        );
        const items = res.items ?? [];
        setInterviews(items.map(toDisplay));
      } catch (e) {
        setError("数据加载失败");
      } finally {
        setLoading(false);
      }
    })();
    fetchPending();
  }, []);

  const handleCreate = async () => {
    setSubmitting(true);
    try {
      // Create a HumanLoop proposal instead of direct interview
      await api.post<{ success: boolean }>("/human-loop/schedule", {
        action_type: "schedule_interview",
        params: {
          candidate_id: form.candidate || "",
          job_id: form.job || "",
          candidate_name: form.candidate || "候选人",
          job_title: form.job || "未指定职位",
          available_slots: form.time ? [form.time] : ["工作日 9:00-18:00"],
        },
      });
      toast.success("面试安排提案已创建，等待审批");
      await fetchPending();
    } catch {
      toast.error("创建提案失败");
    }
    setSubmitting(false);
    setShowCreate(false);
    setForm({ candidate: "", job: "", time: "", interviewer: "", notes: "" });
  };

  const handleConfirm = async (id: string) => {
    try {
      await api.patch(`/interviews/${id}/confirm`);
      setInterviews(prev => prev.map(i => (i.id === id ? { ...i, status: "confirmed" as const } : i)));
    } catch { /* ignore */ }
  };

  const handleCancel = async (id: string) => {
    try {
      await api.patch(`/interviews/${id}/cancel`);
      setInterviews(prev => prev.map(i => (i.id === id ? { ...i, status: "cancelled" as const } : i)));
    } catch { /* ignore */ }
  };

  const handleFeedback = (candidate: string) => {
    alert(`查看 ${candidate} 的面试反馈`);
  };

  const columns = [
    { key: "candidate", label: "候选人", sortable: true },
    { key: "job", label: "职位", sortable: true },
    { key: "time", label: "面试时间", sortable: true },
    { key: "interviewer", label: "面试官", sortable: true },
    {
      key: "status",
      label: "状态",
      sortable: true,
      render: (item: Record<string, unknown>) => {
        const i = item as unknown as InterviewRow;
        const sc = STATUS_MAP[i.status] || { label: i.status, color: "outline" as const };
        return <Badge variant={sc.color}>{sc.label}</Badge>;
      },
    },
    {
      key: "actions",
      label: "操作",
      render: (item: Record<string, unknown>) => {
        const i = item as unknown as InterviewRow;
        return (
          <div className="flex gap-1">
            {i.status === "confirmed" && (
              <Button variant="outline" size="sm" onClick={() => handleCancel(i.id)}>
                取消
              </Button>
            )}
            {i.status === "completed" && (
              <Button variant="outline" size="sm" onClick={() => handleFeedback(i.candidate)}>
                反馈
              </Button>
            )}
            {i.status === "pending" && (
              <Button size="sm" onClick={() => handleConfirm(i.id)}>
                确认
              </Button>
            )}
          </div>
        );
      },
    },
  ];

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
        <div className="flex items-center gap-3">
          <div>
            <h1 className="text-3xl font-bold">面试管理</h1>
            <p className="text-muted-foreground">管理面试安排与进度追踪（Human-in-Loop 审批流程）</p>
          </div>
          {error && (
            <Badge variant="warning" className="gap-1">
              <AlertCircle className="h-3 w-3" />
              {error}
            </Badge>
          )}
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            className="gap-1"
            onClick={() => {
              setShowHistory(v => !v);
              if (!showHistory) fetchHistory();
            }}
          >
            <History className="h-4 w-4" />
            审批历史
          </Button>
          <Button variant="outline" size="sm" className="gap-1">
            <Calendar className="h-4 w-4" />
            日历视图
          </Button>
          <Button onClick={() => setShowCreate(true)} className="gap-1">
            <Plus className="h-4 w-4" />
            安排面试
          </Button>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-4">
        {[
          { label: "总面试", value: interviews.length, icon: Users, color: "text-blue-600" },
          { label: "待确认", value: interviews.filter(i => i.status === "pending").length, icon: Clock, color: "text-amber-600" },
          { label: "今日面试", value: interviews.filter(i => i.rawDate && isSameDay(new Date(i.rawDate), new Date())).length, icon: Calendar, color: "text-violet-600" },
          { label: "已完成", value: interviews.filter(i => i.status === "completed").length, icon: Calendar, color: "text-green-600" },
        ].map(s => {
          const Icon = s.icon;
          return (
            <Card key={s.label}>
              <CardHeader className="flex flex-row items-center justify-between pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground">{s.label}</CardTitle>
                <Icon className={`h-4 w-4 ${s.color}`} />
              </CardHeader>
              <CardContent>
                <p className="text-3xl font-bold">{s.value}</p>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Pending Proposals Section — enhanced */}
      {pendingProposals.length > 0 && (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-base flex items-center gap-2">
              <FileText className="h-4 w-4" />
              AI 面试安排提案
              <Badge variant="warning" className="ml-1">{pendingProposals.length}</Badge>
            </CardTitle>
            <span className="text-xs text-muted-foreground">由 AI 生成，需人工审批后执行</span>
          </CardHeader>
          <CardContent className="space-y-4">
            {pendingProposals.map(p => {
              const prop = p.proposal;
              const isExpanded = expandedId === p.approval_id;
              return (
                <div
                  key={p.approval_id}
                  className="rounded-lg border"
                >
                  {/* Header row */}
                  <div className="flex items-start justify-between p-4">
                    <div className="flex-1 space-y-1">
                      <div className="flex items-center gap-2">
                        <span className="font-medium">
                          {p.action_type === "schedule_interview" ? "面试安排" : p.action_type}
                        </span>
                        <span className="text-xs text-muted-foreground">
                          {new Date(p.created_at).toLocaleString("zh-CN")}
                        </span>
                        <Badge variant="outline" className="text-xs">
                          有效期至 {new Date(p.expires_at).toLocaleDateString("zh-CN")}
                        </Badge>
                      </div>
                      {/* Summary row */}
                      <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted-foreground">
                        <span>📅 {prop.recommended_slot || "待定"}</span>
                        {prop.duration_minutes && <span>⏱ {prop.duration_minutes}分钟</span>}
                        {prop.interview_type && <span>🏷 {prop.interview_type}</span>}
                        {prop.suggested_interviewers?.length ? (
                          <span>👤 {prop.suggested_interviewers.join(", ")}</span>
                        ) : null}
                      </div>
                    </div>
                    <div className="flex gap-2 ml-4">
                      <Button
                        size="sm"
                        variant="outline"
                        className="text-destructive border-destructive/30 hover:bg-destructive/10"
                        onClick={() => openRejectDialog(p.approval_id)}
                        disabled={approvingId === p.approval_id}
                      >
                        <Ban className="h-3 w-3 mr-1" />
                        拒绝
                      </Button>
                      <Button
                        size="sm"
                        onClick={() => handleApprove(p.approval_id)}
                        disabled={approvingId === p.approval_id}
                      >
                        {approvingId === p.approval_id ? (
                          <Loader2 className="h-3 w-3 animate-spin mr-1" />
                        ) : (
                          <Check className="h-3 w-3 mr-1" />
                        )}
                        批准
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => setExpandedId(isExpanded ? null : p.approval_id)}
                      >
                        {isExpanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                      </Button>
                    </div>
                  </div>

                  {/* Expanded details */}
                  {isExpanded && (
                    <div className="border-t px-4 py-3 space-y-3">
                      <div className="grid grid-cols-2 gap-4 text-sm">
                        <div>
                          <span className="font-medium text-muted-foreground">推荐时间</span>
                          <p>{prop.recommended_slot || "—"}</p>
                        </div>
                        <div>
                          <span className="font-medium text-muted-foreground">面试时长</span>
                          <p>{prop.duration_minutes ? `${prop.duration_minutes} 分钟` : "—"}</p>
                        </div>
                        <div>
                          <span className="font-medium text-muted-foreground">面试类型</span>
                          <p>{prop.interview_type || "—"}</p>
                        </div>
                        <div>
                          <span className="font-medium text-muted-foreground">建议面试官</span>
                          <p>{prop.suggested_interviewers?.join(", ") || "—"}</p>
                        </div>
                      </div>

                      {prop.alternatives && prop.alternatives.length > 0 && (
                        <div className="text-sm">
                          <span className="font-medium text-muted-foreground">备选时间</span>
                          <ul className="list-inside list-disc text-muted-foreground mt-1">
                            {prop.alternatives.map((alt, i) => <li key={i}>{alt}</li>)}
                          </ul>
                        </div>
                      )}

                      {prop.invitation_draft && (
                        <div className="text-sm">
                          <span className="font-medium text-muted-foreground">邀请函草稿</span>
                          <div className="mt-1 rounded-md bg-muted/50 p-3 whitespace-pre-wrap text-xs text-muted-foreground">
                            {prop.invitation_draft}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </CardContent>
        </Card>
      )}

      <DataTable columns={columns} data={interviews as unknown as Record<string, unknown>[]} />

      {/* Approval History */}
      {showHistory && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <History className="h-4 w-4" />
              审批历史
            </CardTitle>
          </CardHeader>
          <CardContent>
            {historyLoading ? (
              <div className="flex justify-center py-8">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
              </div>
            ) : historyItems.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-4">暂无审批记录</p>
            ) : (
              <div className="space-y-2">
                {historyItems.map(item => (
                  <div key={item.approval_id} className="flex items-center justify-between rounded-lg border p-3 text-sm">
                    <div className="flex items-center gap-3">
                      {item.status === "approved" ? (
                        <ThumbsUp className="h-4 w-4 text-green-600" />
                      ) : (
                        <ThumbsDown className="h-4 w-4 text-red-600" />
                      )}
                      <div>
                        <span className="font-medium">
                          {item.action_type === "schedule_interview" ? "面试安排" : item.action_type}
                        </span>
                        <span className="ml-2 text-muted-foreground">
                          {item.proposal?.recommended_slot || "—"}
                        </span>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge variant={item.status === "approved" ? "default" : "destructive"}>
                        {item.status === "approved" ? "已批准" : item.status === "rejected" ? "已拒绝" : item.status}
                      </Badge>
                      <span className="text-xs text-muted-foreground">
                        {item.confirmed_at ? new Date(item.confirmed_at).toLocaleString("zh-CN") : ""}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Create Proposal Modal */}
      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={() => setShowCreate(false)}>
          <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-lg font-bold">安排面试（AI 提案）</h2>
              <button onClick={() => setShowCreate(false)}><X className="h-4 w-4" /></button>
            </div>
            <p className="mb-4 text-xs text-muted-foreground">
              AI 将根据您提供的信息生成面试安排建议，提交后需人工审批。
            </p>
            <div className="space-y-3">
              <Input placeholder="候选人姓名" value={form.candidate} onChange={e => setForm({ ...form, candidate: e.target.value })} />
              <Input placeholder="职位名称" value={form.job} onChange={e => setForm({ ...form, job: e.target.value })} />
              <Input type="datetime-local" value={form.time} onChange={e => setForm({ ...form, time: e.target.value })} />
              <Input placeholder="面试官" value={form.interviewer} onChange={e => setForm({ ...form, interviewer: e.target.value })} />
              <Input placeholder="备注（可选）" value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })} />
            </div>
            <div className="mt-4 flex justify-end gap-2">
              <Button variant="outline" onClick={() => setShowCreate(false)}>取消</Button>
              <Button onClick={handleCreate} disabled={submitting}>
                {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                提交提案
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Reject Feedback Dialog */}
      {rejectDialog.open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={() => setRejectDialog({ open: false, approval_id: "" })}>
          <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl" onClick={e => e.stopPropagation()}>
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-lg font-bold">拒绝提案</h2>
              <button onClick={() => setRejectDialog({ open: false, approval_id: "" })}><X className="h-4 w-4" /></button>
            </div>
            <p className="mb-3 text-sm text-muted-foreground">
              请在下方输入拒绝原因（可选），这将帮助 AI 改进后续建议。
            </p>
            <textarea
              className="w-full rounded-lg border bg-transparent p-3 text-sm outline-none focus:ring-2 focus:ring-red-500"
              rows={4}
              value={rejectFeedback}
              onChange={e => setRejectFeedback(e.target.value)}
              placeholder="输入拒绝原因（可选）..."
            />
            <div className="mt-4 flex justify-end gap-2">
              <Button variant="outline" onClick={() => setRejectDialog({ open: false, approval_id: "" })}>
                取消
              </Button>
              <Button
                variant="destructive"
                onClick={handleRejectConfirm}
                disabled={approvingId === rejectDialog.approval_id}
              >
                {approvingId === rejectDialog.approval_id ? (
                  <Loader2 className="h-4 w-4 animate-spin mr-1" />
                ) : null}
                确认拒绝
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
