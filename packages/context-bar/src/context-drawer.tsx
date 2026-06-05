"use client";

import { X } from "lucide-react";
import type { ReactNode, RefObject } from "react";
import { cn } from "./utils";

interface ContextDrawerProps {
  open: boolean;
  onClose: () => void;
  title: string;
  subtitle?: string;
  children: ReactNode;
  footer?: ReactNode;
  closeButtonRef?: RefObject<HTMLButtonElement>;
}

export function ContextDrawer({
  open,
  onClose,
  title,
  subtitle,
  children,
  footer,
  closeButtonRef,
}: ContextDrawerProps) {
  return (
    <div
      className={cn(
        "fixed z-40 bg-background shadow-xl transform transition-transform duration-200",
        "inset-y-0 right-0 w-96 border-l",
        "max-md:inset-x-0 max-md:bottom-0 max-md:top-auto max-md:right-auto max-md:w-full max-md:h-[80vh] max-md:border-l-0 max-md:border-t max-md:rounded-t-2xl",
        open
          ? "translate-x-0 translate-y-0"
          : "max-md:translate-y-full md:translate-x-full pointer-events-none"
      )}
      role="dialog"
      aria-modal="true"
      aria-label={title}
      aria-hidden={!open}
    >
      <div className="flex items-center justify-between border-b px-4 py-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            {open && (
              <span
                aria-hidden
                className="md:hidden inline-block h-1 w-10 rounded-full bg-muted-foreground/30"
              />
            )}
            <h2 className="text-sm font-semibold truncate">{title}</h2>
          </div>
          {subtitle && (
            <p className="text-[11px] text-muted-foreground truncate mt-0.5">
              {subtitle}
            </p>
          )}
        </div>
        <button
          ref={closeButtonRef}
          onClick={onClose}
          className="rounded-md p-1 hover:bg-accent transition-colors shrink-0 ml-2"
          aria-label="关闭抽屉"
        >
          <X className="h-4 w-4 text-muted-foreground" />
        </button>
      </div>
      <div className="overflow-y-auto h-[calc(100vh-7rem)] max-md:h-[calc(80vh-7rem)] p-3">
        {children}
      </div>
      {footer && (
        <div className="absolute bottom-0 left-0 right-0 border-t bg-background px-4 py-2 flex items-center justify-end">
          {footer}
        </div>
      )}
    </div>
  );
}
