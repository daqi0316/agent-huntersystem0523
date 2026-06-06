"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

type CSMTask = {
  id: string;
  user_id: string;
  org_id: string;
  task_type: string;
  priority: string;
  status: string;
  reason: string;
  created_at: string;
  due_at: string | null;
  assigned_to: string | null;
};

const PRIORITY_LABEL: Record<string, string> = {
  P1: "🔴 P1 紧急",
  P2: "🟡 P2 重要",
  P3: "🟢 P3 普通",
};

const STATUS_LABEL: Record<string, string> = {
  open: "待处理",
  in_progress: "处理中",
  resolved: "已解决",
  closed: "已关闭",
};

const TYPE_LABEL: Record<string, string> = {
  health_drop: "健康度下降",
  no_login_7d: "7 天未登录",
  trial_ending: "试用即将到期",
  payment_failed: "支付失败",
  churn_risk: "流失风险",
  manual: "手动任务",
};

export default function CSMPage() {
  const [tasks, setTasks] = useState<CSMTask[]>([]);
  const [filter, setFilter] = useState<"all" | "open" | "resolved">("open");
  const [loading, setLoading] = useState(false);

  async function loadTasks() {
    setLoading(true);
    try {
      const r = await api.get<{ data: CSMTask[] }>(`/csm/tasks?status=${filter === "all" ? "" : filter}`);
      setTasks(r.data || []);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadTasks();
  }, [filter]);

  async function resolveTask(id: string) {
    await api.post(`/csm/tasks/${id}/resolve`, { note: "已处理" });
    loadTasks();
  }

  return (
    <div className="container mx-auto p-6">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">CSM 任务</h1>
        <div className="flex gap-2">
          {(["open", "all", "resolved"] as const).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-3 py-1 rounded text-sm ${
                filter === f ? "bg-blue-600 text-white" : "border"
              }`}
            >
              {f === "open" ? "待处理" : f === "all" ? "全部" : "已处理"}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <p>加载中...</p>
      ) : tasks.length === 0 ? (
        <p className="text-gray-500 py-12 text-center">
          暂无 {STATUS_LABEL[filter] || filter} 任务 🎉
        </p>
      ) : (
        <div className="space-y-3">
          {tasks.map((t) => (
            <div
              key={t.id}
              className="border rounded p-4 flex items-start justify-between gap-4"
            >
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-1">
                  <span className="font-semibold">
                    {TYPE_LABEL[t.task_type] || t.task_type}
                  </span>
                  <span className="text-sm">
                    {PRIORITY_LABEL[t.priority] || t.priority}
                  </span>
                  <span className="text-xs px-2 py-0.5 rounded bg-gray-100">
                    {STATUS_LABEL[t.status] || t.status}
                  </span>
                </div>
                <p className="text-sm text-gray-700 mb-2">{t.reason}</p>
                <div className="text-xs text-gray-500">
                  创建: {new Date(t.created_at).toLocaleString("zh-CN")}
                  {t.due_at && (
                    <> · 截止: {new Date(t.due_at).toLocaleString("zh-CN")}</>
                  )}
                </div>
              </div>
              {t.status === "open" && (
                <button
                  onClick={() => resolveTask(t.id)}
                  className="px-3 py-1 bg-green-600 text-white rounded text-sm whitespace-nowrap"
                >
                  标记已处理
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
