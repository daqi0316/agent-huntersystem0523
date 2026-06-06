"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

function WechatCallbackInner() {
  const router = useRouter();
  const params = useSearchParams();
  const [status, setStatus] = useState<"loading" | "ok" | "fail">("loading");
  const [msg, setMsg] = useState("处理微信登录中...");

  useEffect(() => {
    const token = params.get("token");
    const orgId = params.get("org_id");
    const error = params.get("error");

    if (error) {
      setStatus("fail");
      setMsg(decodeURIComponent(error));
      return;
    }

    if (!token) {
      setStatus("fail");
      setMsg("未拿到 token");
      return;
    }

    localStorage.setItem("ai-recruitment-token", token);
    if (orgId) {
      localStorage.setItem("ai-recruitment-org-id", orgId);
    }

    fetch(`${API_BASE}/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => {
        if (r.ok) {
          setStatus("ok");
          setMsg("登录成功, 跳转中...");
          setTimeout(() => router.push("/dashboard"), 500);
        } else {
          setStatus("fail");
          setMsg("获取用户信息失败");
        }
      })
      .catch(() => {
        setStatus("fail");
        setMsg("网络错误");
      });
  }, [params, router]);

  return (
    <div className="w-full max-w-sm space-y-4 text-center">
      <h1 className="text-xl font-semibold">微信登录</h1>
      <p
        className={
          status === "fail" ? "text-destructive text-sm" : "text-sm text-muted-foreground"
        }
      >
        {msg}
      </p>
      {status === "fail" && (
        <button
          onClick={() => router.push("/login")}
          className="text-sm text-primary underline"
        >
          返回登录
        </button>
      )}
    </div>
  );
}

export default function WechatCallbackPage() {
  return (
    <Suspense fallback={<div className="text-sm">加载中...</div>}>
      <WechatCallbackInner />
    </Suspense>
  );
}
