"use client";

/**
 * useJobDetail — 职位详情 fetch + 缓存 hook（T4）
 *
 * 与 useCandidateDetail 同构：stale-while-revalidate + AbortSignal + 错误分类
 */

import { useEffect, useRef, useState } from "react";
import {
  getCachedJob,
  setCachedJob,
} from "@ai-recruitment/agent-store";
import { api, ApiError } from "./api-client";

export interface JobDetail {
  id: string;
  title: string;
  department: string | null;
  description: string | null;
  requirements: string | null;
  location: string | null;
  salary_range: string | null;
  status: string;
  created_at: string;
  updated_at: string;
}

export type DetailState =
  | { kind: "idle" }
  | { kind: "loading"; fromCache: JobDetail | null }
  | { kind: "ready"; data: JobDetail }
  | { kind: "error"; error: string; code: "not_found" | "forbidden" | "unauthorized" | "server" | "network" | "unknown" };

const FETCH_DEBOUNCE_MS = 5000;

export function useJobDetail(id: string | null) {
  const [state, setState] = useState<DetailState>(() => {
    if (!id) return { kind: "idle" };
    const cached = getCachedJob(id);
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

    const cached = getCachedJob(id);
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
      .get<JobDetail>(`/jobs/${encodeURIComponent(id)}`, { signal: ac.signal })
      .then((data) => {
        setCachedJob(id, data);
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
