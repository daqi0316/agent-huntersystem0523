"use client";

import { useState, useEffect } from "react";
import {
  Calendar, Clock, Users, Plus, Loader2, X, AlertCircle,
} from "lucide-react";
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
  /** ISO date string for filtering, undefined if unscheduled */
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

export default function InterviewPage() {
  const [interviews, setInterviews] = useState<InterviewRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [form, setForm] = useState({ candidate: "", job: "", time: "", interviewer: "", notes: "" });

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
  }, []);

  const handleCreate = async () => {
    setSubmitting(true);
    try {
      const params = new URLSearchParams({
        candidate_id: form.candidate || "new-candidate",
        job_id: form.job || "new-job",
        scheduled_at: form.time || new Date().toISOString(),
        notes: [form.interviewer, form.notes].filter(Boolean).join(" | "),
      });
      const created = await api.post<BackendInterview>(`/interviews?${params}`, {});
      setInterviews((prev) => [toDisplay(created), ...prev]);
    } catch {
      // Optimistic local fallback
      setInterviews((prev) => [
        {
          id: `new-${Date.now()}`,
          candidate: form.candidate || "新候选人",
          job: form.job || "未指定职位",
          time: form.time || new Date().toLocaleString("zh-CN"),
          interviewer: form.interviewer || "待分配",
          status: "pending",
          notes: form.notes,
        },
        ...prev,
      ]);
    }
    setSubmitting(false);
    setShowCreate(false);
    setForm({ candidate: "", job: "", time: "", interviewer: "", notes: "" });
  };

  const handleConfirm = async (id: string) => {
    try {
      await api.patch(`/interviews/${id}/confirm`);
      setInterviews((prev) => prev.map((i) => (i.id === id ? { ...i, status: "confirmed" as const } : i)));
    } catch { /* ignore */ }
  };

  const handleCancel = async (id: string) => {
    try {
      await api.patch(`/interviews/${id}/cancel`);
      setInterviews((prev) => prev.map((i) => (i.id === id ? { ...i, status: "cancelled" as const } : i)));
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
            <p className="text-muted-foreground">管理面试安排与进度追踪</p>
          </div>
          {error && (
            <Badge variant="warning" className="gap-1">
              <AlertCircle className="h-3 w-3" />
              {error}
            </Badge>
          )}
        </div>
        <div className="flex gap-2">
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
          { label: "待确认", value: interviews.filter((i) => i.status === "pending").length, icon: Clock, color: "text-amber-600" },
          { label: "今日面试", value: interviews.filter((i) => i.rawDate && isSameDay(new Date(i.rawDate), new Date())).length, icon: Calendar, color: "text-violet-600" },
          { label: "已完成", value: interviews.filter((i) => i.status === "completed").length, icon: Calendar, color: "text-green-600" },
        ].map((s) => {
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

      <DataTable columns={columns} data={interviews as unknown as Record<string, unknown>[]} />

      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={() => setShowCreate(false)}>
          <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-lg font-bold">安排面试</h2>
              <button onClick={() => setShowCreate(false)}><X className="h-4 w-4" /></button>
            </div>
            <div className="space-y-3">
              <Input placeholder="候选人姓名" value={form.candidate} onChange={(e) => setForm({ ...form, candidate: e.target.value })} />
              <Input placeholder="职位名称" value={form.job} onChange={(e) => setForm({ ...form, job: e.target.value })} />
              <Input type="datetime-local" value={form.time} onChange={(e) => setForm({ ...form, time: e.target.value })} />
              <Input placeholder="面试官" value={form.interviewer} onChange={(e) => setForm({ ...form, interviewer: e.target.value })} />
              <Input placeholder="备注（可选）" value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
            </div>
            <div className="mt-4 flex justify-end gap-2">
              <Button variant="outline" onClick={() => setShowCreate(false)}>取消</Button>
              <Button onClick={handleCreate} disabled={submitting}>
                {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                创建
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
