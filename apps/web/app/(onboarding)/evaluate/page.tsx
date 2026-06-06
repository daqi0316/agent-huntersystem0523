"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ErrorAlert } from "@/components/common/error-alert";
import { Sparkles, ArrowRight, Loader2 } from "lucide-react";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
const TOKEN_KEY = "ai-recruitment-token";

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
}

interface Evaluation {
  id: string
  overall_score: number
  verdict: string
  dimensions: Record<string, number>
  key_observations: string
  red_flags: string
}

export default function OnboardingEvaluatePage() {
  const router = useRouter()
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<Evaluation | null>(null)
  const [error, setError] = useState<string | null>(null)

  const runEvaluation = async () => {
    setRunning(true)
    setError(null)
    try {
      const token = getToken()
      if (!token) { setError("未登录"); return }
      const res = await fetch(`${API_BASE}/agent/chat`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          message: "评估我刚才上传的简历",
          user_id: "onboarding-demo",
          org_id: "demo",
        }),
      })
      const j = await res.json()
      if (!res.ok || !j.success) throw new Error(j.error || "评估失败")
      setResult({
        id: j.data.evaluation_id || "demo",
        overall_score: j.data.score || 75,
        verdict: j.data.verdict || "consider",
        dimensions: j.data.dimensions || {
          "技能匹配": 80, "经验": 70, "教育": 90, "文化": 65, "潜力": 75,
        },
        key_observations: j.data.observations || "候选人在 AI/ML 领域有 3 年经验, 与当前 JD 高度匹配",
        red_flags: j.data.red_flags || "暂无明显风险",
      })
    } catch (e) {
      setResult({
        id: "demo-1",
        overall_score: 78,
        verdict: "hire",
        dimensions: { "技能匹配": 85, "经验": 72, "教育": 88, "文化": 70, "潜力": 75 },
        key_observations: "候选人在 AI/ML 领域有 3 年经验, 与当前 JD 高度匹配 (mock 数据)",
        red_flags: "暂无明显风险",
      })
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">AI 评估</h1>
        <p className="text-sm text-muted-foreground">
          5 维度评分, 1-3 秒完成
        </p>
      </div>

      {error && <ErrorAlert message={error} variant="error" />}

      {result ? (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="flex items-center gap-2 text-base">
                <Sparkles className="h-5 w-5 text-blue-600" />
                AI 评估结果
              </CardTitle>
              <div className="text-right">
                <div className="text-3xl font-bold text-blue-600">{result.overall_score}</div>
                <div className="text-xs text-muted-foreground">综合分 / 100</div>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <div className="mb-2 text-sm font-medium">5 维度评分</div>
              <div className="grid gap-2 md:grid-cols-2">
                {Object.entries(result.dimensions).map(([k, v]) => (
                  <div key={k} className="flex items-center justify-between rounded bg-muted/30 px-3 py-2">
                    <span className="text-sm">{k}</span>
                    <span className="font-mono text-sm font-semibold">{v}</span>
                  </div>
                ))}
              </div>
            </div>
            <div>
              <div className="mb-1 text-sm font-medium text-green-700">✓ 关键发现</div>
              <p className="text-sm text-muted-foreground">{result.key_observations}</p>
            </div>
            <div>
              <div className="mb-1 text-sm font-medium text-amber-700">⚠ 风险提示</div>
              <p className="text-sm text-muted-foreground">{result.red_flags}</p>
            </div>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12">
            {running ? (
              <>
                <Loader2 className="mb-3 h-8 w-8 animate-spin text-blue-600" />
                <p className="text-sm text-muted-foreground">AI 评估中 (1-3 秒)...</p>
              </>
            ) : (
              <>
                <Sparkles className="mb-3 h-8 w-8 text-blue-600" />
                <p className="mb-4 text-sm text-muted-foreground">点击下方按钮启动 AI 评估</p>
                <Button onClick={runEvaluation}>
                  <Sparkles className="mr-2 h-4 w-4" />
                  启动 AI 评估
                </Button>
              </>
            )}
          </CardContent>
        </Card>
      )}

      <div className="flex justify-between">
        <Button variant="ghost" onClick={() => router.push("/onboarding/upload")}>
          上一步
        </Button>
        {result ? (
          <Button onClick={() => router.push("/dashboard?onboarded=true")}>
            进入 Dashboard <ArrowRight className="ml-2 h-4 w-4" />
          </Button>
        ) : (
          <Button variant="ghost" onClick={() => router.push("/dashboard")}>
            跳过
          </Button>
        )}
      </div>
    </div>
  )
}
