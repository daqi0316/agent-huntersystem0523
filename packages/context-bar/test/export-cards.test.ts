// T5 单元测试：URL hash 排序编码 / 导出 JSON
// 跑：corepack pnpm --filter @ai-recruitment/context-bar exec tsx --test test/export-cards.test.ts

import { test } from "node:test";
import assert from "node:assert/strict";
import { buildExportPayload, downloadJson } from "../src/export-cards";
import {
  applyHashOrder,
} from "../src/use-card-order-hash";
import type { DataCard } from "@ai-recruitment/agent-store";

const card = (id: string, createdAt: string): DataCard => ({
  id,
  type: "candidate_list",
  title: `Title ${id}`,
  summary: "",
  payload: null,
  toolName: undefined,
  messageId: `msg_${id}`,
  createdAt,
  isRead: false,
});

test("buildExportPayload 包含 sort order + filter snapshot + timestamp", () => {
  const cards = [card("a", "2026-01-01T00:00:00Z"), card("b", "2026-01-02T00:00:00Z")];
  const payload = buildExportPayload(cards, ["b", "a"], { query: "test", types: ["candidate_list"] });
  assert.equal(payload.sortOrder.length, 2);
  assert.deepEqual(payload.sortOrder, ["b", "a"]);
  assert.equal(payload.filters.query, "test");
  assert.deepEqual(payload.filters.types, ["candidate_list"]);
  assert.match(payload.exportedAt, /^\d{4}-\d{2}-\d{2}T/);
  assert.equal(payload.cards.length, 2);
});

test("buildExportPayload 仅含核心字段", () => {
  const fullCard = card("a", "2026-01-01T00:00:00Z");
  const payload = buildExportPayload([fullCard], ["a"], { query: "", types: [] });
  const cardOut = payload.cards[0];
  assert.ok("id" in cardOut);
  assert.ok("type" in cardOut);
  assert.ok("title" in cardOut);
  // 不应泄漏 isRead 或 messageId（隐私边界）
  assert.ok(!("isRead" in cardOut));
});

test("applyHashOrder 优先 hash 顺序", () => {
  const cards = [
    card("a", "2026-01-01T00:00:00Z"),
    card("b", "2026-01-02T00:00:00Z"),
    card("c", "2026-01-03T00:00:00Z"),
  ];
  const out = applyHashOrder(cards, ["c", "a", "b"]);
  assert.deepEqual(
    out.map((c) => c.id),
    ["c", "a", "b"]
  );
});

test("applyHashOrder 缺失的 cards 追加到末尾按 createdAt 倒序", () => {
  const cards = [
    card("a", "2026-01-01T00:00:00Z"),
    card("b", "2026-01-02T00:00:00Z"),
    card("c", "2026-01-03T00:00:00Z"),
  ];
  const out = applyHashOrder(cards, ["c"]); // a, b 不在 hash
  // c 优先（hash），a 和 b 按 createdAt 倒序
  assert.deepEqual(
    out.map((c) => c.id),
    ["c", "b", "a"]
  );
});

test("applyHashOrder hash 含 cards 不存在的 id 忽略", () => {
  const cards = [card("a", "2026-01-01T00:00:00Z")];
  const out = applyHashOrder(cards, ["nonexistent", "a"]);
  assert.deepEqual(
    out.map((c) => c.id),
    ["a"]
  );
});

test("applyHashOrder hash 为空/null 走默认 createdAt 倒序", () => {
  const cards = [
    card("a", "2026-01-01T00:00:00Z"),
    card("b", "2026-01-02T00:00:00Z"),
  ];
  const out1 = applyHashOrder(cards, null);
  const out2 = applyHashOrder(cards, []);
  assert.deepEqual(
    out1.map((c) => c.id),
    ["b", "a"]
  );
  assert.deepEqual(
    out2.map((c) => c.id),
    ["b", "a"]
  );
});
