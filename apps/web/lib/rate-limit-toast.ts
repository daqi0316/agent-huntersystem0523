"use client";

const TOAST_EVENT = "app:rate-limit-toast";

export interface RateLimitInfo {
  retryAfter: number;
  key: string;
  limit: number;
  message: string;
}

export function showRateLimitToast(info: RateLimitInfo): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(
    new CustomEvent<RateLimitInfo>(TOAST_EVENT, { detail: info })
  );
}

export function onRateLimitToast(handler: (info: RateLimitInfo) => void): () => void {
  if (typeof window === "undefined") return () => {};
  const listener = (e: Event) => {
    const detail = (e as CustomEvent<RateLimitInfo>).detail;
    handler(detail);
  };
  window.addEventListener(TOAST_EVENT, listener);
  return () => window.removeEventListener(TOAST_EVENT, listener);
}

export async function fetchWithRateLimit<T = unknown>(
  url: string,
  init?: RequestInit,
): Promise<T> {
  const res = await fetch(url, init);
  if (res.status === 429) {
    let body: { message?: string; retry_after?: number } = {};
    try { body = await res.json(); } catch { /* noop */ }
    const info: RateLimitInfo = {
      retryAfter: parseInt(res.headers.get("Retry-After") || "60", 10),
      key: res.headers.get("X-RateLimit-Key") || "ip",
      limit: parseInt(res.headers.get("X-RateLimit-Limit") || "0", 10),
      message: body.message || "请求过快",
    };
    showRateLimitToast(info);
    throw new Error(`rate_limited:${info.key}:${info.retryAfter}`);
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const j = await res.json();
      detail = j.error || j.detail || detail;
    } catch { /* noop */ }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}
