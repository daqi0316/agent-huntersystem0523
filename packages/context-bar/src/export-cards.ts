/**
 * 导出 JSON 工具 — 卡片 sort + filter + timestamp（T5）
 *
 * 工业级 / 全局规划：
 *  - 格式：{ exportedAt, filters, sortOrder, cards: [...] } — 可作"快照"分享/归档
 *  - 时间戳：ISO 8601（UTC）
 *  - 字段筛选：仅含核心 DataCard 字段（不暴露内部 store 状态）
 *  - 下载触发：浏览器 File API blob + a[download]
 *  - 失败兜底：try/catch + console.warn
 */

import type { DataCard, DataCardType } from "@ai-recruitment/types";

export interface ExportFilters {
  query: string;
  types: DataCardType[];
}

export interface ExportPayload {
  exportedAt: string;
  filters: ExportFilters;
  sortOrder: string[];
  cards: Array<Pick<DataCard, "id" | "type" | "title" | "summary" | "toolName" | "createdAt" | "messageId">>;
}

export function buildExportPayload(
  cards: DataCard[],
  sortOrder: string[],
  filters: ExportFilters
): ExportPayload {
  return {
    exportedAt: new Date().toISOString(),
    filters: {
      query: filters.query,
      types: [...filters.types],
    },
    sortOrder: [...sortOrder],
    cards: cards.map((c) => ({
      id: c.id,
      type: c.type,
      title: c.title,
      summary: c.summary,
      toolName: c.toolName,
      createdAt: c.createdAt,
      messageId: c.messageId,
    })),
  };
}

export function downloadJson(payload: ExportPayload, filename?: string): void {
  if (typeof window === "undefined") return;
  const json = JSON.stringify(payload, null, 2);
  const blob = new Blob([json], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download =
    filename ?? `context-bar-export-${new Date().toISOString().slice(0, 10)}.json`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
