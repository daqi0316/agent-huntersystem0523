"use client";

import { useState } from "react";
import { FilePen, Loader2, CheckCircle, XCircle, RotateCcw } from "lucide-react";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { ErrorAlert } from "@/components/common/error-alert";
import { Separator } from "@/components/ui/separator";
import { api } from "@/lib/trpc";
import { cn } from "@/lib/utils";

interface JDIteration {
  iteration: number;
  generated: string;
  score?: number;
  feedback?: string;
  passed: boolean;
}

interface JDGenerateResponse {
  success: boolean;
  data: string;
  iterations: JDIteration[];
  total_iterations: number;
  passed: boolean;
}

export default function JDGeneratorPage() {
  const [title, setTitle] = useState("");
  const [requirements, setRequirements] = useState("");
  const [preferences, setPreferences] = useState("");
  const [autoImprove, setAutoImprove] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<JDGenerateResponse | null>(null);

  const canSubmit = title.trim().length > 0 && requirements.trim().length > 0 && !loading;

  const handleSubmit = async () => {
    if (!canSubmit) return;
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const res = await api.post<JDGenerateResponse>("/agent/generate-jd", {
        title: title.trim(),
        requirements: requirements.trim(),
        preferences: preferences.trim() || undefined,
        auto_improve: autoImprove,
      });
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "生成失败，请重试");
    } finally {
      setLoading(false);
    }
  };

  const handleReset = () => {
    setTitle("");
    setRequirements("");
    setPreferences("");
    setAutoImprove(true);
    setResult(null);
    setError(null);
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">JD生成器</h1>
        <p className="text-sm text-muted-foreground mt-1">
          使用 AI 生成高质量的职位描述
        </p>
      </div>

      {!result && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg flex items-center gap-2">
              <FilePen className="h-5 w-5" />
              填写职位信息
            </CardTitle>
            <CardDescription>
              填写职位名称和核心要求，AI 将自动生成完整的职位描述
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <label className="text-sm font-medium">
                职位名称 <span className="text-destructive">*</span>
              </label>
              <Input
                placeholder="例如：高级前端工程师"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                maxLength={200}
              />
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium">
                核心要求 <span className="text-destructive">*</span>
              </label>
              <Textarea
                placeholder="例如：5 年以上 React 开发经验，熟悉 TypeScript，有大型项目架构经验..."
                value={requirements}
                onChange={(e) => setRequirements(e.target.value)}
                rows={5}
                maxLength={3000}
              />
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium text-muted-foreground">
                补充说明（可选）
              </label>
              <Textarea
                placeholder="例如：优先考虑有 AI 产品经验的候选人或提供远程办公选项..."
                value={preferences}
                onChange={(e) => setPreferences(e.target.value)}
                rows={3}
                maxLength={2000}
              />
            </div>

            <div className="flex items-center gap-3 pt-2">
              <Switch
                id="auto-improve"
                checked={autoImprove}
                onCheckedChange={setAutoImprove}
              />
              <label htmlFor="auto-improve" className="text-sm cursor-pointer">
                Gen-Eval 迭代优化
                <span className="text-muted-foreground ml-1">
                  （AI 自我评估并改进 JD 质量）
                </span>
              </label>
            </div>

            {error && <ErrorAlert message={error} />}

            <Button
              onClick={handleSubmit}
              disabled={!canSubmit}
              className="w-full"
              size="lg"
            >
              {loading ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  生成中...
                </>
              ) : (
                <>
                  <FilePen className="mr-2 h-4 w-4" />
                  生成职位描述
                </>
              )}
            </Button>
          </CardContent>
        </Card>
      )}

      {result && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <h2 className="text-lg font-semibold">生成结果</h2>
              <Badge variant={result.passed ? "success" : "warning"}>
                {result.passed ? (
                  <><CheckCircle className="mr-1 h-3 w-3" /> 已通过</>
                ) : (
                  <><XCircle className="mr-1 h-3 w-3" /> 待改进</>
                )}
              </Badge>
              <Badge variant="secondary">
                {result.total_iterations} 轮迭代
              </Badge>
            </div>
            <Button variant="outline" size="sm" onClick={handleReset}>
              <RotateCcw className="mr-2 h-4 w-4" />
              重新生成
            </Button>
          </div>

          <Card>
            <CardHeader>
              <CardTitle className="text-lg">{title}</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="whitespace-pre-wrap text-sm leading-relaxed">
                {result.data}
              </div>
            </CardContent>
          </Card>

          {result.iterations.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">迭代记录</CardTitle>
                <CardDescription>
                  Gen-Eval 循环的每次生成与评估记录
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                {result.iterations.map((iter) => (
                  <div
                    key={iter.iteration}
                    className={cn(
                      "rounded-md border p-4",
                      iter.passed ? "border-green-200 dark:border-green-800" : "border-yellow-200 dark:border-yellow-800"
                    )}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-sm font-medium">
                        第 {iter.iteration} 轮
                      </span>
                      <div className="flex items-center gap-2">
                        {iter.score !== undefined && (
                          <span className="text-xs text-muted-foreground">
                            评分: {iter.score.toFixed(1)}
                          </span>
                        )}
                        <Badge variant={iter.passed ? "success" : "warning"} className="text-xs">
                          {iter.passed ? "通过" : "未通过"}
                        </Badge>
                      </div>
                    </div>
                    {iter.feedback && (
                      <p className="text-xs text-muted-foreground mb-2">
                        {iter.feedback}
                      </p>
                    )}
                  </div>
                ))}
              </CardContent>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}
