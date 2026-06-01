"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { Send, Bot, User, Loader2, AlertCircle, Sparkles, Briefcase, Users, Calendar, FileText, BarChart3, Library, Trash2, Brain, X, Check, XCircle, RefreshCw, Paperclip } from "lucide-react";
import { api } from "@/lib/trpc";
import { ResumeUpload } from "@/components/features/chat/ResumeUpload";
import { OperationPanel } from "@/components/features/chat/OperationPanel";
import { CommandPalette } from "@/components/features/chat/CommandPalette";
import type { UploadedFile } from "@/hooks/useResumeUpload";

// ── Types ──

interface ToolCallInfo {
  name: string;
  args: Record<string, unknown>;
  error?: string | null;
  needs_human?: boolean;
}

interface AgentActionInfo {
  agent: string;
  status: string;
  summary: string;
  approval_id?: string;
}

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  tool_calls?: ToolCallInfo[];
  agent_actions?: AgentActionInfo[];
  error?: boolean;
  model?: string;
}

interface AgentChatResponse {
  success: boolean;
  reply: string;
  tool_calls: ToolCallInfo[];
  agent_actions?: AgentActionInfo[];
  model?: string;
}

const STORAGE_KEY = "agent-chat-history";
const SESSION_KEY = "agent-session-id";

function getSessionId(): string {
  try {
    let sid = localStorage.getItem(SESSION_KEY);
    if (!sid) {
      sid = `web_${crypto.randomUUID().replace(/-/g, "").slice(0, 12)}`;
      localStorage.setItem(SESSION_KEY, sid);
    }
    return sid;
  } catch {
    return `web_${Math.random().toString(36).slice(2, 14)}`;
  }
}

function saveMessages(messages: ChatMessage[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(messages));
  } catch { /* noop */ }
}

function loadMessages(): ChatMessage[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

// ── Suggested prompts ──

const SUGGESTED_PROMPTS = [
  { label: "看板概览", icon: BarChart3, text: "查看招聘数据看板" },
  { label: "搜索候选人", icon: Users, text: "帮我搜索候选人" },
  { label: "职位列表", icon: Briefcase, text: "查看当前招聘职位" },
  { label: "生成 JD", icon: FileText, text: "帮我生成一个高级前端工程师的 JD" },
  { label: "安排面试", icon: Calendar, text: "安排面试" },
  { label: "知识问答", icon: Library, text: "招聘流程中如何做背景调查？" },
];

// ── Helper: render rich content ──

function renderRichContent(content: string): React.ReactNode {
  // Try to detect and format JSON blocks
  const jsonBlocks: string[] = [];
  const cleaned = content.replace(/```(?:json)?\s*([\s\S]*?)```/g, (_, json) => {
    jsonBlocks.push(json.trim());
    return `__JSON_BLOCK_${jsonBlocks.length - 1}__`;
  });

  const parts = cleaned.split(/(__JSON_BLOCK_\d+__)/);

  return parts.map((part, i) => {
    const match = part.match(/__JSON_BLOCK_(\d+)__/);
    if (match) {
      const idx = parseInt(match[1]);
      try {
        const data = JSON.parse(jsonBlocks[idx]);
        return <JsonPreview key={i} data={data} />;
      } catch {
        return <p key={i} className="whitespace-pre-wrap">{jsonBlocks[idx]}</p>;
      }
    }
    return <p key={i} className="whitespace-pre-wrap leading-relaxed">{part}</p>;
  });
}

function JsonPreview({ data }: { data: unknown }) {
  if (Array.isArray(data) && data.length > 0 && data[0].name) {
    // Candidate list
    return (
      <div className="grid gap-2 my-2">
        {data.slice(0, 5).map((item: any, i: number) => (
          <div key={i} className="flex items-center gap-3 rounded-lg border p-3 bg-card">
            <div className="flex h-9 w-9 items-center justify-center rounded-full bg-primary/10 text-primary text-sm font-medium">
              {item.name?.[0] || "?"}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium truncate">{item.name}</p>
              <p className="text-xs text-muted-foreground truncate">
                {item.current_title || "—"} · {item.experience_years ? `${item.experience_years}年经验` : ""}
                {item.current_company ? ` · ${item.current_company}` : ""}
              </p>
            </div>
            {item.skills?.length > 0 && (
              <div className="hidden sm:flex gap-1 flex-wrap">
                {item.skills.slice(0, 3).map((s: string, j: number) => (
                  <span key={j} className="rounded-md bg-secondary px-2 py-0.5 text-xs">{s}</span>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    );
  }

  if (data && typeof data === "object" && "overall_score" in data) {
    // Screening result
    const d = data as Record<string, any>;
    const score = d.overall_score as number;
    let color = "text-red-500";
    if (score >= 80) color = "text-green-500";
    else if (score >= 60) color = "text-amber-500";
    return (
      <div className="rounded-lg border p-4 my-2 bg-card space-y-2">
        <div className="flex items-center gap-3">
          <span className="text-2xl font-bold">{score}</span>
          <span className="text-sm text-muted-foreground">匹配度评分</span>
        </div>
        {d.summary && <p className="text-sm text-muted-foreground">{d.summary}</p>}
      </div>
    );
  }

  if (data && typeof data === "object" && "jd_content" in data) {
    const d = data as Record<string, string>;
    return (
      <div className="rounded-lg border p-4 my-2 bg-card">
        <h4 className="font-medium text-sm mb-2">{d.title}</h4>
        <div className="text-sm text-muted-foreground whitespace-pre-wrap line-clamp-6">{d.jd_content}</div>
      </div>
    );
  }

  // Default: show nothing special, the LLM summary handles it
  return null;
}

// ── Memory Panel ──

interface MemoryFact {
  id: string;
  fact_type: string;
  verb: string;
  object_value: Record<string, unknown> | null;
  created_at: string;
}

const FACT_TYPE_LABELS: Record<string, string> = {
  candidate_action: "候选人操作",
  decision: "决策",
  preference: "偏好设置",
  workflow_state: "流程状态",
  agent_action: "系统操作",
};

function MemoryPanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [facts, setFacts] = useState<MemoryFact[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    api.post<{ success: boolean; facts: MemoryFact[] }>("/memory/facts", { user_id: "default", limit: 50 })
      .then(data => setFacts(data.facts || []))
      .catch(() => setFacts([]))
      .finally(() => setLoading(false));
  }, [open]);

  const grouped = facts.reduce<Record<string, MemoryFact[]>>((acc, f) => {
    const key = f.fact_type || "other";
    if (!acc[key]) acc[key] = [];
    acc[key].push(f);
    return acc;
  }, {});

  const timeAgo = (iso: string) => {
    const diff = Date.now() - new Date(iso).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return "刚刚";
    if (mins < 60) return `${mins}分钟前`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}小时前`;
    return `${Math.floor(hrs / 24)}天前`;
  };

  return (
    <div className={`fixed inset-y-0 right-0 z-50 w-80 bg-background border-l shadow-xl transform transition-transform ${open ? "translate-x-0" : "translate-x-full"}`}>
      <div className="flex items-center justify-between border-b px-4 py-3">
        <div className="flex items-center gap-2">
          <Brain className="h-4 w-4 text-primary" />
          <h2 className="text-sm font-semibold">结构化记忆</h2>
        </div>
        <button onClick={onClose} className="rounded-md p-1 hover:bg-accent transition-colors">
          <X className="h-4 w-4" />
        </button>
      </div>
      <div className="overflow-y-auto h-[calc(100vh-4rem)] p-4 space-y-4">
        {loading && (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        )}
        {!loading && facts.length === 0 && (
          <p className="text-sm text-muted-foreground text-center py-8">暂无记忆</p>
        )}
        {!loading && Object.entries(grouped).map(([type, items]) => (
          <div key={type}>
            <h3 className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-2">
              {FACT_TYPE_LABELS[type] || type}
            </h3>
            <div className="space-y-2">
              {items.map(f => (
                <div key={f.id} className="rounded-lg border p-3 text-xs space-y-1">
                  <p className="font-medium text-foreground">{f.verb}</p>
                  {f.object_value && Object.entries(f.object_value).slice(0, 3).map(([k, v]) => (
                    <p key={k} className="text-muted-foreground">
                      {k}: {typeof v === "object" ? JSON.stringify(v) : String(v)}
                    </p>
                  ))}
                  <p className="text-[10px] text-muted-foreground/60">{timeAgo(f.created_at)}</p>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Main Chat Page ──

interface ApprovalState {
  visible: boolean;
  approval_id: string;
  summary: string;
  loading: boolean;
}

export default function AgentChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>(loadMessages);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [showMemory, setShowMemory] = useState(false);
  const [approval, setApproval] = useState<ApprovalState>({ visible: false, approval_id: "", summary: "", loading: false });
  const [attachment, setAttachment] = useState<UploadedFile | null>(null);
  const [showUpload, setShowUpload] = useState(false);
  const [operationPanel, setOperationPanel] = useState<{
    open: boolean;
    errorMessage?: string;
    operationType?: string;
    operationInput?: Record<string, unknown>;
    needsHuman?: boolean;
  }>({ open: false });
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false);
  const [lastToolCalls, setLastToolCalls] = useState<ToolCallInfo[]>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const historyRef = useRef<ChatMessage[]>(messages);

  useEffect(() => { historyRef.current = messages; }, [messages]);
  useEffect(() => { saveMessages(messages); }, [messages]);

  const clearHistory = () => {
    setMessages([]);
    localStorage.removeItem(STORAGE_KEY);
  };

  const handleApprovalAction = useCallback(async (approve: boolean) => {
    const { approval_id } = approval;
    if (!approval_id) return;
    setApproval(prev => ({ ...prev, loading: true }));

    try {
      await api.post("/human-loop/approve", {
        action_type: "schedule_interview",
        approval_id,
        approved: approve,
      });

      if (!approve) {
        setApproval({ visible: false, approval_id: "", summary: "", loading: false });
        return;
      }

      // resume orchestrator
      const resumeResult = await api.post<{ success: boolean; data: { status: string; summary: string; outputs: any[] } }>("/human-loop/resume", {
        approval_id,
      });

      if (resumeResult.success) {
        const { data } = resumeResult;
        setMessages(prev => [...prev, {
          role: "assistant",
          content: `✅ 审批通过，编排继续执行。\n\n${data.summary}`,
          agent_actions: (data.outputs || []).map((o: any) => ({
            agent: o.agent || "",
            status: o.status || "",
            summary: o.summary || "",
          })),
          model: `orchestrator/${data.status}`,
        }]);
      }
    } catch (err: any) {
      setMessages(prev => [...prev, {
        role: "assistant",
        content: err.message || "审批处理失败",
        error: true,
      }]);
    } finally {
      setApproval({ visible: false, approval_id: "", summary: "", loading: false });
    }
  }, [approval]);

  const handleApprovalAutoResume = useCallback((actions: AgentActionInfo[], userText: string) => {
    const awaitingAction = actions.find(a => a.status === "awaiting_approval");
    if (awaitingAction && awaitingAction.approval_id) {
      setApproval({
        visible: true,
        approval_id: awaitingAction.approval_id,
        summary: awaitingAction.summary || "待审批",
        loading: false,
      });
    }
  }, []);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  const handleOperationPanelSuccess = useCallback((summary: string) => {
    setMessages(prev => [...prev, {
      role: "assistant",
      content: `✅ ${summary}`,
    }]);
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  const sendMessage = useCallback(async (text: string) => {
    if (!text.trim() && !attachment) return;

    const userMsg: ChatMessage = { role: "user", content: text.trim() || (attachment ? `上传简历: ${attachment.filename}` : "") };
    const currentHistory = historyRef.current;
    setMessages(prev => [...prev, userMsg]);
    setInput("");
    setLoading(true);

    try {
      const data = await api.post<AgentChatResponse>("/agent/chat", {
        message: text.trim() || (attachment ? `解析这份简历: ${attachment.filename}` : ""),
        history: currentHistory.map(m => ({ role: m.role, content: m.content })),
        session_id: getSessionId(),
        attachment: attachment ? { file_url: attachment.file_url, file_type: attachment.file_type, filename: attachment.filename } : undefined,
      });

      const assistantMsg: ChatMessage = {
        role: "assistant",
        content: data.reply,
        tool_calls: data.tool_calls?.filter(tc => tc.name),
        agent_actions: data.agent_actions,
        model: data.model,
      };
      setMessages(prev => [...prev, assistantMsg]);
      setLastToolCalls(data.tool_calls?.filter(tc => tc.name) || []);
      setAttachment(null);
      setShowUpload(false);

      if (data.model === "orchestrator/awaiting_approval" && data.agent_actions) {
        handleApprovalAutoResume(data.agent_actions, text);
      }

      // Auto-open OperationPanel if any tool_call returned an error
      const toolCallsWithError = data.tool_calls?.filter(tc => tc.name && tc.error);
      if (toolCallsWithError?.length) {
        const failedTool = toolCallsWithError[0];
        setOperationPanel({
          open: true,
          errorMessage: failedTool.error || "工具执行失败",
          operationType: failedTool.name,
          operationInput: failedTool.args,
          needsHuman: failedTool.needs_human ?? false,
        });
      }
    } catch (err: any) {
      const errorMsg = err.message || "请求失败，请稍后重试";
      setMessages(prev => [
        ...prev,
        { role: "assistant", content: errorMsg, error: true },
      ]);
      const failedTool = lastToolCalls.find(tc => tc.error) || lastToolCalls[0];
      let opType: string | undefined;
      let opInput: Record<string, unknown> | undefined;
      if (failedTool) {
        opType = failedTool.name;
        opInput = failedTool.args;
      }
      setOperationPanel({ open: true, errorMessage: errorMsg, operationType: opType, operationInput: opInput });
    } finally {
      setLoading(false);
    }
  }, [loading, attachment]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "/" && input === "") {
      e.preventDefault();
      setCommandPaletteOpen(true);
      return;
    }
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage(input);
    }
  };

  const handleSuggestion = (text: string) => {
    sendMessage(text);
  };

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
          <div key={i} className={`flex gap-3 ${msg.role === "user" ? "justify-end" : ""}`}>
            {msg.role === "assistant" && (
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary/10 mt-0.5">
                <Bot className="h-4 w-4 text-primary" />
              </div>
            )}

            <div className={`max-w-[75%] space-y-1 ${msg.role === "user" ? "order-first" : ""}`}>
              <div
                className={`rounded-2xl px-4 py-2.5 text-sm ${
                  msg.role === "user"
                    ? "bg-primary text-primary-foreground"
                    : msg.error
                    ? "bg-destructive/10 text-destructive"
                    : "bg-muted"
                }`}
              >
                {msg.role === "assistant" ? renderRichContent(msg.content) : msg.content}
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
                  <span className="text-[10px] text-muted-foreground mr-0.5 self-center">编排:</span>
                  {msg.agent_actions.map((ac, j) => (
                    <span
                      key={j}
                      className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs font-medium ${
                        ac.status === "completed" ? "bg-green-50 text-green-700 dark:bg-green-950 dark:text-green-300" :
                        ac.status === "awaiting_approval" ? "bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-300" :
                        ac.status === "failed" ? "bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-300" :
                        "bg-secondary text-secondary-foreground"
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

      {/* Approval Popup Banner */}
      {approval.visible && (
        <div className="border-t bg-amber-50 dark:bg-amber-950/30 px-4 py-3">
          <div className="max-w-4xl mx-auto flex items-center justify-between gap-4">
            <div className="flex items-center gap-3 min-w-0">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-amber-100 dark:bg-amber-900">
                <AlertCircle className="h-4 w-4 text-amber-600 dark:text-amber-400" />
              </div>
              <div className="min-w-0">
                <p className="text-sm font-medium text-amber-800 dark:text-amber-200">待审批</p>
                <p className="text-xs text-amber-600 dark:text-amber-400 truncate">{approval.summary}</p>
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
      <div className="border-t p-4">
        {showUpload && (
          <div className="max-w-4xl mx-auto mb-3">
            <ResumeUpload
              onUploadSuccess={(file) => {
                setAttachment(file);
                setShowUpload(false);
              }}
              onCancel={() => setShowUpload(false)}
            />
          </div>
        )}
        {attachment && !showUpload && (
          <div className="flex items-center gap-2 max-w-4xl mx-auto mb-3">
            <div className="flex items-center gap-2 rounded-lg border bg-card px-3 py-1.5 text-sm">
              <FileText className="h-4 w-4 text-primary" />
              <span className="truncate max-w-[200px]">{attachment.filename}</span>
              <span className="text-xs text-muted-foreground">
                ({(attachment.file_size / 1024).toFixed(0)} KB)
              </span>
            </div>
            <button
              onClick={() => { setAttachment(null); setShowUpload(false); }}
              className="rounded-md p-1 hover:bg-accent transition-colors"
            >
              <X className="h-4 w-4 text-muted-foreground" />
            </button>
          </div>
        )}
        <div className="flex gap-3 max-w-4xl mx-auto">
          <button
            onClick={() => setShowUpload(v => !v)}
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border bg-background hover:bg-accent transition-colors"
            title="上传简历"
          >
            <Paperclip className="h-4 w-4 text-muted-foreground" />
          </button>
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="输入你的需求，例如「搜索会 React 的候选人」"
            rows={1}
            className="flex-1 resize-none rounded-xl border bg-background px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary/20 min-h-[44px] max-h-32"
          />
          <button
            onClick={() => sendMessage(input)}
            disabled={(!input.trim() && !attachment) || loading}
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-primary text-primary-foreground disabled:opacity-40 transition-opacity"
          >
            <Send className="h-4 w-4" />
          </button>
        </div>
        <p className="text-center text-[11px] text-muted-foreground mt-2">
          按 Enter 发送 · Shift+Enter 换行
        </p>
      </div>

      <MemoryPanel open={showMemory} onClose={() => setShowMemory(false)} />
      <OperationPanel
        open={operationPanel.open}
        onClose={() => setOperationPanel(p => ({ ...p, open: false }))}
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
          setInput(cmd + " ");
          setCommandPaletteOpen(false);
          inputRef.current?.focus();
        }}
        triggerInput={input}
      />
    </div>
  );
}
