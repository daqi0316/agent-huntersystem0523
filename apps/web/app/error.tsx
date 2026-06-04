"use client";

import { useEffect } from "react";
import { AlertCircle, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // eslint-disable-next-line no-console
    console.error("[page error]", error);
  }, [error]);

  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-4 p-6">
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-destructive/10">
        <AlertCircle className="h-6 w-6 text-destructive" />
      </div>
      <h2 className="text-lg font-semibold text-foreground">页面出错了</h2>
      <p className="text-sm text-muted-foreground max-w-md text-center">
        渲染本页面时遇到错误。错误已记录，可以重试或返回首页。
      </p>
      {error.digest && (
        <code className="text-xs text-muted-foreground/60 font-mono">
          digest: {error.digest}
        </code>
      )}
      <div className="flex gap-2">
        <Button onClick={reset} variant="outline">
          <RefreshCw className="h-4 w-4" />
          重试
        </Button>
        <Button onClick={() => (window.location.href = "/")}>
          回到首页
        </Button>
      </div>
    </div>
  );
}
