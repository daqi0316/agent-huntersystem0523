import Link from "next/link"
import { notFound } from "next/navigation"
import { ArrowLeft, Calendar, Clock } from "lucide-react"

const POSTS: Record<string, { title: string; date: string; category: string; readingTime: number; content: string[] }> = {
  "ai-resume-screening-5-dimensions": {
    title: "AI 简历评估的 5 维度模型: 为什么我们用这个",
    date: "2026-06-01",
    category: "技术",
    readingTime: 8,
    content: [
      "在 4 个月的客户白鼠中, 我们发现单一指标 (如学历) 的 AI 评估准确率只有 60%, 而 5 维度加权 (技能 / 经验 / 教育 / 文化 / 潜力) 准确率达 85%。",
      "## 5 维度权重",
      "- 技能匹配 (40%): 候选人技能与 JD 要求的关键字 / 概念匹配度, 用 embedding 相似度",
      "- 经验 (25%): 相关行业经验年限 + 项目复杂度",
      "- 教育 (10%): 学历 + 学校 + 专业相关度 (权重低, 避免学历歧视)",
      "- 文化 (15%): 公司价值观 + 候选人职业倾向匹配",
      "- 潜力 (10%): 学习能力 + 成长轨迹 (用历史职位晋升数据)",
      "## 工程实现",
      "5 维度独立 LLM 调用, 后聚合权重。每个维度都有 explainability (为何这个分), 落 ai_score_source JSON。",
      "## 客户反馈",
      "A 客户 (互联网 HR): '比之前用的工具准确率高, 尤其是潜力分'。B 客户 (制造业): '文化分帮助识别价值观匹配'。",
    ],
  },
  "wechat-pay-vs-alipay-b2b": {
    title: "B2B 订阅支付: 微信支付 vs 支付宝 (2026 实测)",
    date: "2026-05-25",
    category: "实战",
    readingTime: 12,
    content: [
      "国内 B 端订阅模式 (SaaS 月付/年付), 微信支付和支付宝的优劣对比, 来自 4 个月客户白鼠的实战数据。",
      "## 接入成本",
      "微信支付: 商户号申请 1-3d, API 接入 1-2d, 退款 1d 配置。",
      "支付宝: 商户号申请 1-2d, RSA2 密钥对 1d, 回调 1d 配置。",
      "## 用户偏好",
      "微信支付占 60% (微信生态在国内 HR 工具天然优势), 支付宝占 40% (财务部门偏好)。",
      "## 退款 SLA",
      "微信支付 1-3 工作日, 支付宝 1-2 工作日。两者都有 dispute 处理机制, 但支付宝 SLA 严于微信 (72h vs 7d)。",
      "## 推荐策略",
      "同时接两个通道, 客户自助选择。退款 / dispute 处理 SOP 必备 (P6-11)。",
    ],
  },
  "multi-tenant-rls-postgres": {
    title: "PostgreSQL RLS 多租户: 实战 + 性能基准",
    date: "2026-05-18",
    category: "技术",
    readingTime: 15,
    content: [
      "3 层防御 (业务层 + 中间件 + DB RLS) 是国内 SaaS 多租户的标配。本文分享我们的 10 PR 实施过程 + 性能基准。",
      "## 性能基准",
      "14 张业务表加 RLS 后, P99 延迟增加 2-5ms (5%), 可接受。如果超过 10ms 需考虑 connection pool 调优。",
      "## 跨租户测试",
      "1 个 dedicated negative test + 22 unit tests 100% 通过。P5-1 阶段共 1 万行代码改动, 0 跨租户泄漏事故。",
    ],
  },
  "pipl-30-day-deletion": {
    title: "PIPL 个保法合规: 30 天宽限期的工程实现",
    date: "2026-05-10",
    category: "合规",
    readingTime: 10,
    content: [
      "PIPL 17 条要求用户撤回后删除数据, 但实际工程面临外键约束。本文分享外键占位策略。",
      "## 流程",
      "1. 用户撤回 → 软删 (is_active=False, 30d 内禁登录)",
      "2. 30d 宽限期: 可撤回, 恢复 is_active",
      "3. 30d 后硬删: PII 匿名化 (邮箱 → deleted_<uuid>@deleted.local), 所有外键引用改占位 UUID",
      "## 占位策略",
      "占位 UUID = 'deleted_user_<random>' + 建一个假 user row (不可登录)。audit_log / payment 引用改到占位, 保留链可追溯。",
    ],
  },
  "llm-rate-limit-cost-control": {
    title: "LLM 限流: 3-key (org/user/IP) + 灰度发布实战",
    date: "2026-05-01",
    category: "技术",
    readingTime: 11,
    content: [
      "3-key 限流 (org/user/IP) 防止 1 个客户端刷爆 LLM 配额。灰度 1%→10%→100% 上线 4 周观察期。",
      "## 配额设计",
      "Starter: 500K tokens / 月, Pro: 2M, Enterprise: 10M。超 100% 自动熔断 (返 429, 飞书通知 owner)。",
      "## 灰度机制",
      "RATELIMIT_ROLLOUT_PCT env (0-100)。上线节奏: 1% (1d) → 10% (1d) → 50% (1d) → 100%。任何阶段回滚 = 改 env 0%。",
    ],
  },
  "ai-disclosure-2026-regulation": {
    title: "2026-08 生成式 AI 服务管理办法: AI 评分必须可追溯",
    date: "2026-04-20",
    category: "合规",
    readingTime: 9,
    content: [
      "2026-08 实施的新规要求生成式 AI 服务必须显式标识 AI 生成, 用户有覆盖 + 申诉权。",
      "## 工程要求",
      "- AI 评分字段: ai_score_source JSON (LLM/model/version/prompt_hash/generated_at)",
      "- UI: 评分旁显式标识 (Sparkles 图标), hover 显示来源",
      "- 用户覆盖: 任何评分可改写, 改后 audit 落 AI_OVERRIDE",
      "- 申诉: 7d 内必回复, 超时告警",
    ],
  },
}

export function generateStaticParams() {
  return Object.keys(POSTS).map((slug) => ({ slug }))
}

export default async function BlogPostPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params
  const post = POSTS[slug]
  if (!post) notFound()

  return (
    <article className="mx-auto max-w-3xl px-6 py-16">
      <Link
        href="/blog"
        className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-3 w-3" /> 返回博客
      </Link>
      <header className="mt-6 border-b pb-6">
        <div className="flex items-center gap-3 text-xs text-muted-foreground">
          <span className="rounded bg-blue-50 px-2 py-0.5 font-medium text-blue-700">
            {post.category}
          </span>
          <span className="flex items-center gap-1">
            <Calendar className="h-3 w-3" /> {post.date}
          </span>
          <span className="flex items-center gap-1">
            <Clock className="h-3 w-3" /> {post.readingTime} 分钟
          </span>
        </div>
        <h1 className="mt-4 text-4xl font-bold">{post.title}</h1>
      </header>
      <div className="prose prose-slate mt-8 max-w-none">
        {post.content.map((para, i) => {
          if (para.startsWith("## ")) {
            return <h2 key={i} className="mt-8 text-2xl font-bold">{para.replace("## ", "")}</h2>
          }
          if (para.startsWith("- ")) {
            return <li key={i} className="ml-4 list-disc text-base">{para.replace("- ", "")}</li>
          }
          return <p key={i} className="mt-4 text-base leading-relaxed text-muted-foreground">{para}</p>
        })}
      </div>
    </article>
  )
}
