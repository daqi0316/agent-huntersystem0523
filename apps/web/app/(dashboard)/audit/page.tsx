"use client";

import { useState } from "react";
import { Shield, Activity, Brain } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import AuditPanel from "@/components/features/audit/audit-panel";
import AuditLogPanel from "@/components/features/audit/audit-log-panel";
import AiAuditPanel from "@/components/features/audit/ai-audit-panel";

type TabKey = "operation" | "audit" | "ai";

export default function AuditPage() {
  const [tab, setTab] = useState<TabKey>("operation");

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-3xl font-bold">
            <Shield className="h-7 w-7" />
            审计中心
          </h1>
          <p className="text-muted-foreground">
            操作日志 (Agent) · 审计日志 (用户合规) · 系统健康监控
          </p>
        </div>
      </div>

      <div className="flex items-center gap-1 border-b">
        <button
          onClick={() => setTab("operation")}
          className={`flex items-center gap-2 border-b-2 px-4 py-2 text-sm font-medium transition ${
            tab === "operation"
              ? "border-primary text-primary"
              : "border-transparent text-muted-foreground hover:text-foreground"
          }`}
        >
          <Activity className="h-3 w-3" />
          操作日志
        </button>
        <button
          onClick={() => setTab("audit")}
          className={`flex items-center gap-2 border-b-2 px-4 py-2 text-sm font-medium transition ${
            tab === "audit"
              ? "border-primary text-primary"
              : "border-transparent text-muted-foreground hover:text-foreground"
          }`}
        >
          <Shield className="h-3 w-3" />
          审计日志 (P5-1)
        </button>
        <button
          onClick={() => setTab("ai")}
          className={`flex items-center gap-2 border-b-2 px-4 py-2 text-sm font-medium transition ${
            tab === "ai"
              ? "border-primary text-primary"
              : "border-transparent text-muted-foreground hover:text-foreground"
          }`}
        >
          <Brain className="h-3 w-3" />
          AI 决策审计
        </button>
      </div>

      {tab === "operation" ? (
        <Card>
          <CardContent className="pt-6">
            <AuditPanel />
          </CardContent>
        </Card>
      ) : tab === "audit" ? (
        <AuditLogPanel />
      ) : (
        <AiAuditPanel />
      )}
    </div>
  );
}
