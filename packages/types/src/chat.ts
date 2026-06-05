// ── Agent Chat types（共享给 @ai-recruitment/agent-store 和 @ai-recruitment/context-bar）──
// 从 apps/web/types/chat.ts 提取，让 store / 解析器 / UI 包独立可消费。

export interface ToolCallInfo {
  name: string;
  args: Record<string, unknown>;
  error?: string | null;
  needs_human?: boolean;
}

export interface AgentActionInfo {
  agent: string;
  status: string;
  summary: string;
  approval_id?: string;
}

export interface ChatMessage {
  id: string;
  createdAt: string;
  role: "user" | "assistant";
  content: string;
  tool_calls?: ToolCallInfo[];
  agent_actions?: AgentActionInfo[];
  error?: boolean;
  model?: string;
}

export function newMessage(
  role: "user" | "assistant",
  content: string,
  extra: Partial<ChatMessage> = {}
): ChatMessage {
  return {
    id:
      typeof crypto !== "undefined" && crypto.randomUUID
        ? crypto.randomUUID()
        : `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`,
    createdAt: new Date().toISOString(),
    role,
    content,
    ...extra,
  };
}

export interface AgentChatResponse {
  success: boolean;
  reply: string;
  tool_calls: ToolCallInfo[];
  agent_actions?: AgentActionInfo[];
  model?: string;
}

export interface ApprovalState {
  visible: boolean;
  approval_id: string;
  summary: string;
  loading: boolean;
}

export interface MemoryFact {
  id: string;
  fact_type: string;
  verb: string;
  object_value: Record<string, unknown> | null;
  created_at: string;
}

export interface OperationPanelState {
  open: boolean;
  errorMessage?: string;
  operationType?: string;
  operationInput?: Record<string, unknown>;
  needsHuman?: boolean;
}

export interface UploadedFile {
  file_url: string;
  filename: string;
  file_size: number;
  file_type: string;
}

// ── Context Bar types (DataCard / ChatContext / SessionStats) ──
// 从 agent-store 提取，独立可消费。

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

export interface SessionStats {
  messageCount: number;
  toolCallCount: number;
  usedTools: string[];
  startedAt: string | null;
}
