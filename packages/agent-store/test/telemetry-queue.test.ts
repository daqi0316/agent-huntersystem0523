// T6 埋点队列单元测试
// 跑：cd packages/agent-store && npx tsx --test test/telemetry-queue.test.ts

import { test, beforeEach } from "node:test";
import assert from "node:assert/strict";
import {
  createTelemetryQueue,
  __resetTelemetryStateForTests,
} from "../src/telemetry-queue";

beforeEach(() => {
  __resetTelemetryStateForTests();
});

function makeFetch(impl: (url: string, init?: RequestInit) => Promise<Response> | Response) {
  return ((url: string, init?: RequestInit) => {
    const p = Promise.resolve(impl(url, init));
    return p as unknown as Promise<Response>;
  }) as unknown as typeof fetch;
}

test("track 接受合法事件并入队", async () => {
  const q = createTelemetryQueue();
  q.track("drawer_open", { source: "chip" });
  assert.equal(q.size(), 1);
  q.destroy();
});

test("track 拒绝未知事件名（白名单）", async () => {
  const q = createTelemetryQueue();
  q.track("malicious_event_xx", { source: "x" });
  assert.equal(q.size(), 0);
  q.destroy();
});

test("track 过滤未知 props 字段", async () => {
  const fetchCalls: Array<{ url: string; body: string }> = [];
  (globalThis as any).fetch = makeFetch((url, init) => {
    fetchCalls.push({ url, body: String(init?.body ?? "") });
    return new Response("{}", { status: 200 });
  });
  const q = createTelemetryQueue();
  q.track("drawer_open", { source: "chip", unknown_field: "x", evil: 1 } as any);
  void q.flush();
  await new Promise((r) => setTimeout(r, 50));
  assert.equal(fetchCalls.length, 1);
  const body = JSON.parse(fetchCalls[0].body);
  assert.equal(body.events[0].props.source, "chip");
  assert.equal(body.events[0].props.unknown_field, undefined);
  assert.equal(body.events[0].props.evil, undefined);
  q.destroy();
});

test("throttle: 相同 event 500ms 内只发 1 次", async () => {
  const q = createTelemetryQueue();
  q.track("drawer_open", { source: "chip" });
  q.track("drawer_open", { source: "chip" });
  q.track("drawer_open", { source: "chip" });
  assert.equal(q.size(), 1);
  q.destroy();
});

test("flush 发送 queued events 给后端", async () => {
  const fetchCalls: string[] = [];
  (globalThis as any).fetch = makeFetch((_url, init) => {
    fetchCalls.push(String(init?.body ?? ""));
    return new Response('{"accepted":1}', { status: 200 });
  });
  const q = createTelemetryQueue();
  q.track("drawer_open", { source: "chip" });
  q.track("search_use", { result_count: 3 });
  assert.equal(q.size(), 2);
  await q.flush();
  await new Promise((r) => setTimeout(r, 30));
  assert.equal(fetchCalls.length, 1);
  const body = JSON.parse(fetchCalls[0]);
  assert.equal(body.events.length, 2);
  assert.equal(body.events[0].event, "drawer_open");
  assert.equal(body.events[1].event, "search_use");
  assert.equal(q.size(), 0);
  q.destroy();
});

test("flush 失败时 fetch 仍被调用", async () => {
  let calls = 0;
  (globalThis as any).fetch = makeFetch(() => {
    calls += 1;
    return Promise.resolve(new Response("err", { status: 500 }));
  });
  const q = createTelemetryQueue();
  q.track("drawer_open", { source: "chip" });
  await q.flush();
  assert.equal(calls, 1);
  q.destroy();
});

test("MAX_QUEUE_SIZE 上限：超出截断最早", async () => {
  const q = createTelemetryQueue();
  for (let i = 0; i < 250; i += 1) {
    q.track("card_view", { card_type: "x" });
  }
  assert.ok(q.size() <= 200);
  q.destroy();
});

test("destroy 后 track 无效", async () => {
  const q = createTelemetryQueue();
  q.destroy();
  q.track("drawer_open", { source: "chip" });
  assert.equal(q.size(), 0);
});

test("destroy 后不再触发 flush timer", async () => {
  let called = 0;
  (globalThis as any).fetch = makeFetch(() => {
    called += 1;
    return new Response("{}", { status: 200 });
  });
  const q = createTelemetryQueue();
  q.track("drawer_open", { source: "chip" });
  q.destroy();
  await new Promise((r) => setTimeout(r, 5500));
  assert.equal(called, 0);
});
