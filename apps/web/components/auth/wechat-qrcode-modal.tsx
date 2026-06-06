"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth-context";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

interface QrcodeResponse {
  qrcode_url: string;
  state: string;
  expires_in: number;
  mock: boolean;
}

interface MockLoginResponse {
  access_token: string;
  token_type: string;
  org_id: string;
  user_id: string;
  unionid: string;
  mock: boolean;
}

interface WeChatQrcodeModalProps {
  open: boolean;
  onClose: () => void;
  onSuccess: (token: string) => void;
}

export function WeChatQrcodeModal({ open, onClose, onSuccess }: WeChatQrcodeModalProps) {
  const [qrcode, setQrcode] = useState<QrcodeResponse | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [secondsLeft, setSecondsLeft] = useState(0);

  useEffect(() => {
    if (!open) return;
    setError("");
    setLoading(true);
    fetch(`${API_BASE}/auth/wechat/qrcode`)
      .then((r) => r.json())
      .then((j) => {
        if (j.success) {
          setQrcode(j.data);
          setSecondsLeft(j.data.expires_in);
        } else {
          setError(j.error || "生成二维码失败");
        }
      })
      .catch((e) => setError(e instanceof Error ? e.message : "网络错误"))
      .finally(() => setLoading(false));
  }, [open]);

  useEffect(() => {
    if (secondsLeft <= 0) return;
    const t = setTimeout(() => setSecondsLeft((s) => s - 1), 1000);
    return () => clearTimeout(t);
  }, [secondsLeft]);

  if (!open) return null;

  const handleMockLogin = async () => {
    setError("");
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/auth/wechat/mock-login?code=mockcode_${Date.now()}`, {
        method: "POST",
      });
      const j: { success: boolean; data?: MockLoginResponse; error?: string } = await res.json();
      if (j.success && j.data) {
        onSuccess(j.data.access_token);
      } else {
        setError(j.error || "登录失败");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "网络错误");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-white rounded-lg p-6 max-w-sm w-full mx-4 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">企业微信扫码登录</h2>
          <button
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground"
            aria-label="关闭"
          >
            ✕
          </button>
        </div>

        {loading && !qrcode && (
          <div className="text-center text-sm text-muted-foreground py-8">
            加载二维码中...
          </div>
        )}

        {qrcode && (
          <div className="space-y-3">
            <div className="bg-muted rounded p-4 flex items-center justify-center min-h-[200px]">
              <QrCodeDisplay url={qrcode.qrcode_url} mock={qrcode.mock} />
            </div>
            <p className="text-xs text-center text-muted-foreground">
              {qrcode.mock ? "Mock 模式 — 扫码后实际不会跳转" : "使用企业微信扫一扫"}
            </p>
            <p className="text-xs text-center text-muted-foreground">
              过期倒计时: {secondsLeft}s
            </p>
            {qrcode.mock && (
              <Button
                type="button"
                variant="outline"
                className="w-full"
                onClick={handleMockLogin}
                disabled={loading}
              >
                {loading ? "登录中..." : "Mock 一键登录 (开发用)"}
              </Button>
            )}
          </div>
        )}

        {error && (
          <p className="text-sm text-destructive text-center">{error}</p>
        )}

        <Button
          type="button"
          variant="ghost"
          className="w-full"
          onClick={onClose}
        >
          取消
        </Button>
      </div>
    </div>
  );
}

function QrCodeDisplay({ url, mock }: { url: string; mock: boolean }) {
  if (mock) {
    return (
      <div className="text-center space-y-2">
        <div className="text-4xl">📱</div>
        <p className="text-xs text-muted-foreground">Mock 二维码</p>
        <p className="text-[10px] break-all text-muted-foreground px-2">
          {url}
        </p>
      </div>
    );
  }
  return (
    <img
      src={`https://api.qrserver.com/v1/create-qr-code/?size=180x180&data=${encodeURIComponent(url)}`}
      alt="微信扫码二维码"
      className="w-[180px] h-[180px]"
    />
  );
}
