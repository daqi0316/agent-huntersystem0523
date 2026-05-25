"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { Send, Bot, User, Loader2, AlertCircle, Sparkles, Briefcase, Users, Calendar, FileText, BarChart3, Library, Trash2 } from "lucide-react";
import { api } from "@/lib/trpc";

// ── Types ──

interface ToolCallInfo {
  name: string;
  args: Record<string, unknown>;
  error?: string | null;
}

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  tool_calls?: ToolCallInfo[];
  error?: boolean;
}

interface AgentChatResponse {
  success: boolean;
  reply: string;
  tool_calls: ToolCallInfo[];
}

const STORAGE_KEY = "agent-chat-history";

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

// ── Main Chat Page ──

export default function AgentChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>(loadMessages);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const historyRef = useRef<ChatMessage[]>(messages);

  useEffect(() => { historyRef.current = messages; }, [messages]);
  useEffect(() => { saveMessages(messages); }, [messages]);

  const clearHistory = () => {
    setMessages([]);
    localStorage.removeItem(STORAGE_KEY);
  };

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  const sendMessage = useCallback(async (text: string) => {
    if (!text.trim() || loading) return;

    const userMsg: ChatMessage = { role: "user", content: text.trim() };
    const currentHistory = historyRef.current;
    setMessages(prev => [...prev, userMsg]);
    setInput("");
    setLoading(true);

    try {
      const data = await api.post<AgentChatResponse>("/agent/chat", {
        message: text.trim(),
        history: currentHistory.map(m => ({ role: m.role, content: m.content })),
      });

      const assistantMsg: ChatMessage = {
        role: "assistant",
        content: data.reply,
        tool_calls: data.tool_calls?.filter(tc => tc.name),
      };
      setMessages(prev => [...prev, assistantMsg]);
    } catch (err: any) {
      setMessages(prev => [
        ...prev,
        { role: "assistant", content: err.message || "请求失败，请稍后重试", error: true },
      ]);
    } finally {
      setLoading(false);
    }
  }, [loading]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
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

      {/* Input */}
      <div className="border-t p-4">
        <div className="flex gap-3 max-w-4xl mx-auto">
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
            disabled={!input.trim() || loading}
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-primary text-primary-foreground disabled:opacity-40 transition-opacity"
          >
            <Send className="h-4 w-4" />
          </button>
        </div>
        <p className="text-center text-[11px] text-muted-foreground mt-2">
          按 Enter 发送 · Shift+Enter 换行
        </p>
      </div>
    </div>
  );
}
