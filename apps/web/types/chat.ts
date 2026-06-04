// ── Agent Chat types ──
// Extracted from apps/web/app/(dashboard)/agent/page.tsx during refactor.
// All consumers must use these types (no in-place definitions).

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
