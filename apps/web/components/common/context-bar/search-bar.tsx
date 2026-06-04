"use client";

/**
 * SearchBar — 抽屉顶部搜索/过滤
 *
 * 行为：
 *  - 文本输入 → 实时过滤卡片（title + summary + type）
 *  - type chip 多选过滤
 *  - Esc 清空搜索
 *  - ⌘K 打开时自动 focus
 */

import { useEffect, useRef } from "react";
import { Search, X } from "lucide-react";
import { useAgentStore, type DataCardType } from "@/stores/agent-store";
import { cn } from "../../../lib/utils";

const TYPE_FILTERS: Array<{ key: DataCardType | "all"; label: string }> = [
  { key: "all", label: "全部" },
  { key: "candidate_list", label: "候选人" },
  { key: "dashboard_stats", label: "看板" },
  { key: "evaluation", label: "评估" },
  { key: "jd", label: "JD" },
  { key: "interview_schedule", label: "面试" },
];

export interface SearchFilters {
  query: string;
  types: DataCardType[];
}

export const EMPTY_FILTERS: SearchFilters = {
  query: "",
  types: [],
};

export function filterCards<T extends { type: DataCardType; title?: string; summary?: string }>(
  items: T[],
  filters: SearchFilters
): T[] {
  if (!filters.query && filters.types.length === 0) return items;
  const q = filters.query.toLowerCase();
  return items.filter((item) => {
    if (filters.types.length > 0 && !filters.types.includes(item.type)) return false;
    if (q) {
      const hay = `${item.title ?? ""} ${item.summary ?? ""}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
}

interface SearchBarProps {
  query: string;
  onQueryChange: (q: string) => void;
  activeTypes: DataCardType[];
  onActiveTypesChange: (types: DataCardType[]) => void;
  resultCount: number;
  totalCount: number;
}

export function SearchBar({
  query,
  onQueryChange,
  activeTypes,
  onActiveTypesChange,
  resultCount,
  totalCount,
}: SearchBarProps) {
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const toggleType = (t: DataCardType) => {
    if (activeTypes.includes(t)) {
      onActiveTypesChange(activeTypes.filter((x) => x !== t));
    } else {
      onActiveTypesChange([...activeTypes, t]);
    }
  };

  return (
    <div className="border-b bg-background px-3 py-2 space-y-1.5">
      <div className="relative">
        <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => onQueryChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Escape") onQueryChange("");
          }}
          placeholder="搜索卡片标题或摘要..."
          className="w-full rounded-md border bg-muted/30 pl-8 pr-8 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
        />
        {query && (
          <button
            onClick={() => onQueryChange("")}
            className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-0.5 hover:bg-accent"
            aria-label="清空搜索"
          >
            <X className="h-3 w-3 text-muted-foreground" />
          </button>
        )}
      </div>
      <div className="flex flex-wrap gap-1">
        {TYPE_FILTERS.slice(0, 5).map((f) => {
          const isAll = f.key === "all";
          const isActive = isAll
            ? activeTypes.length === 0
            : activeTypes.includes(f.key as DataCardType);
          return (
            <button
              key={f.key}
              onClick={() => {
                if (isAll) onActiveTypesChange([]);
                else toggleType(f.key as DataCardType);
              }}
              className={cn(
                "rounded-md px-1.5 py-0.5 text-[10px] font-medium border transition-colors",
                isActive
                  ? "border-primary bg-primary/10 text-primary"
                  : "border-border bg-background text-muted-foreground hover:bg-accent"
              )}
            >
              {f.label}
            </button>
          );
        })}
        <span className="ml-auto text-[10px] text-muted-foreground self-center">
          {resultCount}/{totalCount}
        </span>
      </div>
    </div>
  );
}
