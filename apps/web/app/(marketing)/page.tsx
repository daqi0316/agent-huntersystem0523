import type { Metadata } from "next"
import Link from "next/link"
import { ArrowRight, CheckCircle2, Sparkles, Upload, Brain, Users, Zap } from "lucide-react"

export const metadata: Metadata = {
  title: "AI Recruitment - 国内 B2B 招聘 AI 助手 | 简历评估 + 智能匹配",
  description:
    "5 分钟内体验 AI 简历评估与候选人匹配。14 天免费试用, 微信支付秒到账, 国内 B2B 招聘团队的智能助手。",
  keywords: ["AI 招聘", "简历评估", "智能匹配", "B2B 招聘", "HR 工具", "招聘系统"],
  openGraph: {
    title: "AI Recruitment - 国内 B2B 招聘 AI 助手",
    description: "5 分钟体验 AI 简历评估, 14 天免费试用",
    type: "website",
    locale: "zh_CN",
    siteName: "AI Recruitment",
  },
  alternates: {
    canonical: "https://airecruit.com/",
  },
}

const FEATURES = [
  {
    icon: Brain,
    title: "AI 简历评估",
    desc: "5 维度 (技能 / 经验 / 教育 / 文化 / 潜力) 评分, 1-3 秒完成, 优势/风险自动摘要",
  },
  {
    icon: Users,
    title: "智能候选人匹配",
    desc: "1-on-1 候选人-职位匹配度评分, 自动推送给 HR, 节省 80% 筛选时间",
  },
  {
    icon: Sparkles,
    title: "团队协作",
    desc: "邀请同事 (老带新 seat+1), 邀请评审人, 6 个月 audit 留痕",
  },
  {
    icon: Zap,
    title: "集成钉钉/飞书/企微",
    desc: "通知/审批无缝同步, 面试官不用切应用, 国内 HR 工具一站打通",
  },
]

const STATS = [
  { value: "5 分钟", label: "跑通第一个评估" },
  { value: "3 秒", label: "AI 评估速度" },
  { value: "14 天", label: "免费试用" },
  { value: "¥299/月", label: "Pro 起步价" },
]

export default function HomePage() {
  return (
    <div className="bg-gradient-to-b from-blue-50/50 to-background">
      <section className="mx-auto max-w-6xl px-6 py-20 text-center md:py-32">
        <div className="mx-auto inline-flex items-center gap-2 rounded-full border bg-white px-3 py-1 text-xs text-muted-foreground">
          <Sparkles className="h-3 w-3 text-blue-600" />
          国内首个 LLM 驱动的 B2B 招聘 AI 助手
        </div>
        <h1 className="mt-6 text-4xl font-bold tracking-tight md:text-6xl">
          5 分钟体验 AI 简历评估
          <br />
          <span className="bg-gradient-to-r from-blue-600 to-purple-600 bg-clip-text text-transparent">
            节省 80% 筛选时间
          </span>
        </h1>
        <p className="mx-auto mt-6 max-w-2xl text-lg text-muted-foreground">
          14 天免费试用, 无需信用卡。微信支付 / 支付宝秒到账, 国内 B2B 招聘团队的智能助手。
        </p>
        <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
          <Link
            href="/onboarding/welcome"
            className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-6 py-3 text-sm font-medium text-white hover:bg-blue-700"
          >
            免费试用 14 天
            <ArrowRight className="h-4 w-4" />
          </Link>
          <Link
            href="/pricing"
            className="inline-flex items-center gap-2 rounded-lg border bg-white px-6 py-3 text-sm font-medium hover:bg-muted/30"
          >
            查看价格
          </Link>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-6 py-12">
        <div className="grid grid-cols-2 gap-6 md:grid-cols-4">
          {STATS.map((s) => (
            <div key={s.label} className="rounded-lg border bg-white p-6 text-center">
              <div className="text-3xl font-bold text-blue-600">{s.value}</div>
              <div className="mt-1 text-xs text-muted-foreground">{s.label}</div>
            </div>
          ))}
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-6 py-20">
        <div className="mb-12 text-center">
          <h2 className="text-3xl font-bold">核心功能</h2>
          <p className="mt-2 text-muted-foreground">从简历到 offer, AI 陪你每一步</p>
        </div>
        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-4">
          {FEATURES.map((f) => {
            const Icon = f.icon
            return (
              <div key={f.title} className="rounded-lg border bg-white p-6">
                <Icon className="h-8 w-8 text-blue-600" />
                <h3 className="mt-3 text-lg font-semibold">{f.title}</h3>
                <p className="mt-2 text-sm text-muted-foreground">{f.desc}</p>
              </div>
            )
          })}
        </div>
      </section>

      <section className="bg-gradient-to-r from-blue-600 to-purple-600 py-20 text-white">
        <div className="mx-auto max-w-4xl px-6 text-center">
          <h2 className="text-3xl font-bold">立即开始 14 天免费试用</h2>
          <p className="mt-4 text-lg text-blue-100">
            无需信用卡, 5 分钟体验完整功能
          </p>
          <Link
            href="/onboarding/welcome"
            className="mt-8 inline-flex items-center gap-2 rounded-lg bg-white px-6 py-3 text-sm font-medium text-blue-600 hover:bg-blue-50"
          >
            开始试用
            <ArrowRight className="h-4 w-4" />
          </Link>
        </div>
      </section>
    </div>
  )
}
