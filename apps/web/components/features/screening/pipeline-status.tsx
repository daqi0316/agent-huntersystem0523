"use client";

import { Loader2, CheckCircle, XCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import { PipelineProgress } from "@/types";

interface PipelineStatusProps {
  progress: PipelineProgress | null;
  className?: string;
}

export function PipelineStatus({ progress, className }: PipelineStatusProps) {
  if (!progress || progress.status === "running") {
    return (
      <div className={cn("flex items-center gap-2 text-sm text-muted-foreground", className)}>
        <Loader2 className="h-4 w-4 animate-spin" />
        <span>流水线运行中...</span>
      </div>
    );
  }

  if (progress.status === "completed") {
    return (
      <div className={cn("flex items-center gap-2 text-sm text-green-600", className)}>
        <CheckCircle className="h-4 w-4" />
        <span>流水线完成</span>
      </div>
    );
  }

  return (
    <div className={cn("flex items-center gap-2 text-sm text-red-600", className)}>
      <XCircle className="h-4 w-4" />
      <span>流水线失败: {progress.error}</span>
    </div>
  );
}
