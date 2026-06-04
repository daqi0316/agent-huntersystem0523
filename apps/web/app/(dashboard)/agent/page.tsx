"use client";

/**
 * AI 招聘助手主页 — Phase 0.1 重构后版本
 *
 * 拆分说明（原 730 行 → 本文件 ~220 行）：
 *  - types          → /types/chat.ts
 *  - session        → /hooks/chat/use-chat-session.ts
 *  - messages       → /hooks/chat/use-chat-messages.ts
 *  - stream         → /hooks/chat/use-chat-stream.ts
 *  - render helpers → /lib/chat/render-message.tsx
 *  - MemoryPanel    → /components/features/chat/MemoryPanel.tsx
 *  - ChatInput      → /components/features/chat/ChatInput.tsx
 *  - OperationPanel → 维持原 /components/features/chat/OperationPanel.tsx（共用）
 *  - CommandPalette → 维持原 /components/features/chat/CommandPalette.tsx（共用）
 *
 * 三个 panel 全部保留为"内联在 /agent 页面"模式，不并入右上角缩略按钮。
 */

import { useState, useEffect, useCallback } from "react";
import {
  Send,
  Bot,
  User,
  Loader2,
  Sparkles,
  Trash2,
  Brain,
  AlertCircle,
  Check,
  XCircle,
  BarChart3,
  Briefcase,
  Users,
  Calendar,
  FileText,
  Library,
} from "lucide-react";
import { useChatMessages } from "@/hooks/chat/use-chat-messages";
import { useChatStream } from "@/hooks/chat/use-chat-stream";
import { renderRichContent } from "@/lib/chat/render-message";
import { MemoryPanel } from "@/components/features/chat/MemoryPanel";
import { ChatInput } from "@/components/features/chat/ChatInput";
import { OperationPanel } from "@/components/features/chat/OperationPanel";
import { CommandPalette } from "@/components/features/chat/CommandPalette";

// ── Suggested prompts ──

const SUGGESTED_PROMPTS = [
  { label: "看板概览", icon: BarChart3, text: "查看招聘数据看板" },
  { label: "搜索候选人", icon: Users, text: "帮我搜索候选人" },
  { label: "职位列表", icon: Briefcase, text: "查看当前招聘职位" },
  { label: "生成 JD", icon: FileText, text: "帮我生成一个高级前端工程师的 JD" },
  { label: "安排面试", icon: Calendar, text: "安排面试" },
  { label: "知识问答", icon: Library, text: "招聘流程中如何做背景调查？" },
];

// ── Main page ──

export default function AgentChatPage() {
  const { messages, setMessages, historyRef, clearHistory } = useChatMessages();
  const {
    loading,
    approval,
    operationPanel,
    setOperationPanel,
    sendMessage,
    handleApprovalAction,
    handleOperationPanelSuccess,
    messagesEndRef,
    scrollToBottom,
  } = useChatStream({ messages, setMessages, historyRef });

  const [showMemory, setShowMemory] = useState(false);
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  const handleSuggestion = useCallback(
    (text: string) => {
      sendMessage(text, null);
    },
    [sendMessage]
  );

  return (
    <div className="flex h-[calc(100vh-4rem)] flex-col">
      {/* Header */}
      <div className="flex items-center justify-between border-b px-4 py-3">
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10">
            <Bot className="h-4 w-4 text-primary" />
          </div>
          <div>
            <h1 className="text-base font-semibold">AI 招聘助手</h1>
            <p className="text-xs text-muted-foreground">输入自然语言，完成所有招聘操作</p>
          </div>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => setShowMemory(true)}
            className="flex items-center gap-1 rounded-md px-2 py-1 text-xs text-muted-foreground hover:text-primary transition-colors"
            title="查看结构化记忆"
          >
            <Brain className="h-3.5 w-3.5" />
            记忆
          </button>
          {messages.length > 0 && (
            <button
              onClick={clearHistory}
              className="flex items-center gap-1 rounded-md px-2 py-1 text-xs text-muted-foreground hover:text-destructive transition-colors"
              title="清空对话记录"
            >
              <Trash2 className="h-3.5 w-3.5" />
              清空
            </button>
          )}
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
        {messages.length === 0 && !loading && (
          <div className="flex flex-col items-center justify-center h-full text-center space-y-6">
            <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-primary/10">
              <Bot className="h-8 w-8 text-primary" />
            </div>
            <div>
              <h2 className="text-xl font-semibold">有什么我可以帮你的？</h2>
              <p className="text-sm text-muted-foreground mt-1">
                智能招聘助手，支持搜索候选人、初筛简历、生成 JD、安排面试等
              </p>
            </div>
            <div className="grid grid-cols-2 gap-2 max-w-lg">
              {SUGGESTED_PROMPTS.map((item) => {
                const Icon = item.icon;
                return (
                  <button
                    key={item.label}
                    onClick={() => handleSuggestion(item.text)}
                    className="flex items-center gap-2 rounded-lg border p-3 text-sm hover:bg-accent transition-colors text-left"
                  >
                    <Icon className="h-4 w-4 shrink-0 text-primary" />
                    <span>{item.label}</span>
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {messages.map((msg, i) => (
          <div
            key={i}
            className={`flex gap-3 ${msg.role === "user" ? "justify-end" : ""}`}
          >
            {msg.role === "assistant" && (
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary/10 mt-0.5">
                <Bot className="h-4 w-4 text-primary" />
              </div>
            )}

            <div
              className={`max-w-[75%] space-y-1 ${
                msg.role === "user" ? "order-first" : ""
              }`}
            >
              <div
                className={`rounded-2xl px-4 py-2.5 text-sm ${
                  msg.role === "user"
                    ? "bg-primary text-primary-foreground"
                    : msg.error
                    ? "bg-destructive/10 text-destructive"
                    : "bg-muted"
                }`}
              >
                {msg.role === "assistant" ? (
                  renderRichContent(msg.content)
                ) : (
                  msg.content
                )}
              </div>

              {/* Tool call info */}
              {msg.tool_calls && msg.tool_calls.length > 0 && (
                <div className="flex flex-wrap gap-1.5 px-1">
                  {msg.tool_calls.map((tc, j) => (
                    <span
                      key={j}
                      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs ${
                        tc.error
                          ? "bg-destructive/10 text-destructive"
                          : "bg-primary/5 text-primary"
                      }`}
                    >
                      <Sparkles className="h-3 w-3" />
                      {tc.error ? `${tc.name} ❌` : tc.name}
                    </span>
                  ))}
                </div>
              )}

              {/* Agent action bubbles */}
              {msg.agent_actions && msg.agent_actions.length > 0 && (
                <div className="flex flex-wrap gap-1.5 px-1 mt-1">
                  <span className="text-[10px] text-muted-foreground mr-0.5 self-center">
                    编排:
                  </span>
                  {msg.agent_actions.map((ac, j) => (
                    <span
                      key={j}
                      className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs font-medium ${
                        ac.status === "completed"
                          ? "bg-green-50 text-green-700 dark:bg-green-950 dark:text-green-300"
                          : ac.status === "awaiting_approval"
                          ? "bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-300"
                          : ac.status === "failed"
                          ? "bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-300"
                          : "bg-secondary text-secondary-foreground"
                      }`}
                      title={ac.summary}
                    >
                      {ac.agent}
                    </span>
                  ))}
                </div>
              )}
            </div>

            {msg.role === "user" && (
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary mt-0.5">
                <User className="h-4 w-4 text-primary-foreground" />
              </div>
            )}
          </div>
        ))}

        {loading && (
          <div className="flex gap-3">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary/10">
              <Bot className="h-4 w-4 text-primary" />
            </div>
            <div className="rounded-2xl bg-muted px-4 py-3">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Approval Banner */}
      {approval.visible && (
        <div className="border-t bg-amber-50 dark:bg-amber-950/30 px-4 py-3">
          <div className="max-w-4xl mx-auto flex items-center justify-between gap-4">
            <div className="flex items-center gap-3 min-w-0">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-amber-100 dark:bg-amber-900">
                <AlertCircle className="h-4 w-4 text-amber-600 dark:text-amber-400" />
              </div>
              <div className="min-w-0">
                <p className="text-sm font-medium text-amber-800 dark:text-amber-200">
                  待审批
                </p>
                <p className="text-xs text-amber-600 dark:text-amber-400 truncate">
                  {approval.summary}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <button
                onClick={() => handleApprovalAction(false)}
                disabled={approval.loading}
                className="flex items-center gap-1.5 rounded-lg border bg-background px-3 py-1.5 text-xs font-medium hover:bg-accent transition-colors disabled:opacity-50"
              >
                <XCircle className="h-3.5 w-3.5" />
                拒绝
              </button>
              <button
                onClick={() => handleApprovalAction(true)}
                disabled={approval.loading}
                className="flex items-center gap-1.5 rounded-lg bg-amber-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-amber-700 transition-colors disabled:opacity-50"
              >
                {approval.loading ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Check className="h-3.5 w-3.5" />
                )}
                批准
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Input */}
      <ChatInput
        loading={loading}
        onSend={sendMessage}
        onOpenCommandPalette={() => setCommandPaletteOpen(true)}
      />

      {/* Co-existing panels (NOT folded into context-bar) */}
      <MemoryPanel open={showMemory} onClose={() => setShowMemory(false)} />
      <OperationPanel
        open={operationPanel.open}
        onClose={() => setOperationPanel((p) => ({ ...p, open: false }))}
        errorMessage={operationPanel.errorMessage}
        operationType={operationPanel.operationType}
        operationInput={operationPanel.operationInput}
        needsHuman={operationPanel.needsHuman}
        onSuccess={handleOperationPanelSuccess}
      />
      <CommandPalette
        open={commandPaletteOpen}
        onClose={() => setCommandPaletteOpen(false)}
        onSelect={(cmd) => {
          setCommandPaletteOpen(false);
        }}
        triggerInput=""
      />
    </div>
  );
}
