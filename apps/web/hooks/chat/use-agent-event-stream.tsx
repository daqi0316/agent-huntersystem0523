"use client";

/**
 * useAgentEventStream — 订阅后端 SSE 事件，跨设备同步 agent-store
 *
 * Phase 4.1 + T3 增强：
 *  - 连接 GET /api/v1/agent/events（SSE，自动重连）
 *  - lastEventId 持久化（useEventSource 内置）：断线时把 lastEventId 拼到 URL
 *  - 服务端 XRANGE 重放离线期间 events（T3 验收）
 *  - 监听事件：
 *      · data_card.created   → 写入本地 dataCards
 *      · context.updated     → 写入本地 currentContext
 *      · approval.requested  → 写入本地 approval 队列
 *      · approval.resolved   → resetApproval
 *      · chat_response        → 跨设备 chat 同步
 *      · notification.fired   → 写入通知 store（T3 新增）
 *      · ping/connected       → 静默忽略
 *  - 与 BroadcastChannel（Phase 4.2）协同：本地更新走 BC，跨设备走 SSE
 *
 * 用法（已接入 AgentProvider）：
 *   useEffect(() => initAgentEventStream(), []);
 */

import { useEffect } from "react";
import { useEventSource } from "@/hooks/use-event-source";
import {
  useAgentStore,
  type DataCard,
  type ChatContext,
} from "@ai-recruitment/agent-store";
import { useNotificationsStore } from "@ai-recruitment/agent-store";

const ENDPOINT = "/agent/events";

interface DataCardCreatedPayload {
  id: string;
  type: DataCard["type"];
  title: string;
  summary: string;
  payload: unknown;
  toolName?: string;
  messageId?: string;
  createdAt: string;
  isRead?: boolean;
}

interface ContextUpdatedPayload extends Partial<ChatContext> {}

interface NotificationFiredPayload {
  id: string;
  user_id: string;
  kind: string;
  title: string;
  body: string;
  action_url?: string | null;
  created_at: string;
}

let initialized = false;

export function initAgentEventStream(): () => void {
  if (initialized) return () => undefined;
  initialized = true;

  return () => {
    initialized = false;
  };
}

export function AgentEventStreamBridge() {
  const { subscribe, connected } = useEventSource(ENDPOINT);

  useEffect(() => {
    if (!connected) return;

    const unsubCard = subscribe("data_card.created", (data) => {
      const payload = data as DataCardCreatedPayload;
      if (!payload?.id || !payload?.type) return;
      useAgentStore.getState().addRemoteCard({
        id: payload.id,
        type: payload.type,
        title: payload.title || "",
        summary: payload.summary || "",
        payload: payload.payload,
        toolName: payload.toolName,
        messageId: payload.messageId ?? "",
        createdAt: payload.createdAt || new Date().toISOString(),
        isRead: payload.isRead ?? false,
      });
    });

    const unsubChat = subscribe("chat_response", (data) => {
      const payload = data as {
        reply?: string;
        tool_calls?: Array<{ name: string; args?: Record<string, unknown> }>;
        model?: string;
      };
      if (!payload?.reply) return;
      import("@ai-recruitment/agent-store/parser").then(
        ({ parseDataCardsFromMessage }) => {
          const fakeMsg = {
            id:
              typeof crypto !== "undefined" && crypto.randomUUID
                ? crypto.randomUUID()
                : `evt_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
            createdAt: new Date().toISOString(),
            role: "assistant" as const,
            content: payload.reply || "",
            tool_calls: (payload.tool_calls ?? [])
              .filter((tc) => !!tc.name)
              .map((tc) => ({
                name: tc.name,
                args: tc.args ?? {},
                error: null as string | null,
                needs_human: false,
              })),
          };
          const cards = parseDataCardsFromMessage(fakeMsg);
          for (const card of cards) {
            useAgentStore.getState().addCard(card);
          }
          const toolCalls = fakeMsg.tool_calls || [];
          const candidateIds: string[] = [];
          const jobIds: string[] = [];
          let lastTool: string | undefined;
          for (const tc of toolCalls) {
            if (tc.name) lastTool = tc.name;
            const args = (tc.args || {}) as Record<string, unknown>;
            for (const [k, v] of Object.entries(args)) {
              if (typeof v === "string" && v) {
                if (/(candidate|candid)/i.test(k)) candidateIds.push(v);
                if (/(job[_-]?id|position[_-]?id)/i.test(k)) jobIds.push(v);
              }
            }
          }
          const recentTopic = (payload.reply || "").slice(0, 30);
          useAgentStore.getState().setCurrentContext({
            currentCandidateIds: Array.from(new Set(candidateIds)),
            currentJobIds: Array.from(new Set(jobIds)),
            recentTopic,
            lastToolUsed: lastTool,
          });
        }
      );
    });

    const unsubApproval = subscribe("approval.requested", (data) => {
      const payload = data as {
        approval_id: string;
        action_type: string;
        status: string;
        expires_at?: string;
        proposal_summary?: string;
      };
      if (!payload?.approval_id) return;
      useAgentStore.getState().setApproval({
        visible: true,
        approval_id: payload.approval_id,
        summary:
          payload.proposal_summary || `待审批：${payload.action_type}`,
        loading: false,
      });
    });

    const unsubApprovalResolved = subscribe("approval.resolved", (data) => {
      const payload = data as { approval_id: string };
      if (!payload?.approval_id) return;
      useAgentStore.getState().resetApproval();
    });

    const unsubContext = subscribe("context.updated", (data) => {
      const payload = data as ContextUpdatedPayload;
      useAgentStore.getState().setCurrentContext(payload);
    });

    // T3: notification.fired 业务通知
    const unsubNotification = subscribe("notification.fired", (data) => {
      const payload = data as NotificationFiredPayload;
      if (!payload?.id) return;
      // payload.kind 来自后端 SSE 字符串；前端 NotificationKind 是 union literal
      // 容错：未知 kind 降级为 "system"，避免运行时 undefined
      const allowedKinds = [
        "candidate_status_changed",
        "approval_requested",
        "approval_resolved",
        "system",
      ] as const;
      const kind = (allowedKinds as readonly string[]).includes(payload.kind)
        ? (payload.kind as (typeof allowedKinds)[number])
        : "system";
      useNotificationsStore.getState().addNotification({
        id: payload.id,
        userId: payload.user_id,
        kind,
        title: payload.title,
        body: payload.body,
        actionUrl: payload.action_url ?? null,
        createdAt: payload.created_at,
        read: false,
      });
    });

    return () => {
      unsubCard();
      unsubContext();
      unsubChat();
      unsubApproval();
      unsubApprovalResolved();
      unsubNotification();
    };
  }, [connected, subscribe]);

  return null;
}
