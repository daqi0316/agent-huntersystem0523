"use client";

import { useEffect, useState } from "react";
import { Loader2, CheckCircle, Circle } from "lucide-react";
import { cn } from "@/lib/utils";
import { useEventSource } from "@/hooks/use-event-source";

interface Step {
  name: string;
  label: string;
  description: string;
}

interface ProgressEvent {
  pipeline_id: string;
  status: "running" | "completed" | "failed";
  progress: number;
  current_step: string;
  step_label?: string;
  step_description?: string;
}

const PIPELINE_STEPS: Step[] = [
  { name: "parse", label: "简历解析", description: "解析候选人的简历信息" },
  { name: "match", label: "职位匹配", description: "与职位要求进行匹配分析" },
  { name: "gate", label: "质检门控", description: "质检审核与评分汇总" },
];

interface StepIndicatorProps {
  taskId: string;
  onComplete?: () => void;
  className?: string;
}

export function StepIndicator({
  taskId,
  onComplete,
  className,
}: StepIndicatorProps) {
  const [progress, setProgress] = useState<ProgressEvent | null>(null);
  const [error, setError] = useState<string | null>(null);

  const endpoint = taskId ? `/pipeline/${taskId}/stream` : null;
  const { connected, subscribe } = useEventSource(endpoint);

  useEffect(() => {
    if (!connected) return;

    const unsubProgress = subscribe("progress", (data) => {
      setProgress(data as ProgressEvent);
    });

    const unsubComplete = subscribe("complete", () => {
      onComplete?.();
    });

    const unsubError = subscribe("error", (data) => {
      setError((data as Record<string, unknown>).message as string || "流水线执行失败");
    });

    return () => {
      unsubProgress();
      unsubComplete();
      unsubError();
    };
  }, [connected, subscribe, onComplete]);

  if (error) {
    return (
      <div className={cn("text-sm text-destructive", className)}>
        进度连接失败: {error}
      </div>
    );
  }

  if (!progress) {
    return (
      <div className={cn("flex items-center gap-2 text-sm text-muted-foreground", className)}>
        <Loader2 className="h-4 w-4 animate-spin" />
        连接中...
      </div>
    );
  }

  const currentIdx = PIPELINE_STEPS.findIndex(
    (s) => s.name === progress.current_step
  );

  return (
    <div className={cn("space-y-2", className)}>
      {progress.status === "running" && (
        <p className="text-sm text-muted-foreground">
          {progress.step_label || "流水线运行中..."}
          {progress.step_description && (
            <span className="block text-xs">- {progress.step_description}</span>
          )}
        </p>
      )}
      <div className="flex items-center gap-2">
        {PIPELINE_STEPS.map((step, idx) => {
          const isDone = idx < currentIdx || (progress.status === "completed");
          const isCurrent = idx === currentIdx && progress.status === "running";

          return (
            <div key={step.name} className="flex items-center gap-2">
              {isDone ? (
                <CheckCircle className="h-5 w-5 text-green-500" />
              ) : isCurrent ? (
                <Loader2 className="h-5 w-5 animate-spin text-primary" />
              ) : (
                <Circle className="h-5 w-5 text-muted-foreground/40" />
              )}
              <span
                className={cn(
                  "text-sm",
                  isDone && "text-green-600",
                  isCurrent && "font-medium text-primary",
                  !isDone && !isCurrent && "text-muted-foreground/60"
                )}
              >
                {step.label}
              </span>
              {idx < PIPELINE_STEPS.length - 1 && (
                <div
                  className={cn(
                    "mx-1 h-px w-6",
                    idx < currentIdx ? "bg-green-400" : "bg-border"
                  )}
                />
              )}
            </div>
          );
        })}
      </div>
      {progress.status === "completed" && (
        <p className="text-sm text-green-600 font-medium">流水线完成</p>
      )}
    </div>
  );
}
