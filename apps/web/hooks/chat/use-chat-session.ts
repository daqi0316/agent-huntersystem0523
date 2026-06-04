"use client";

/**
 * 会话 ID 管理 — 提取自 agent/page.tsx
 * 单一职责：localStorage 中存/取 web session id（用于服务端 agent 关联）
 */

const SESSION_KEY = "agent-session-id";

export function getSessionId(): string {
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
