/**
 * Data Card Parser — 单元测试（node:test，零额外依赖）
 *
 * 运行：node --import tsx --test apps/web/lib/chat/data-card-parser.test.ts
 * 或：  npx tsx --test apps/web/lib/chat/data-card-parser.test.ts
 *
 * 若项目后续引入 vitest/jest，可直接重命名为 *.test.ts 并复用。
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import {
  parseDataCardsFromMessage,
  parseDataCardsFromMessages,
} from "./data-card-parser";
import type { ChatMessage } from "@/types/chat";

function makeMsg(
  role: "user" | "assistant",
  content: string,
  toolName?: string
): ChatMessage {
  return {
    id: `test_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
    createdAt: new Date().toISOString(),
    role,
    content,
    tool_calls: toolName
      ? [{ name: toolName, args: {}, error: null, needs_human: false }]
      : undefined,
  };
}

test("candidate_list: 数组含 name 字段被识别", () => {
  const msg = makeMsg(
    "assistant",
    '```json\n[{"name":"张三","current_title":"前端"},{"name":"李四"}]\n```',
    "search_candidates"
  );
  const cards = parseDataCardsFromMessage(msg);
  assert.equal(cards.length, 1);
  assert.equal(cards[0].type, "candidate_list");
  assert.equal(cards[0].title, "候选人列表 (2)");
  assert.equal(cards[0].summary, "张三 等 2 人");
  assert.equal(cards[0].toolName, "search_candidates");
});

test("dashboard_stats: 看板字段被识别", () => {
  const msg = makeMsg(
    "assistant",
    '```json\n{"total_candidates":42,"total_jobs":5,"active_interviews":3}\n```',
    "get_dashboard_stats"
  );
  const cards = parseDataCardsFromMessage(msg);
  assert.equal(cards.length, 1);
  assert.equal(cards[0].type, "dashboard_stats");
  assert.equal(cards[0].title, "招聘看板数据");
  assert.equal(cards[0].summary, "42 候选人 · 5 职位 · 3 待面试");
});

test("evaluation: overall_score 字段被识别", () => {
  const msg = makeMsg(
    "assistant",
    '```json\n{"overall_score":85,"summary":"匹配度较高"}\n```',
    "screen_resume"
  );
  const cards = parseDataCardsFromMessage(msg);
  assert.equal(cards.length, 1);
  assert.equal(cards[0].type, "evaluation");
  assert.equal(cards[0].summary, "匹配度 85 分");
});

test("jd: jd_content 字段被识别", () => {
  const msg = makeMsg(
    "assistant",
    '```json\n{"title":"高级前端","jd_content":"..."}\n```',
    "generate_jd"
  );
  const cards = parseDataCardsFromMessage(msg);
  assert.equal(cards.length, 1);
  assert.equal(cards[0].type, "jd");
  assert.equal(cards[0].summary, "高级前端");
});

test("interview_schedule: interview_id 字段被识别", () => {
  const msg = makeMsg(
    "assistant",
    '```json\n{"interview_id":"int_001","scheduled_at":"2026-06-10T10:00:00Z"}\n```',
    "schedule_interview"
  );
  const cards = parseDataCardsFromMessage(msg);
  assert.equal(cards.length, 1);
  assert.equal(cards[0].type, "interview_schedule");
});

test("tool hint 优先于内容字段识别", () => {
  const msg = makeMsg(
    "assistant",
    '```json\n{"some_unknown_field":"value"}\n```',
    "get_dashboard_stats"
  );
  const cards = parseDataCardsFromMessage(msg);
  assert.equal(cards.length, 1);
  assert.equal(cards[0].type, "dashboard_stats");
});

test("'other' 类型不产生卡片（噪音过滤）", () => {
  const msg = makeMsg("assistant", "只是一段普通文本回答");
  const cards = parseDataCardsFromMessage(msg);
  assert.equal(cards.length, 0);
});

test("user 消息不解析", () => {
  const msg = makeMsg("user", '```json\n[{"name":"x"}]\n```');
  const cards = parseDataCardsFromMessage(msg);
  assert.equal(cards.length, 0);
});

test("error 消息不解析", () => {
  const msg: ChatMessage = {
    id: "test_error_msg",
    createdAt: new Date().toISOString(),
    role: "assistant",
    content: "```json\n[{\"name\":\"x\"}]\n```",
    error: true,
  };
  const cards = parseDataCardsFromMessage(msg);
  assert.equal(cards.length, 0);
});

test("非法 JSON 静默跳过", () => {
  const msg = makeMsg("assistant", "```json\n{invalid json}\n```");
  const cards = parseDataCardsFromMessage(msg);
  assert.equal(cards.length, 0);
});

test("多个 JSON 块产生多张卡片", () => {
  const msg = makeMsg(
    "assistant",
    '```json\n[{"name":"a"}]\n``` 中间文本 ```json\n{"overall_score":90}\n```'
  );
  const cards = parseDataCardsFromMessage(msg);
  assert.equal(cards.length, 2);
  assert.equal(cards[0].type, "candidate_list");
  assert.equal(cards[1].type, "evaluation");
});

test("messageId 反映 msg.id", () => {
  const msg = makeMsg(
    "assistant",
    '```json\n{"overall_score":80}\n```',
    "screen_resume"
  );
  const cards = parseDataCardsFromMessage(msg);
  assert.equal(cards.length, 1);
  const card = cards[0];
  assert.ok(card, "expected 1 card");
  assert.match(card.messageId, /^msg_test_.+_block_0$/);
});

test("parseDataCardsFromMessages 批量解析", () => {
  const msgs: ChatMessage[] = [
    makeMsg("user", "搜索候选人"),
    makeMsg(
      "assistant",
      '```json\n[{"name":"a"}]\n```',
      "search_candidates"
    ),
    makeMsg("user", "查看看板"),
    makeMsg(
      "assistant",
      '```json\n{"total_candidates":10}\n```',
      "get_dashboard_stats"
    ),
  ];
  const cards = parseDataCardsFromMessages(msgs);
  assert.equal(cards.length, 2);
  assert.equal(cards[0].type, "candidate_list");
  assert.equal(cards[1].type, "dashboard_stats");
});

test("空 content 返回空", () => {
  const msg = makeMsg("assistant", "");
  const cards = parseDataCardsFromMessage(msg);
  assert.equal(cards.length, 0);
});
