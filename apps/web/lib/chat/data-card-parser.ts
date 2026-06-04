/**
 * Data Card Parser — 从助手消息中提取结构化数据卡片
 *
 * 检测逻辑：
 *  1. 扫描消息 content 中的 ```json``` 代码块
 *  2. 解析每个 JSON，按字段特征识别 DataCardType
 *  3. 命中规则则产出 DataCard（type/title/summary/payload）
 *
 * 类型识别规则（与 lib/chat/render-message.tsx 保持一致）：
 *  - Array + items[].name                → candidate_list
 *  - Object + overall_score              → evaluation
 *  - Object + jd_content                 → jd
 *  - Object + total_candidates/jobs/...  → dashboard_stats
 *  - Object + interview_id/scheduled_at → interview_schedule
 *  - 其它                                → other
 */

import type { ChatMessage } from "@/types/chat";
import type { DataCard, DataCardType } from "@/stores/agent-store";

const TOOL_HINT_TO_TYPE: Record<string, DataCardType> = {
  get_dashboard_stats: "dashboard_stats",
  dashboard: "dashboard_stats",
  search_candidates: "candidate_list",
  candidate_search: "candidate_list",
  screen_resume: "evaluation",
  evaluate_resume: "evaluation",
  generate_jd: "jd",
  jd_generator: "jd",
  schedule_interview: "interview_schedule",
  get_schedule: "interview_schedule",
  get_upcoming_interviews: "interview_schedule",
};

function extractJsonBlocks(content: string): string[] {
  const blocks: string[] = [];
  content.replace(
    /```(?:json)?\s*([\s\S]*?)```/g,
    (_, json: string) => {
      blocks.push(json.trim());
      return "";
    }
  );
  return blocks;
}

function detectType(
  data: unknown,
  toolHint?: string
): DataCardType {
  if (toolHint && TOOL_HINT_TO_TYPE[toolHint]) {
    return TOOL_HINT_TO_TYPE[toolHint];
  }

  if (Array.isArray(data) && data.length > 0) {
    const first = data[0] as Record<string, unknown>;
    if (first && typeof first === "object" && "name" in first) {
      return "candidate_list";
    }
  }

  if (data && typeof data === "object") {
    const d = data as Record<string, unknown>;
    if ("overall_score" in d) return "evaluation";
    if ("jd_content" in d) return "jd";
    if (
      "total_candidates" in d ||
      "total_jobs" in d ||
      "active_interviews" in d
    ) {
      return "dashboard_stats";
    }
    if ("interview_id" in d || "scheduled_at" in d) {
      return "interview_schedule";
    }
  }

  return "other";
}

function buildTitle(type: DataCardType, data: unknown): string {
  switch (type) {
    case "candidate_list": {
      if (Array.isArray(data)) {
        return `候选人列表 (${data.length})`;
      }
      return "候选人列表";
    }
    case "dashboard_stats":
      return "招聘看板数据";
    case "evaluation":
      return "简历评估结果";
    case "jd":
      return "职位描述 (JD)";
    case "interview_schedule":
      return "面试安排";
    default:
      return "数据卡片";
  }
}

function buildSummary(type: DataCardType, data: unknown): string {
  if (type === "candidate_list" && Array.isArray(data)) {
    const first = data[0] as Record<string, unknown> | undefined;
    if (first?.name) {
      const more = data.length > 1 ? ` 等 ${data.length} 人` : "";
      return `${first.name}${more}`;
    }
  }

  if (type === "evaluation" && data && typeof data === "object") {
    const d = data as Record<string, unknown>;
    const score = d.overall_score;
    if (typeof score === "number") return `匹配度 ${score} 分`;
  }

  if (type === "jd" && data && typeof data === "object") {
    const d = data as Record<string, unknown>;
    if (typeof d.title === "string") return d.title;
  }

  if (type === "dashboard_stats" && data && typeof data === "object") {
    const d = data as Record<string, unknown>;
    const parts: string[] = [];
    if (typeof d.total_candidates === "number") {
      parts.push(`${d.total_candidates} 候选人`);
    }
    if (typeof d.total_jobs === "number") {
      parts.push(`${d.total_jobs} 职位`);
    }
    if (typeof d.active_interviews === "number") {
      parts.push(`${d.active_interviews} 待面试`);
    }
    if (parts.length > 0) return parts.join(" · ");
  }

  return "";
}

function cardFromData(
  data: unknown,
  toolHint: string | undefined,
  blockIdx: number,
  messageIdx: number
): DataCard | null {
  if (data == null) return null;

  const type = detectType(data, toolHint);
  if (type === "other") return null;

  return {
    id: "",
    type,
    title: buildTitle(type, data),
    summary: buildSummary(type, data),
    payload: data,
    toolName: toolHint,
    messageId: `msg_${messageIdx}_block_${blockIdx}`,
    createdAt: "",
    isRead: false,
  };
}

export function parseDataCardsFromMessage(
  msg: ChatMessage,
  messageIdx: number
): Omit<DataCard, "id" | "createdAt" | "isRead">[] {
  if (msg.role !== "assistant") return [];
  if (msg.error) return [];

  const toolHint = msg.tool_calls?.[0]?.name;
  const blocks = extractJsonBlocks(msg.content);
  if (blocks.length === 0) return [];

  const cards: Omit<DataCard, "id" | "createdAt" | "isRead">[] = [];
  for (let i = 0; i < blocks.length; i++) {
    let parsed: unknown;
    try {
      parsed = JSON.parse(blocks[i]);
    } catch {
      continue;
    }
    const card = cardFromData(parsed, toolHint, i, messageIdx);
    if (card) cards.push(card);
  }
  return cards;
}

export function parseDataCardsFromMessages(
  messages: ChatMessage[]
): Omit<DataCard, "id" | "createdAt" | "isRead">[] {
  const out: Omit<DataCard, "id" | "createdAt" | "isRead">[] = [];
  messages.forEach((m, idx) => {
    out.push(...parseDataCardsFromMessage(m, idx));
  });
  return out;
}
