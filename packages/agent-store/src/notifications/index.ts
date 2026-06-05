/**
 * Notifications Store — 业务通知状态层（T3）
 *
 * 工业级 / 全局规划：
 *  - 持久化：notification 列表存 localStorage（user 离开页面/刷新后仍可见）
 *  - 容量：最多保留 50 条（与 dataCards 策略一致）；超出时丢弃最早的已读
 *  - 幂等：addNotification 重复 id 跳过（防止 SSE 重放 + 实时重复接收）
 *  - 不持久化 lastEventId（用 useEventSource 的独立 key）
 */

"use client";

import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";

export type NotificationKind =
  | "candidate_status_changed"
  | "approval_requested"
  | "approval_resolved"
  | "system";

export interface Notification {
  id: string;
  userId: string;
  kind: NotificationKind;
  title: string;
  body: string;
  actionUrl: string | null;
  createdAt: string;
  read: boolean;
}

const MAX_NOTIFICATIONS = 50;

export interface NotificationsStoreState {
  notifications: Notification[];
  permission: NotificationPermission | "unsupported";

  addNotification: (n: Notification) => void;
  markRead: (id: string) => void;
  markAllRead: () => void;
  clear: () => void;

  setPermission: (p: NotificationPermission | "unsupported") => void;
}

export const useNotificationsStore = create<NotificationsStoreState>()(
  persist(
    (set) => ({
      notifications: [],
      permission: "default",

      addNotification: (n) =>
        set((s) => {
          if (s.notifications.some((x) => x.id === n.id)) return s;
          const next = [{ ...n, read: false }, ...s.notifications].slice(
            0,
            MAX_NOTIFICATIONS
          );
          return { notifications: next };
        }),

      markRead: (id) =>
        set((s) => ({
          notifications: s.notifications.map((x) =>
            x.id === id ? { ...x, read: true } : x
          ),
        })),

      markAllRead: () =>
        set((s) => ({
          notifications: s.notifications.map((x) => ({ ...x, read: true })),
        })),

      clear: () => set({ notifications: [] }),

      setPermission: (permission) => set({ permission }),
    }),
    {
      name: "ai-recruitment-notifications",
      storage: createJSONStorage(() => {
        if (typeof window === "undefined") {
          return {
            getItem: () => null,
            setItem: () => undefined,
            removeItem: () => undefined,
          };
        }
        return localStorage;
      }),
      partialize: (state) => ({ notifications: state.notifications }),
      version: 1,
    }
  )
);

export const selectUnreadNotificationCount = (s: NotificationsStoreState): number =>
  s.notifications.filter((n) => !n.read).length;
