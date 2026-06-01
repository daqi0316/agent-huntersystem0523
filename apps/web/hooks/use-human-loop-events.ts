"use client";

import { useEffect } from "react";
import { useEventSource } from "@/hooks/use-event-source";

interface PendingProposal {
  approval_id: string;
  candidate_name?: string;
  job_title?: string;
  action_type: string;
  proposal: Record<string, unknown>;
  params: Record<string, unknown>;
  status: string;
  created_at: string;
  expires_at: string;
  [key: string]: unknown;
}

interface UseHumanLoopEventsOptions {
  onPendingUpdated?: (proposals: PendingProposal[]) => void;
  onError?: (message: string) => void;
}

export function useHumanLoopEvents(
  enabled: boolean,
  options: UseHumanLoopEventsOptions
) {
  const { connected, subscribe } = useEventSource(
    enabled ? "/human-loop/events" : null
  );

  useEffect(() => {
    if (!connected) return;

    const unsub = subscribe("pending_updated", (data) => {
      const payload = data as { data?: PendingProposal[] };
      if (payload.data) {
        options.onPendingUpdated?.(payload.data);
      }
    });

    return unsub;
  }, [connected, subscribe, options.onPendingUpdated]);

  useEffect(() => {
    if (!connected) return;

    const unsub = subscribe("error", (data) => {
      const payload = data as { message?: string };
      options.onError?.(payload.message || "审批事件流连接失败");
    });

    return unsub;
  }, [connected, subscribe, options.onError]);

  return { connected };
}
