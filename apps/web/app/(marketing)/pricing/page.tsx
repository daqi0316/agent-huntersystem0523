import type { Metadata } from "next"
import Link from "next/link"
import { CheckCircle2, X } from "lucide-react"

export const metadata: Metadata = {
  title: "价格 - AI Recruitment | 14 天免费试用",
  description: "Starter 免费, Pro ¥299/月, Enterprise ¥999/月。微信支付 / 支付宝秒到账。",
  alternates: { canonical: "https://airecruit.com/pricing" },
}

const PLANS = [
  {
    name: "Starter",
    price: 0,
    priceLabel: "免费",
    period: "永久",
    description: "小团队 / 试用 / 验证",
    features: [
      "10 用户",
      "1,000 候选人",
      "500K LLM tokens / 月",
      "基础 AI 简历评估",
      "邮件支持",
    ],
    notIncluded: [
      "智能匹配推荐",
      "钉钉/飞书集成",
      "审计日志导出",
    ],
    cta: "免费开始",
    highlight: false,
  },
  {
    name: "Pro",
    price: 299,
    priceLabel: "¥299",
    period: "/ 月",
    description: "中型 HR 团队 (5-50 人)",
    features: [
      "50 用户",
      "10,000 候选人",
      "2M LLM tokens / 月",
      "AI 评估 + 智能匹配",
      "微信 / 支付宝支付",
      "5×8 工单支持",
      "审计日志",
    ],
    notIncluded: [
      "钉钉/飞书集成 (Phase 6+)",
      "Enterprise SLA",
    ],
    cta: "开始 14 天试用",
    highlight: true,
  },
  {
    name: "Enterprise",
    price: 999,
    priceLabel: "¥999",
    period: "/ 月",
    description: "大型企业 / 国央企",
    features: [
      "500 用户",
      "100,000 候选人",
      "10M LLM tokens / 月",
      "全功能开放",
      "钉钉/飞书/企微集成",
      "7×24 客户成功",
      "私有化部署 (条件)",
      "SAML SSO + SCIM",
    ],
    notIncluded: [],
    cta: "联系销售",
    highlight: false,
  },
]

export default function PricingPage() {
  return (
    <div className="mx-auto max-w-6xl px-6 py-16">
      <div className="mb-12 text-center">
        <h1 className="text-4xl font-bold">价格</h1>
        <p className="mt-3 text-lg text-muted-foreground">
          14 天免费试用, 无需信用卡, 随时升级或降级
        </p>
      </div>

      <div className="grid gap-6 md:grid-cols-3">
        {PLANS.map((p) => (
          <div
            key={p.name}
            className={`relative rounded-lg border bg-white p-6 ${
              p.highlight ? "ring-2 ring-blue-500" : ""
            }`}
          >
            {p.highlight && (
              <div className="absolute -top-3 right-4 rounded-full bg-blue-600 px-3 py-1 text-xs font-medium text-white">
                推荐
              </div>
            )}
            <h3 className="text-lg font-semibold">{p.name}</h3>
            <p className="mt-1 text-xs text-muted-foreground">{p.description}</p>
            <div className="mt-4">
              <span className="text-4xl font-bold">{p.priceLabel}</span>
              <span className="text-sm text-muted-foreground">{p.period}</span>
            </div>
            <Link
              href={p.price === 0 ? "/onboarding/welcome" : "/settings/subscription"}
              className={`mt-6 block rounded-lg py-2 text-center text-sm font-medium ${
                p.highlight
                  ? "bg-blue-600 text-white hover:bg-blue-700"
                  : "border bg-white hover:bg-muted/30"
              }`}
            >
              {p.cta}
            </Link>
            <ul className="mt-6 space-y-2 text-sm">
              {p.features.map((f) => (
                <li key={f} className="flex items-start gap-2">
                  <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-green-600" />
                  <span>{f}</span>
                </li>
              ))}
              {p.notIncluded.map((f) => (
                <li key={f} className="flex items-start gap-2 text-muted-foreground">
                  <X className="mt-0.5 h-4 w-4 shrink-0" />
                  <span className="line-through">{f}</span>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>

      <div className="mt-12 rounded-lg border bg-muted/30 p-6 text-center">
        <p className="text-sm text-muted-foreground">
          所有计划含: 14 天免费试用 · 微信/支付宝支付 · 数据导出 · 7d 数据保留 · 端到端加密
        </p>
      </div>
    </div>
  )
}
