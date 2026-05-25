"use client";

import { cn } from "@/lib/utils";

interface MatchScoreBadgeProps {
  score: number;
  className?: string;
}

export function MatchScoreBadge({ score, className }: MatchScoreBadgeProps) {
  const percentage = Math.round(score * 100);
  const color =
    score >= 0.8 ? "text-green-600" : score >= 0.6 ? "text-yellow-600" : "text-red-600";

  return (
    <span className={cn("font-semibold tabular-nums", color, className)}>
      {percentage}%
    </span>
  );
}
