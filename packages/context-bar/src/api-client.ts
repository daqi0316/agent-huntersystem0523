/**
 * API Client — 包内 fetch 工具（T4）
 *
 * 工业级 / 全局规划：
 *  - 与 apps/web/lib/trpc.ts 行为一致：自动 unwrap {success: true, data: T}
 *  - 自动从 localStorage 注入 Bearer token
 *  - 抛出 ApiError 含 status 字段（前端 hook 区分 404/403/500）
 *  - 错误响应：后端统一返 {success: false, error: string}，HTTP 状态码正确（404/500）
 *  - 不依赖 apps/web 私有路径（保持包自包含）
 */

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public code?: string
  ) {
    super(message);
    this.name = "ApiError";
  }
}

const API_BASE =
  (typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_URL) ||
  "http://localhost:8000/api/v1";
const TOKEN_KEY = "ai-recruitment-token";

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export interface RequestOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
  /** AbortSignal — 支持 fetch 取消（detail 抽屉关闭时） */
  signal?: AbortSignal;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { body, signal, headers, ...rest } = options;

  const finalHeaders: Record<string, string> = {
    "Content-Type": "application/json",
    ...((headers as Record<string, string> | undefined) ?? {}),
  };
  const token = getToken();
  if (token) {
    finalHeaders["Authorization"] = `Bearer ${token}`;
  }

  const res = await fetch(`${API_BASE}${path}`, {
    ...rest,
    headers: finalHeaders,
    body: body !== undefined ? JSON.stringify(body) : undefined,
    signal,
  });

  let payload: unknown;
  try {
    payload = await res.json();
  } catch {
    if (!res.ok) {
      throw new ApiError(`请求失败 (${res.status})`, res.status);
    }
    return undefined as T;
  }

  if (payload && typeof payload === "object" && "success" in payload) {
    const p = payload as Record<string, unknown>;
    if (p.success === false) {
      throw new ApiError(
        (p.error as string) || `请求失败 (${res.status})`,
        res.status,
        p.code as string | undefined
      );
    }
  }

  if (!res.ok) {
    const detail =
      payload && typeof payload === "object"
        ? (payload as Record<string, unknown>).detail
        : undefined;
    throw new ApiError(
      (detail as string) || `请求失败 (${res.status})`,
      res.status
    );
  }

  if (
    payload &&
    typeof payload === "object" &&
    "success" in payload &&
    "data" in payload
  ) {
    const p = payload as Record<string, unknown>;
    const data = p.data;
    if (data !== undefined && !Array.isArray(data)) {
      return data as T;
    }
  }

  return payload as T;
}

export const api = {
  get: <T>(path: string, options?: RequestOptions) =>
    request<T>(path, { ...options, method: "GET" }),
  post: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>(path, { ...options, method: "POST", body }),
  put: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>(path, { ...options, method: "PUT", body }),
  delete: <T>(path: string, options?: RequestOptions) =>
    request<T>(path, { ...options, method: "DELETE" }),
};
