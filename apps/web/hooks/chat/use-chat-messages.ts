"use client";

/**
 * 消息列表状态 + localStorage 持久化
 * 提取自 agent/page.tsx（原 line 60-73, 278-304, 296-299）
 */

import { useEffect, useRef, useState, useCallback } from "react";
import type { ChatMessage } from "@/types/chat";

const STORAGE_KEY = "agent-chat-history";

function saveMessages(messages: ChatMessage[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(messages));
  } catch {
    /* noop */
  }
}

function loadMessages(): ChatMessage[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
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
