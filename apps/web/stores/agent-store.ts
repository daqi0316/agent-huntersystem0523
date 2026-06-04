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
 */

import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import { immer } from "zustand/middleware/immer";
import type {
  ChatMessage,
  OperationPanelState,
} from "@/types/chat";
import type { UploadedFile } from "@/hooks/useResumeUpload";

// ── Types ──

export type DataCardType =
  | "candidate_list" // 候选人列表（JsonPreview 中前 5 个）
  | "dashboard_stats" // 看板数据（get_dashboard_stats）
  | "search_result" // 搜索结果
  | "evaluation" // 评估结果（含 overall_score）
  | "jd" // JD 内容（jd_content）
  | "interview_schedule" // 面试安排
  | "other"; // 兜底

export interface DataCard {
  id: string;
  type: DataCardType;
  title: string; // 卡片标题（用于缩略按钮 tooltip）
  summary: string; // 简短摘要（用于缩略按钮副标题）
  payload: unknown; // 原始数据（结构化）
  toolName?: string; // 来源工具名
  messageId?: string; // 来源消息 ID（可关联）
  createdAt: string;
  isRead: boolean; // 缩略按钮未读徽章用
}

export interface ChatContext {
  currentCandidateIds: string[]; // 最近讨论的候选人 ID 列表
  currentJobIds: string[]; // 最近讨论的职位 ID 列表
  recentTopic: string; // 最近的话题
  lastToolUsed?: string; // 最近一次工具调用名
}

export interface ApprovalState {
  visible: boolean;
  approval_id: string;
  summary: string;
  loading: boolean;
}

export interface AgentStoreState {
  // ── 消息（当前仍由 useChatMessages 内部管理，本字段预留给 Phase 0.3 迁移） ──
  messages: ChatMessage[];

  // ── 数据卡片（Phase 0.4 填充；Phase 1 缩略按钮读取） ──
  dataCards: DataCard[];

  // ── 上下文（Phase 2 上下文感知） ──
  currentContext: ChatContext;

  // ── 审批状态（Phase 0.3 从 useChatStream 迁入） ──
  approval: ApprovalState;

  // ── 当前附件（Phase 0.3 从 ChatInput 迁入，可选） ──
  attachment: UploadedFile | null;

  // ── 最近工具调用（用于错误时回填到 OperationPanel） ──
  lastToolCalls: Array<{
    name: string;
    args: Record<string, unknown>;
    error?: string | null;
    needs_human?: boolean;
  }>;

  // ── 操作面板状态（Phase 0.3 从 useChatStream 迁入） ──
  operationPanel: OperationPanelState;

  // ── Actions: messages ──
  setMessages: (messages: ChatMessage[]) => void;
  addMessage: (message: ChatMessage) => void;
  clearMessages: () => void;

  // ── Actions: dataCards ──
  addCard: (card: Omit<DataCard, "id" | "createdAt" | "isRead">) => void;
  removeCard: (id: string) => void;
  markCardRead: (id: string) => void;
  clearCards: () => void;

  // ── Actions: context ──
  setCurrentContext: (ctx: Partial<ChatContext>) => void;
  resetContext: () => void;

  // ── Actions: approval ──
  setApproval: (approval: ApprovalState) => void;
  resetApproval: () => void;

  // ── Actions: attachment ──
  setAttachment: (file: UploadedFile | null) => void;

  // ── Actions: lastToolCalls ──
  setLastToolCalls: (
    calls: Array<{
      name: string;
      args: Record<string, unknown>;
      error?: string | null;
      needs_human?: boolean;
    }>
  ) => void;

  // ── Actions: operationPanel ──
  setOperationPanel: (state: OperationPanelState) => void;
  closeOperationPanel: () => void;

  // ── 全局重置 ──
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

// ── Store ──

export const useAgentStore = create<AgentStoreState>()(
  persist(
    immer((set) => ({
      messages: [],
      dataCards: [],
      currentContext: INITIAL_CONTEXT,
      approval: INITIAL_APPROVAL,
      attachment: null,
      lastToolCalls: [],
      operationPanel: INITIAL_OPERATION_PANEL,

      // ── messages ──
      setMessages: (messages) =>
        set((s) => {
          s.messages = messages;
        }),
      addMessage: (message) =>
        set((s) => {
          s.messages.push(message);
        }),
      clearMessages: () =>
        set((s) => {
          s.messages = [];
        }),

      // ── dataCards ──
      addCard: (card) =>
        set((s) => {
          s.dataCards.unshift({
            ...card,
            id:
              typeof crypto !== "undefined" && crypto.randomUUID
                ? `card_${crypto.randomUUID().slice(0, 8)}`
                : `card_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
            createdAt: new Date().toISOString(),
            isRead: false,
          });
          // 限制最大 50 张（避免内存膨胀）
          if (s.dataCards.length > 50) {
            s.dataCards = s.dataCards.slice(0, 50);
          }
        }),
      removeCard: (id) =>
        set((s) => {
          s.dataCards = s.dataCards.filter((c: DataCard) => c.id !== id);
        }),
      markCardRead: (id) =>
        set((s) => {
          const c = s.dataCards.find((x: DataCard) => x.id === id);
          if (c) c.isRead = true;
        }),
      clearCards: () =>
        set((s) => {
          s.dataCards = [];
        }),

      // ── context ──
      setCurrentContext: (ctx) =>
        set((s) => {
          s.currentContext = { ...s.currentContext, ...ctx };
        }),
      resetContext: () =>
        set((s) => {
          s.currentContext = INITIAL_CONTEXT;
        }),

      // ── approval ──
      setApproval: (approval) =>
        set((s) => {
          s.approval = approval;
        }),
      resetApproval: () =>
        set((s) => {
          s.approval = INITIAL_APPROVAL;
        }),

      // ── attachment ──
      setAttachment: (file) =>
        set((s) => {
          s.attachment = file;
        }),

      // ── lastToolCalls ──
      setLastToolCalls: (calls) =>
        set((s) => {
          s.lastToolCalls = calls;
        }),

      // ── operationPanel ──
      setOperationPanel: (state) =>
        set((s) => {
          s.operationPanel = state;
        }),
      closeOperationPanel: () =>
        set((s) => {
          s.operationPanel = INITIAL_OPERATION_PANEL;
        }),

      // ── 全局重置 ──
      reset: () =>
        set((s) => {
          s.messages = [];
          s.dataCards = [];
          s.currentContext = INITIAL_CONTEXT;
          s.approval = INITIAL_APPROVAL;
          s.attachment = null;
          s.lastToolCalls = [];
          s.operationPanel = INITIAL_OPERATION_PANEL;
        }),
    })),
    {
      name: "ai-recruitment-agent-store",
      storage: createJSONStorage(() => {
        // SSR-safe：服务端没有 localStorage
        if (typeof window === "undefined") {
          return {
            getItem: () => null,
            setItem: () => undefined,
            removeItem: () => undefined,
          };
        }
        return localStorage;
      }),
      // 持久化白名单：只持久化需要跨刷新的状态
      partialize: (state) => ({
        dataCards: state.dataCards,
        currentContext: state.currentContext,
        // messages 由 useChatMessages 独立持久化（避免重复）
        // approval / attachment / operationPanel / lastToolCalls 是临时状态
      }),
      version: 1,
    }
  )
);

// ── Selectors（避免不必要的 re-render） ──

export const selectUnreadCardCount = (s: AgentStoreState): number =>
  s.dataCards.filter((c) => !c.isRead).length;

export const selectLatestCards = (limit: number) => (s: AgentStoreState): DataCard[] =>
  s.dataCards.slice(0, limit);
