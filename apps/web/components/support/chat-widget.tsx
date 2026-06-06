"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

type Ticket = {
  id: string;
  subject: string;
  status: string;
};

const STATUS_COLORS: Record<string, string> = {
  open: "bg-yellow-100 text-yellow-800",
  pending_customer: "bg-blue-100 text-blue-800",
  pending_internal: "bg-purple-100 text-purple-800",
  resolved: "bg-green-100 text-green-800",
  closed: "bg-gray-100 text-gray-800",
};

export default function ChatWidget() {
  const [open, setOpen] = useState(false);
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [created, setCreated] = useState<string | null>(null);
  const [reply, setReply] = useState("");
  const [activeTicket, setActiveTicket] = useState<string | null>(null);
  const [messages, setMessages] = useState<any[]>([]);

  async function loadTickets() {
    const r = await api.get<{ data: Ticket[] }>("/support/tickets");
    setTickets(r.data || []);
  }

  useEffect(() => {
    if (open && tickets.length === 0) loadTickets();
  }, [open]);

  async function createTicket() {
    if (!subject.trim() || !body.trim()) return;
    const r = await api.post<{ data: Ticket }>("/support/tickets", {
      subject, body, priority: "normal",
    });
    if (r.data) {
      setCreated(r.data.id);
      setSubject(""); setBody("");
      loadTickets();
    }
  }

  async function openTicket(id: string) {
    setActiveTicket(id);
    const r = await api.get<{ data: { messages: any[] } }>(`/support/tickets/${id}`);
    setMessages(r.data?.messages || []);
  }

  async function sendReply() {
    if (!activeTicket || !reply.trim()) return;
    const r = await api.post<{ data: any }>(`/support/tickets/${activeTicket}/messages`, {
      body: reply,
    });
    if (r.data) {
      setMessages([...messages, r.data]);
      setReply("");
    }
  }

  return (
    <>
      <button
        onClick={() => setOpen(!open)}
        className="fixed bottom-6 right-6 w-14 h-14 bg-blue-600 text-white rounded-full shadow-lg hover:bg-blue-700 flex items-center justify-center text-2xl z-50"
        aria-label="联系客服"
      >
        {open ? "×" : "💬"}
      </button>

      {open && (
        <div className="fixed bottom-24 right-6 w-96 max-w-[calc(100vw-3rem)] bg-white rounded-lg shadow-2xl border z-50 flex flex-col" style={{ maxHeight: "70vh" }}>
          <div className="p-4 border-b bg-blue-600 text-white rounded-t-lg">
            <div className="font-semibold">需要帮助?</div>
            <div className="text-xs opacity-90">我们 1 个工作日内回复</div>
          </div>

          {!activeTicket ? (
            <div className="flex-1 overflow-y-auto p-3">
              {created && (
                <div className="mb-3 p-2 bg-green-50 text-green-800 text-sm rounded">
                  ✅ 工单已创建, 客服会尽快回复
                </div>
              )}

              <details className="mb-3" open>
                <summary className="cursor-pointer text-sm font-medium text-blue-600 mb-2">
                  + 提交新工单
                </summary>
                <input
                  className="w-full p-2 border rounded mb-2 text-sm"
                  placeholder="主题"
                  value={subject}
                  onChange={(e) => setSubject(e.target.value)}
                />
                <textarea
                  className="w-full p-2 border rounded mb-2 text-sm"
                  placeholder="详细描述..."
                  rows={3}
                  value={body}
                  onChange={(e) => setBody(e.target.value)}
                />
                <button
                  onClick={createTicket}
                  className="w-full py-2 bg-blue-600 text-white rounded text-sm"
                >
                  提交
                </button>
              </details>

              {tickets.length > 0 && (
                <div>
                  <div className="text-sm font-medium mb-2">我的工单</div>
                  <div className="space-y-1">
                    {tickets.map((t) => (
                      <button
                        key={t.id}
                        onClick={() => openTicket(t.id)}
                        className="w-full text-left p-2 border rounded text-sm hover:bg-gray-50"
                      >
                        <div className="flex items-center justify-between">
                          <span className="truncate">{t.subject}</span>
                          <span className={`text-xs px-1.5 py-0.5 rounded ${STATUS_COLORS[t.status] || ""}`}>
                            {t.status}
                          </span>
                        </div>
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="flex-1 flex flex-col">
              <button
                onClick={() => setActiveTicket(null)}
                className="text-sm text-blue-600 p-2 text-left border-b"
              >
                ← 返回工单列表
              </button>
              <div className="flex-1 overflow-y-auto p-3 space-y-2">
                {messages.map((m) => (
                  <div
                    key={m.id}
                    className={`p-2 rounded text-sm ${
                      m.sender_type === "customer" ? "bg-blue-50 ml-6" : "bg-gray-50 mr-6"
                    }`}
                  >
                    <div className="text-xs text-gray-500 mb-1">
                      {m.sender_type === "customer" ? "你" : "客服"} · {new Date(m.created_at).toLocaleString("zh-CN")}
                    </div>
                    {m.body}
                  </div>
                ))}
              </div>
              <div className="p-2 border-t flex gap-1">
                <input
                  className="flex-1 p-2 border rounded text-sm"
                  placeholder="回复..."
                  value={reply}
                  onChange={(e) => setReply(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && sendReply()}
                />
                <button onClick={sendReply} className="px-3 py-2 bg-blue-600 text-white rounded text-sm">
                  发送
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </>
  );
}
