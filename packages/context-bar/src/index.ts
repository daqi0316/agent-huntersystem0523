/**
 * @ai-recruitment/context-bar — 公共 API 入口（facade）
 *
 * 当前所有实现仍在 apps/web 内部，本文件仅 re-export。
 * 未来如需真正独立打包：将 apps/web/components/common/context-bar、
 * hooks/chat/use-{agent-event-stream,global-shortcut}、
 * lib/chat/{data-card-parser,tool-labels,render-message}、
 * stores/agent-store 整体迁入 src/，然后本 facade 改为 named exports。
 */

export { ContextBar } from "@/components/common/context-bar";
export { useAgentStore, selectUnreadCardCount } from "@/stores/agent-store";
export type {
  DataCard,
  DataCardType,
  ChatContext,
  ApprovalState,
  OperationPanelState,
  AgentStoreState,
  SessionStats,
} from "@/stores/agent-store";
export {
  parseDataCardsFromMessage,
  parseDataCardsFromMessages,
} from "@/lib/chat/data-card-parser";
export { TOOL_LABELS, toolLabel } from "@/lib/chat/tool-labels";
export { renderRichContent } from "@/lib/chat/render-message";
export { useGlobalShortcut } from "@/hooks/chat/use-global-shortcut";
export {
  initAgentEventStream,
  AgentEventStreamBridge,
} from "@/hooks/chat/use-agent-event-stream";
