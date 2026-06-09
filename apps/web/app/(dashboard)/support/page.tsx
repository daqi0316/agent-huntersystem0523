"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

type Ticket = {
  id: string;
  subject: string;
  status: string;
  priority: string;
  category: string | null;
  created_at: string;
  updated_at: string;
};

type Message = {
  id: string;
  body: string;
  sender_type: string;
  created_at: string;
};

const STATUS_LABEL: Record<string, string> = {
  open: "待处理",
  pending_customer: "待客户回复",
  pending_internal: "待内部处理",
  resolved: "已解决",
  closed: "已关闭",
};

const PRIORITY_LABEL: Record<string, string> = {
  low: "低",
  normal: "普通",
  high: "高",
  urgent: "紧急",
};

export default function SupportPage() {
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [loading, setLoading] = useState(false);
  const [showNew, setShowNew] = useState(false);
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [priority, setPriority] = useState("normal");
  const [selected, setSelected] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [reply, setReply] = useState("");

  async function loadTickets() {
    setLoading(true);
    try {
      const r = await api.get<{ data: Ticket[] }>("/support/tickets");
      setTickets(r.data || []);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadTickets();
  }, []);

  async function createTicket() {
    if (!subject.trim() || !body.trim()) return;
    const r = await api.post<{ data: Ticket }>("/support/tickets", {
      subject, body, priority,
    });
    if (r.data) {
      setTickets([r.data, ...tickets]);
      setSubject(""); setBody(""); setPriority("normal");
      setShowNew(false);
    }
  }

  async function openTicket(id: string) {
    setSelected(id);
    const r = await api.get<{ data: { messages: Message[] } }>(`/support/tickets/${id}`);
    setMessages(r.data?.messages || []);
  }

  async function sendReply() {
    if (!selected || !reply.trim()) return;
    const r = await api.post<{ data: Message }>(`/support/tickets/${selected}/messages`, {
      body: reply,
    });
    if (r.data) {
      setMessages([...messages, r.data]);
      setReply("");
    }
  }

  async function closeTicket() {
    if (!selected) return;
    await api.post(`/support/tickets/${selected}/close`, {});
    loadTickets();
    setSelected(null);
  }

  return (
    <div className="container mx-auto p-6">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">客户支持</h1>
        <button
          onClick={() => setShowNew(!showNew)}
          className="px-4 py-2 bg-blue-600 text-white rounded"
        >
          {showNew ? "取消" : "提交工单"}
        </button>
      </div>

      {showNew && (
        <div className="border rounded p-4 mb-6 bg-gray-50">
          <input
            className="w-full p-2 border rounded mb-2"
            placeholder="主题"
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
          />
          <textarea
            className="w-full p-2 border rounded mb-2"
            placeholder="详细描述"
            rows={4}
            value={body}
            onChange={(e) => setBody(e.target.value)}
          />
          <select
            className="p-2 border rounded mb-2"
            value={priority}
            onChange={(e) => setPriority(e.target.value)}
          >
            <option value="low">低</option>
            <option value="normal">普通</option>
            <option value="high">高</option>
            <option value="urgent">紧急</option>
          </select>
          <button
            onClick={createTicket}
            className="px-4 py-2 bg-blue-600 text-white rounded"
          >
            提交
          </button>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <h2 className="text-lg font-semibold mb-2">我的工单</h2>
          {loading ? <p>加载中...</p> : tickets.length === 0 ? (
            <p className="text-gray-500">还没有工单</p>
          ) : (
            <ul className="space-y-2">
              {tickets.map((t) => (
                <li
                  key={t.id}
                  onClick={() => openTicket(t.id)}
                  className={`p-3 border rounded cursor-pointer hover:bg-gray-50 ${
                    selected === t.id ? "border-blue-500" : ""
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-medium">{t.subject}</span>
                    <span className="text-xs px-2 py-1 rounded bg-gray-200">
                      {STATUS_LABEL[t.status] || t.status}
                    </span>
                  </div>
                  <div className="text-sm text-gray-500 mt-1">
                    优先级: {PRIORITY_LABEL[t.priority] || t.priority} ·{" "}
                    {new Date(t.created_at).toLocaleString("zh-CN")}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div>
          {selected ? (
            <div>
              <div className="flex items-center justify-between mb-2">
                <h2 className="text-lg font-semibold">对话</h2>
                <button
                  onClick={closeTicket}
                  className="text-sm px-3 py-1 border rounded"
                >
                  关闭工单
                </button>
              </div>
              <div className="space-y-2 mb-4 max-h-96 overflow-y-auto">
                {messages.map((m) => (
                  <div
                    key={m.id}
                    className={`p-2 rounded ${
                      m.sender_type === "customer"
                        ? "bg-blue-50 ml-8"
                        : "bg-gray-50 mr-8"
                    }`}
                  >
                    <div className="text-xs text-gray-500 mb-1">
                      {m.sender_type === "customer" ? "你" : "客服"} ·{" "}
                      {new Date(m.created_at).toLocaleString("zh-CN")}
                    </div>
                    <div className="whitespace-pre-wrap">{m.body}</div>
                  </div>
                ))}
              </div>
              <textarea
                className="w-full p-2 border rounded mb-2"
                placeholder="回复..."
                rows={3}
                value={reply}
                onChange={(e) => setReply(e.target.value)}
              />
              <button
                onClick={sendReply}
                className="px-4 py-2 bg-blue-600 text-white rounded"
              >
                发送
              </button>
            </div>
          ) : (
            <p className="text-gray-500">选择工单查看对话</p>
          )}
        </div>
      </div>
    </div>
  );
}
