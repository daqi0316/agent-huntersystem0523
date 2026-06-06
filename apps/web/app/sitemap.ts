import type { MetadataRoute } from "next"

export default function sitemap(): MetadataRoute.Sitemap {
  const base = "https://airecruit.com"
  const now = new Date()

  const staticPages = [
    { url: `${base}/`, changeFrequency: "weekly" as const, priority: 1.0 },
    { url: `${base}/pricing`, changeFrequency: "monthly" as const, priority: 0.9 },
    { url: `${base}/blog`, changeFrequency: "weekly" as const, priority: 0.8 },
  ]

  const blogSlugs = [
    "ai-resume-screening-5-dimensions",
    "wechat-pay-vs-alipay-b2b",
    "multi-tenant-rls-postgres",
    "pipl-30-day-deletion",
    "llm-rate-limit-cost-control",
    "ai-disclosure-2026-regulation",
  ]

  const blogPages = blogSlugs.map((slug) => ({
    url: `${base}/blog/${slug}`,
    lastModified: now,
    changeFrequency: "monthly" as const,
    priority: 0.7,
  }))

  return [...staticPages, ...blogPages]
}
