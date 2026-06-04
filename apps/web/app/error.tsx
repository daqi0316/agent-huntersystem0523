"use client";

import { useEffect } from "react";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("[page error]", error);
  }, [error]);

  return (
    <div
      style={{
        display: "flex",
        minHeight: "60vh",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: "16px",
        padding: "24px",
        fontFamily: "system-ui, sans-serif",
      }}
    >
      <div
        style={{
          display: "flex",
          height: "48px",
          width: "48px",
          alignItems: "center",
          justifyContent: "center",
          borderRadius: "9999px",
          background: "rgba(220, 38, 38, 0.1)",
          color: "#dc2626",
          fontSize: "24px",
          fontWeight: 700,
        }}
      >
        !
      </div>
      <h2 style={{ fontSize: "18px", fontWeight: 600, margin: 0 }}>页面出错了</h2>
      <p
        style={{
          fontSize: "14px",
          color: "#666",
          maxWidth: "420px",
          textAlign: "center",
          margin: 0,
        }}
      >
        渲染本页面时遇到错误。错误已记录，可以重试或返回首页。
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
      <div style={{ display: "flex", gap: "8px" }}>
        <button
          onClick={reset}
          style={{
            padding: "8px 16px",
            border: "1px solid #d4d4d8",
            borderRadius: "6px",
            background: "white",
            cursor: "pointer",
            fontSize: "14px",
          }}
        >
          重试
        </button>
        <button
          onClick={() => {
            window.location.href = "/";
          }}
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
          回到首页
        </button>
      </div>
    </div>
  );
}
