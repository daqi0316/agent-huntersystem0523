"use client";

import Link from "next/link";
import { notFound } from "next/navigation";

const CASES: Record<string, any> = {
  "alpha-tech": {
    industry: "互联网 / SaaS",
    company: "Alpha Tech (示例)",
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
  "beta-retail": {
    industry: "零售 / 连锁",
    company: "Beta Retail (示例)",
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
  "gamma-finance": {
    industry: "金融 / 财富管理",
    company: "Gamma Finance (示例)",
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
};

export default function CaseDetail({ params }: { params: { slug: string } }) {
  const c = CASES[params.slug];
  if (!c) notFound();

  return (
    <div className="container mx-auto p-6 max-w-3xl">
      <Link href="/cases" className="text-sm text-blue-600 hover:underline mb-4 inline-block">
        ← 返回案例列表
      </Link>

      <header className="mb-8">
        <h1 className="text-3xl font-bold mb-2">{c.company}</h1>
        <p className="text-gray-600">{c.industry} · {c.size}</p>
      </header>

      <section className="mb-8">
        <h2 className="text-xl font-semibold mb-2">挑战</h2>
        <p>{c.challenge}</p>
      </section>

      <section className="mb-8">
        <h2 className="text-xl font-semibold mb-2">方案</h2>
        <p>{c.solution}</p>
      </section>

      <section className="mb-8">
        <h2 className="text-xl font-semibold mb-4">结果</h2>
        <div className="grid gap-3">
          {c.results.map((r: any) => (
            <div key={r.metric} className="bg-blue-50 p-4 rounded">
              <div className="text-sm text-gray-500">{r.metric}</div>
              <div className="text-xl font-bold text-blue-700">{r.value}</div>
            </div>
          ))}
        </div>
      </section>

      <blockquote className="border-l-4 border-blue-500 pl-4 italic text-gray-700">
        &ldquo;{c.quote}&rdquo;
        <footer className="text-sm text-gray-500 mt-1 not-italic">— {c.author}</footer>
      </blockquote>
    </div>
  );
}
