"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ArrowRight, CheckCircle2, Clock, Sparkles } from "lucide-react";

export default function OnboardingWelcomePage() {
  const router = useRouter()
  return (
    <div className="space-y-6">
      <div className="text-center">
        <h1 className="text-3xl font-bold">欢迎使用 AI Recruitment</h1>
        <p className="mt-2 text-muted-foreground">
          5 分钟内体验 AI 简历评估与匹配, 无需信用卡
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader className="pb-2">
            <Clock className="h-5 w-5 text-blue-600" />
            <CardTitle className="text-sm">5 分钟跑通</CardTitle>
          </CardHeader>
          <CardContent className="text-xs text-muted-foreground">
            上传 1 份简历 + 1 个 JD → AI 评估 + 匹配分数
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <Sparkles className="h-5 w-5 text-purple-600" />
            <CardTitle className="text-sm">14 天试用</CardTitle>
          </CardHeader>
          <CardContent className="text-xs text-muted-foreground">
            全功能开放, 无需信用卡, 到期前 3 天提醒
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CheckCircle2 className="h-5 w-5 text-green-600" />
            <CardTitle className="text-sm">随时升级</CardTitle>
          </CardHeader>
          <CardContent className="text-xs text-muted-foreground">
            试用期内可随时升级, 微信 / 支付宝秒到账
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>接下来 3 步</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex items-start gap-3 rounded border bg-muted/30 p-3">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-blue-600 text-xs text-white">1</span>
            <div>
              <div className="font-medium">上传候选人简历 (PDF / Word)</div>
              <div className="text-xs text-muted-foreground">支持 1 个候选人, 完成后可批量导入</div>
            </div>
          </div>
          <div className="flex items-start gap-3 rounded border bg-muted/30 p-3">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-blue-600 text-xs text-white">2</span>
            <div>
              <div className="font-medium">AI 评估简历 (1-3 秒)</div>
              <div className="text-xs text-muted-foreground">5 维度评分 + 优势/风险摘要</div>
            </div>
          </div>
          <div className="flex items-start gap-3 rounded border bg-muted/30 p-3">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-blue-600 text-xs text-white">3</span>
            <div>
              <div className="font-medium">匹配职位 (推荐)</div>
              <div className="text-xs text-muted-foreground">1-on-1 匹配度评分 + 推送 HR</div>
            </div>
          </div>
        </CardContent>
      </Card>

      <div className="flex justify-between">
        <Button variant="ghost" onClick={() => router.push("/dashboard")}>
          跳过引导
        </Button>
        <Button onClick={() => router.push("/onboarding/upload")}>
          开始 <ArrowRight className="ml-2 h-4 w-4" />
        </Button>
      </div>
    </div>
  )
}
