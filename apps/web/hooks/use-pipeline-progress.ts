"use client";

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
