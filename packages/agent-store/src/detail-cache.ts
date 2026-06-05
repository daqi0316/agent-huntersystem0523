/**
 * Detail Cache — 候选人/职位详情跨抽屉缓存（T4）
 *
 * 工业级 / 全局规划：
 *  - 同一会话内多次打开同一候选人/职位 → 不重复 fetch（stale-while-revalidate）
 *  - 持久化到 sessionStorage（不跨刷新；面试试间断网时用内存）
 *  - 容量：最近 100 条（LRU 淘汰）
 *  - 失败/404 状态不缓存（每次重试重 fetch，避免 stale error）
 *
 * 不放 zustand persist：详情数据可能很大（候选人/职位的完整字段），
 * sessionStorage 5MB 限制；内存 Map 即可。
 */

"use client";

import type { CandidateRead, JobRead } from "./types";

export interface CachedCandidate {
  data: CandidateRead;
  fetchedAt: number;
}

export interface CachedJob {
  data: JobRead;
  fetchedAt: number;
}

const CACHE_TTL_MS = 5 * 60 * 1000;
const CACHE_MAX_ENTRIES = 100;

const candidateCache = new Map<string, CachedCandidate>();
const jobCache = new Map<string, CachedJob>();

function lruPrune<K, V>(cache: Map<K, V>): void {
  while (cache.size > CACHE_MAX_ENTRIES) {
    const firstKey = cache.keys().next().value;
    if (firstKey === undefined) break;
    cache.delete(firstKey);
  }
}

export function getCachedCandidate(id: string): CachedCandidate | null {
  const entry = candidateCache.get(id);
  if (!entry) return null;
  if (Date.now() - entry.fetchedAt > CACHE_TTL_MS) {
    candidateCache.delete(id);
    return null;
  }
  return entry;
}

export function setCachedCandidate(id: string, data: CandidateRead): void {
  candidateCache.set(id, { data, fetchedAt: Date.now() });
  lruPrune(candidateCache);
}

export function invalidateCandidate(id: string): void {
  candidateCache.delete(id);
}

export function getCachedJob(id: string): CachedJob | null {
  const entry = jobCache.get(id);
  if (!entry) return null;
  if (Date.now() - entry.fetchedAt > CACHE_TTL_MS) {
    jobCache.delete(id);
    return null;
  }
  return entry;
}

export function setCachedJob(id: string, data: JobRead): void {
  jobCache.set(id, { data, fetchedAt: Date.now() });
  lruPrune(jobCache);
}

export function invalidateJob(id: string): void {
  jobCache.delete(id);
}

export function clearAllDetailCache(): void {
  candidateCache.clear();
  jobCache.clear();
}
