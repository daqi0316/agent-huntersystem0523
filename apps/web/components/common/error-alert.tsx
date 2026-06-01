"use client";

import { AlertCircle, CheckCircle2, X } from "lucide-react";
import { cn } from "@/lib/utils";

export type AlertVariant = "error" | "success" | "warning";

interface ErrorAlertProps {
  message: string | null;
  variant?: AlertVariant;
  onDismiss?: () => void;
  className?: string;
}

const variantStyles: Record<AlertVariant, string> = {
  error:
    "border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-300",
  success:
    "border-green-200 bg-green-50 text-green-700 dark:border-green-800 dark:bg-green-950 dark:text-green-300",
  warning:
    "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-300",
};

const variantIcons: Record<AlertVariant, typeof AlertCircle> = {
  error: AlertCircle,
  success: CheckCircle2,
  warning: AlertCircle,
};

export function ErrorAlert({
  message,
  variant = "error",
  onDismiss,
  className,
}: ErrorAlertProps) {
  if (!message) return null;

  const Icon = variantIcons[variant];

  return (
    <div
      className={cn(
        "flex items-center gap-2 rounded-lg border px-4 py-3 text-sm",
        variantStyles[variant],
        className
      )}
    >
      <Icon className="h-4 w-4 shrink-0" />
      <span className="flex-1">{message}</span>
      {onDismiss && (
        <button
          onClick={onDismiss}
          className="rounded-full p-0.5 hover:bg-black/5 dark:hover:bg-white/10 transition-colors"
          aria-label="关闭"
        >
          <X className="h-4 w-4" />
        </button>
      )}
    </div>
  );
}
