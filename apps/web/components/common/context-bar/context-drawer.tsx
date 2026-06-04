"use client";

import { X } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

interface ContextDrawerProps {
  open: boolean;
  onClose: () => void;
  title: string;
  subtitle?: string;
  children: ReactNode;
  footer?: ReactNode;
}

export function ContextDrawer({
  open,
  onClose,
  title,
  subtitle,
  children,
  footer,
}: ContextDrawerProps) {
  return (
    <div
      className={cn(
        "fixed inset-y-0 right-0 z-40 w-96 bg-background border-l shadow-xl transform transition-transform duration-200",
        open ? "translate-x-0" : "translate-x-full pointer-events-none"
      )}
      aria-hidden={!open}
    >
      <div className="flex items-center justify-between border-b px-4 py-3">
        <div className="min-w-0 flex-1">
          <h2 className="text-sm font-semibold truncate">{title}</h2>
          {subtitle && (
            <p className="text-[11px] text-muted-foreground truncate mt-0.5">
              {subtitle}
            </p>
          )}
        </div>
        <button
          onClick={onClose}
          className="rounded-md p-1 hover:bg-accent transition-colors shrink-0 ml-2"
          aria-label="关闭抽屉"
        >
          <X className="h-4 w-4 text-muted-foreground" />
        </button>
      </div>
      <div className="overflow-y-auto h-[calc(100vh-7rem)] p-3">{children}</div>
      {footer && (
        <div className="absolute bottom-0 left-0 right-0 border-t bg-background px-4 py-2 flex items-center justify-end">
          {footer}
        </div>
      )}
    </div>
  );
}
