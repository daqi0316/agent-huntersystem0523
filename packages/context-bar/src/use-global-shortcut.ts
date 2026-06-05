"use client";

/**
 * useGlobalShortcut — 全局键盘快捷键 hook
 *
 * 行为：
 *  - 监听 keydown，匹配指定组合（⌘K / Ctrl+K 等）
 *  - 输入框/可编辑元素聚焦时自动失效（避免误触）
 *  - preventDefault + stopPropagation
 *
 * 用法：
 *   useGlobalShortcut("k", () => setOpen(true), { mod: true });
 */

import { useEffect } from "react";

type Modifiers = {
  mod?: boolean; // Cmd on Mac, Ctrl on Win/Linux
  shift?: boolean;
  alt?: boolean;
};

const isMac =
  typeof navigator !== "undefined" &&
  /Mac|iPhone|iPad|iPod/.test(navigator.platform);

function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return true;
  if (target.isContentEditable) return true;
  return false;
}

export function useGlobalShortcut(
  key: string,
  callback: (e: KeyboardEvent) => void,
  modifiers: Modifiers = {}
): void {
  useEffect(() => {
    function handler(e: KeyboardEvent) {
      if (e.key.toLowerCase() !== key.toLowerCase()) return;
      if (modifiers.mod && !(isMac ? e.metaKey : e.ctrlKey)) return;
      if (modifiers.shift && !e.shiftKey) return;
      if (modifiers.alt && !e.altKey) return;

      if (isEditableTarget(e.target)) return;

      e.preventDefault();
      e.stopPropagation();
      callback(e);
    }
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [key, callback, modifiers.mod, modifiers.shift, modifiers.alt]);
}
