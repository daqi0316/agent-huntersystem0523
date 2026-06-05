/**
 * useAgentContext — 自动从消息流中追踪"当前在讨论什么"
 *
 * 提取规则：
 *  - currentCandidateIds: 扫描所有 tool_calls.args 中形如 candidate_id / candidateId 的字段
 *  - currentJobIds: 同上，针对 job_id / jobId / position_id
 *  - recentTopic: 最近一条 user 消息的前 30 字符
 *  - lastToolUsed: 最近一条 assistant 消息中第一个具名 tool_call
 *
 * 调用方：在 /agent 页面挂一次，订阅 messages 即可
 *   const { messages, ... } = useChatMessages();
 *   useAgentContext(messages);
 *
 * 写入目标：agent-store.currentContext（持久化、跨页面、跨刷新）
 * 缩略按钮可订阅此字段，显示"正在讨论 X"
 */

"use client";

import { useEffect, useRef } from "react";
import { useAgentStore } from "@ai-recruitment/agent-store";
import type { ChatMessage } from "@/types/chat";

const TOPIC_LIMIT = 30;
const CANDIDATE_ID_KEY_RE = /(candidate|candid)/i;
const JOB_ID_KEY_RE = /(job[_-]?id|position[_-]?id|positionid)/i;
const CONTEXT_HISTORY_LIMIT = 20;

function extractIdsFromArgs(
  args: Record<string, unknown> | undefined
): { candidateIds: string[]; jobIds: string[] } {
  const candidateIds: string[] = [];
  const jobIds: string[] = [];
  if (!args) return { candidateIds, jobIds };

  for (const [k, v] of Object.entries(args)) {
    if (typeof v !== "string" || !v) continue;
    if (CANDIDATE_ID_KEY_RE.test(k)) candidateIds.push(v);
    if (JOB_ID_KEY_RE.test(k)) jobIds.push(v);
  }
  return { candidateIds, jobIds };
}

function dedupPreserveOrder(items: string[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const it of items) {
    if (!seen.has(it)) {
      seen.add(it);
      out.push(it);
    }
  }
  return out;
}

export function useAgentContext(messages: ChatMessage[]): void {
  const lastProcessedIdx = useRef(-1);
  const setCurrentContext = useAgentStore((s) => s.setCurrentContext);

  useEffect(() => {
    if (messages.length === 0) {
      setCurrentContext({
        currentCandidateIds: [],
        currentJobIds: [],
        recentTopic: "",
        lastToolUsed: undefined,
      });
      lastProcessedIdx.current = -1;
      return;
    }

    const start = Math.max(0, lastProcessedIdx.current + 1);
    if (start >= messages.length) return;

    const candidateIds: string[] = [];
    const jobIds: string[] = [];
    let recentTopic = "";
    let lastToolUsed: string | undefined;

    const window = messages.slice(
      Math.max(0, messages.length - CONTEXT_HISTORY_LIMIT)
    );

    for (const msg of window) {
      if (msg.role === "user" && msg.content) {
        recentTopic = msg.content.slice(0, TOPIC_LIMIT);
      }
      if (msg.role === "assistant" && msg.error) continue;
      for (const tc of msg.tool_calls || []) {
        if (!tc.name) continue;
        lastToolUsed = tc.name;
        const ext = extractIdsFromArgs(tc.args);
        candidateIds.push(...ext.candidateIds);
        jobIds.push(...ext.jobIds);
      }
    }

    setCurrentContext({
      currentCandidateIds: dedupPreserveOrder(candidateIds).slice(0, 20),
      currentJobIds: dedupPreserveOrder(jobIds).slice(0, 20),
      recentTopic,
      lastToolUsed,
    });

    lastProcessedIdx.current = messages.length - 1;
  }, [messages, setCurrentContext]);
}
