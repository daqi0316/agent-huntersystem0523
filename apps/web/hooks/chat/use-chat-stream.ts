"use client";

/**
 * 发送消息 + 审批处理 + 操作面板状态
 * 提取自 agent/page.tsx（原 line 306-441）
 *
 * 行为兼容：
 *  - sendMessage 接收 text + attachment（可选）
 *  - 调用 POST /agent/chat，传 history（来自 historyRef）+ session_id
 *  - 成功后追加 assistant message，触发 approval / operationPanel 自动展开
 *  - 失败后追加 error message + 自动展开 operationPanel
 */

import { useState, useRef, useCallback } from "react";
import { api } from "@/lib/trpc";
import { getSessionId } from "./use-chat-session";
import { ensureBackendSession } from "./use-backend-session";
import { useAgentStore } from "@/stores/agent-store";
import { parseDataCardsFromMessage } from "@/lib/chat/data-card-parser";
import type { UploadedFile } from "@/hooks/useResumeUpload";
import type {
  AgentChatResponse,
  AgentActionInfo,
  ChatMessage,
  OperationPanelState,
  ToolCallInfo,
} from "@/types/chat";

export interface UseChatStreamParams {
  messages: ChatMessage[];
  setMessages: React.Dispatch<React.SetStateAction<ChatMessage[]>>;
  historyRef: React.MutableRefObject<ChatMessage[]>;
}

export interface UseChatStreamReturn {
  loading: boolean;
  lastToolCalls: ToolCallInfo[];
  approval: { visible: boolean; approval_id: string; summary: string; loading: boolean };
  operationPanel: OperationPanelState;
  setApproval: React.Dispatch<React.SetStateAction<{
    visible: boolean;
    approval_id: string;
    summary: string;
    loading: boolean;
  }>>;
  setOperationPanel: React.Dispatch<React.SetStateAction<OperationPanelState>>;
  sendMessage: (text: string, attachment?: UploadedFile | null) => Promise<void>;
  handleApprovalAction: (approve: boolean) => Promise<void>;
  handleOperationPanelSuccess: (summary: string) => void;
  messagesEndRef: React.MutableRefObject<HTMLDivElement | null>;
  scrollToBottom: () => void;
}

export function useChatStream({
  setMessages,
  historyRef,
}: UseChatStreamParams): UseChatStreamReturn {
  const [loading, setLoading] = useState(false);
  const [lastToolCalls, setLastToolCalls] = useState<ToolCallInfo[]>([]);
  const [approval, setApproval] = useState<{
    visible: boolean;
    approval_id: string;
    summary: string;
    loading: boolean;
  }>({ visible: false, approval_id: "", summary: "", loading: false });
  const [operationPanel, setOperationPanel] = useState<OperationPanelState>({
    open: false,
  });
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  const handleApprovalAction = useCallback(
    async (approve: boolean) => {
      const { approval_id } = approval;
      if (!approval_id) return;
      setApproval((prev) => ({ ...prev, loading: true }));

      try {
        await api.post("/human-loop/approve", {
          action_type: "schedule_interview",
          approval_id,
          approved: approve,
        });

        if (!approve) {
          setApproval({ visible: false, approval_id: "", summary: "", loading: false });
          return;
        }

        // resume orchestrator
        const resumeResult = await api.post<{
          success: boolean;
          data: { status: string; summary: string; outputs: any[] };
        }>("/human-loop/resume", { approval_id });

        if (resumeResult.success) {
          const { data } = resumeResult;
          setMessages((prev) => [
            ...prev,
            {
              role: "assistant",
              content: `✅ 审批通过，编排继续执行。\n\n${data.summary}`,
              agent_actions: (data.outputs || []).map((o: any) => ({
                agent: o.agent || "",
                status: o.status || "",
                summary: o.summary || "",
              })),
              model: `orchestrator/${data.status}`,
            },
          ]);
        }
      } catch (err: any) {
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: err.message || "审批处理失败",
            error: true,
          },
        ]);
      } finally {
        setApproval({ visible: false, approval_id: "", summary: "", loading: false });
      }
    },
    [approval, setMessages]
  );

  const handleApprovalAutoResume = useCallback(
    (actions: AgentActionInfo[]) => {
      const awaitingAction = actions.find((a) => a.status === "awaiting_approval");
      if (awaitingAction && awaitingAction.approval_id) {
        setApproval({
          visible: true,
          approval_id: awaitingAction.approval_id,
          summary: awaitingAction.summary || "待审批",
          loading: false,
        });
      }
    },
    []
  );

  const handleOperationPanelSuccess = useCallback(
    (summary: string) => {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: `✅ ${summary}` },
      ]);
    },
    [setMessages]
  );

  const sendMessage = useCallback(
    async (text: string, attachment?: UploadedFile | null) => {
      if (!text.trim() && !attachment) return;

      const userMsg: ChatMessage = {
        role: "user",
        content:
          text.trim() ||
          (attachment ? `上传简历: ${attachment.filename}` : ""),
      };
      const currentHistory = historyRef.current;
      setMessages((prev) => [...prev, userMsg]);
      useAgentStore.getState().recordMessage();
      setLoading(true);

      try {
        const backendSessionId = await ensureBackendSession();
        const sessionId = backendSessionId || getSessionId();

        const data = await api.post<AgentChatResponse>("/agent/chat", {
          message:
            text.trim() ||
            (attachment ? `解析这份简历: ${attachment.filename}` : ""),
          history: currentHistory.map((m) => ({
            role: m.role,
            content: m.content,
          })),
          session_id: sessionId,
          attachment: attachment
            ? {
                file_url: attachment.file_url,
                file_type: attachment.file_type,
                filename: attachment.filename,
              }
            : undefined,
        });

        const assistantMsg: ChatMessage = {
          role: "assistant",
          content: data.reply,
          tool_calls: data.tool_calls?.filter((tc) => tc.name),
          agent_actions: data.agent_actions,
          model: data.model,
        };
        const newCards = parseDataCardsFromMessage(
          assistantMsg,
          historyRef.current.length
        );
        setMessages((prev) => [...prev, assistantMsg]);
        for (const tc of assistantMsg.tool_calls || []) {
          if (tc.name) {
            useAgentStore.getState().recordToolCall(tc.name);
          }
        }
        for (const card of newCards) {
          useAgentStore.getState().addCard(card);
        }
        setLastToolCalls(
          data.tool_calls?.filter((tc) => tc.name) || []
        );

        if (
          data.model === "orchestrator/awaiting_approval" &&
          data.agent_actions
        ) {
          handleApprovalAutoResume(data.agent_actions);
        }

        // Auto-open OperationPanel if any tool_call returned an error
        const toolCallsWithError = data.tool_calls?.filter(
          (tc) => tc.name && tc.error
        );
        if (toolCallsWithError?.length) {
          const failedTool = toolCallsWithError[0];
          setOperationPanel({
            open: true,
            errorMessage: failedTool.error || "工具执行失败",
            operationType: failedTool.name,
            operationInput: failedTool.args,
            needsHuman: failedTool.needs_human ?? false,
          });
        }
      } catch (err: any) {
        const errorMsg = err.message || "请求失败，请稍后重试";
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: errorMsg, error: true },
        ]);
        const failedTool =
          lastToolCalls.find((tc) => tc.error) || lastToolCalls[0];
        let opType: string | undefined;
        let opInput: Record<string, unknown> | undefined;
        if (failedTool) {
          opType = failedTool.name;
          opInput = failedTool.args;
        }
        setOperationPanel({
          open: true,
          errorMessage: errorMsg,
          operationType: opType,
          operationInput: opInput,
        });
      } finally {
        setLoading(false);
      }
    },
    [historyRef, lastToolCalls, setMessages, handleApprovalAutoResume]
  );

  return {
    loading,
    lastToolCalls,
    approval,
    operationPanel,
    setApproval,
    setOperationPanel,
    sendMessage,
    handleApprovalAction,
    handleOperationPanelSuccess,
    messagesEndRef,
    scrollToBottom,
  };
}
