"use client";

import { useEffect, useState } from "react";
import { Download, Trash2, AlertTriangle, Loader2, CheckCircle, Clock } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ErrorAlert } from "@/components/common/error-alert";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
const TOKEN_KEY = "ai-recruitment-token";

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
}

interface ExportRequest {
  id: string;
  status: string;
  requested_at: string | null;
  completed_at: string | null;
  file_size_bytes: number | null;
  row_counts: Record<string, number>;
  expires_at: string | null;
  download_path: string | null;
  error_message: string | null;
}

interface DeleteRequest {
  id: string;
  status: string;
  requested_at: string | null;
  scheduled_hard_delete_at: string | null;
  grace_period_days_left: number | null;
  placeholder_uuid: string | null;
}

const STATUS_COLORS: Record<string, string> = {
  pending: "bg-gray-100 text-gray-700",
  processing: "bg-blue-100 text-blue-700",
  completed: "bg-green-100 text-green-700",
  failed: "bg-red-100 text-red-700",
  expired: "bg-gray-100 text-gray-500",
  soft_deleted: "bg-yellow-100 text-yellow-700",
  grace_period: "bg-yellow-100 text-yellow-700",
  hard_deleted: "bg-red-100 text-red-700",
  cancelled: "bg-gray-100 text-gray-700",
};

const STATUS_LABELS: Record<string, string> = {
  pending: "等待中",
  processing: "生成中",
  completed: "已完成",
  failed: "失败",
  expired: "已过期",
  soft_deleted: "已软删",
  grace_period: "宽限期",
  hard_deleted: "已硬删",
  cancelled: "已撤回",
};

function formatBytes(bytes: number | null): string {
  if (bytes === null) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
}

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  try { return new Date(iso).toLocaleString("zh-CN"); } catch { return iso; }
}

export default function PrivacyPage() {
  const [exports, setExports] = useState<ExportRequest[]>([]);
  const [deletes, setDeletes] = useState<DeleteRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionInProgress, setActionInProgress] = useState<string | null>(null);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const token = getToken();
      if (!token) { setError("未登录"); return; }
      const [expRes, delRes] = await Promise.all([
        fetch(`${API_BASE}/privacy/export`, { headers: { Authorization: `Bearer ${token}` } }),
        fetch(`${API_BASE}/privacy/delete`, { headers: { Authorization: `Bearer ${token}` } }),
      ]);
      if (!expRes.ok || !delRes.ok) throw new Error("加载失败");
      const [expJson, delJson] = await Promise.all([expRes.json(), delRes.json()]);
      setExports(expJson.data || []);
      setDeletes(delJson.data || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const handleRequestExport = async () => {
    setActionInProgress("export");
    setError(null);
    try {
      const token = getToken();
      const res = await fetch(`${API_BASE}/privacy/export`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      const j = await res.json();
      if (!res.ok || !j.success) throw new Error(j.error || "请求失败");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "请求失败");
    } finally {
      setActionInProgress(null);
    }
  };

  const handleRequestDelete = async () => {
    setActionInProgress("delete");
    setError(null);
    try {
      const token = getToken();
      const res = await fetch(`${API_BASE}/privacy/delete`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      const j = await res.json();
      if (!res.ok || !j.success) throw new Error(j.error || "请求失败");
      setShowDeleteConfirm(false);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "请求失败");
    } finally {
      setActionInProgress(null);
    }
  };

  const handleConfirmDelete = async (requestId: string) => {
    setActionInProgress(`confirm-${requestId}`);
    setError(null);
    try {
      const token = getToken();
      const res = await fetch(`${API_BASE}/privacy/delete/${requestId}/confirm`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      const j = await res.json();
      if (!res.ok || !j.success) throw new Error(j.error || "确认失败");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "确认失败");
    } finally {
      setActionInProgress(null);
    }
  };

  const handleCancelDelete = async (requestId: string) => {
    setActionInProgress(`cancel-${requestId}`);
    setError(null);
    try {
      const token = getToken();
      const res = await fetch(`${API_BASE}/privacy/delete/${requestId}/cancel`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      const j = await res.json();
      if (!res.ok || !j.success) throw new Error(j.error || "撤回失败");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "撤回失败");
    } finally {
      setActionInProgress(null);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center p-12 text-muted-foreground">
        <Loader2 className="mr-2 h-4 w-4 animate-spin" /> 加载隐私设置...
      </div>
    );
  }

  const pendingDelete = deletes.find((d) => d.status === "pending");
  const activeDelete = deletes.find((d) => d.status === "grace_period" || d.status === "soft_deleted");
  const activeExport = exports.find((e) => ["pending", "processing"].includes(e.status));

  return (
    <div className="space-y-6 p-6">
      <div>
        <h1 className="text-3xl font-bold">
          隐私与数据
        </h1>
        <p className="text-muted-foreground">
          依据《个人信息保护法》第 15/17 条 — 数据导出与删除
        </p>
      </div>

      {error && <ErrorAlert message={error} variant="error" />}

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Download className="h-4 w-4" />
            数据导出 (Art. 15)
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            导出您在本系统的所有数据, 包括 user / memberships / invitations / audit_logs / sessions / memory / payment 等。生成后保留 7 天, 请及时下载。
          </p>

          {activeExport ? (
            <div className="flex items-center gap-2 rounded border bg-blue-50 p-3 text-sm">
              <Loader2 className="h-4 w-4 animate-spin text-blue-600" />
              <span>正在生成导出, 完成后可在下方下载</span>
            </div>
          ) : (
            <Button onClick={handleRequestExport} disabled={actionInProgress !== null}>
              {actionInProgress === "export" ? <Loader2 className="mr-1 h-3 w-3 animate-spin" /> : <Download className="mr-1 h-3 w-3" />}
              申请新导出
            </Button>
          )}

          {exports.length > 0 && (
            <div className="divide-y rounded border">
              {exports.map((e) => (
                <div key={e.id} className="flex items-center justify-between p-3 text-sm">
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <Badge variant="outline" className={STATUS_COLORS[e.status] || ""}>
                        {STATUS_LABELS[e.status] || e.status}
                      </Badge>
                      <span className="font-mono text-xs text-muted-foreground">
                        {e.id.slice(0, 8)}...
                      </span>
                    </div>
                    <div className="mt-1 flex flex-wrap gap-3 text-xs text-muted-foreground">
                      <span>大小: {formatBytes(e.file_size_bytes)}</span>
                      {Object.keys(e.row_counts).length > 0 && (
                        <span>表: {Object.entries(e.row_counts).map(([k, v]) => `${k}=${v}`).join(", ")}</span>
                      )}
                      <span>申请: {formatDate(e.requested_at)}</span>
                      {e.expires_at && <span>过期: {formatDate(e.expires_at)}</span>}
                    </div>
                    {e.error_message && (
                      <p className="mt-1 text-xs text-red-600">错误: {e.error_message}</p>
                    )}
                  </div>
                  {e.status === "completed" && e.download_path && (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        const token = getToken();
                        const a = document.createElement("a");
                        a.href = `${API_BASE.replace("/api/v1", "")}${e.download_path}&user_id=${getToken()?.split('.')[1] || ""}`;
                        a.download = `export_${e.id}.json`;
                        a.click();
                      }}
                    >
                      下载
                    </Button>
                  )}
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base text-red-600">
            <Trash2 className="h-4 w-4" />
            数据删除 (Art. 17)
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            申请删除后, 账号将立即被禁用, 30 天宽限期内可撤回。30 天后系统将:
          </p>
          <ul className="ml-4 list-disc space-y-1 text-sm text-muted-foreground">
            <li>邮箱/姓名/微信绑定 全部匿名化</li>
            <li>所有外键引用替换为占位 UUID, 保留审计链</li>
            <li>导出文件与备份数据保留 7 天后自动清除</li>
          </ul>

          {activeDelete ? (
            <div className="rounded border border-yellow-200 bg-yellow-50 p-3">
              <div className="flex items-center gap-2 text-sm">
                <Clock className="h-4 w-4 text-yellow-600" />
                <span>
                  账号已禁用, 距硬删还有 <strong>{activeDelete.grace_period_days_left ?? "—"}</strong> 天
                </span>
              </div>
              <div className="mt-2 text-xs text-muted-foreground">
                定时硬删时间: {formatDate(activeDelete.scheduled_hard_delete_at)}
              </div>
              <div className="mt-3 flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => handleCancelDelete(activeDelete.id)}
                  disabled={actionInProgress !== null}
                >
                  {actionInProgress === `cancel-${activeDelete.id}` ? <Loader2 className="mr-1 h-3 w-3 animate-spin" /> : null}
                  撤回删除
                </Button>
              </div>
            </div>
          ) : pendingDelete ? (
            <div className="rounded border border-blue-200 bg-blue-50 p-3 text-sm">
              <p>删除请求已创建, 需确认后才会真正禁用账号。</p>
              <div className="mt-3 flex gap-2">
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={() => handleConfirmDelete(pendingDelete.id)}
                  disabled={actionInProgress !== null}
                >
                  {actionInProgress === `confirm-${pendingDelete.id}` ? <Loader2 className="mr-1 h-3 w-3 animate-spin" /> : null}
                  确认删除 (开始 30 天宽限期)
                </Button>
              </div>
            </div>
          ) : (
            <Button
              variant="destructive"
              onClick={() => setShowDeleteConfirm(true)}
              disabled={actionInProgress !== null}
            >
              <Trash2 className="mr-1 h-3 w-3" />
              申请删除
            </Button>
          )}

          {deletes.length > 0 && (
            <details className="text-xs text-muted-foreground">
              <summary className="cursor-pointer">历史删除请求 ({deletes.length})</summary>
              <div className="mt-2 divide-y rounded border">
                {deletes.map((d) => (
                  <div key={d.id} className="flex items-center justify-between p-2">
                    <span className="font-mono">{d.id.slice(0, 8)}...</span>
                    <Badge variant="outline" className={STATUS_COLORS[d.status] || ""}>
                      {STATUS_LABELS[d.status] || d.status}
                    </Badge>
                    <span>{formatDate(d.requested_at)}</span>
                  </div>
                ))}
              </div>
            </details>
          )}
        </CardContent>
      </Card>

      {showDeleteConfirm && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
          onClick={() => setShowDeleteConfirm(false)}
        >
          <div
            className="w-full max-w-md rounded-lg bg-white p-6"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-4 flex items-center gap-2 text-red-600">
              <AlertTriangle className="h-5 w-5" />
              <h2 className="text-lg font-semibold">确认申请删除?</h2>
            </div>
            <div className="space-y-2 text-sm text-muted-foreground">
              <p>删除后账号将立即被禁用, 您将无法登录。</p>
              <p>30 天内可撤回 (在宽限期结束前)。</p>
              <p>30 天后所有 PII 将永久匿名化, 不可恢复。</p>
            </div>
            <div className="mt-4 flex justify-end gap-2">
              <Button variant="outline" onClick={() => setShowDeleteConfirm(false)}>
                取消
              </Button>
              <Button
                variant="destructive"
                onClick={handleRequestDelete}
                disabled={actionInProgress !== null}
              >
                {actionInProgress === "delete" ? <Loader2 className="mr-1 h-3 w-3 animate-spin" /> : null}
                申请删除
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
