import type { Metadata } from "next"
import Link from "next/link"
import { Calendar, ArrowRight } from "lucide-react"

export const metadata: Metadata = {
  title: "博客 - AI Recruitment | 招聘 AI 实战分享",
  description: "AI 简历评估、智能匹配、HR 工具对比、招聘效率提升实战。",
  alternates: { canonical: "https://airecruit.com/blog" },
}

const POSTS = [
  {
    slug: "ai-resume-screening-5-dimensions",
    title: "AI 简历评估的 5 维度模型: 为什么我们用这个",
    excerpt: "技能匹配 / 经验 / 教育 / 文化 / 潜力, 5 维度评分如何避免单一指标偏见",
    date: "2026-06-01",
    readingTime: 8,
    category: "技术",
  },
  {
    slug: "wechat-pay-vs-alipay-b2b",
    title: "B2B 订阅支付: 微信支付 vs 支付宝 (2026 实测)",
    excerpt: "B 端订阅模式在国内两大支付通道的优劣对比, 退款 / 续费 / dispute 处理",
    date: "2026-05-25",
    readingTime: 12,
    category: "实战",
  },
  {
    slug: "multi-tenant-rls-postgres",
    title: "PostgreSQL RLS 多租户: 实战 + 性能基准",
    excerpt: "3 层防御 (业务层 + 中间件 + DB RLS) 如何设计, 跨租户测试 100% 通过",
    date: "2026-05-18",
    readingTime: 15,
    category: "技术",
  },
  {
    slug: "pipl-30-day-deletion",
    title: "PIPL 个保法合规: 30 天宽限期的工程实现",
    excerpt: "外键占位策略 + 软删/硬删 + 申诉流程, 满足个保法第 17 条",
    date: "2026-05-10",
    readingTime: 10,
    category: "合规",
  },
  {
    slug: "llm-rate-limit-cost-control",
    title: "LLM 限流: 3-key (org/user/IP) + 灰度发布实战",
    excerpt: "P99 < 2s, 误限率 < 0.1%, 灰度 1%→10%→100% 的 4 周上线",
    date: "2026-05-01",
    readingTime: 11,
    category: "技术",
  },
  {
    slug: "ai-disclosure-2026-regulation",
    title: "2026-08 生成式 AI 服务管理办法: AI 评分必须可追溯",
    excerpt: "AI 评分必须标识 LLM/model/version, 用户有覆盖 + 申诉权, 7d 内回复",
    date: "2026-04-20",
    readingTime: 9,
    category: "合规",
  },
]

export default function BlogPage() {
  return (
    <div className="mx-auto max-w-4xl px-6 py-16">
      <h1 className="text-4xl font-bold">博客</h1>
      <p className="mt-3 text-lg text-muted-foreground">
        AI 招聘技术、实战、合规分享
      </p>

      <div className="mt-10 grid gap-6">
        {POSTS.map((p) => (
          <Link
            key={p.slug}
            href={`/blog/${p.slug}`}
            className="group block rounded-lg border bg-white p-6 transition hover:border-blue-500 hover:shadow-md"
          >
            <div className="flex items-center gap-3 text-xs text-muted-foreground">
              <span className="rounded bg-blue-50 px-2 py-0.5 font-medium text-blue-700">
                {p.category}
              </span>
              <span className="flex items-center gap-1">
                <Calendar className="h-3 w-3" />
                {p.date}
              </span>
              <span>{p.readingTime} 分钟阅读</span>
            </div>
            <h2 className="mt-3 text-xl font-semibold group-hover:text-blue-600">
              {p.title}
            </h2>
            <p className="mt-2 text-sm text-muted-foreground">{p.excerpt}</p>
            <div className="mt-4 inline-flex items-center gap-1 text-sm font-medium text-blue-600">
              阅读全文
              <ArrowRight className="h-3 w-3" />
            </div>
          </Link>
        ))}
      </div>
    </div>
  )
}
