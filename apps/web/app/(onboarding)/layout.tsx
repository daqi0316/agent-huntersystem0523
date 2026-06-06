"use client";

import { ReactNode } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Upload, Sparkles, CheckCircle2 } from "lucide-react";

const STEPS = [
  { key: "welcome", label: "欢迎", href: "/onboarding/welcome", icon: CheckCircle2 },
  { key: "upload", label: "上传简历", href: "/onboarding/upload", icon: Upload },
  { key: "evaluate", label: "AI 评估", href: "/onboarding/evaluate", icon: Sparkles },
];

export default function OnboardingLayout({ children }: { children: ReactNode }) {
  const pathname = usePathname() ?? "";
  const currentStepIdx = STEPS.findIndex((s) => pathname.endsWith(s.key));
  const activeIdx = currentStepIdx >= 0 ? currentStepIdx : 0;

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b bg-white">
        <div className="mx-auto max-w-3xl px-6 py-4">
          <div className="mb-2 flex items-center justify-between">
            <Link href="/dashboard" className="text-sm text-muted-foreground hover:text-foreground">
              ← 跳到 dashboard
            </Link>
            <span className="text-xs text-muted-foreground">第 {activeIdx + 1} 步 / 共 {STEPS.length} 步</span>
          </div>
          <div className="flex items-center gap-2">
            {STEPS.map((s, i) => {
              const Icon = s.icon
              const isActive = i === activeIdx
              const isDone = i < activeIdx
              return (
                <div key={s.key} className="flex flex-1 items-center gap-2">
                  <div
                    className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${
                      isActive
                        ? "bg-blue-600 text-white"
                        : isDone
                          ? "bg-green-100 text-green-700"
                          : "bg-muted text-muted-foreground"
                    }`}
                  >
                    {isDone ? <Icon className="h-4 w-4" /> : i + 1}
                  </div>
                  <div className="flex-1">
                    <div className={`text-sm font-medium ${isActive ? "text-foreground" : "text-muted-foreground"}`}>
                      {s.label}
                    </div>
                    <div className="mt-1 h-1 rounded-full bg-muted">
                      <div
                        className={`h-1 rounded-full transition-all ${
                          isActive ? "w-1/2 bg-blue-600" : isDone ? "w-full bg-green-500" : "w-0"
                        }`}
                      />
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-3xl px-6 py-8">{children}</main>
    </div>
  )
}
