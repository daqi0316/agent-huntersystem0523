/**
 * @ai-recruitment/context-bar — 公共 API 入口
 *
 * 真正独立的 npm 包（T1 完成）。所有实现从 apps/web/components/common/context-bar
 * 迁入 src/，apps/web 通过 `import { ContextBar } from "@ai-recruitment/context-bar"` 消费。
 *
 * 工业级 / 全局规划：
 *  - 包内组件不直接依赖 @/lib/trpc 等 host 私有路径；业务回调（审批等）由 host 通过
 *    ContextBar props 注入
 *  - peerDeps 包含所有运行时依赖（react/zustand/next/lucide-react/clsx/tailwind-merge）
 *  - dual ESM + CJS + .d.ts；sideEffects: false 支持 tree-shaking
 */

export { ContextBar } from "./index.tsx";
export type { ContextBarProps } from "./index.tsx";

export { ContextChip } from "./context-chip";
export { ContextDrawer } from "./context-drawer";
export { DataCardItem } from "./data-card-item";
export { CurrentContextSection } from "./current-context-section";
export { PendingApprovalSection } from "./pending-approval-section";
export type { PendingApprovalSectionProps } from "./pending-approval-section";
export { QuickActionsSection } from "./quick-actions-section";
export { RecentActivitySection } from "./recent-activity-section";
export { SearchBar, filterCards, EMPTY_FILTERS } from "./search-bar";
export { SessionStatsSection } from "./session-stats-section";
export { useGlobalShortcut } from "./use-global-shortcut";
export { NotificationsSection } from "./notifications/notifications-section";
export { useBrowserNotification } from "./notifications/use-browser-notification";

export {
  useAgentStore,
  selectUnreadCardCount,
  selectLatestCards,
  useNotificationsStore,
  selectUnreadNotificationCount,
} from "@ai-recruitment/agent-store";
export type {
  AgentStoreState,
  DataCard,
  DataCardType,
  ChatContext,
  ApprovalState,
  OperationPanelState,
  SessionStats,
  ChatMessage,
  UploadedFile,
  ToolCallInfo,
  AgentActionInfo,
  AgentChatResponse,
  MemoryFact,
  Notification,
  NotificationKind,
  NotificationsStoreState,
} from "@ai-recruitment/agent-store";
export { newMessage } from "@ai-recruitment/agent-store";

export { TOOL_LABELS, toolLabel } from "@ai-recruitment/agent-store/tool-labels";

export {
  parseDataCardsFromMessage,
  parseDataCardsFromMessages,
} from "@ai-recruitment/agent-store/parser";
