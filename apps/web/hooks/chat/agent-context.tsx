/**
 * Agent Context Provider — 单一 Provider 包裹 store 到 React 树
 *
 * 设计：
 *  - Zustand store 本身已经是 reactive 的，不强制需要 Provider
 *  - 但为了未来插入 server-side initialization（Phase 0.3 接入会话服务）、
 *    跨 tab 同步（Phase 4）、devtools hook 等能力，预留 Context 入口
 *  - 当前实现是 pass-through，只在客户端 hydrate 时调用 store 的 rehydrate
 *
 * 用法：
 *   <AgentProvider>
 *     <DashboardLayout>{children}</DashboardLayout>
 *   </AgentProvider>
 *
 * Phase 0.2 范围：仅搭骨架，行为不改变 useChatMessages 内部状态管理。
 * Phase 0.3+ 将在此 Provider 内接入后端 ConversationService。
 */

"use client";

import { useEffect, type ReactNode } from "react";
import { useAgentStore } from "@ai-recruitment/agent-store";
import {
  initAgentStoreSync,
  teardownAgentStoreSync,
} from "@/lib/agent-store-sync";
import { AgentEventStreamBridge } from "@/hooks/chat/use-agent-event-stream";

interface AgentProviderProps {
  children: ReactNode;
}

export function AgentProvider({ children }: AgentProviderProps) {
  useEffect(() => {
    useAgentStore.persist.rehydrate();
    initAgentStoreSync();
    return () => {
      teardownAgentStoreSync();
    };
  }, []);

  return (
    <>
      <AgentEventStreamBridge />
      {children}
    </>
  );
}
