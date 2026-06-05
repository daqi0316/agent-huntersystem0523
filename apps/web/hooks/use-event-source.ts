"use client";

/**
 * useEventSource — EventSource 客户端 hook（T3 增强：Last-Event-ID 持久化 + 重传）
 *
 * 工业级 / 全局规划：
 *  - 记录 lastEventId 到 localStorage：断线重连时把 lastEventId 拼到 URL ?last_event_id=
 *  - 服务端拿到后调 Redis Streams XRANGE 重放离线期间 events
 *  - EventSource 原生支持 MessageEvent.lastEventId，但要在 addEventListener
 *    内 e.lastEventId 取；本 hook 统一处理
 *  - 重连时 URL 变化需要 close + new EventSource 触发（浏览器自动重连不会传 query）
 *
 * 用法：见 use-agent-event-stream.tsx
 */

import { useEffect, useRef, useState } from "react";

const BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
const TOKEN_KEY = "ai-recruitment-token";
const LAST_EVENT_ID_PREFIX = "agent_events:last_event_id:";

function getStoredToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

function loadLastEventId(endpoint: string): string | null {
  if (typeof window === "undefined") return null;
  try {
    return localStorage.getItem(LAST_EVENT_ID_PREFIX + endpoint);
  } catch {
    return null;
  }
}

function saveLastEventId(endpoint: string, id: string): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(LAST_EVENT_ID_PREFIX + endpoint, id);
  } catch {
    /* quota exceeded — ignore */
  }
}

function clearLastEventId(endpoint: string): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.removeItem(LAST_EVENT_ID_PREFIX + endpoint);
  } catch {
    /* ignore */
  }
}

export function useEventSource(endpoint: string | null) {
  const [connected, setConnected] = useState(false);
  const esRef = useRef<EventSource | null>(null);
  const cleanupFnsRef = useRef<Array<() => void>>([]);

  useEffect(() => {
    if (!endpoint) return;

    const token = getStoredToken();
    const lastEventId = loadLastEventId(endpoint);

    const params: string[] = [];
    if (token) params.push(`token=${encodeURIComponent(token)}`);
    if (lastEventId) params.push(`last_event_id=${encodeURIComponent(lastEventId)}`);
    const query = params.length ? `?${params.join("&")}` : "";
    const url = `${BASE_URL}${endpoint}${query}`;

    const es = new EventSource(url);
    esRef.current = es;
    cleanupFnsRef.current = [];

    // 任何 event 携带 id 时记录到 localStorage（T3 重连依据）
    const recordId = (e: MessageEvent) => {
      if (e.lastEventId) {
        saveLastEventId(endpoint, e.lastEventId);
      }
    };

    es.onopen = () => setConnected(true);
    es.onerror = () => {
      setConnected(false);
      // 不在 onerror 清 lastEventId — 服务端可能仍在跑，重连会用
    };

    // EventSource 默认 'message' 事件也带 lastEventId，记录
    es.addEventListener("message", recordId);

    cleanupFnsRef.current.push(() => {
      es.removeEventListener("message", recordId);
    });

    return () => {
      es.close();
      esRef.current = null;
      setConnected(false);
      cleanupFnsRef.current.forEach((fn) => fn());
      cleanupFnsRef.current = [];
    };
  }, [endpoint]);

  function subscribe(event: string, handler: (data: unknown) => void) {
    const es = esRef.current;
    if (!es) {
      const noop = () => {};
      cleanupFnsRef.current.push(noop);
      return noop;
    }
    const wrapped = (e: MessageEvent) => {
      if (e.lastEventId) {
        saveLastEventId(endpoint!, e.lastEventId);
      }
      try {
        handler(JSON.parse(e.data));
      } catch (parseErr) {
        try {
          const { getTelemetryQueue } = require("@ai-recruitment/agent-store");
          getTelemetryQueue().track("sse_parse_error", {
            source: "use-event-source",
            success: false,
          });
        } catch {}
        if (typeof console !== "undefined") {
          console.warn("[SSE] JSON parse failed, falling back to raw data", parseErr);
        }
        handler(e.data);
      }
    };
    es.addEventListener(event, wrapped);
    const unsubscribe = () => es.removeEventListener(event, wrapped);
    cleanupFnsRef.current.push(unsubscribe);
    return unsubscribe;
  }

  function clearReplayCursor() {
    if (endpoint) clearLastEventId(endpoint);
  }

  return { connected, subscribe, clearReplayCursor };
}
