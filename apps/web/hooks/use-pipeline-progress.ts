"use client";

// 已废弃: 改用 StepIndicator 组件 (SSE 方案) 替代轮询。
// step-indicator.tsx 通过 EventSource + useEventSource hook
// 订阅 /pipeline/{taskId}/stream SSE 端点获取实时进度。
// 如需独立使用 SSE 进度，请直接引用 useEventSource hook。

import { useState, useEffect, useCallback } from "react";

interface PipelineProgress {
  pipelineId: string;
  status: string;
  progress: number;
  currentStep: string;
}

export function usePipelineProgress(pipelineId: string | null) {
  const [progress, setProgress] = useState<PipelineProgress | null>(null);
  const [error, setError] = useState<string | null>(null);

  const poll = useCallback(async () => {
    if (!pipelineId) return;
    try {
      const res = await fetch(
        `http://localhost:8000/api/v1/pipeline/${pipelineId}/progress`
      );
      const data = await res.json();
      setProgress(data);
      if (data.status === "completed" || data.status === "failed") {
        return; // Stop polling
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Polling failed");
    }
  }, [pipelineId]);

  useEffect(() => {
    if (!pipelineId) return;
    const interval = setInterval(poll, 1000);
    return () => clearInterval(interval);
  }, [pipelineId, poll]);

  return { progress, error };
}
