"use client";

/**
 * 顶部 Header — 接入 context-bar 包
 *
 * 工业级 / 全局规划：原 pending-approval-section 调后端 /human-loop/approve
 * 与 /human-loop/resume 的业务逻辑保留在 apps/web 端（不污染包内 UI 纯度）。
 * 本文件作为 host 注入层，把 api.post 包装成 ContextBar.onApprovalApprove/
 * onApprovalReject props。
 */

import { Bell, Moon, Sun, LogOut } from "lucide-react";
import { useTheme } from "next-themes";
import { useCallback, useEffect, useState } from "react";
import { ContextBar, useAgentStore, newMessage } from "@ai-recruitment/context-bar";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth-context";
import { api } from "@/lib/trpc";

export function Header() {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  const { user, logout } = useAuth();

  useEffect(() => setMounted(true), []);

  const handleApprovalApprove = useCallback(async (approvalId: string) => {
    const approveResult = await api.post<{ success: boolean; status: string }>(
      "/human-loop/approve",
      {
        action_type: "schedule_interview",
        approval_id: approvalId,
        approved: true,
      }
    );
    if (!approveResult.success) {
      throw new Error("审批操作失败");
    }
    const resume = await api.post<{
      success: boolean;
      data?: { status: string; summary: string };
    }>("/human-loop/resume", { approval_id: approvalId });
    if (resume.success && resume.data) {
      useAgentStore.getState().addMessage(
        newMessage("assistant", `✅ 审批通过，编排继续执行。\n\n${resume.data.summary}`)
      );
    }
  }, []);

  const handleApprovalReject = useCallback(async (approvalId: string) => {
    await api.post("/human-loop/approve", {
      action_type: "schedule_interview",
      approval_id: approvalId,
      approved: false,
    });
  }, []);

  return (
    <header className="flex h-14 items-center justify-between border-b bg-card px-6">
      <div className="flex items-center gap-2">
        {user && (
          <span className="text-sm text-muted-foreground">
            {user.name}
            <span className="mx-1 text-xs">|</span>
            <span className="text-xs capitalize">{user.role}</span>
          </span>
        )}
      </div>
      <div className="flex items-center gap-2">
        <ContextBar
          onApprovalApprove={handleApprovalApprove}
          onApprovalReject={handleApprovalReject}
        />
        <Button variant="ghost" size="icon">
          <Bell className="h-4 w-4" />
        </Button>
        {mounted && (
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          >
            {theme === "dark" ? (
              <Sun className="h-4 w-4" />
            ) : (
              <Moon className="h-4 w-4" />
            )}
          </Button>
        )}
        <Button variant="ghost" size="icon" onClick={logout} title="退出登录">
          <LogOut className="h-4 w-4" />
        </Button>
      </div>
    </header>
  );
}
