"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { onRateLimitToast, RateLimitInfo } from "@/lib/rate-limit-toast";
import { X, Clock, CreditCard } from "lucide-react";

export function RateLimitToast() {
  const router = useRouter();
  const [info, setInfo] = useState<RateLimitInfo | null>(null);
  const [secondsLeft, setSecondsLeft] = useState(0);

  useEffect(() => {
    return onRateLimitToast((payload) => {
      setInfo(payload);
      setSecondsLeft(payload.retryAfter);
    });
  }, []);

  useEffect(() => {
    if (!info || secondsLeft <= 0) return;
    if (secondsLeft === 1) {
      setInfo(null);
      return;
    }
    const t = setTimeout(() => setSecondsLeft((s) => s - 1), 1000);
    return () => clearTimeout(t);
  }, [info, secondsLeft]);

  if (!info) return null;

  const upgradeUrl = "/settings/subscription";

  return (
    <div className="fixed bottom-4 right-4 z-50 max-w-sm">
      <div className="rounded-lg border bg-white p-4 shadow-lg">
        <div className="mb-2 flex items-start justify-between gap-2">
          <div className="flex items-center gap-2">
            <Clock className="h-4 w-4 text-amber-600" />
            <h3 className="text-sm font-semibold">请求过快</h3>
          </div>
          <button
            onClick={() => setInfo(null)}
            className="text-muted-foreground hover:text-foreground"
            aria-label="关闭"
          >
            <X className="h-3 w-3" />
          </button>
        </div>
        <p className="text-xs text-muted-foreground">
          {info.message}。维度 <code className="rounded bg-muted px-1 py-0.5 text-xs">{info.key}</code>。
          将在 <strong>{secondsLeft}s</strong> 后恢复。
        </p>
        <button
          onClick={() => {
            setInfo(null);
            router.push(upgradeUrl);
          }}
          className="mt-2 flex w-full items-center justify-center gap-1 rounded border border-amber-200 bg-amber-50 px-3 py-1.5 text-xs text-amber-900 hover:bg-amber-100"
        >
          <CreditCard className="h-3 w-3" />
          升级到更高 plan 以提高限额
        </button>
      </div>
    </div>
  );
}
