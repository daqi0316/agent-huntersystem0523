"use client";

import { useEffect } from "react";
import { Button } from "@/components/ui/button";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // eslint-disable-next-line no-console
    console.error("[app error]", error);
  }, [error]);

  return (
    <html lang="zh-CN">
      <body>
        <div
          style={{
            display: "flex",
            minHeight: "100vh",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            gap: "16px",
            padding: "24px",
            fontFamily: "system-ui, sans-serif",
          }}
        >
          <h1 style={{ fontSize: "24px", fontWeight: 600 }}>出错了</h1>
          <p style={{ color: "#666" }}>
            页面渲染时发生错误。错误已记录，可重试。
          </p>
          {error.digest && (
            <code
              style={{
                fontSize: "12px",
                color: "#999",
                fontFamily: "monospace",
              }}
            >
              digest: {error.digest}
            </code>
          )}
          <Button onClick={reset}>重试</Button>
        </div>
      </body>
    </html>
  );
}
