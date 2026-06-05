/**
 * Agent Store — 统一管理 AI 助手页面的全局状态
 *
 * 设计原则：
 *  - useChatMessages 内部仍用 useState + localStorage（行为兼容，Phase 0.1 已 commit）
 *  - 本 store 作为**扩展层**，承载：
 *      · dataCards  (Phase 0.4 填充)
 *      · currentContext (Phase 2 上下文感知)
 *      · approval / attachment / operationPanel (Phase 0.3/0.4 接入 useChatStream)
 *  - persist 中间件开启，跨页面 + 跨刷新保留
 *  - 不与 useChatMessages 冲突：messages 走 hook 内部，dataCards 走 store
 *
 * 用法（Phase 1 缩略按钮接入示例）：
 *   const cards = useAgentStore(s => s.dataCards);
 *   const addCard = useAgentStore(s => s.addCard);
 *
 * 注意：不使用 immer 中间件（避免新增 immer 依赖），改用 spread 模式手动不可变更新。
 */

import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import type {
  ChatMessage,
  OperationPanelState,
} from "@/types/chat";
import type { UploadedFile } from "@/hooks/useResumeUpload";

// ── Types ──

export type DataCardType =
  | "candidate_list"
  | "dashboard_stats"
  | "search_result"
  | "evaluation"
  | "jd"
  | "interview_schedule"
  | "other";

export interface DataCard {
  id: string;
  type: DataCardType;
  title: string;
  summary: string;
  payload: unknown;
  toolName?: string;
  messageId: string;
  createdAt: string;
  isRead: boolean;
}

export interface ChatContext {
  currentCandidateIds: string[];
  currentJobIds: string[];
  recentTopic: string;
  lastToolUsed?: string;
}

export interface ApprovalState {
  visible: boolean;
  approval_id: string;
  summary: string;
  loading: boolean;
}

export interface SessionStats {
  messageCount: number;
  toolCallCount: number;
  usedTools: string[];
  startedAt: string | null;
}

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
  },
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
        set((s) => ({
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
