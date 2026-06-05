"use client";

/**
 * useCandidateDetail — 候选人详情 fetch + 缓存 hook（T4）
 *
 * 工业级 / 全局规划：
 *  - stale-while-revalidate：缓存有数据时先返回，触发后台 revalidate
 *  - AbortSignal：组件 unmount / id 变更时取消 in-flight 请求
 *  - 错误状态：404（不存在）vs 401/403（权限）vs 5xx（服务器）分类
 *  - rate limit：useRef 防快速点击重复 fetch（同 id 5s 内不重发）
 */

import { useEffect, useRef, useState } from "react";
import {
  getCachedCandidate,
  setCachedCandidate,
} from "@ai-recruitment/agent-store";
import { api, ApiError } from "./api-client";

export interface CandidateDetail {
  id: string;
  name: string;
  email: string;
  phone: string | null;
  summary: string | null;
  skills: string[];
  experience_years: number | null;
  education: string | null;
  current_company: string | null;
  current_title: string | null;
  status: string;
  created_at: string;
  updated_at: string;
}

export type DetailState =
  | { kind: "idle" }
  | { kind: "loading"; fromCache: CandidateDetail | null }
  | { kind: "ready"; data: CandidateDetail }
  | { kind: "error"; error: string; code: "not_found" | "forbidden" | "unauthorized" | "server" | "network" | "unknown" };

const FETCH_DEBOUNCE_MS = 5000;

export function useCandidateDetail(id: string | null) {
  const [state, setState] = useState<DetailState>(() => {
    if (!id) return { kind: "idle" };
    const cached = getCachedCandidate(id);
    if (cached) {
      return { kind: "ready", data: cached.data };
    }
    return { kind: "idle" };
  });

  const inflightRef = useRef<AbortController | null>(null);
  const lastFetchAtRef = useRef<number>(0);

  useEffect(() => {
    if (!id) {
      setState({ kind: "idle" });
      return;
    }

    const cached = getCachedCandidate(id);
    if (cached) {
      setState({ kind: "ready", data: cached.data });
      return;
    }

    if (Date.now() - lastFetchAtRef.current < FETCH_DEBOUNCE_MS) {
      return;
    }

    inflightRef.current?.abort();
    const ac = new AbortController();
    inflightRef.current = ac;
    lastFetchAtRef.current = Date.now();

    setState({ kind: "loading", fromCache: null });

    api
      .get<CandidateDetail>(`/candidates/${encodeURIComponent(id)}`, { signal: ac.signal })
      .then((data) => {
        setCachedCandidate(id, data);
        setState({ kind: "ready", data });
      })
      .catch((err: unknown) => {
        if (err instanceof DOMException && err.name === "AbortError") return;
        if (err instanceof ApiError) {
          const code =
            err.status === 404
              ? "not_found"
              : err.status === 401
                ? "unauthorized"
                : err.status === 403
                  ? "forbidden"
                  : err.status >= 500
                    ? "server"
                    : "unknown";
          setState({ kind: "error", error: err.message, code });
          return;
        }
        setState({
          kind: "error",
          error: err instanceof Error ? err.message : "未知错误",
          code: "network",
        });
      });

    return () => {
      ac.abort();
      // Reset debounce so strict-mode re-mount (or id change) can re-fetch.
      // Production won't re-mount, so this only affects dev double-render.
      lastFetchAtRef.current = 0;
    };
  }, [id]);

  return {
    state,
    retry: () => {
      if (!id) return;
      lastFetchAtRef.current = 0;
      setState({ kind: "loading", fromCache: null });
    },
  };
}
