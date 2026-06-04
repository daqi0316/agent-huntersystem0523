"use client";

import { useEffect } from "react";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("[app error]", error);
  }, [error]);

  return (
    <html lang="zh-CN">
      <body
        style={{
          margin: 0,
          fontFamily: "system-ui, sans-serif",
        }}
      >
        <div
          style={{
            display: "flex",
            minHeight: "100vh",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            gap: "16px",
            padding: "24px",
          }}
        >
          <h1 style={{ fontSize: "24px", fontWeight: 600, margin: 0 }}>
            出错了
          </h1>
          <p style={{ color: "#666", margin: 0 }}>
            页面渲染时发生错误。错误已记录，可重试。
          </p>
          {error.digest ? (
            <code
              style={{
                fontSize: "12px",
                color: "#999",
                fontFamily: "monospace",
              }}
            >
              digest: {error.digest}
            </code>
          ) : null}
          <button
            onClick={reset}
            style={{
              padding: "8px 16px",
              border: "none",
              borderRadius: "6px",
              background: "#18181b",
              color: "white",
              cursor: "pointer",
              fontSize: "14px",
            }}
          >
            重试
          </button>
        </div>
      </body>
    </html>
  );
}
