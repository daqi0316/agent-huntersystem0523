// T6 埋点队列 — 工业级 / 全局规划 / 稳定开发
//
// 设计原则：
// - 节流：相同 event name 500ms 内最多 1 次（防抖，防误触连点）
// - 批量：每 5s 或队列 ≥ 20 条时 flush
// - 退避：失败重试 3 次（exponential 1s/2s/4s）
// - 卸载：pagehide / visibilitychange hidden 时 sendBeacon flush（保留数据）
// - PII 安全：所有事件先过白名单（后端再过一道，前端尽早 fail-fast）

import type { TelemetryEvent } from "./telemetry-types";

const FLUSH_INTERVAL_MS = 5_000;
const FLUSH_BATCH_SIZE = 20;
const THROTTLE_MS = 500;
const MAX_RETRY = 3;
const BACKOFF_BASE_MS = 1_000;
const MAX_QUEUE_SIZE = 200;

const ALLOWED_EVENTS = new Set<string>([
  "drawer_open",
  "drawer_close",
  "card_view",
  "card_export",
  "search_use",
  "hash_order_change",
  "drag_drop",
  "keyboard_nav",
  "approval_action",
  "notification_view",
]);

const ALLOWED_PROPS = new Set<string>([
  "card_type",
  "duration_ms",
  "success",
  "source",
  "result_count",
]);

export interface TelemetryQueue {
  track: (event: string, props?: Record<string, unknown>) => void;
  flush: () => Promise<void>;
  destroy: () => void;
  size: () => number;
}

interface QueuedEvent {
  event: string;
  props: Record<string, unknown> | null;
  ts: number;
  retries: number;
}

const _seen: Map<string, number> = new Map();
const _queue: QueuedEvent[] = [];
let _flushTimer: ReturnType<typeof setTimeout> | null = null;
let _destroyed = false;
let _endpoint = "/api/v1/agent/telemetry";

function _sanitize(event: string, props?: Record<string, unknown>): QueuedEvent | null {
  if (!ALLOWED_EVENTS.has(event)) {
    if (typeof console !== "undefined") {
      console.warn(`[telemetry] unknown event: ${event}`);
    }
    return null;
  }
  if (!props) {
    return { event, props: null, ts: Date.now(), retries: 0 };
  }
  const sanitized: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(props)) {
    if (!ALLOWED_PROPS.has(k)) continue;
    if (typeof v === "string" && v.length > 256) continue;
    sanitized[k] = v;
  }
  return { event, props: sanitized, ts: Date.now(), retries: 0 };
}

function _shouldThrottle(event: string): boolean {
  const now = Date.now();
  const last = _seen.get(event) ?? 0;
  if (now - last < THROTTLE_MS) return true;
  _seen.set(event, now);
  return false;
}

function _scheduleFlush(): void {
  if (_flushTimer || _destroyed) return;
  _flushTimer = setTimeout(() => {
    _flushTimer = null;
    void _flush("timer");
  }, FLUSH_INTERVAL_MS);
}

async function _send(events: QueuedEvent[]): Promise<boolean> {
  if (events.length === 0) return true;
  const payload = {
    events: events.map((e) => ({ event: e.event, props: e.props ?? {}, ts: e.ts / 1000 })),
  };
  try {
    const res = await fetch(_endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      credentials: "include",
    });
    return res.ok;
  } catch {
    return false;
  }
}

function _sendBeacon(events: QueuedEvent[]): boolean {
  if (events.length === 0) return true;
  if (typeof navigator === "undefined" || !navigator.sendBeacon) return false;
  const payload = JSON.stringify({
    events: events.map((e) => ({ event: e.event, props: e.props ?? {}, ts: e.ts / 1000 })),
  });
  try {
    return navigator.sendBeacon(
      _endpoint,
      new Blob([payload], { type: "application/json" })
    );
  } catch {
    return false;
  }
}

async function _flush(reason: "timer" | "size" | "manual" | "unload"): Promise<void> {
  if (_queue.length === 0) return;
  const batch = _queue.splice(0, FLUSH_BATCH_SIZE);
  const success = reason === "unload" ? _sendBeacon(batch) : await _send(batch);

  if (!success && reason !== "unload") {
    for (const evt of batch) {
      if (evt.retries < MAX_RETRY) {
        evt.retries += 1;
        const delay = BACKOFF_BASE_MS * Math.pow(2, evt.retries - 1);
        setTimeout(() => {
          if (_destroyed) return;
          _queue.push(evt);
          _scheduleFlush();
        }, delay);
      }
    }
  }

  if (_queue.length > 0) _scheduleFlush();
}

function _onPageHide(): void {
  void _flush("unload");
}

export function createTelemetryQueue(): TelemetryQueue {
  if (typeof window !== "undefined") {
    window.addEventListener("pagehide", _onPageHide);
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "hidden") void _flush("unload");
    });
  }

  return {
    track(event, props) {
      if (_destroyed) return;
      if (_shouldThrottle(event)) return;
      const evt = _sanitize(event, props);
      if (!evt) return;
      if (_queue.length >= MAX_QUEUE_SIZE) {
        _queue.splice(0, _queue.length - MAX_QUEUE_SIZE + 1);
      }
      _queue.push(evt);
      if (_queue.length >= FLUSH_BATCH_SIZE) {
        void _flush("size");
      } else {
        _scheduleFlush();
      }
    },
    flush: () => _flush("manual"),
    destroy() {
      _destroyed = true;
      if (_flushTimer) {
        clearTimeout(_flushTimer);
        _flushTimer = null;
      }
      if (typeof window !== "undefined") {
        window.removeEventListener("pagehide", _onPageHide);
      }
    },
    size: () => _queue.length,
  };
}

let _singleton: TelemetryQueue | null = null;
export function getTelemetryQueue(): TelemetryQueue {
  if (!_singleton) _singleton = createTelemetryQueue();
  return _singleton;
}

export function setTelemetryEndpoint(url: string): void {
  _endpoint = url;
}

export function __resetTelemetryStateForTests(): void {
  _destroyed = false;
  _queue.length = 0;
  _seen.clear();
  if (_flushTimer) {
    clearTimeout(_flushTimer);
    _flushTimer = null;
  }
  _singleton = null;
  _endpoint = "/api/v1/agent/telemetry";
}
