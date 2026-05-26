/**
 * API client wrapper for FastAPI backend.
 * Automatically includes auth token from localStorage.
 * Handles errors globally with toast notifications.
 *
 * Response format handling:
 *   - Unwraps {success: true, data: T} → T (for single-item endpoints)
 *   - Passes through {success: true, data: [...], items: [...], ...} (ListResponse)
 *   - Passes through {success: true, kpis: ..., ...} (dashboard/unstructured)
 *   - Throws ApiError on {success: false, error: ...} (any status code)
 *   - Throws ApiError on HTTP non-ok status
 */

import { toast } from "sonner";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
const TOKEN_KEY = "ai-recruitment-token";

function getAuthHeaders(): Record<string, string> {
  if (typeof window === "undefined") return {};
  try {
    const token = localStorage.getItem(TOKEN_KEY);
    if (token) return { Authorization: `Bearer ${token}` };
  } catch {
    /* noop */
  }
  return {};
}

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

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...getAuthHeaders(),
      ...options.headers,
    },
    ...options,
  });

  // Parse response body (404 etc. may have no body)
  let body: unknown;
  try {
    body = await res.json();
  } catch {
    if (!res.ok) {
      throw new ApiError(`请求失败 (${res.status})`, res.status);
    }
    return undefined as T;
  }

  // 1) Backend error responses: {success: false, error: "..."} on any status
  if (body && typeof body === "object" && "success" in body) {
    const b = body as Record<string, unknown>;
    if (b.success === false) {
      throw new ApiError(
        (b.error as string) || `请求失败 (${res.status})`,
        res.status,
        b.code as string | undefined
      );
    }
  }

  // 2) HTTP errors (non-ok, no success=false body)
  if (!res.ok) {
    const detail = body && typeof body === "object"
      ? (body as Record<string, unknown>).detail as string | undefined
      : undefined;
    throw new ApiError(detail || `请求失败 (${res.status})`, res.status);
  }

  // 3) Unwrap {success: true, data: T} for single-item responses
  //    Skip ListResponse where data is an array (items are in .items)
  if (
    body &&
    typeof body === "object" &&
    "success" in body &&
    "data" in body
  ) {
    const b = body as Record<string, unknown>;
    const data = b.data;
    // Unwrap when data is present and not an array (single item)
    if (data !== undefined && !Array.isArray(data)) {
      return data as T;
    }
    // For ListResponse / dashboard / other formats, return body as-is
    return body as T;
  }

  // 4) Plain response_model / raw dict (no success wrapper)
  return body as T;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "POST", body: JSON.stringify(body) }),
  put: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "PUT", body: JSON.stringify(body) }),
  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: "PATCH",
      ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
    }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
};

/**
 * Wraps an async operation with error handling.
 * Shows toast on error and returns the result or null.
 */
export async function withErrorHandling<T>(
  fn: () => Promise<T>,
  options?: { success?: string; error?: string }
): Promise<T | null> {
  try {
    const result = await fn();
    if (options?.success) toast.success(options.success);
    return result;
  } catch (err) {
    const message =
      err instanceof ApiError
        ? err.message
        : err instanceof Error
          ? err.message
          : "操作失败";
    toast.error(options?.error || message);
    return null;
  }
}
