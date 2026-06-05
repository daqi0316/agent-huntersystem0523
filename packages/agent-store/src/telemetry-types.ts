// T6 埋点类型 — 前后端共享
export interface TelemetryEvent {
  event: string;
  props?: Record<string, unknown>;
  ts?: number; // seconds (前端传 ms/1000)
}

export interface TelemetryBatch {
  events: TelemetryEvent[];
}
