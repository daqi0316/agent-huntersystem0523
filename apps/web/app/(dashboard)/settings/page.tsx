"use client";

import { useState, useEffect, useCallback } from "react";
import { Save, Bot, Bell, Globe, CheckCircle2, Eye, EyeOff, History, Pencil, Trash2, Check, X, Plus, Zap, Star, Copy, AlertCircle } from "lucide-react";
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

// ── 模型接入预设 ──
interface ModelProvider {
  id: string;
  name: string;        // 用户自定义名称
  provider: string;    // 预设标识
  baseUrl: string;
  model: string;
  apiKey: string;
  isActive: boolean;   // 当前激活
}

const PROVIDER_PRESETS: Record<string, { label: string; baseUrl: string; defaultModel: string; description: string }> = {
  openai:       { label: "OpenAI",        baseUrl: "https://api.openai.com/v1",                            defaultModel: "gpt-4o",            description: "GPT-4o / GPT-4 系列" },
  qwen:         { label: "通义千问",       baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1",    defaultModel: "qwen-plus",         description: "阿里云 DashScope" },
  deepseek:     { label: "DeepSeek",      baseUrl: "https://api.deepseek.com/v1",                          defaultModel: "deepseek-chat",     description: "DeepSeek Chat / R1" },
  zhipu:        { label: "智谱 GLM",      baseUrl: "https://open.bigmodel.cn/api/paas/v4/",                defaultModel: "glm-4-plus",        description: "智谱 AI GLM-4 系列" },
  omlx:         { label: "OMLX (本地)",    baseUrl: "http://localhost:8000/v1",                              defaultModel: "qwen3.6",           description: "本地 OMLX 推理服务" },
  vllm:         { label: "vLLM (远程)",    baseUrl: "http://localhost:8080/v1",                              defaultModel: "Qwen/Qwen2.5-72B-Instruct", description: "远程 GPU vLLM 推理" },
  custom:       { label: "自定义",         baseUrl: "",                                                      defaultModel: "",                   description: "任意 OpenAI 兼容 API" },
};

const MODELS_STORAGE_KEY = "ai-recruitment-model-providers";

function generateId() {
  return Math.random().toString(36).slice(2, 10);
}

const DEFAULT_PROVIDERS: ModelProvider[] = [
  {
    id: generateId(),
    name: "OMLX 本地模型",
    provider: "omlx",
    baseUrl: PROVIDER_PRESETS.omlx.baseUrl,
    model: PROVIDER_PRESETS.omlx.defaultModel,
    apiKey: "",
    isActive: true,
  },
];

interface Settings {
  embedModel: string;
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
  embedModel: "bge-m3",
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
  const [showKeys, setShowKeys] = useState<Record<string, boolean>>({});

  // ── 模型接入状态 ──
  const [providers, setProviders] = useState<ModelProvider[]>(DEFAULT_PROVIDERS);
  const [showAddForm, setShowAddForm] = useState(false);
  const [newProviderPreset, setNewProviderPreset] = useState("openai");
  const [newProviderName, setNewProviderName] = useState("");
  const [newProviderBaseUrl, setNewProviderBaseUrl] = useState("");
  const [newProviderModel, setNewProviderModel] = useState("");
  const [newProviderApiKey, setNewProviderApiKey] = useState("");
  const [editingProviderId, setEditingProviderId] = useState<string | null>(null);
  const [connectionTestResult, setConnectionTestResult] = useState<{ id: string; status: "success" | "error"; message: string } | null>(null);

  useEffect(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) {
        setSettings({ ...DEFAULTS, ...JSON.parse(stored) });
      }
      const storedProviders = localStorage.getItem(MODELS_STORAGE_KEY);
      if (storedProviders) {
        const parsed = JSON.parse(storedProviders);
        if (Array.isArray(parsed) && parsed.length > 0) setProviders(parsed);
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
    localStorage.setItem(MODELS_STORAGE_KEY, JSON.stringify(providers));
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  const update = <K extends keyof Settings>(key: K, value: Settings[K]) => {
    setSettings((prev) => ({ ...prev, [key]: value }));
  };

  // ── 模型接入操作 ──
  const handlePresetChange = (preset: string) => {
    setNewProviderPreset(preset);
    const p = PROVIDER_PRESETS[preset];
    setNewProviderName(p.label);
    setNewProviderBaseUrl(p.baseUrl);
    setNewProviderModel(p.defaultModel);
  };

  const handleAddProvider = () => {
    if (!newProviderName.trim() || !newProviderModel.trim()) return;
    const newProvider: ModelProvider = {
      id: generateId(),
      name: newProviderName.trim(),
      provider: newProviderPreset,
      baseUrl: newProviderBaseUrl.trim(),
      model: newProviderModel.trim(),
      apiKey: newProviderApiKey.trim(),
      isActive: false,
    };
    setProviders((prev) => [...prev, newProvider]);
    setShowAddForm(false);
    setNewProviderName("");
    setNewProviderBaseUrl("");
    setNewProviderModel("");
    setNewProviderApiKey("");
  };

  const handleDeleteProvider = (id: string) => {
    setProviders((prev) => {
      const target = prev.find((p) => p.id === id);
      if (target?.isActive) return prev; // 不允许删除当前激活项
      return prev.filter((p) => p.id !== id);
    });
  };

  const handleActivateProvider = (id: string) => {
    setProviders((prev) =>
      prev.map((p) => ({ ...p, isActive: p.id === id }))
    );
  };

  const handleUpdateProvider = (id: string, field: keyof ModelProvider, value: string) => {
    setProviders((prev) =>
      prev.map((p) => (p.id === id ? { ...p, [field]: value } : p))
    );
  };

  const handleTestConnection = async (id: string) => {
    const provider = providers.find((p) => p.id === id);
    if (!provider) return;
    setConnectionTestResult({ id, status: "success", message: "测试中..." });
    try {
      const res = await fetch(`${provider.baseUrl}/models`, {
        headers: provider.apiKey ? { Authorization: `Bearer ${provider.apiKey}` } : {},
        signal: AbortSignal.timeout(10000),
      });
      if (res.ok) {
        setConnectionTestResult({ id, status: "success", message: "连接成功 ✓" });
      } else {
        setConnectionTestResult({ id, status: "error", message: `HTTP ${res.status}` });
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "连接失败";
      setConnectionTestResult({ id, status: "error", message: msg });
    }
    setTimeout(() => setConnectionTestResult(null), 5000);
  };

  const handleDuplicateProvider = (id: string) => {
    const source = providers.find((p) => p.id === id);
    if (!source) return;
    const dup: ModelProvider = {
      ...source,
      id: generateId(),
      name: `${source.name} (副本)`,
      isActive: false,
    };
    setProviders((prev) => [...prev, dup]);
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

      {/* ── 模型接入管理 ── */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Bot className="h-5 w-5 text-primary" />
              <CardTitle className="text-base">模型接入</CardTitle>
            </div>
            <Button
              size="sm"
              variant="outline"
              className="gap-1"
              onClick={() => {
                handlePresetChange("openai");
                setShowAddForm(true);
              }}
            >
              <Plus className="h-4 w-4" />
              添加模型
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          {/* 预设选择弹窗 */}
          {showAddForm && (
            <div className="rounded-lg border border-primary/30 bg-primary/5 p-4 space-y-4 animate-in fade-in">
              <div className="flex items-center justify-between">
                <h4 className="text-sm font-semibold">添加新的模型接入</h4>
                <button
                  onClick={() => setShowAddForm(false)}
                  className="text-muted-foreground hover:text-foreground"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>

              {/* 预设选择 */}
              <div className="space-y-1.5">
                <label className="text-sm font-medium">选择预设</label>
                <select
                  value={newProviderPreset}
                  onChange={(e) => handlePresetChange(e.target.value)}
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                >
                  {Object.entries(PROVIDER_PRESETS).map(([key, preset]) => (
                    <option key={key} value={key}>
                      {preset.label} — {preset.description}
                    </option>
                  ))}
                </select>
              </div>

              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <label className="text-sm font-medium">显示名称</label>
                  <Input
                    value={newProviderName}
                    onChange={(e) => setNewProviderName(e.target.value)}
                    placeholder="例：OpenAI GPT-4o"
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="text-sm font-medium">模型名称</label>
                  <Input
                    value={newProviderModel}
                    onChange={(e) => setNewProviderModel(e.target.value)}
                    placeholder="例：gpt-4o"
                  />
                </div>
                <div className="space-y-1.5 sm:col-span-2">
                  <label className="text-sm font-medium">API Base URL</label>
                  <Input
                    value={newProviderBaseUrl}
                    onChange={(e) => setNewProviderBaseUrl(e.target.value)}
                    placeholder="https://api.openai.com/v1"
                  />
                </div>
                <div className="space-y-1.5 sm:col-span-2">
                  <label className="text-sm font-medium">API Key</label>
                  <Input
                    type="password"
                    value={newProviderApiKey}
                    onChange={(e) => setNewProviderApiKey(e.target.value)}
                    placeholder="sk-..."
                  />
                </div>
              </div>

              <div className="flex justify-end gap-2">
                <Button size="sm" variant="outline" onClick={() => setShowAddForm(false)}>
                  取消
                </Button>
                <Button size="sm" onClick={handleAddProvider} disabled={!newProviderName.trim() || !newProviderModel.trim()}>
                  <Check className="h-3.5 w-3.5 mr-1" />
                  确认添加
                </Button>
              </div>
            </div>
          )}

          {/* 已添加的模型列表 */}
          {providers.length === 0 && !showAddForm ? (
            <p className="text-sm text-muted-foreground text-center py-8">
              暂无模型配置，请点击上方「添加模型」
            </p>
          ) : (
            providers.map((p) => (
              <div
                key={p.id}
                className={`rounded-lg border p-4 space-y-3 transition-colors ${
                  p.isActive ? "border-primary/40 bg-primary/5" : "border-border"
                }`}
              >
                {editingProviderId === p.id ? (
                  /* ── 编辑模式 ── */
                  <div className="space-y-3">
                    <div className="grid gap-3 sm:grid-cols-2">
                      <div className="space-y-1.5">
                        <label className="text-sm font-medium">显示名称</label>
                        <Input
                          value={p.name}
                          onChange={(e) => handleUpdateProvider(p.id, "name", e.target.value)}
                        />
                      </div>
                      <div className="space-y-1.5">
                        <label className="text-sm font-medium">模型名称</label>
                        <Input
                          value={p.model}
                          onChange={(e) => handleUpdateProvider(p.id, "model", e.target.value)}
                        />
                      </div>
                      <div className="space-y-1.5 sm:col-span-2">
                        <label className="text-sm font-medium">API Base URL</label>
                        <Input
                          value={p.baseUrl}
                          onChange={(e) => handleUpdateProvider(p.id, "baseUrl", e.target.value)}
                        />
                      </div>
                      <div className="space-y-1.5 sm:col-span-2">
                        <label className="text-sm font-medium">API Key</label>
                        <Input
                          type="password"
                          value={p.apiKey}
                          onChange={(e) => handleUpdateProvider(p.id, "apiKey", e.target.value)}
                        />
                      </div>
                    </div>
                    <div className="flex justify-end">
                      <Button size="sm" onClick={() => setEditingProviderId(null)}>
                        <Check className="h-3.5 w-3.5 mr-1" />
                        完成编辑
                      </Button>
                    </div>
                  </div>
                ) : (
                  /* ── 展示模式 ── */
                  <>
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <Zap className={`h-4 w-4 ${p.isActive ? "text-primary" : "text-muted-foreground"}`} />
                        <span className="font-medium text-sm">{p.name}</span>
                        <Badge variant={p.isActive ? "default" : "outline"} className="text-[10px] px-1.5">
                          {PROVIDER_PRESETS[p.provider]?.label ?? p.provider}
                        </Badge>
                        {p.isActive && (
                          <Badge variant="secondary" className="text-[10px] px-1.5 bg-primary/10 text-primary">
                            当前使用
                          </Badge>
                        )}
                      </div>
                      <div className="flex items-center gap-1">
                        {!p.isActive && (
                          <Button
                            size="sm"
                            variant="ghost"
                            className="h-7 px-2 text-xs"
                            onClick={() => handleActivateProvider(p.id)}
                          >
                            <Star className="h-3.5 w-3.5 mr-1" />
                            启用
                          </Button>
                        )}
                        <Button
                          size="sm"
                          variant="ghost"
                          className="h-7 px-2"
                          onClick={() => handleTestConnection(p.id)}
                        >
                          <Zap className="h-3.5 w-3.5 mr-1" />
                          测试
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          className="h-7 px-2"
                          onClick={() => setEditingProviderId(p.id)}
                        >
                          <Pencil className="h-3.5 w-3.5" />
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          className="h-7 px-2"
                          onClick={() => handleDuplicateProvider(p.id)}
                        >
                          <Copy className="h-3.5 w-3.5" />
                        </Button>
                        {!p.isActive && (
                          <Button
                            size="sm"
                            variant="ghost"
                            className="h-7 px-2 text-destructive"
                            onClick={() => handleDeleteProvider(p.id)}
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        )}
                      </div>
                    </div>

                    <div className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs text-muted-foreground">
                      <span className="font-medium text-foreground/70">模型:</span>
                      <span className="font-mono">{p.model}</span>
                      <span className="font-medium text-foreground/70">接口:</span>
                      <span className="font-mono truncate">{p.baseUrl}</span>
                      <span className="font-medium text-foreground/70">密钥:</span>
                      <span className="font-mono">
                        {p.apiKey
                          ? (showKeys[p.id]
                              ? p.apiKey
                              : p.apiKey.slice(0, 6) + "••••••" + p.apiKey.slice(-4))
                          : "(未设置)"}
                        {p.apiKey && (
                          <button
                            className="ml-2 text-muted-foreground hover:text-foreground align-middle"
                            onClick={() => setShowKeys((prev) => ({ ...prev, [p.id]: !prev[p.id] }))}
                          >
                            {showKeys[p.id] ? <EyeOff className="h-3 w-3 inline" /> : <Eye className="h-3 w-3 inline" />}
                          </button>
                        )}
                      </span>
                    </div>

                    {connectionTestResult?.id === p.id && (
                      <div
                        className={`flex items-center gap-1.5 text-xs px-2 py-1 rounded ${
                          connectionTestResult.status === "success"
                            ? "bg-green-50 text-green-700"
                            : "bg-red-50 text-red-700"
                        }`}
                      >
                        {connectionTestResult.status === "error" && <AlertCircle className="h-3.5 w-3.5" />}
                        {connectionTestResult.message}
                      </div>
                    )}
                  </>
                )}
              </div>
            ))
          )}

          {/* Embed Model (全局) */}
          <div className="flex items-center gap-3 pt-2 border-t">
            <label className="text-sm font-medium whitespace-nowrap">Embedding 模型:</label>
            <Input
              className="h-8 max-w-[200px]"
              value={settings.embedModel}
              onChange={(e) => update("embedModel", e.target.value)}
            />
          </div>
        </CardContent>
      </Card>

      {/* 安全设置 */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Globe className="h-5 w-5 text-primary" />
            <CardTitle className="text-base">安全设置</CardTitle>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-1.5">
            <label className="text-sm font-medium">JWT 密钥</label>
            <Input
              type="password"
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
