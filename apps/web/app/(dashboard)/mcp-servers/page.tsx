"use client";

import { useState, useEffect, useCallback } from "react";
import {
  Plus, Trash2, Pencil, Wifi, WifiOff, Loader2, CheckCircle2,
  XCircle, Server, Globe, Plug, Eye, EyeOff, Power, PowerOff,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { api, withErrorHandling } from "@/lib/trpc";

/* ── Types ────────────────────────────────────────────── */

interface MCPToolDef {
  name: string;
  description: string;
  input_schema: Record<string, unknown>;
}

interface MCPServerRead {
  id: string;
  name: string;
  server_url: string;
  protocol: string;
  auth_type: string;
  enabled: boolean;
  tools_cache: MCPToolDef[] | null;
  last_heartbeat: string | null;
  created_at: string;
  updated_at: string;
}

interface ServerForm {
  name: string;
  server_url: string;
  protocol: string;
  auth_type: string;
  auth_token: string;
}

const EMPTY_FORM: ServerForm = {
  name: "",
  server_url: "",
  protocol: "streamable-http",
  auth_type: "none",
  auth_token: "",
};

/* ── Dialog ───────────────────────────────────────────── */

function Dialog({
  open,
  onClose,
  title,
  children,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
}) {
  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={onClose}
    >
      <div
        className="bg-background rounded-lg shadow-lg w-full max-w-lg p-6 max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-lg font-semibold mb-4">{title}</h2>
        {children}
      </div>
    </div>
  );
}

/* ── Main Page ────────────────────────────────────────── */

export default function MCPServersPage() {
  const [servers, setServers] = useState<MCPServerRead[]>([]);
  const [loading, setLoading] = useState(true);

  // Dialog state
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<ServerForm>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);

  // Test connection result
  const [testResult, setTestResult] = useState<{
    serverId: string | null;
    loading: boolean;
    success?: boolean;
    serverName?: string;
    tools?: MCPToolDef[];
    error?: string;
  }>({ serverId: null, loading: false });

  const fetchServers = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get<{ success: boolean; data: MCPServerRead[] }>("/mcp/servers");
      setServers(res.data ?? []);
    } catch {
      setServers([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchServers();
  }, [fetchServers]);

  /* ── Form handlers ──────────────────────────────────── */

  const openAdd = () => {
    setEditingId(null);
    setForm(EMPTY_FORM);
    setTestResult({ serverId: null, loading: false });
    setDialogOpen(true);
  };

  const openEdit = (s: MCPServerRead) => {
    setEditingId(s.id);
    setForm({
      name: s.name,
      server_url: s.server_url,
      protocol: s.protocol,
      auth_type: s.auth_type,
      auth_token: "",
    });
    setTestResult({ serverId: null, loading: false });
    setDialogOpen(true);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      if (editingId) {
        await withErrorHandling(
          () => api.put(`/mcp/servers/${editingId}`, form),
          { success: "MCP 服务器已更新" },
        );
      } else {
        await withErrorHandling(
          () => api.post("/mcp/servers", form),
          { success: "MCP 服务器已添加" },
        );
      }
      setDialogOpen(false);
      fetchServers();
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: string, name: string) => {
    if (!window.confirm(`确定删除 MCP 服务器「${name}」？`)) return;
    await withErrorHandling(
      () => api.delete(`/mcp/servers/${id}`),
      { success: "已删除" },
    );
    fetchServers();
  };

  const handleToggleEnabled = async (s: MCPServerRead) => {
    await withErrorHandling(
      () => api.put(`/mcp/servers/${s.id}`, { enabled: !s.enabled }),
    );
    fetchServers();
  };

  /* ── Test connection ─────────────────────────────────── */

  const handleTest = async (id: string) => {
    setTestResult({ serverId: id, loading: true });
    try {
      const res = await api.post<{
        success: boolean;
        server_name?: string;
        tools?: MCPToolDef[];
        error?: string;
      }>(`/mcp/servers/${id}/test`, {});
      setTestResult({
        serverId: id,
        loading: false,
        success: res.success,
        serverName: res.server_name,
        tools: res.tools,
        error: res.error,
      });
    } catch (e) {
      setTestResult({
        serverId: id,
        loading: false,
        success: false,
        error: String(e),
      });
    }
  };

  const handleTestNew = async () => {
    if (!form.server_url) return;
    setTestResult({ serverId: "__new__", loading: true });
    try {
      const res = await api.post<{
        success: boolean;
        server_name?: string;
        tools?: MCPToolDef[];
        error?: string;
      }>("/mcp/servers/test", {
        server_url: form.server_url,
        auth_type: form.auth_type,
        auth_token: form.auth_token,
      });
      setTestResult({
        serverId: "__new__",
        loading: false,
        success: res.success,
        serverName: res.server_name,
        tools: res.tools,
        error: res.error,
      });
    } catch (e) {
      setTestResult({
        serverId: "__new__",
        loading: false,
        success: false,
        error: String(e),
      });
    }
  };

  /* ── Render ──────────────────────────────────────────── */

  return (
    <div className="max-w-4xl space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">MCP 服务器管理</h1>
          <p className="text-muted-foreground">
            管理和配置外部 MCP 服务器连接，扩展 Agent 的能力
          </p>
        </div>
        <Button onClick={openAdd} className="gap-1">
          <Plus className="h-4 w-4" />
          添加服务器
        </Button>
      </div>

      {/* Server List */}
      {loading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      ) : servers.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12 gap-3">
            <Server className="h-10 w-10 text-muted-foreground" />
            <p className="text-muted-foreground text-sm">暂无 MCP 服务器配置</p>
            <Button variant="outline" onClick={openAdd} className="gap-1">
              <Plus className="h-4 w-4" />
              添加服务器
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          {servers.map((s) => (
            <Card key={s.id} className={s.enabled ? "" : "opacity-60"}>
              <CardContent className="p-4">
                <div className="flex items-start justify-between gap-4">
                  {/* Left: info */}
                  <div className="flex-1 min-w-0 space-y-2">
                    <div className="flex items-center gap-2">
                      <span className="font-medium truncate">{s.name}</span>
                      <Badge variant={s.enabled ? "default" : "secondary"} className="text-xs">
                        {s.enabled ? (
                          <><Wifi className="h-3 w-3 mr-1" />已启用</>
                        ) : (
                          <><WifiOff className="h-3 w-3 mr-1" />已禁用</>
                        )}
                      </Badge>
                      <Badge variant="outline" className="text-xs font-mono">
                        {s.protocol}
                      </Badge>
                    </div>
                    <p className="text-sm text-muted-foreground truncate font-mono">
                      {s.server_url}
                    </p>
                    <div className="flex items-center gap-4 text-xs text-muted-foreground">
                      <span className="flex items-center gap-1">
                        <Plug className="h-3 w-3" />
                        工具: {s.tools_cache?.length ?? 0}
                      </span>
                      {s.last_heartbeat && (
                        <span>
                          最后心跳: {new Date(s.last_heartbeat).toLocaleString("zh-CN")}
                        </span>
                      )}
                    </div>
                    {/* Test result inline */}
                    {testResult.serverId === s.id && !testResult.loading && (
                      <div className={`text-xs mt-1 ${testResult.success ? "text-green-600" : "text-red-600"}`}>
                        {testResult.success ? (
                          <div className="space-y-1">
                            <div className="flex items-center gap-1">
                              <CheckCircle2 className="h-3 w-3" />
                              连接成功 — {testResult.serverName}
                            </div>
                            {testResult.tools && testResult.tools.length > 0 && (
                              <div className="pl-4 space-y-0.5">
                                {testResult.tools.map((t) => (
                                  <div key={t.name}>
                                    <span className="font-medium">{t.name}</span>
                                    {t.description && <span className="text-muted-foreground"> — {t.description}</span>}
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        ) : (
                          <div className="flex items-center gap-1">
                            <XCircle className="h-3 w-3" />
                            {testResult.error}
                          </div>
                        )}
                      </div>
                    )}
                    {testResult.serverId === s.id && testResult.loading && (
                      <div className="flex items-center gap-1 text-xs text-muted-foreground">
                        <Loader2 className="h-3 w-3 animate-spin" />
                        连接测试中...
                      </div>
                    )}
                  </div>

                  {/* Right: actions */}
                  <div className="flex items-center gap-1 shrink-0">
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => handleTest(s.id)}
                      title="测试连接"
                      disabled={testResult.serverId === s.id && testResult.loading}
                    >
                      <Globe className="h-4 w-4" />
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => handleToggleEnabled(s)}
                      title={s.enabled ? "禁用" : "启用"}
                    >
                      {s.enabled ? (
                        <Power className="h-4 w-4 text-green-600" />
                      ) : (
                        <PowerOff className="h-4 w-4 text-muted-foreground" />
                      )}
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => openEdit(s)}
                      title="编辑"
                    >
                      <Pencil className="h-4 w-4" />
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => handleDelete(s.id, s.name)}
                      title="删除"
                    >
                      <Trash2 className="h-4 w-4 text-destructive" />
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* ── Add/Edit Dialog ──────────────────────────────── */}
      <Dialog
        open={dialogOpen}
        onClose={() => setDialogOpen(false)}
        title={editingId ? "编辑 MCP 服务器" : "添加 MCP 服务器"}
      >
        <div className="space-y-4">
          <div className="space-y-1.5">
            <label className="text-sm font-medium">名称 *</label>
            <Input
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="邮件助手"
            />
          </div>

          <div className="space-y-1.5">
            <label className="text-sm font-medium">Server URL *</label>
            <Input
              value={form.server_url}
              onChange={(e) => setForm({ ...form, server_url: e.target.value })}
              placeholder="http://localhost:8002/mcp"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <label className="text-sm font-medium">协议</label>
              <select
                value={form.protocol}
                onChange={(e) => setForm({ ...form, protocol: e.target.value })}
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <option value="streamable-http">Streamable HTTP</option>
                <option value="sse">SSE</option>
              </select>
            </div>
            <div className="space-y-1.5">
              <label className="text-sm font-medium">认证方式</label>
              <select
                value={form.auth_type}
                onChange={(e) => setForm({ ...form, auth_type: e.target.value })}
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <option value="none">无</option>
                <option value="bearer">Bearer Token</option>
                <option value="basic">Basic Auth</option>
              </select>
            </div>
          </div>

          {form.auth_type !== "none" && (
            <div className="space-y-1.5">
              <label className="text-sm font-medium">Token / 密码</label>
              <Input
                type="password"
                value={form.auth_token}
                onChange={(e) => setForm({ ...form, auth_token: e.target.value })}
                placeholder={form.auth_type === "bearer" ? "sk-..." : "username:password"}
              />
            </div>
          )}

          {/* Test new connection */}
          <div className="border-t pt-3">
            <Button
              variant="outline"
              size="sm"
              onClick={handleTestNew}
              disabled={testResult.serverId === "__new__" && testResult.loading}
              className="gap-1"
            >
              {testResult.serverId === "__new__" && testResult.loading ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : (
                <Globe className="h-3 w-3" />
              )}
              测试连接
            </Button>

            {testResult.serverId === "__new__" && !testResult.loading && (
              <div className={`mt-2 text-sm ${testResult.success ? "text-green-600" : "text-red-600"}`}>
                {testResult.success ? (
                  <div className="space-y-1">
                    <div className="flex items-center gap-1 font-medium">
                      <CheckCircle2 className="h-4 w-4" />
                      连接成功 — {testResult.serverName}
                    </div>
                    {testResult.tools && testResult.tools.length > 0 && (
                      <div className="pl-5 space-y-0.5 text-xs">
                        <p className="text-muted-foreground">可用工具:</p>
                        {testResult.tools.map((t) => (
                          <div key={t.name}>
                            <span className="font-medium">{t.name}</span>
                            {t.description && <span className="text-muted-foreground"> — {t.description}</span>}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="flex items-center gap-1">
                    <XCircle className="h-4 w-4" />
                    {testResult.error}
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Actions */}
          <div className="flex justify-end gap-2 pt-2 border-t">
            <Button variant="outline" onClick={() => setDialogOpen(false)}>
              取消
            </Button>
            <Button onClick={handleSave} disabled={saving || !form.name || !form.server_url}>
              {saving ? (
                <><Loader2 className="h-4 w-4 mr-1 animate-spin" />保存中</>
              ) : (
                "保存"
              )}
            </Button>
          </div>
        </div>
      </Dialog>
    </div>
  );
}
