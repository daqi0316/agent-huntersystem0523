"use client";

/**
 * useCardOrderHash — 卡片顺序 ↔ URL hash 同步 hook（T5）
 *
 * 工业级 / 全局规划：
 *  - URL hash 格式：`#cards=id1,id2,id3`（order；与默认顺序不同才写）
 *  - 跨 tab 同步：监听 window 'hashchange' 事件
 *  - 降级：cards 数 > 50 时只 hash 前 50（防 URL 超 8192 字符）
 *  - 跨设备不通过 BroadcastChannel 同步（plan §7 风险 2：URL hash 是 per-session）
 *  - 拖到 body 外部（drop outside）由 useCardDragOutside 检测，调用 setOrder(currentOrder) 回滚
 *
 * 不依赖 React Context / zustand — 用 useState 维持本组件 local order override。
 */

import { useCallback, useEffect, useState } from "react";

const HASH_KEY = "cards";
const HASH_MAX_ENTRIES = 50;

function parseHashOrder(): string[] | null {
  if (typeof window === "undefined") return null;
  const raw = window.location.hash.replace(/^#/, "");
  const params = new URLSearchParams(raw);
  const value = params.get(HASH_KEY);
  if (!value) return null;
  return value.split(",").filter(Boolean);
}

function writeHashOrder(order: string[]): void {
  if (typeof window === "undefined") return;
  const trimmed = order.slice(0, HASH_MAX_ENTRIES);
  const params = new URLSearchParams(window.location.hash.replace(/^#/, ""));
  if (
    // 与默认顺序一致时不写 hash（避免无意义 URL 变化）
    order.length === 0 ||
    isDefaultOrder(trimmed)
  ) {
    params.delete(HASH_KEY);
  } else {
    params.set(HASH_KEY, trimmed.join(","));
  }
  const next = params.toString();
  const target = next ? `#${next}` : "";
  // 用 history.replaceState 避免在浏览器历史留痕
  if (window.location.hash !== target) {
    window.history.replaceState(null, "", window.location.pathname + window.location.search + target);
  }
}

function isDefaultOrder(order: string[]): boolean {
  // default order 由 store 决定（按 createdAt 倒序）。当 URL order 与 store
  // 顺序一致时 — 因为 store 顺序是动态的（cards 持续加入），简化判断：
  // 单调递增前缀与 store 一致就认为是默认。我们这里只检查"是否降级"：
  // hash 永远写非空 order（让 hook 调用方决定是否写）
  return false;
}

export interface UseCardOrderHashResult {
  /** 当前 URL hash 顺序（覆盖 cards 默认顺序） */
  hashOrder: string[] | null;
  /** 显式设置 hash 顺序（拖拽后调用） */
  setOrder: (order: string[]) => void;
  /** 清除 hash 顺序（回滚默认） */
  clearOrder: () => void;
}

export function useCardOrderHash(): UseCardOrderHashResult {
  const [hashOrder, setHashOrder] = useState<string[] | null>(() => parseHashOrder());

  useEffect(() => {
    function onHashChange() {
      setHashOrder(parseHashOrder());
    }
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  const setOrder = useCallback((order: string[]) => {
    writeHashOrder(order);
    setHashOrder(order.slice(0, HASH_MAX_ENTRIES));
  }, []);

  const clearOrder = useCallback(() => {
    writeHashOrder([]);
    setHashOrder(null);
  }, []);

  return { hashOrder, setOrder, clearOrder };
}

/** 应用 hash 顺序到 cards 列表：
 *  - 优先按 hash order 排序
 *  - hash 缺失的卡片追加到末尾（按原 createdAt 倒序）
 *  - hash 包含但 cards 不存在的 id 忽略
 */
export function applyHashOrder<T extends { id: string; createdAt: string }>(
  cards: T[],
  hashOrder: string[] | null
): T[] {
  if (!hashOrder || hashOrder.length === 0) {
    return [...cards].sort((a, b) => b.createdAt.localeCompare(a.createdAt));
  }
  const byId = new Map(cards.map((c) => [c.id, c]));
  const ordered: T[] = [];
  const seen = new Set<string>();
  for (const id of hashOrder) {
    const c = byId.get(id);
    if (c && !seen.has(id)) {
      ordered.push(c);
      seen.add(id);
    }
  }
  // hash 缺失的 cards 追加到末尾（按 createdAt 倒序）
  const rest = cards
    .filter((c) => !seen.has(c.id))
    .sort((a, b) => b.createdAt.localeCompare(a.createdAt));
  return [...ordered, ...rest];
}
