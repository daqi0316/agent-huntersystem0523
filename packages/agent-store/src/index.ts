/**
 * Agent Store — AI 助手全局状态层（共享给 apps/web 和 @ai-recruitment/context-bar）
 *
 * 设计原则：
 *  - 跨包共享：apps/web（use-chat-stream 等 hook）和 context-bar 包（UI）都用此 store
 *  - persist 中间件开启，跨页面 + 跨刷新保留
 *  - 不使用 immer 中间件（避免新增 immer 依赖），改用 spread 模式手动不可变更新
 *
 * persist key 保持 "ai-recruitment-agent-store" 与原位置一致，迁包后用户数据不丢。
 */

import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import type {
  ChatMessage,
  OperationPanelState,
  UploadedFile,
  DataCard,
  ChatContext,
  ApprovalState,
  SessionStats,
} from "./types";

export type {
  ChatMessage,
  OperationPanelState,
  UploadedFile,
  DataCard,
  ChatContext,
  ApprovalState,
  SessionStats,
  DataCardType,
  ToolCallInfo,
  AgentActionInfo,
  AgentChatResponse,
  MemoryFact,
} from "./types";
export { newMessage } from "./types";

// ── State ──

export interface AgentStoreState {
  messages: ChatMessage[];
  dataCards: DataCard[];
  currentContext: ChatContext;
  approval: ApprovalState;
  attachment: UploadedFile | null;
  lastToolCalls: Array<{
    name: string;
    args: Record<string, unknown>;
    error?: string | null;
    needs_human?: boolean;
  }>;
  operationPanel: OperationPanelState;
  sessionStats: SessionStats;

  setMessages: (messages: ChatMessage[]) => void;
  addMessage: (message: ChatMessage) => void;
  clearMessages: () => void;

  addCard: (card: Omit<DataCard, "id" | "createdAt" | "isRead">) => void;
  addRemoteCard: (card: DataCard) => void;
  removeCard: (id: string) => void;
  markCardRead: (id: string) => void;
  markAllCardsRead: () => void;
  clearCards: () => void;

  setCurrentContext: (ctx: Partial<ChatContext>) => void;
  resetContext: () => void;

  setApproval: (approval: ApprovalState) => void;
  resetApproval: () => void;

  setAttachment: (file: UploadedFile | null) => void;

  setLastToolCalls: (
    calls: Array<{
      name: string;
      args: Record<string, unknown>;
      error?: string | null;
      needs_human?: boolean;
    }>
  ) => void;

  setOperationPanel: (state: OperationPanelState) => void;
  closeOperationPanel: () => void;

  recordMessage: () => void;
  recordToolCall: (name: string) => void;
  resetSession: () => void;

  reset: () => void;
}

// ── Initial state ──

const INITIAL_CONTEXT: ChatContext = {
  currentCandidateIds: [],
  currentJobIds: [],
  recentTopic: "",
};

const INITIAL_APPROVAL: ApprovalState = {
  visible: false,
  approval_id: "",
  summary: "",
  loading: false,
};

const INITIAL_OPERATION_PANEL: OperationPanelState = { open: false };

const EMPTY_STATE = {
  messages: [] as ChatMessage[],
  dataCards: [] as DataCard[],
  currentContext: INITIAL_CONTEXT,
  approval: INITIAL_APPROVAL,
  attachment: null as UploadedFile | null,
  lastToolCalls: [] as AgentStoreState["lastToolCalls"],
  operationPanel: INITIAL_OPERATION_PANEL,
  sessionStats: {
    messageCount: 0,
    toolCallCount: 0,
    usedTools: [],
    startedAt: null,
  } as SessionStats,
};

function genCardId(): string {
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return `card_${crypto.randomUUID().slice(0, 8)}`;
  }
  return `card_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

// ── Store ──

export const useAgentStore = create<AgentStoreState>()(
  persist(
    (set) => ({
      ...EMPTY_STATE,

      setMessages: (messages) => set({ messages }),

      addMessage: (message) =>
        set((s) => ({ messages: [...s.messages, message] })),

      clearMessages: () => set({ messages: [] }),

      addCard: (card) =>
        set((s) => {
          const newCard: DataCard = {
            ...card,
            id: genCardId(),
            createdAt: new Date().toISOString(),
            isRead: false,
          };
          const next = [newCard, ...s.dataCards].slice(0, 50);
          return { dataCards: next };
        }),

      addRemoteCard: (card) =>
        set((s) => {
          if (s.dataCards.some((c) => c.id === card.id)) return s;
          const next = [card, ...s.dataCards].slice(0, 50);
          return { dataCards: next };
        }),

      removeCard: (id) =>
        set((s) => ({ dataCards: s.dataCards.filter((c) => c.id !== id) })),

      markCardRead: (id) =>
        set((s) => ({
          dataCards: s.dataCards.map((c) =>
            c.id === id ? { ...c, isRead: true } : c
          ),
        })),

      markAllCardsRead: () =>
        set((s) => ({
          dataCards: s.dataCards.map((c) => ({ ...c, isRead: true })),
        })),

      clearCards: () => set({ dataCards: [] }),

      setCurrentContext: (ctx) =>
        set((s) => ({ currentContext: { ...s.currentContext, ...ctx } })),

      resetContext: () => set({ currentContext: INITIAL_CONTEXT }),

      setApproval: (approval) => set({ approval }),

      resetApproval: () => set({ approval: INITIAL_APPROVAL }),

      setAttachment: (file) => set({ attachment: file }),

      setLastToolCalls: (calls) => set({ lastToolCalls: calls }),

      setOperationPanel: (state) => set({ operationPanel: state }),

      closeOperationPanel: () => set({ operationPanel: INITIAL_OPERATION_PANEL }),

      recordMessage: () =>
        set((s) => ({
          sessionStats: {
            messageCount: s.sessionStats.messageCount + 1,
            toolCallCount: s.sessionStats.toolCallCount,
            usedTools: s.sessionStats.usedTools,
            startedAt: s.sessionStats.startedAt ?? new Date().toISOString(),
          },
        })),

      recordToolCall: (name) =>
        set((s) => {
          if (s.sessionStats.usedTools.includes(name)) {
            return {
              sessionStats: {
                ...s.sessionStats,
                toolCallCount: s.sessionStats.toolCallCount + 1,
              },
            };
          }
          return {
            sessionStats: {
              ...s.sessionStats,
              toolCallCount: s.sessionStats.toolCallCount + 1,
              usedTools: [...s.sessionStats.usedTools, name],
            },
          };
        }),

      resetSession: () =>
        set(() => ({
          sessionStats: {
            messageCount: 0,
            toolCallCount: 0,
            usedTools: [],
            startedAt: null,
          },
        })),

      reset: () => set({ ...EMPTY_STATE }),
    }),
    {
      name: "ai-recruitment-agent-store",
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
      partialize: (state) => ({
        dataCards: state.dataCards,
        currentContext: state.currentContext,
      }),
      version: 1,
    }
  )
);

// ── Selectors ──

export const selectUnreadCardCount = (s: AgentStoreState): number =>
  s.dataCards.filter((c) => !c.isRead).length;

export const selectLatestCards =
  (limit: number) =>
  (s: AgentStoreState): DataCard[] =>
    s.dataCards.slice(0, limit);
