"use client";

import { useState, useEffect, useMemo } from "react";
import {
  Calendar, Clock, Users, Plus, Loader2, X,
  Check, Ban, FileText, History, ChevronDown, ChevronUp, ThumbsUp, ThumbsDown,
} from "lucide-react";
import { toast } from "sonner";
import { ErrorAlert } from "@/components/common/error-alert";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { DataTable } from "@/components/common/data-table";
import EvaluationDialog from "@/components/features/interview/evaluation-dialog";
import { CalendarView } from "@/components/features/interview/calendar-view";
import { InterviewRecorder } from "@/components/features/interview/interview-recorder";
import { api } from "@/lib/trpc";
import { useHumanLoopEvents } from "@/hooks/use-human-loop-events";

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
  proposal: Record<string, unknown>;
  params: Record<string, unknown>;
  status: string;
  created_at: string;
  expires_at: string;
  candidate_name?: string;
  job_title?: string;
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
  const [rawInterviews, setRawInterviews] = useState<BackendInterview[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [form, setForm] = useState({ candidate: "", job: "", time: "", interviewer: "", notes: "" });
  const [pendingProposals, setPendingProposals] = useState<PendingProposal[]>([]);
  const [approvingId, setApprovingId] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<"all" | "pending" | "today" | "completed">("all");
  const [viewMode, setViewMode] = useState<"list" | "calendar">(() => {
    if (typeof window === "undefined") return "list";
    return (localStorage.getItem("interview_view_mode") as "list" | "calendar") || "list";
  });
  const [selectedDate, setSelectedDate] = useState<Date | null>(null);

  // 缓存 today：避免按钮 count 和 filter 跨午夜不一致
  const today = useMemo(() => new Date(), []);
  const filteredInterviews = useMemo(() => {
    switch (statusFilter) {
      case "pending":   return interviews.filter(i => i.status === "pending");
      case "today":     return interviews.filter(i => i.rawDate && isSameDay(new Date(i.rawDate), today));
      case "completed": return interviews.filter(i => i.status === "completed");
      default:          return interviews;
    }
  }, [interviews, statusFilter, today]);

  // Evaluation dialog
  const [evalDialog, setEvalDialog] = useState<{ open: boolean; interviewId: string; candidateName: string }>({
    open: false, interviewId: "", candidateName: "",
  });

  // Reject feedback dialog
  const [rejectDialog, setRejectDialog] = useState<{ open: boolean; approval_id: string }>({ open: false, approval_id: "" });
  const [rejectFeedback, setRejectFeedback] = useState("");

  // Approval history
  const [showHistory, setShowHistory] = useState(false);
  const [historyItems, setHistoryItems] = useState<ApprovalHistoryItem[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);

  // Full proposal detail
  const [expandedId, setExpandedId] = useState<string | null>(null);

  useHumanLoopEvents(true, {
    onPendingUpdated: (proposals) => setPendingProposals(proposals),
    onError: (msg) => toast.error(msg),
  });

  const fetchPending = async () => {
    try {
      const res = await api.get<{ success: boolean; data: PendingProposal[] }>("/human-loop/pending");
      setPendingProposals(res.data ?? []);
    } catch {
      // silent
    }
  };

  const fetchHistory = async () => {
    setHistoryLoading(true);
    try {
      const res = await api.get<{ success: boolean; data: ApprovalHistoryItem[] }>("/human-loop/history?limit=50");
      setHistoryItems(res.data ?? []);
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
      const { proposal: rawProposal, params: proposalParams } = proposalItem || {};
      const castProposal = rawProposal as unknown as InterviewProposal | undefined;
      const candidateId = (proposalParams?.candidate_id as string) || "";
      const jobId = (proposalParams?.job_id as string) || "";

      if (castProposal && candidateId && jobId) {
        try {
          const created = await api.post<BackendInterview>("/interviews/from-proposal", {
            candidate_id: candidateId,
            job_id: jobId,
            scheduled_at: castProposal.recommended_slot || new Date().toISOString(),
            type: castProposal.interview_type || "video",
            duration_minutes: castProposal.duration_minutes || 60,
            notes: [castProposal.interview_type || "面试", castProposal.invitation_draft?.slice(0, 100)].filter(Boolean).join(" | "),
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

  // 持久化 viewMode：放 fetch useEffect 之后，确保所有 useState 已声明
  useEffect(() => {
    if (typeof window !== "undefined") {
      localStorage.setItem("interview_view_mode", viewMode);
    }
  }, [viewMode]);

  // 日历视图点击日期后，弹窗显示当日面试；放所有 useState 之后确保 hooks 顺序稳定
  const selectedDateInterviews = useMemo(() => {
    if (!selectedDate) return [];
    const key = `${selectedDate.getFullYear()}-${String(selectedDate.getMonth() + 1).padStart(2, "0")}-${String(selectedDate.getDate()).padStart(2, "0")}`;
    return interviews.filter(
      (i) => i.rawDate && i.rawDate.slice(0, 10) === key,
    );
  }, [selectedDate, interviews]);

  const defaultRecordingInterviewId = useMemo(() => {
    return interviews.find((i) => i.status === "confirmed")?.id
      || interviews.find((i) => i.status === "completed")?.id
      || interviews[0]?.id
      || "";
  }, [interviews]);

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

  const handleFeedback = (id: string) => {
    const raw = rawInterviews.find((r) => r.id === id);
    if (!raw) return;
    setEvalDialog({ open: true, interviewId: id, candidateName: raw.candidate_id });
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
              <Button variant="outline" size="sm" onClick={() => handleFeedback(i.id)}>
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
      <div className="space-y-6">
        <Skeleton className="h-8 w-32" />
        <Skeleton className="h-4 w-64" />
        <Card>
          <CardHeader className="pb-2">
            <div className="flex gap-4">
              <Skeleton className="h-10 w-64" />
              <Skeleton className="h-10 w-32 ml-auto" />
            </div>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {Array.from({ length: 5 }).map((_, i) => (
                <div key={i} className="flex gap-4 py-3">
                  <Skeleton className="h-4 w-24" />
                  <Skeleton className="h-4 w-32" />
                  <Skeleton className="h-4 w-20" />
                  <Skeleton className="h-4 w-16" />
                  <Skeleton className="h-5 w-16 ml-auto" />
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
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
          {error && <ErrorAlert message={error} variant="warning" />}
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
          <Button
            variant={viewMode === "calendar" ? "default" : "outline"}
            size="sm"
            className="gap-1"
            onClick={() => setViewMode(viewMode === "calendar" ? "list" : "calendar")}
            aria-pressed={viewMode === "calendar"}
          >
            <Calendar className="h-4 w-4" />
            日历视图
          </Button>
          <Button onClick={() => setShowCreate(true)} className="gap-1">
            <Plus className="h-4 w-4" />
            安排面试
          </Button>
        </div>
      </div>

      <div className="grid gap-3 md:grid-cols-4">
        {([
          { key: "all",       label: "总面试",  value: interviews.length,                                       icon: Users,    color: "text-blue-600" },
          { key: "pending",   label: "待确认",  value: interviews.filter(i => i.status === "pending").length,  icon: Clock,    color: "text-amber-600" },
          { key: "today",     label: "今日面试", value: interviews.filter(i => i.rawDate && isSameDay(new Date(i.rawDate), today)).length, icon: Calendar, color: "text-violet-600" },
          { key: "completed", label: "已完成",  value: interviews.filter(i => i.status === "completed").length,  icon: Check,    color: "text-green-600" },
        ] as const).map(s => {
          const Icon = s.icon;
          const active = statusFilter === s.key;
          return (
            <Button
              key={s.key}
              type="button"
              variant={active ? "default" : "outline"}
              className="h-auto py-4 flex-col items-start gap-1"
              onClick={() => setStatusFilter(s.key)}
              aria-pressed={active}
            >
              <div className="flex w-full items-center justify-between">
                <span className="text-sm font-medium">{s.label}</span>
                <Icon className={`h-4 w-4 ${active ? "" : s.color}`} />
              </div>
              <span className="text-3xl font-bold">{s.value}</span>
            </Button>
          );
        })}
      </div>

      <InterviewRecorder defaultInterviewId={defaultRecordingInterviewId} />

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
              const prop = p.proposal as unknown as InterviewProposal;
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

      {viewMode === "list" ? (
        <DataTable columns={columns} data={filteredInterviews as unknown as Record<string, unknown>[]} />
      ) : (
        <CalendarView
          interviews={interviews}
          onSelectDate={setSelectedDate}
        />
      )}

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
              <div className="space-y-2 py-4">
                {Array.from({ length: 3 }).map((_, i) => (
                  <div key={i} className="flex items-center gap-3 rounded-lg border p-3">
                    <Skeleton className="h-4 w-4 rounded-full" />
                    <div className="flex-1 space-y-1">
                      <Skeleton className="h-4 w-32" />
                      <Skeleton className="h-3 w-48" />
                    </div>
                    <Skeleton className="h-5 w-16" />
                  </div>
                ))}
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

      {/* Calendar Date Modal (M3 — 自建 Sheet 模式，复用现有 modal 风格) */}
      {selectedDate && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
          onClick={() => setSelectedDate(null)}
        >
          <div
            className="w-full max-w-2xl rounded-xl bg-white p-6 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-lg font-bold">
                {selectedDate.toLocaleDateString("zh-CN", { year: "numeric", month: "long", day: "numeric" })} 的面试（{selectedDateInterviews.length} 场）
              </h2>
              <button onClick={() => setSelectedDate(null)}>
                <X className="h-4 w-4" />
              </button>
            </div>
            <DataTable
              columns={columns}
              data={selectedDateInterviews as unknown as Record<string, unknown>[]}
            />
          </div>
        </div>
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

      {/* Evaluation Dialog */}
      <EvaluationDialog
        open={evalDialog.open}
        onClose={() => setEvalDialog({ ...evalDialog, open: false })}
        interviewId={evalDialog.interviewId}
        candidateName={evalDialog.candidateName}
      />
    </div>
  );
}
