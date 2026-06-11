"use client";

import { useEffect } from "react";
import { useSourcingWSStore, TaskProgressEvent, PlatformProgress } from "@/stores/sourcing-ws-store";

export function useSourcingTaskWS(taskId: string | undefined) {
  const connect = useSourcingWSStore((s) => s.connect);
  const disconnect = useSourcingWSStore((s) => s.disconnect);
  const connected = useSourcingWSStore((s) => taskId ? s.connectedTasks[taskId] : false);
  const taskProgress = useSourcingWSStore((s) => taskId ? s.taskProgress[taskId] : undefined);
  const platformProgress = useSourcingWSStore((s) => taskId ? s.platformProgress[taskId] : undefined);

  useEffect(() => {
    if (!taskId) return;
    connect(taskId);
    return () => {
      disconnect(taskId);
    };
  }, [taskId, connect, disconnect]);

  return { connected, taskProgress, platformProgress };
}
