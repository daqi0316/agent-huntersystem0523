"use client";

import { create } from "zustand";

export interface TaskProgressEvent {
  task_id: string;
  status?: string;
  platform?: string;
  index?: number;
  total?: number;
  found?: number;
  new?: number;
  error?: string;
  keyword?: string;
  platforms?: string[];
  total_found?: number;
  after_dedup?: number;
  new_this_run?: number;
  progress?: Record<string, unknown>;
}

export interface PlatformProgress {
  status: string;
  found?: number;
  new?: number;
  error?: string;
}

interface SourcingWSState {
  connections: Record<string, WebSocket | null>;
  connectedTasks: Record<string, boolean>;
  taskProgress: Record<string, TaskProgressEvent>;
  platformProgress: Record<string, Record<string, PlatformProgress>>;
  connect: (taskId: string) => void;
  disconnect: (taskId: string) => void;
  disconnectAll: () => void;
  clearTask: (taskId: string) => void;
}

const BASE_URL = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000";

function getStoredToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return localStorage.getItem("ai-recruitment-token");
  } catch {
    return null;
  }
}

export const useSourcingWSStore = create<SourcingWSState>((set, get) => ({
  connections: {},
  connectedTasks: {},
  taskProgress: {},
  platformProgress: {},

  connect: (taskId: string) => {
    const { connections } = get();
    if (connections[taskId]) return;

    const token = getStoredToken();
    const params = token ? `?token=${encodeURIComponent(token)}` : "";
    const url = `${BASE_URL}/ws/sourcing/tasks/${taskId}${params}`;
    const ws = new WebSocket(url);

    ws.onopen = () => {
      set((s) => ({
        connectedTasks: { ...s.connectedTasks, [taskId]: true },
      }));
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        const { event: eventType, data } = msg;

        if (eventType === "task_started") {
          set((s) => ({
            taskProgress: { ...s.taskProgress, [taskId]: data },
            platformProgress: { ...s.platformProgress, [taskId]: {} },
          }));
        } else if (eventType === "platform_start") {
          set((s) => ({
            platformProgress: {
              ...s.platformProgress,
              [taskId]: {
                ...s.platformProgress[taskId],
                [data.platform]: { status: "running" },
              },
            },
          }));
        } else if (eventType === "platform_done") {
          set((s) => ({
            platformProgress: {
              ...s.platformProgress,
              [taskId]: {
                ...s.platformProgress[taskId],
                [data.platform]: {
                  status: data.status,
                  found: data.found,
                  new: data.new,
                  error: data.error,
                },
              },
            },
          }));
        } else if (eventType === "task_done") {
          set((s) => ({
            taskProgress: { ...s.taskProgress, [taskId]: data },
          }));
        }
      } catch {
        // ignore parse errors
      }
    };

    ws.onclose = () => {
      set((s) => ({
        connectedTasks: { ...s.connectedTasks, [taskId]: false },
        connections: { ...s.connections, [taskId]: null },
      }));
    };

    ws.onerror = () => {
      ws.close();
    };

    set((s) => ({
      connections: { ...s.connections, [taskId]: ws },
    }));
  },

  disconnect: (taskId: string) => {
    const { connections } = get();
    connections[taskId]?.close();
    set((s) => ({
      connections: { ...s.connections, [taskId]: null },
      connectedTasks: { ...s.connectedTasks, [taskId]: false },
    }));
  },

  disconnectAll: () => {
    const { connections } = get();
    Object.values(connections).forEach((ws) => ws?.close());
    set({ connections: {}, connectedTasks: {}, taskProgress: {}, platformProgress: {} });
  },

  clearTask: (taskId: string) => {
    get().disconnect(taskId);
    set((s) => {
      const tp = { ...s.taskProgress };
      const pp = { ...s.platformProgress };
      delete tp[taskId];
      delete pp[taskId];
      return { taskProgress: tp, platformProgress: pp };
    });
  },
}));
