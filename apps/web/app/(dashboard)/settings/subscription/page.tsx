"use client";

import { useEffect, useState } from "react";
import { Check, Loader2, QrCode, X, Sparkles, Crown } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ErrorAlert } from "@/components/common/error-alert";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
const TOKEN_KEY = "ai-recruitment-token";

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
}

interface Plan {
  plan: string;
  monthly_price_cents: number;
  monthly_price_yuan: number;
  quota: { max_users: number; max_candidates: number; llm_tokens_per_month: number };
  is_current: boolean;
}

interface Subscription {
  plan: string;
  status: string;
  current_period_start: string;
  current_period_end: string;
  grace_period_end: string | null;
  auto_renew: boolean;
  pending_plan: string | null;
}

interface SubscriptionResponse {
  subscription: Subscription | null;
  plans: Plan[];
}

interface OrderResult {
  out_trade_no: string;
  amount_cents: number;
  qr_code: string | null;
  expires_at: string;
  mock: boolean;
  plan: string;
}

const PLAN_ICONS: Record<string, typeof Sparkles> = {
  starter: Sparkles,
  pro: Crown,
  enterprise: Crown,
};

const PLAN_COLORS: Record<string, string> = {
  starter: "border-gray-200",
  pro: "border-blue-500 ring-1 ring-blue-200",
  enterprise: "border-purple-500 ring-1 ring-purple-200",
};

export default function SubscriptionPage() {
  const [data, setData] = useState<SubscriptionResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [paymentOrder, setPaymentOrder] = useState<OrderResult | null>(null);
  const [changing, setChanging] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const token = getToken();
      if (!token) { setError("未登录"); return; }
      const res = await fetch(`${API_BASE}/payment/subscription`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const j = await res.json();
      setData(j.data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const handleChangePlan = async (newPlan: string) => {
    if (!data) return;
    setError(null);
    setChanging(newPlan);
    try {
      const token = getToken();
      const res = await fetch(`${API_BASE}/payment/subscription/change-plan`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ new_plan: newPlan, channel: "wechat" }),
      });
      const j = await res.json();
      if (!res.ok || !j.success) throw new Error(j.error || "切换失败");
      if (j.data.action === "upgrade" && j.data.order) {
        setPaymentOrder({ ...j.data.order, plan: newPlan, mock: true });
      } else if (j.data.action === "downgrade") {
        await load();
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "切换失败");
    } finally {
      setChanging(null);
    }
  };

  const handleMockPay = async () => {
    if (!paymentOrder) return;
    try {
      const token = getToken();
      const res = await fetch(`${API_BASE}/payment/mock-pay`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ out_trade_no: paymentOrder.out_trade_no }),
      });
      const j = await res.json();
      if (!res.ok || !j.success) throw new Error(j.error || "支付失败");
      setPaymentOrder(null);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "支付失败");
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center p-12 text-muted-foreground">
        <Loader2 className="mr-2 h-4 w-4 animate-spin" /> 加载订阅信息...
      </div>
    );
  }

  const sub = data?.subscription;
  const plans = data?.plans || [];

  return (
    <div className="space-y-6 p-6">
      <div>
        <h1 className="text-3xl font-bold">
          订阅与计费
        </h1>
        <p className="text-muted-foreground">管理您的订阅计划与支付方式</p>
      </div>

      {error && <ErrorAlert message={error} variant="error" />}

      {sub && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">当前订阅</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
              <div>
                <p className="text-xs text-muted-foreground">计划</p>
                <p className="text-lg font-semibold">
                  <Badge variant="outline" className="text-sm">{sub.plan.toUpperCase()}</Badge>
                </p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">状态</p>
                <p className="text-sm">
                  {sub.status === "active" && <Badge className="bg-green-100 text-green-700">活跃</Badge>}
                  {sub.status === "grace_period" && <Badge className="bg-yellow-100 text-yellow-700">宽限期</Badge>}
                  {sub.status === "cancelled" && <Badge className="bg-gray-100 text-gray-700">已取消</Badge>}
                  {sub.status === "expired" && <Badge className="bg-red-100 text-red-700">已过期</Badge>}
                </p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">续期日</p>
                <p className="text-sm font-mono">
                  {new Date(sub.current_period_end).toLocaleDateString("zh-CN")}
                </p>
              </div>
              {sub.pending_plan && (
                <div className="md:col-span-3 rounded border border-yellow-200 bg-yellow-50 p-3 text-sm">
                  ⚠️ 当前周期结束后将切换到 <strong>{sub.pending_plan.toUpperCase()}</strong>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      <div>
        <h2 className="mb-4 text-xl font-semibold">选择计划</h2>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          {plans.map((p) => {
            const Icon = PLAN_ICONS[p.plan] || Sparkles;
            const isCurrent = p.is_current;
            const isPro = p.plan === "pro";
            return (
              <Card key={p.plan} className={`relative ${PLAN_COLORS[p.plan] || ""}`}>
                {isPro && (
                  <Badge className="absolute -top-2 right-4 bg-blue-600">
                    推荐
                  </Badge>
                )}
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Icon className="h-4 w-4" />
                    {p.plan.toUpperCase()}
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div>
                    <span className="text-3xl font-bold">
                      ¥{p.monthly_price_yuan}
                    </span>
                    <span className="text-sm text-muted-foreground"> / 月</span>
                  </div>

                  <ul className="space-y-1 text-sm">
                    <li className="flex items-center gap-1">
                      <Check className="h-3 w-3 text-green-600" /> {p.quota.max_users} 用户
                    </li>
                    <li className="flex items-center gap-1">
                      <Check className="h-3 w-3 text-green-600" /> {p.quota.max_candidates.toLocaleString()} 候选人
                    </li>
                    <li className="flex items-center gap-1">
                      <Check className="h-3 w-3 text-green-600" />
                      {" "}{(p.quota.llm_tokens_per_month / 1_000_000).toFixed(1)}M LLM tokens / 月
                    </li>
                  </ul>

                  {isCurrent ? (
                    <Button disabled className="w-full">当前计划</Button>
                  ) : p.monthly_price_cents === 0 ? (
                    <Button
                      variant="outline"
                      className="w-full"
                      onClick={() => handleChangePlan(p.plan)}
                      disabled={changing !== null}
                    >
                      {changing === p.plan ? <Loader2 className="mr-1 h-3 w-3 animate-spin" /> : null}
                      降级到此
                    </Button>
                  ) : (
                    <Button
                      className="w-full"
                      onClick={() => handleChangePlan(p.plan)}
                      disabled={changing !== null}
                    >
                      {changing === p.plan ? <Loader2 className="mr-1 h-3 w-3 animate-spin" /> : null}
                      {sub && p.monthly_price_cents > 0 ? "升级 / 切换" : "升级到此"}
                    </Button>
                  )}
                </CardContent>
              </Card>
            );
          })}
        </div>
      </div>

      {paymentOrder && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
          onClick={() => setPaymentOrder(null)}
        >
          <div
            className="w-full max-w-md rounded-lg bg-white p-6"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-lg font-semibold">完成支付</h2>
              <button
                onClick={() => setPaymentOrder(null)}
                className="text-muted-foreground hover:text-foreground"
                aria-label="关闭"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="space-y-4 text-center">
              <div className="rounded border bg-muted/30 p-6">
                {paymentOrder.mock ? (
                  <>
                    <QrCode className="mx-auto mb-2 h-12 w-12 opacity-50" />
                    <p className="text-xs text-muted-foreground">Mock 模式</p>
                    <p className="mt-2 text-2xl font-bold">¥{(paymentOrder.amount_cents / 100).toFixed(2)}</p>
                    <p className="mt-1 font-mono text-xs text-muted-foreground">
                      {paymentOrder.out_trade_no}
                    </p>
                  </>
                ) : (
                  <img
                    src={`https://api.qrserver.com/v1/create-qr-code/?size=180x180&data=${encodeURIComponent(paymentOrder.qr_code || "")}`}
                    alt="支付二维码"
                    className="mx-auto h-[180px] w-[180px]"
                  />
                )}
              </div>
              <p className="text-xs text-muted-foreground">
                过期时间: {new Date(paymentOrder.expires_at).toLocaleTimeString("zh-CN")}
              </p>
              {paymentOrder.mock && (
                <Button className="w-full" onClick={handleMockPay}>
                  Mock 一键支付 (开发用)
                </Button>
              )}
              <Button
                variant="outline"
                className="w-full"
                onClick={() => setPaymentOrder(null)}
              >
                取消
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
