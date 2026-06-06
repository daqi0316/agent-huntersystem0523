"use client";

import { useEffect, useState } from "react";
import { X, Cookie } from "lucide-react";
import { Button } from "@/components/ui/button";

const CONSENT_KEY = "ai-recruitment-cookie-consent";

export function CookieConsent() {
  const [show, setShow] = useState(false);

  useEffect(() => {
    try {
      const stored = localStorage.getItem(CONSENT_KEY);
      if (!stored) {
        const timer = setTimeout(() => setShow(true), 1500);
        return () => clearTimeout(timer);
      }
    } catch {
      setShow(true);
    }
  }, []);

  const accept = (analytics: boolean) => {
    try {
      localStorage.setItem(
        CONSENT_KEY,
        JSON.stringify({
          necessary: true,
          analytics,
          accepted_at: new Date().toISOString(),
        })
      );
    } catch {
      /* noop */
    }
    setShow(false);
  };

  if (!show) return null;

  return (
    <div className="fixed bottom-4 left-4 right-4 z-50 md:left-auto md:right-4 md:max-w-md">
      <div className="rounded-lg border bg-white p-4 shadow-lg">
        <div className="mb-2 flex items-start justify-between gap-2">
          <div className="flex items-center gap-2">
            <Cookie className="h-4 w-4 text-amber-600" />
            <h3 className="text-sm font-semibold">Cookie 与隐私</h3>
          </div>
          <button
            onClick={() => accept(false)}
            className="text-muted-foreground hover:text-foreground"
            aria-label="关闭"
          >
            <X className="h-3 w-3" />
          </button>
        </div>
        <p className="text-xs text-muted-foreground">
          我们使用必要 cookie 维持登录态; 可选的分析 cookie 帮助改进产品。
          详见
          <a href="/legal/privacy" className="ml-1 text-primary underline">
            隐私政策
          </a>
          。
        </p>
        <div className="mt-3 flex gap-2">
          <Button
            size="sm"
            variant="outline"
            onClick={() => accept(false)}
            className="flex-1 text-xs"
          >
            仅必要
          </Button>
          <Button
            size="sm"
            onClick={() => accept(true)}
            className="flex-1 text-xs"
          >
            全部接受
          </Button>
        </div>
      </div>
    </div>
  );
}
