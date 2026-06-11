"use client";

/**
 * P2a-6: Sourcing API hooks (TanStack Query)
 *
 * 封装 /api/v1/sourcing/* 全套 API
 * 响应格式:
 *   {success: true, data: T}  → 单个对象
 *   {success: true, data: [...], total, page, page_size} → 列表
 */
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";

/* ── Types ── */

export interface SourcingTask {
  id: string;
  keyword: string;
  platforms: string[];
  filters: Record<string, unknown>;
  status: string;
  progress: Record<string, unknown>;
  total_found: number;
  after_dedup: number;
  new_this_run: number;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface TaskListResponse {
  success: boolean;
  data: SourcingTask[];
  total: number;
  page: number;
  page_size: number;
}

export interface AiAnalysis {
  skills_extracted?: string[];
  skill_categories?: Record<string, string[]>;
  career_trajectory?: {
    direction?: string;
    stability?: string;
    avg_tenure_years?: number | null;
    industry_trend?: string[];
  };
  summary?: {
    one_liner?: string;
    strengths?: string[];
    risks?: string[];
    recommended_roles?: string[];
  };
  confidence?: number;
}

export interface MatchScore {
  overall_score?: number;
  dimensions?: {
    skills_match?: { score?: number; matched?: string[]; missing?: string[]; detail?: string };
    experience_match?: { score?: number; detail?: string };
    industry_match?: { score?: number; detail?: string };
  };
  summary?: string;
  confidence?: number;
}

export interface SourcingCandidate {
  id: string;
  name: string;
  email: string;
  phone?: string;
  current_company?: string;
  current_title?: string;
  location?: string;
  salary?: string;
  skills: string[];
  experience_years?: number;
  education?: string;
  summary?: string;
  source_platforms?: string[];
  source_urls?: Record<string, string>;
  raw_data?: Record<string, any>;
  dedup_fingerprint?: string;
  ai_analysis?: AiAnalysis;
  match_scores?: Record<string, MatchScore> | MatchScore;
  last_crawled_at?: string;
  created_at: string;
}

export interface CandidateListResponse {
  success: boolean;
  data: SourcingCandidate[];
  total: number;
  page: number;
  page_size: number;
}

export interface CrawlLog {
  id: string;
  platform: string;
  status: string;
  candidates_found: number;
  error_message?: string;
  duration_seconds: number;
  proxy_used?: string;
  captcha_solved: boolean;
  retry_count: number;
  started_at: string;
  finished_at: string;
}

export interface TaskCreateBody {
  org_id: string;
  created_by: string;
  keyword: string;
  platforms?: string[];
  filters?: Record<string, unknown>;
  priority?: number;
}

export interface HealthStatus {
  status: string;
  services: Record<string, string>;
  queue: { pending: number; running: number };
  platforms: { total: number; available: number };
}

export interface PlatformConfig {
  name: string;
  display_name: string;
  category: string;
  anti_crawl_level: number;
  enabled: boolean;
  health_status: string;
  health_checked_at?: string;
  rate_limit: number;
  daily_quota_per_account: number;
  requires_login: boolean;
}

export interface PlatformAccount {
  id: string;
  platform: string;
  display_name: string;
  account_type: string;
  is_active: boolean;
  status: string;
  daily_used: number;
  consecutive_failures: number;
}

/* ── Query Keys ── */

export const sourcingKeys = {
  tasks: {
    all: ["sourcing", "tasks"] as const,
    list: (filters?: Record<string, unknown>) =>
      ["sourcing", "tasks", "list", filters] as const,
    detail: (id: string) => ["sourcing", "tasks", id] as const,
    logs: (id: string) => ["sourcing", "tasks", id, "logs"] as const,
  },
  candidates: {
    all: ["sourcing", "candidates"] as const,
    list: (filters?: Record<string, unknown>) =>
      ["sourcing", "candidates", "list", filters] as const,
    detail: (id: string) => ["sourcing", "candidates", id] as const,
  },
  health: ["sourcing", "health"] as const,
  platforms: {
    all: ["sourcing", "platforms"] as const,
    accounts: (name: string) => ["sourcing", "platforms", name, "accounts"] as const,
  },
};

/* ── Hooks: Tasks ── */

export function useTaskList(params?: {
  status_filter?: string;
  platform?: string;
  keyword?: string;
  page?: number;
  page_size?: number;
}) {
  const searchParams = new URLSearchParams();
  if (params?.status_filter) searchParams.set("status_filter", params.status_filter);
  if (params?.platform) searchParams.set("platform", params.platform);
  if (params?.keyword) searchParams.set("keyword", params.keyword);
  if (params?.page) searchParams.set("page", String(params.page));
  if (params?.page_size) searchParams.set("page_size", String(params.page_size));

  const qs = searchParams.toString();
  return useQuery<TaskListResponse>({
    queryKey: sourcingKeys.tasks.list(params),
    queryFn: () => api.get<TaskListResponse>(`/sourcing/tasks${qs ? `?${qs}` : ""}`),
    refetchInterval: params?.page ? 5000 : false, // 轮询 5s 仅列表页
  });
}

export function useTaskDetail(taskId: string) {
  return useQuery<{ success: boolean; data: SourcingTask }>({
    queryKey: sourcingKeys.tasks.detail(taskId),
    queryFn: () => api.get<{ success: boolean; data: SourcingTask }>(`/sourcing/tasks/${taskId}`),
    enabled: !!taskId,
    refetchInterval: 5000,
  });
}

export function useTaskLogs(taskId: string) {
  return useQuery<{ success: boolean; data: CrawlLog[]; total: number }>({
    queryKey: sourcingKeys.tasks.logs(taskId),
    queryFn: () =>
      api.get<{ success: boolean; data: CrawlLog[]; total: number }>(
        `/sourcing/tasks/${taskId}/logs`
      ),
    enabled: !!taskId,
    refetchInterval: 5000,
  });
}

export function useCreateTask() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: TaskCreateBody) =>
      api.post<{ success: boolean; data: { id: string; keyword: string; status: string } }>(
        "/sourcing/tasks",
        body
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: sourcingKeys.tasks.all });
    },
  });
}

export function useCancelTask() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (taskId: string) =>
      api.post<{ success: boolean }>(`/sourcing/tasks/${taskId}/cancel`, {}),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: sourcingKeys.tasks.all });
    },
  });
}

export function useDispatchTask() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (taskId: string) =>
      api.post<{ success: boolean }>(`/sourcing/tasks/${taskId}/dispatch`, {}),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: sourcingKeys.tasks.all });
    },
  });
}

/* ── Hooks: Candidates ── */

export function useSourcingCandidateList(params?: {
  task_id?: string;
  platform?: string;
  skill?: string;
  page?: number;
  page_size?: number;
}) {
  const searchParams = new URLSearchParams();
  if (params?.task_id) searchParams.set("task_id", params.task_id);
  if (params?.platform) searchParams.set("platform", params.platform);
  if (params?.skill) searchParams.set("skill", params.skill);
  if (params?.page) searchParams.set("page", String(params.page));
  if (params?.page_size) searchParams.set("page_size", String(params.page_size));

  const qs = searchParams.toString();
  return useQuery<CandidateListResponse>({
    queryKey: sourcingKeys.candidates.list(params),
    queryFn: () =>
      api.get<CandidateListResponse>(`/sourcing/candidates${qs ? `?${qs}` : ""}`),
  });
}

/* ── Hooks: Health ── */

export function useSourcingHealth() {
  return useQuery<HealthStatus>({
    queryKey: sourcingKeys.health,
    queryFn: () => api.get<HealthStatus>("/sourcing/health"),
    refetchInterval: 30000,
  });
}

/* ── Hooks: Analyze Candidate ── */

export function useAnalyzeCandidate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      candidateId,
      jd_id,
    }: {
      candidateId: string;
      jd_id?: string;
    }) =>
      api.post<{
        success: boolean;
        data: { analysis: AiAnalysis; match_score?: MatchScore };
      }>(`/sourcing/candidates/${candidateId}/analyze`, { jd_id }),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: sourcingKeys.candidates.detail(variables.candidateId),
      });
    },
  });
}

/* ── Hooks: Merge Candidates ── */

export function useMergeCandidates() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: { primary_id: string; merge_ids: string[] }) =>
      api.post<{ success: boolean; data: SourcingCandidate }>(
        "/sourcing/candidates/merge",
        body
      ),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: sourcingKeys.candidates.all });
      queryClient.invalidateQueries({
        queryKey: sourcingKeys.candidates.detail(variables.primary_id),
      });
    },
  });
}

/* ── Hooks: Candidate Detail ── */

export function useCandidateDetail(candidateId: string) {
  return useQuery<{ success: boolean; data: SourcingCandidate }>({
    queryKey: sourcingKeys.candidates.detail(candidateId),
    queryFn: () =>
      api.get<{ success: boolean; data: SourcingCandidate }>(
        `/sourcing/candidates/${candidateId}`
      ),
    enabled: !!candidateId,
  });
}

/* ── Hooks: Platforms ── */

export function usePlatformList() {
  return useQuery<{ success: boolean; data: PlatformConfig[] }>({
    queryKey: sourcingKeys.platforms.all,
    queryFn: () => api.get<{ success: boolean; data: PlatformConfig[] }>("/sourcing/platforms"),
  });
}

export function usePlatformAccounts(platform: string) {
  return useQuery<{ success: boolean; data: PlatformAccount[] }>({
    queryKey: sourcingKeys.platforms.accounts(platform),
    queryFn: () =>
      api.get<{ success: boolean; data: PlatformAccount[] }>(
        `/sourcing/platforms/${platform}/accounts`
      ),
    enabled: !!platform,
  });
}

export function useUpdatePlatform() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ platform, data }: { platform: string; data: Partial<PlatformConfig> }) =>
      api.patch<{ success: boolean; data: PlatformConfig }>(
        `/sourcing/platforms/${platform}`,
        data
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: sourcingKeys.platforms.all });
    },
  });
}

export function useCreateAccount() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      platform,
      data,
    }: {
      platform: string;
      data: { display_name: string; account_type: string; encrypted_cookies?: string };
    }) =>
      api.post<{ success: boolean; data: PlatformAccount }>(
        `/sourcing/platforms/${platform}/accounts`,
        data
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: sourcingKeys.platforms.all });
    },
  });
}
