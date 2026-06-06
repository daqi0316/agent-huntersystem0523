"use client";

import Link from "next/link";
import { ReactNode } from "react";
import { Sparkles, Menu, X } from "lucide-react";
import { useState } from "react";

const NAV_ITEMS = [
  { href: "/", label: "首页" },
  { href: "/pricing", label: "价格" },
  { href: "/blog", label: "博客" },
  { href: "/case-studies", label: "案例" },
];

export default function MarketingLayout({ children }: { children: ReactNode }) {
  const [menuOpen, setMenuOpen] = useState(false)
  return (
    <div className="min-h-screen bg-background">
      <header className="sticky top-0 z-50 border-b bg-white/80 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <Link href="/" className="flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-blue-600" />
            <span className="text-lg font-semibold">AI Recruitment</span>
          </Link>
          <nav className="hidden items-center gap-6 md:flex">
            {NAV_ITEMS.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className="text-sm text-muted-foreground hover:text-foreground"
              >
                {item.label}
              </Link>
            ))}
            <Link
              href="/login"
              className="text-sm text-muted-foreground hover:text-foreground"
            >
              登录
            </Link>
            <Link
              href="/onboarding/welcome"
              className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
            >
              免费试用 14 天
            </Link>
          </nav>
          <button
            onClick={() => setMenuOpen(!menuOpen)}
            className="md:hidden"
            aria-label="菜单"
          >
            {menuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
        </div>
        {menuOpen && (
          <nav className="border-t bg-white px-6 py-3 md:hidden">
            {NAV_ITEMS.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => setMenuOpen(false)}
                className="block py-2 text-sm text-muted-foreground hover:text-foreground"
              >
                {item.label}
              </Link>
            ))}
          </nav>
        )}
      </header>
      <main>{children}</main>
      <footer className="mt-16 border-t bg-muted/30">
        <div className="mx-auto grid max-w-6xl gap-8 px-6 py-12 md:grid-cols-4">
          <div>
            <div className="mb-2 flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-blue-600" />
              <span className="font-semibold">AI Recruitment</span>
            </div>
            <p className="text-xs text-muted-foreground">
              国内 B2B 招聘 AI 助手, 简历评估 + 智能匹配 + 团队管理。
            </p>
          </div>
          <div>
            <h4 className="mb-2 text-sm font-semibold">产品</h4>
            <ul className="space-y-1 text-xs text-muted-foreground">
              <li><Link href="/pricing">价格</Link></li>
              <li><Link href="/onboarding/welcome">免费试用</Link></li>
              <li><Link href="/blog">博客</Link></li>
            </ul>
          </div>
          <div>
            <h4 className="mb-2 text-sm font-semibold">资源</h4>
            <ul className="space-y-1 text-xs text-muted-foreground">
              <li><Link href="/case-studies">客户案例</Link></li>
              <li><Link href="/legal/privacy">隐私政策</Link></li>
              <li><Link href="/legal/terms">服务条款</Link></li>
            </ul>
          </div>
          <div>
            <h4 className="mb-2 text-sm font-semibold">联系</h4>
            <ul className="space-y-1 text-xs text-muted-foreground">
              <li>support@airecruit.com</li>
              <li>微信公众号: AI Recruitment</li>
            </ul>
          </div>
        </div>
        <div className="border-t py-4 text-center text-xs text-muted-foreground">
          © 2026 AI Recruitment. 国内 B2B 招聘 AI 助手.
        </div>
      </footer>
    </div>
  )
}
