"use client";

/**
 * 消息列表状态 + localStorage 持久化
 * 提取自 agent/page.tsx（原 line 60-73, 278-304, 296-299）
 */

import { useEffect, useRef, useState, useCallback } from "react";
import { newMessage, type ChatMessage } from "@/types/chat";

const STORAGE_KEY = "agent-chat-history";

function saveMessages(messages: ChatMessage[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(messages));
  } catch {
    /* noop */
  }
}

function backfillIds(raws: Array<Record<string, unknown>>): ChatMessage[] {
  return raws.map((r, i) => {
    const id =
      typeof r.id === "string" && r.id
        ? r.id
        : typeof crypto !== "undefined" && crypto.randomUUID
          ? crypto.randomUUID()
          : `legacy_${Date.now()}_${i}_${Math.random().toString(36).slice(2, 10)}`;
    const createdAt =
      typeof r.createdAt === "string" && r.createdAt
        ? r.createdAt
        : new Date().toISOString();
    return { ...r, id, createdAt } as ChatMessage;
  });
}

function loadMessages(): ChatMessage[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return backfillIds(parsed as Array<Record<string, unknown>>);
  } catch (err) {
    try {
      const { getTelemetryQueue } = require("@ai-recruitment/agent-store");
      getTelemetryQueue().track("sse_parse_error", {
        source: "use-chat-messages",
        success: false,
      });
    } catch {}
    if (typeof console !== "undefined") {
      console.warn("[chat-messages] localStorage parse failed, resetting", err);
    }
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch {}
    return [];
  }
}

export interface UseChatMessagesReturn {
  messages: ChatMessage[];
  setMessages: React.Dispatch<React.SetStateAction<ChatMessage[]>>;
  historyRef: React.MutableRefObject<ChatMessage[]>;
  clearHistory: () => void;
}

export function useChatMessages(): UseChatMessagesReturn {
  const [messages, setMessages] = useState<ChatMessage[]>(loadMessages);
  const historyRef = useRef<ChatMessage[]>(messages);

  useEffect(() => {
    historyRef.current = messages;
  }, [messages]);

  useEffect(() => {
    saveMessages(messages);
  }, [messages]);

  const clearHistory = useCallback(() => {
    setMessages([]);
    localStorage.removeItem(STORAGE_KEY);
  }, []);

  return { messages, setMessages, historyRef, clearHistory };
}
