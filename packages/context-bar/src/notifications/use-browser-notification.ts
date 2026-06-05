"use client";

/**
 * useBrowserNotification — 浏览器 Notification API hook（T3）
 *
 * 工业级 / 全局规划：
 *  - 权限 UX：首次使用时弹权限请求（ContextBar 抽屉首次打开时触发）
 *  - 降级：用户拒绝时 fallback 为 sonner toast（已全局可用）
 *  - 节流：同 id 通知不发第二次
 *  - 点击跳转：actionUrl 跳路由（用 next/navigation）
 *  - 关闭：组件 unmount 时清通知引用避免内存泄漏
 *
 * 浏览器兼容：HTTPS / localhost 才有 Notification API。
 */

import { useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { useNotificationsStore } from "@ai-recruitment/agent-store";

const PERMISSION_KEY = "ai-recruitment:notification-permission-asked";

function browserNotificationSupported(): boolean {
  return (
    typeof window !== "undefined" &&
    "Notification" in window &&
    typeof Notification !== "undefined"
  );
}

export function useBrowserNotification() {
  const router = useRouter();
  const permission = useNotificationsStore((s) => s.permission);
  const setPermission = useNotificationsStore((s) => s.setPermission);
  const lastShownRef = useRef<Set<string>>(new Set());

  // 同步真实浏览器权限到 store
  useEffect(() => {
    if (!browserNotificationSupported()) {
      if (permission !== "unsupported") setPermission("unsupported");
      return;
    }
    const realPermission = Notification.permission;
    if (realPermission !== permission) {
      setPermission(realPermission);
    }
  }, [permission, setPermission]);

  function requestPermission(): void {
    if (!browserNotificationSupported()) return;
    if (Notification.permission !== "default") return;
    try {
      localStorage.setItem(PERMISSION_KEY, "1");
    } catch {
      /* ignore */
    }
    void Notification.requestPermission().then((result) => {
      setPermission(result);
    });
  }

  function shouldAskPermission(): boolean {
    if (!browserNotificationSupported()) return false;
    if (Notification.permission !== "default") return false;
    try {
      return !localStorage.getItem(PERMISSION_KEY);
    } catch {
      return true;
    }
  }

  function show(notification: {
    id: string;
    title: string;
    body: string;
    actionUrl: string | null;
  }): void {
    // 幂等：同 id 已显示过跳过
    if (lastShownRef.current.has(notification.id)) return;
    lastShownRef.current.add(notification.id);

    if (
      browserNotificationSupported() &&
      Notification.permission === "granted"
    ) {
      try {
        const n = new Notification(notification.title, {
          body: notification.body,
          tag: notification.id,
        });
        n.onclick = () => {
          window.focus();
          if (notification.actionUrl) router.push(notification.actionUrl);
          n.close();
        };
        // 自动关 8s（不阻塞用户操作）
        window.setTimeout(() => n.close(), 8000);
      } catch (e) {
        // 浏览器限制 / 沙箱环境 → 降级 toast
        showToastFallback(notification);
      }
    } else {
      // 拒绝 / 不支持 / 默认：toast 兜底
      showToastFallback(notification);
    }
  }

  return {
    show,
    requestPermission,
    shouldAskPermission,
    supported: browserNotificationSupported(),
    permission,
  };
}

function showToastFallback(n: { title: string; body: string; actionUrl: string | null }) {
  toast(n.title, {
    description: n.body,
    action: n.actionUrl
      ? {
          label: "查看",
          onClick: () => {
            window.location.href = n.actionUrl!;
          },
        }
      : undefined,
  });
}
