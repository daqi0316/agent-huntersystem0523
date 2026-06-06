"use client";

const CASES = [
  {
    slug: "alpha-tech",
    industry: "互联网 / SaaS",
    company: "Alpha Tech (示例)",
    logo: "A",
    size: "200-500 人",
    challenge: "工程岗位每月 800+ 简历, 2 个 HR 全靠人工初筛, 漏筛率高, 面试安排混乱。",
    solution: "3 步 onboarding + AI 评估 + 自动面试协调。",
    results: [
      { metric: "初筛时间", value: "从 4h/岗位 → 15min/岗位" },
      { metric: "简历漏筛率", value: "从 18% → 4%" },
      { metric: "HR 周活", value: "92%" },
    ],
    quote: "我们 HR 现在专注面候选人本身, 而不是被淹没在简历里。",
    author: "陈经理 · Alpha Tech People Ops",
  },
  {
    slug: "beta-retail",
    industry: "零售 / 连锁",
    company: "Beta Retail (示例)",
    logo: "B",
    size: "5000+ 人 · 80+ 门店",
    challenge: "门店店长 / 督导招聘分散, 标准不统一, 区域 HR 协作难。",
    solution: "组织多级权限 + 模板化评估 + 移动端面试。",
    results: [
      { metric: "门店到岗时间", value: "从 21 天 → 9 天" },
      { metric: "评估一致性", value: "从 65% → 89%" },
      { metric: "招聘总成本", value: "下降 32%" },
    ],
    quote: "80 家门店店长招到了对的人, 而不是先到的人。",
    author: "李总监 · Beta Retail 招聘",
  },
  {
    slug: "gamma-finance",
    industry: "金融 / 财富管理",
    company: "Gamma Finance (示例)",
    logo: "G",
    size: "100-200 人",
    challenge: "理财顾问 / 风控岗位要求严, 候选人质量把关难, AI 评估透明度是合规关键。",
    solution: "AI 评估 + 人工 override + 7d 申诉 + 完整审计链。",
    results: [
      { metric: "合规申诉处理", value: "48h 内 100% 闭环" },
      { metric: "面试通过率", value: "从 28% → 41%" },
      { metric: "AI 误判率", value: "< 3%, 持续下降" },
    ],
    quote: "AI 评分 + 人工覆盖, 监管来查时审计链一清二楚。",
    author: "王合规官 · Gamma Finance",
  },
];

export default function CasesPage() {
  return (
    <div className="container mx-auto p-6">
      <h1 className="text-3xl font-bold mb-2">客户案例</h1>
      <p className="text-gray-600 mb-8">
        真实使用 AI 招聘助手的企业, 覆盖互联网 / 零售 / 金融 3 大行业。
      </p>

      <div className="grid gap-8">
        {CASES.map((c) => (
          <article
            key={c.slug}
            className="border rounded-lg p-6 hover:shadow-lg transition-shadow"
          >
            <div className="flex items-start gap-4">
              <div className="w-16 h-16 rounded bg-gradient-to-br from-blue-500 to-purple-600 text-white text-2xl font-bold flex items-center justify-center flex-shrink-0">
                {c.logo}
              </div>
              <div className="flex-1">
                <div className="flex items-center justify-between mb-2">
                  <h2 className="text-xl font-semibold">{c.company}</h2>
                  <span className="text-sm text-gray-500">{c.industry} · {c.size}</span>
                </div>

                <div className="mb-4">
                  <h3 className="text-sm font-semibold text-gray-500 mb-1">挑战</h3>
                  <p>{c.challenge}</p>
                </div>

                <div className="mb-4">
                  <h3 className="text-sm font-semibold text-gray-500 mb-1">方案</h3>
                  <p>{c.solution}</p>
                </div>

                <div className="mb-4">
                  <h3 className="text-sm font-semibold text-gray-500 mb-2">结果</h3>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                    {c.results.map((r) => (
                      <div key={r.metric} className="bg-blue-50 p-3 rounded">
                        <div className="text-xs text-gray-500">{r.metric}</div>
                        <div className="text-lg font-bold text-blue-700">{r.value}</div>
                      </div>
                    ))}
                  </div>
                </div>

                <blockquote className="border-l-4 border-blue-500 pl-4 italic text-gray-700">
                  &ldquo;{c.quote}&rdquo;
                  <footer className="text-sm text-gray-500 mt-1 not-italic">
                    — {c.author}
                  </footer>
                </blockquote>
              </div>
            </div>
          </article>
        ))}
      </div>

      <div className="mt-12 p-6 bg-gray-50 rounded-lg text-center">
        <h2 className="text-2xl font-bold mb-2">成为下一个案例</h2>
        <p className="text-gray-600 mb-4">
          14 天免费试用, 1-on-1 onboarding, 7 天内见效。
        </p>
        <a
          href="/trial"
          className="inline-block px-6 py-3 bg-blue-600 text-white rounded font-semibold"
        >
          立即试用
        </a>
      </div>
    </div>
  );
}
