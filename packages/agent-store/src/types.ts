// 共享类型 — 与 packages/types/src/chat.ts 保持同步但自带 copy，
// 避免 packages/agent-store 跨包 import（保持包自包含）。
// 字段变更时需同步更新 packages/types/src/chat.ts。

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

export interface CandidateRead {
  id: string;
  name: string;
  email: string;
  phone: string | null;
  summary: string | null;
  skills: string[];
  experience_years: number | null;
  education: string | null;
  current_company: string | null;
  current_title: string | null;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface JobRead {
  id: string;
  title: string;
  department: string | null;
  description: string | null;
  requirements: string | null;
  location: string | null;
  salary_range: string | null;
  status: string;
  created_at: string;
  updated_at: string;
}
