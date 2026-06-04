"use client";

/**
 * 后端会话接入 — 渐进式迁移 localStorage → ConversationService
 *
 * 行为兼容：
 *  - 优先使用后端 session_id（POST /api/v1/conversation/session 创建）
 *  - 后端不可达时降级到 localStorage 的 web_xxx session_id（Phase 0.1 行为）
 *  - 不破坏 useChatMessages 的 localStorage 持久化（消息历史仍由 useChatMessages 管理）
 *
 * 关键设计：模块级 promise dedupe，避免每次 sendMessage 都重新创建 session
 */

import { api } from "@/lib/trpc";
import { getSessionId } from "./use-chat-session";

const BACKEND_SESSION_KEY = "agent-backend-session-id";

interface SessionCreateResponse {
  id: string;
  title?: string;
  message_count?: number;
  created_at?: string;
}

// Module-level dedupe：同一会话生命周期内只创建一次 backend session
let backendSessionPromise: Promise<string | null> | null = null;

/**
 * 确保有后端 session_id 可用。
 * - 命中 localStorage 缓存 → 直接返回
 * - 命中未完成的 promise → 复用
 * - 否则发起 POST /conversation/session，缓存并返回
 * - 任何错误（网络/401/500）→ 返回 null（降级）
 */
export function ensureBackendSession(): Promise<string | null> {
  if (typeof window === "undefined") {
    return Promise.resolve(null);
  }

  // 1. localStorage 缓存
  try {
    const cached = localStorage.getItem(BACKEND_SESSION_KEY);
    if (cached) {
      return Promise.resolve(cached);
    }
  } catch {
    /* SSR / private mode */
  }

  // 2. dedupe 现有 promise
  if (backendSessionPromise) {
    return backendSessionPromise;
  }

  // 3. 创建新 session
  backendSessionPromise = (async () => {
    try {
      const res = await api.post<SessionCreateResponse>(
        "/conversation/session",
        { title: "AI 招聘助手对话" }
      );
      if (res?.id) {
        try {
          localStorage.setItem(BACKEND_SESSION_KEY, res.id);
        } catch {
          /* noop */
        }
        return res.id;
      }
      return null;
    } catch (err) {
      // 静默降级：后端不可达时使用本地 session_id
      // eslint-disable-next-line no-console
      console.warn(
        "[useBackendSession] Failed to create backend session, falling back to local:",
        err instanceof Error ? err.message : err
      );
      backendSessionPromise = null; // 下次重试
      return null;
    }
  })();

  return backendSessionPromise;
}

/**
 * 同步获取 active session id（带本地降级）。
 * 用于不需要 await 的场景。
 */
export function getActiveSessionIdSync(): string {
  try {
    const cached = localStorage.getItem(BACKEND_SESSION_KEY);
    if (cached) return cached;
  } catch {
    /* noop */
  }
  return getSessionId();
}

/**
 * 清理后端 session 缓存（用于"开启新对话"等场景）。
 * 注意：不会删除后端 session，需要的话调用 DELETE /conversation/session/{id}。
 */
export function clearBackendSessionCache(): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.removeItem(BACKEND_SESSION_KEY);
  } catch {
    /* noop */
  }
  backendSessionPromise = null;
}
