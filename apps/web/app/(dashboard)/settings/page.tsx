"use client";

import { useState, useEffect } from "react";
import { Save, Key, Bot, Bell, Globe, Loader2, CheckCircle2, Eye, EyeOff } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";

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
    </div>
  );
}
