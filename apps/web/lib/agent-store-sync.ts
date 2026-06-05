/**
 * Agent Store Multi-Tab Sync — BroadcastChannel 包装
 *
 * 行为：
 *  - 同一浏览器多 tab 打开时，agent-store 关键切片（dataCards / currentContext）实时同步
 *  - 本 tab 的 state 变化通过 BroadcastChannel 广播
 *  - 其他 tab 接收后应用（用 setState 避免触发 echo 循环）
 *  - SSR-safe：服务端 window 不存在时静默跳过
 *  - BroadcastChannel 不可用时（极旧浏览器）也静默跳过
 *
 * 用法（dashboard/layout.tsx 已通过 AgentProvider 接入）：
 *   useEffect(() => { initAgentStoreSync(); }, []);
 *
 * 与后端 SSE 的区别：
 *  - BroadcastChannel：同浏览器、同设备的 tab 之间
 *  - SSE：跨设备、跨浏览器（Phase 4.1，暂未实现）
 */

import { useAgentStore, type DataCard, type ChatContext } from "@ai-recruitment/agent-store";

const CHANNEL_NAME = "ai-recruitment-agent-sync";
const SYNC_KEYS = ["dataCards", "currentContext"] as const;
type SyncKey = (typeof SYNC_KEYS)[number];
type SyncPayload = {
  dataCards?: DataCard[];
  currentContext?: ChatContext;
};

let channel: BroadcastChannel | null = null;
let isReceiving = false;
let unsubscribe: (() => void) | null = null;

function getTabId(): string {
  if (typeof window === "undefined") return "ssr";
  try {
    let id = sessionStorage.getItem("__agent_tab_id");
    if (!id) {
      id = `tab_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
      sessionStorage.setItem("__agent_tab_id", id);
    }
    return id;
  } catch {
    return `tab_${Math.random().toString(36).slice(2, 8)}`;
  }
}

export function initAgentStoreSync(): void {
  if (typeof window === "undefined") return;
  if (typeof BroadcastChannel === "undefined") {
    // eslint-disable-next-line no-console
    console.warn("[agent-store-sync] BroadcastChannel unavailable, multi-tab sync disabled");
    return;
  }
  if (channel) return;

  const tabId = getTabId();
  channel = new BroadcastChannel(CHANNEL_NAME);

  channel.onmessage = (e: MessageEvent) => {
    const { source, payload } = (e.data || {}) as {
      source?: string;
      payload?: SyncPayload;
    };
    if (source === tabId) return;
    if (!payload) return;

    isReceiving = true;
    try {
      const update: SyncPayload = {};
      if (payload.dataCards !== undefined) {
        (update as { dataCards: DataCard[] }).dataCards = payload.dataCards;
      }
      if (payload.currentContext !== undefined) {
        (update as { currentContext: ChatContext }).currentContext =
          payload.currentContext;
      }
      useAgentStore.setState(update as Partial<typeof EMPTY_STATE>);
    } finally {
      isReceiving = false;
    }
  };

  unsubscribe = useAgentStore.subscribe((state, prev) => {
    if (isReceiving) return;
    const payload: SyncPayload = {};
    for (const key of SYNC_KEYS) {
      const cur = state[key];
      const pre = prev[key];
      if (cur !== pre) {
        (payload as Record<SyncKey, unknown>)[key] = cur;
      }
    }
    if (Object.keys(payload).length > 0) {
      channel?.postMessage({ source: tabId, payload });
    }
  });
}

export function teardownAgentStoreSync(): void {
  unsubscribe?.();
  unsubscribe = null;
  channel?.close();
  channel = null;
  isReceiving = false;
}

const EMPTY_STATE = {
  messages: [],
  dataCards: [],
  currentContext: {
    currentCandidateIds: [],
    currentJobIds: [],
    recentTopic: "",
  },
  approval: { visible: false, approval_id: "", summary: "", loading: false },
  attachment: null,
  lastToolCalls: [],
  operationPanel: { open: false },
};
