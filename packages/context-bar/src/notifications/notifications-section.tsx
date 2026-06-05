"use client";

/**
 * NotificationsSection — 抽屉顶部"业务通知"区块（T3）
 *
 * 工业级 / 全局规划：
 *  - 渲染：未读数徽章 + 列表（标题 + body + 跳转链接）
 *  - 集成：useBrowserNotification 自动 trigger 浏览器原生通知
 *  - 空态：完全隐藏（与 CurrentContextSection 行为一致）
 *  - a11y：<section aria-label> + 通知项 <button> + 跳转链接
 */

import { Bell, Check } from "lucide-react";
import { useEffect } from "react";
import Link from "next/link";
import { cn } from "../utils";
import { useNotificationsStore, type Notification } from "@ai-recruitment/agent-store";
import { useBrowserNotification } from "./use-browser-notification";

const KIND_LABEL: Record<Notification["kind"], string> = {
  candidate_status_changed: "候选人",
  approval_requested: "审批",
  approval_resolved: "审批",
  system: "系统",
};

export function NotificationsSection() {
  const notifications = useNotificationsStore((s) => s.notifications);
  const markRead = useNotificationsStore((s) => s.markRead);
  const markAllRead = useNotificationsStore((s) => s.markAllRead);
  const { show, shouldAskPermission, requestPermission } = useBrowserNotification();

  const unread = notifications.filter((n) => !n.read).length;

  useEffect(() => {
    if (unread === 0) return;
    for (const n of notifications) {
      if (!n.read) show(n);
    }
  }, [notifications, unread, show]);

  useEffect(() => {
    if (shouldAskPermission()) {
      requestPermission();
    }
  }, [shouldAskPermission, requestPermission]);

  if (notifications.length === 0) return null;

  return (
    <section
      className="rounded-lg border bg-card/50 p-3 mb-3"
      aria-label="业务通知"
    >
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-1.5">
          <Bell className="h-3.5 w-3.5 text-primary" />
          <p className="text-xs font-semibold text-foreground">业务通知</p>
          {unread > 0 && (
            <span className="inline-flex items-center justify-center min-w-[1rem] h-4 px-1 rounded-full bg-primary text-primary-foreground text-[10px] font-bold">
              {unread > 99 ? "99+" : unread}
            </span>
          )}
        </div>
        {unread > 0 && (
          <button
            onClick={markAllRead}
            className="text-[10px] text-muted-foreground hover:text-foreground flex items-center gap-0.5"
            aria-label="全部标为已读"
          >
            <Check className="h-3 w-3" />
            全部已读
          </button>
        )}
      </div>

      <ul className="space-y-1.5">
        {notifications.slice(0, 5).map((n) => (
          <li key={n.id}>
            <NotificationItem
              notification={n}
              onRead={() => markRead(n.id)}
            />
          </li>
        ))}
      </ul>
    </section>
  );
}

function NotificationItem({
  notification,
  onRead,
}: {
  notification: Notification;
  onRead: () => void;
}) {
  const inner = (
    <div
      className={cn(
        "block rounded-md border px-2 py-1.5 text-[11px] transition-colors",
        notification.read
          ? "bg-muted/30 text-muted-foreground"
          : "bg-amber-50/60 dark:bg-amber-950/20 border-amber-300/40"
      )}
    >
      <div className="flex items-center gap-1.5">
        <span className="font-mono text-[9px] text-muted-foreground shrink-0">
          {KIND_LABEL[notification.kind]}
        </span>
        <span className="font-medium truncate">{notification.title}</span>
      </div>
      <p className="text-[10px] text-muted-foreground mt-0.5 line-clamp-2">
        {notification.body}
      </p>
    </div>
  );

  if (notification.actionUrl) {
    return (
      <Link
        href={notification.actionUrl}
        onClick={onRead}
        className="block"
      >
        {inner}
      </Link>
    );
  }
  return (
    <button
      type="button"
      onClick={onRead}
      className="block w-full text-left"
    >
      {inner}
    </button>
  );
}
