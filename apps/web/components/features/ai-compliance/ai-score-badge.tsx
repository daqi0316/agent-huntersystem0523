"use client";

import { Sparkles, Pencil, Clock } from "lucide-react";
import { Badge } from "@/components/ui/badge";

interface AISource {
  llm: string;
  model_version?: string;
  prompt_hash?: string;
  generated_at?: string;
  temperature?: number;
}

interface AIScoreBadgeProps {
  score: number | null;
  aiSource: AISource | null | undefined;
  overridden?: boolean;
  originalScore?: number | null;
  onOverride?: () => void;
  onAppeal?: () => void;
}

export function AIScoreBadge({ score, aiSource, overridden, originalScore, onOverride, onAppeal }: AIScoreBadgeProps) {
  if (score === null || score === undefined) {
    return <span className="text-xs text-muted-foreground">—</span>;
  }

  return (
    <div className="inline-flex items-center gap-1">
      {overridden ? (
        <Badge variant="outline" className="bg-amber-50 text-amber-700 border-amber-300">
          <Pencil className="mr-1 h-3 w-3" />
          人工 {score}
          {originalScore !== null && originalScore !== undefined && (
            <span className="ml-1 text-xs line-through opacity-60">{originalScore}</span>
          )}
        </Badge>
      ) : (
        <div className="group relative inline-block">
          <Badge variant="outline" className="bg-blue-50 text-blue-700 border-blue-200 cursor-help">
            <Sparkles className="mr-1 h-3 w-3" />
            AI {score}
          </Badge>
          {aiSource && (
            <div className="pointer-events-none invisible absolute bottom-full left-1/2 z-10 mb-1 -translate-x-1/2 whitespace-nowrap rounded border bg-white px-2 py-1 text-xs opacity-0 shadow-md transition group-hover:visible group-hover:opacity-100">
              <div className="font-mono text-[10px]">
                <div>LLM: {aiSource.llm}</div>
                {aiSource.model_version && <div>Model: {aiSource.model_version}</div>}
                {aiSource.prompt_hash && <div>Hash: {aiSource.prompt_hash.slice(0, 12)}…</div>}
                {aiSource.generated_at && <div>At: {aiSource.generated_at.slice(0, 16)}</div>}
              </div>
            </div>
          )}
        </div>
      )}

      {!overridden && onOverride && (
        <button
          onClick={onOverride}
          className="text-xs text-muted-foreground hover:text-foreground"
          aria-label="改写评分"
          title="HR 改写评分"
        >
          <Pencil className="h-3 w-3" />
        </button>
      )}
      {onAppeal && (
        <button
          onClick={onAppeal}
          className="text-xs text-muted-foreground hover:text-foreground"
          aria-label="申诉"
          title="对 AI 评分申诉"
        >
          <Clock className="h-3 w-3" />
        </button>
      )}
    </div>
  );
}
