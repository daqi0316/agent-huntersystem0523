"use client";

import { useState, useEffect, useCallback } from "react";
import { Save, Key, Bot, Bell, Globe, Loader2, CheckCircle2, Eye, EyeOff, History, Pencil, Trash2, Check, X } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/trpc";

interface MemoryItem {
  id: string;
  session_id: string;
  summary: string;
  created_at: string | null;
  updated_at: string | null;
}

interface MemoryListResponse {
  success: boolean;
  data: MemoryItem[];
  total: number;
  skip: number;
  limit: number;
}

interface Settings {
  llmProvider: string;
  llmBaseUrl: string;
  llmModel: string;
  embedModel: string;
  apiKey: string;
  jwtSecret: string;
  language: string;
  timezone: string;
  resultsPerPage: number;
  notifyNewApplicant: boolean;
  notifyInterviewReminder: boolean;
  notifyEvalComplete: boolean;
  notifySystemUpdate: boolean;
}

const DEFAULTS: Settings = {
  llmProvider: "omlx",
  llmBaseUrl: "http://localhost:8000/v1",
  llmModel: "qwen3.6",
  embedModel: "bge-m3",
  apiKey: "",
  jwtSecret: "",
  language: "zh-CN",
  timezone: "Asia/Shanghai",
  resultsPerPage: 20,
  notifyNewApplicant: true,
  notifyInterviewReminder: true,
  notifyEvalComplete: true,
  notifySystemUpdate: false,
};

const STORAGE_KEY = "ai-recruitment-settings";

export default function SettingsPage() {
  const [settings, setSettings] = useState<Settings>(DEFAULTS);
  const [saved, setSaved] = useState(false);
  const [showKeys, setShowKeys] = useState(false);

  useEffect(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) {
        setSettings({ ...DEFAULTS, ...JSON.parse(stored) });
      }
    } catch {
      // ignore corrupt local storage
    }
  }, []);

  const [memories, setMemories] = useState<MemoryItem[]>([]);
  const [memoryTotal, setMemoryTotal] = useState(0);
  const [memorySkip, setMemorySkip] = useState(0);
  const [memoryLoading, setMemoryLoading] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editText, setEditText] = useState("");

  const fetchMemories = useCallback(async (skip: number) => {
    setMemoryLoading(true);
    try {
      const res = await api.get<MemoryListResponse>(`/summaries?skip=${skip}&limit=20`);
      if (res && res.success) {
        setMemories(res.data || []);
        setMemoryTotal(res.total || 0);
        setMemorySkip(res.skip || 0);
      }
    } catch {
      setMemories([]);
    } finally {
      setMemoryLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchMemories(0);
  }, [fetchMemories]);

  const handleSave = () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  const update = <K extends keyof Settings>(key: K, value: Settings[K]) => {
    setSettings((prev) => ({ ...prev, [key]: value }));
  };

  return (
    <div className="max-w-2xl space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">系统设置</h1>
          <p className="text-muted-foreground">管理系统配置、API 密钥和用户偏好</p>
        </div>
        <Button onClick={handleSave} className="gap-1" disabled={saved}>
          {saved ? (
            <>
              <CheckCircle2 className="h-4 w-4" />
              已保存
            </>
          ) : (
            <>
              <Save className="h-4 w-4" />
              保存
            </>
          )}
        </Button>
      </div>

      {/* LLM Config */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Bot className="h-5 w-5 text-primary" />
            <CardTitle className="text-base">LLM 配置</CardTitle>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <label className="text-sm font-medium">LLM Provider</label>
              <select
                value={settings.llmProvider}
                onChange={(e) => update("llmProvider", e.target.value)}
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <option value="omlx">omlx</option>
                <option value="vllm">vLLM</option>
              </select>
            </div>
            <div className="space-y-1.5">
              <label className="text-sm font-medium">Base URL</label>
              <Input value={settings.llmBaseUrl} onChange={(e) => update("llmBaseUrl", e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <label className="text-sm font-medium">Model</label>
              <Input value={settings.llmModel} onChange={(e) => update("llmModel", e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <label className="text-sm font-medium">Embed Model</label>
              <Input value={settings.embedModel} onChange={(e) => update("embedModel", e.target.value)} />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* API Keys */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Key className="h-5 w-5 text-primary" />
            <CardTitle className="text-base">API 密钥</CardTitle>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-1.5">
            <label className="text-sm font-medium">通用 API 密钥</label>
            <div className="relative">
              <Input
                type={showKeys ? "text" : "password"}
                value={settings.apiKey}
                onChange={(e) => update("apiKey", e.target.value)}
                placeholder="sk-..."
              />
              <button
                className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                onClick={() => setShowKeys(!showKeys)}
              >
                {showKeys ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
          </div>
          <div className="space-y-1.5">
            <label className="text-sm font-medium">JWT 密钥</label>
            <Input
              type={showKeys ? "text" : "password"}
              value={settings.jwtSecret}
              onChange={(e) => update("jwtSecret", e.target.value)}
              placeholder="your-jwt-secret"
            />
          </div>
        </CardContent>
      </Card>

      {/* System Preferences */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Globe className="h-5 w-5 text-primary" />
            <CardTitle className="text-base">系统偏好</CardTitle>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-3">
            <div className="space-y-1.5">
              <label className="text-sm font-medium">语言</label>
              <select
                value={settings.language}
                onChange={(e) => update("language", e.target.value)}
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <option value="zh-CN">中文</option>
                <option value="en">English</option>
              </select>
            </div>
            <div className="space-y-1.5">
              <label className="text-sm font-medium">时区</label>
              <select
                value={settings.timezone}
                onChange={(e) => update("timezone", e.target.value)}
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <option value="Asia/Shanghai">Asia/Shanghai (UTC+8)</option>
                <option value="America/New_York">America/New_York (UTC-5)</option>
                <option value="Europe/London">Europe/London (UTC+0)</option>
              </select>
            </div>
            <div className="space-y-1.5">
              <label className="text-sm font-medium">每页条数</label>
              <Input
                type="number"
                value={settings.resultsPerPage}
                onChange={(e) => update("resultsPerPage", Number(e.target.value))}
                min={5}
                max={100}
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Notification Settings */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Bell className="h-5 w-5 text-primary" />
            <CardTitle className="text-base">通知设置</CardTitle>
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          {[
            { key: "notifyNewApplicant" as const, label: "候选人新申请" },
            { key: "notifyInterviewReminder" as const, label: "面试提醒" },
            { key: "notifyEvalComplete" as const, label: "评估完成" },
            { key: "notifySystemUpdate" as const, label: "系统更新" },
          ].map((n) => (
            <div key={n.key} className="flex items-center justify-between">
              <span className="text-sm">{n.label}</span>
              <button
                onClick={() => update(n.key, !settings[n.key])}
                className={`relative h-6 w-11 rounded-full transition-colors ${
                  settings[n.key] ? "bg-primary" : "bg-muted-foreground/30"
                }`}
              >
                <span
                  className={`absolute left-0.5 top-0.5 h-5 w-5 rounded-full bg-white transition-transform ${
                    settings[n.key] ? "translate-x-5" : "translate-x-0"
                  }`}
                />
              </button>
            </div>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <History className="h-5 w-5 text-primary" />
            <CardTitle className="text-base">历史记忆管理</CardTitle>
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          {memoryLoading ? (
            <div className="space-y-2 py-4">
              {Array.from({ length: 3 }).map((_, i) => (
                <div key={i} className="rounded-lg border p-3 space-y-2">
                  <div className="flex items-center justify-between">
                    <Skeleton className="h-4 w-24" />
                    <Skeleton className="h-3 w-12" />
                  </div>
                  <Skeleton className="h-12 w-full" />
                  <Skeleton className="h-8 w-20" />
                </div>
              ))}
            </div>
          ) : memories.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-8">暂无历史记忆</p>
          ) : (
            <>
              {memories.map((m) => (
                <div key={m.id} className="rounded-lg border p-3 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-mono text-muted-foreground">
                      {m.session_id.slice(0, 8)}...
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {m.updated_at ? new Date(m.updated_at).toLocaleDateString("zh-CN") : ""}
                    </span>
                  </div>
                  {editingId === m.id ? (
                    <div className="space-y-2">
                      <Textarea
                        value={editText}
                        onChange={(e) => setEditText(e.target.value)}
                        rows={3}
                      />
                      <div className="flex gap-2 justify-end">
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => setEditingId(null)}
                        >
                          <X className="h-3 w-3 mr-1" />
                          取消
                        </Button>
                        <Button
                          size="sm"
                          onClick={async () => {
                            try {
                              await api.put(`/summaries/${m.id}`, { summary: editText });
                              setEditingId(null);
                              fetchMemories(memorySkip);
                            } catch {
                              setEditingId(null);
                            }
                          }}
                        >
                          <Check className="h-3 w-3 mr-1" />
                          保存
                        </Button>
                      </div>
                    </div>
                  ) : (
                    <div className="flex items-start justify-between gap-2">
                      <p className="text-sm line-clamp-2 flex-1">{m.summary}</p>
                      <div className="flex gap-1 shrink-0">
                        <button
                          className="p-1 rounded hover:bg-muted text-muted-foreground hover:text-foreground"
                          onClick={() => {
                            setEditText(m.summary);
                            setEditingId(m.id);
                          }}
                          title="编辑"
                        >
                          <Pencil className="h-3.5 w-3.5" />
                        </button>
                        <button
                          className="p-1 rounded hover:bg-muted text-muted-foreground hover:text-destructive"
                          onClick={async () => {
                            if (window.confirm("确定删除这条记忆？")) {
                              try {
                                await api.delete(`/summaries/${m.id}`);
                                fetchMemories(memorySkip);
                              } catch {
                                // ignore
                              }
                            }
                          }}
                          title="删除"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              ))}
              {memoryTotal > 20 && (
                <div className="flex items-center justify-between pt-2">
                  <span className="text-xs text-muted-foreground">
                    共 {memoryTotal} 条，第 {memorySkip / 20 + 1} 页
                  </span>
                  <div className="flex gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={memorySkip === 0}
                      onClick={() => fetchMemories(memorySkip - 20)}
                    >
                      上一页
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={memorySkip + 20 >= memoryTotal}
                      onClick={() => fetchMemories(memorySkip + 20)}
                    >
                      下一页
                    </Button>
                  </div>
                </div>
              )}
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
