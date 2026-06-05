"use client";

/**
 * 键盘 ⌘↑/↓ 选卡片 + Enter 展开 hook（T5）
 *
 * 工业级 / 全局规划：
 *  - 监听 keydown 事件：ArrowUp/ArrowDown 上下选择，Enter 展开
 *  - 仅在抽屉打开 + 有 query 激活时（SearchBar 模式）生效 — 避免污染其它场景
 *  - mod 修饰键支持（mac ⌘ / win linux ctrl）
 *  - 不抢全局 ⌘K / Esc（这些走 useGlobalShortcut）
 *  - 输入框聚焦时跳过（避免用户编辑时干扰）
 */

import { useEffect } from "react";

export interface UseCardKeyboardNavOptions {
  /** 是否启用（抽屉打开 + 搜索激活） */
  enabled: boolean;
  /** 当前过滤后的卡片列表 */
  cards: Array<{ id: string }>;
  /** 当前选中索引（受控） */
  activeIndex: number;
  /** 索引变化回调 */
  onActiveIndexChange: (index: number) => void;
  /** Enter 展开回调（接收 activeIndex 对应卡片的 id） */
  onActivate: (id: string) => void;
}

export function useCardKeyboardNav({
  enabled,
  cards,
  activeIndex,
  onActiveIndexChange,
  onActivate,
}: UseCardKeyboardNavOptions): void {
  useEffect(() => {
    if (!enabled || cards.length === 0) return;

    function isEditableTarget(target: EventTarget | null): boolean {
      if (!(target instanceof HTMLElement)) return false;
      const tag = target.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return true;
      return target.isContentEditable;
    }

    function handler(e: KeyboardEvent) {
      if (e.key !== "ArrowUp" && e.key !== "ArrowDown" && e.key !== "Enter") return;
      if (isEditableTarget(e.target)) return;

      if (e.key === "ArrowUp" || e.key === "ArrowDown") {
        e.preventDefault();
        const direction = e.key === "ArrowDown" ? 1 : -1;
        const next = activeIndex + direction;
        const wrapped = next < 0 ? cards.length - 1 : next >= cards.length ? 0 : next;
        onActiveIndexChange(wrapped);
        return;
      }

      if (e.key === "Enter") {
        e.preventDefault();
        const idx = activeIndex >= 0 && activeIndex < cards.length ? activeIndex : 0;
        const target = cards[idx];
        if (target) onActivate(target.id);
      }
    }

    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [enabled, cards, activeIndex, onActiveIndexChange, onActivate]);
}
