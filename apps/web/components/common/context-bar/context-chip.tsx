"use client";

import { BarChart3 } from "lucide-react";
import { cn } from "@/lib/utils";

interface ContextChipProps {
  unreadCount: number;
  active: boolean;
  onClick: () => void;
  title?: string;
  subtitle?: string;
}

export function ContextChip({
  unreadCount,
  active,
  onClick,
  title,
  subtitle,
}: ContextChipProps) {
  return (
    <button
      onClick={onClick}
      title={title || `数据看板 · ${unreadCount} 项未读`}
      aria-label={title || `数据看板 ${unreadCount} 项未读`}
      className={cn(
        "relative flex h-9 items-center gap-1.5 rounded-md border px-2.5 text-xs font-medium transition-colors",
        active
          ? "border-primary bg-primary/10 text-primary"
          : "border-border bg-background text-muted-foreground hover:text-foreground hover:bg-accent"
      )}
    >
      <BarChart3 className="h-3.5 w-3.5" />
      <span>数据看板</span>
      {unreadCount > 0 && (
        <span
          className={cn(
            "ml-0.5 flex h-4 min-w-4 items-center justify-center rounded-full px-1 text-[10px] font-semibold",
            active
              ? "bg-primary text-primary-foreground"
              : "bg-destructive text-destructive-foreground"
          )}
        >
          {unreadCount > 99 ? "99+" : unreadCount}
        </span>
      )}
      {subtitle && (
        <span
          className={cn(
            "hidden md:inline-block max-w-[140px] truncate text-[10px] font-normal",
            active ? "text-primary/70" : "text-muted-foreground/70"
          )}
          title={subtitle}
        >
          · {subtitle}
        </span>
      )}
    </button>
  );
}
