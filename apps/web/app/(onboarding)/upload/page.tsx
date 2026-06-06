"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ErrorAlert } from "@/components/common/error-alert";
import { Upload, ArrowRight, CheckCircle2, FileText, X } from "lucide-react";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
const TOKEN_KEY = "ai-recruitment-token";

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
}

export default function OnboardingUploadPage() {
  const router = useRouter()
  const [file, setFile] = useState<File | null>(null)
  const [uploading, setUploading] = useState(false)
  const [uploaded, setUploaded] = useState<{ id: string; name: string } | null>(null)
  const [error, setError] = useState<string | null>(null)

  const handleFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    if (f) {
      if (f.size > 10 * 1024 * 1024) {
        setError("文件超过 10MB, 请压缩后再上传")
        return
      }
      setFile(f)
      setError(null)
    }
  }

  const handleUpload = async () => {
    if (!file) return
    setUploading(true)
    setError(null)
    try {
      const token = getToken()
      if (!token) { setError("未登录"); return }
      const formData = new FormData()
      formData.append("file", file)
      const res = await fetch(`${API_BASE}/resume/upload`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      })
      const j = await res.json()
      if (!res.ok || !j.success) throw new Error(j.error || "上传失败")
      setUploaded({ id: j.data.id, name: file.name })
    } catch (e) {
      setError(e instanceof Error ? e.message : "上传失败")
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">上传候选人简历</h1>
        <p className="text-sm text-muted-foreground">
          支持 PDF / Word / TXT, 单文件最大 10MB
        </p>
      </div>

      {error && <ErrorAlert message={error} variant="error" />}

      {uploaded ? (
        <Card>
          <CardContent className="flex items-center gap-3 p-6">
            <CheckCircle2 className="h-8 w-8 text-green-600" />
            <div className="flex-1">
              <div className="font-medium">{uploaded.name}</div>
              <div className="text-xs text-muted-foreground">上传成功, 准备评估</div>
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setUploaded(null)
                setFile(null)
              }}
            >
              <X className="h-4 w-4" />
            </Button>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">选择文件</CardTitle>
          </CardHeader>
          <CardContent>
            <label
              htmlFor="resume-file"
              className="flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed border-muted-foreground/30 bg-muted/30 px-6 py-12 text-center transition hover:border-primary hover:bg-primary/5"
            >
              {file ? (
                <>
                  <FileText className="mb-2 h-8 w-8 text-primary" />
                  <div className="font-medium">{file.name}</div>
                  <div className="text-xs text-muted-foreground">
                    {(file.size / 1024).toFixed(1)} KB
                  </div>
                </>
              ) : (
                <>
                  <Upload className="mb-2 h-8 w-8 text-muted-foreground" />
                  <div className="font-medium">点击或拖拽上传</div>
                  <div className="mt-1 text-xs text-muted-foreground">
                    PDF / Word / TXT (最大 10MB)
                  </div>
                </>
              )}
            </label>
            <input
              id="resume-file"
              type="file"
              accept=".pdf,.doc,.docx,.txt"
              onChange={handleFile}
              className="hidden"
            />
          </CardContent>
        </Card>
      )}

      <div className="flex justify-between">
        <Button variant="ghost" onClick={() => router.push("/onboarding/welcome")}>
          上一步
        </Button>
        {uploaded ? (
          <Button onClick={() => router.push("/onboarding/evaluate")}>
            下一步: AI 评估 <ArrowRight className="ml-2 h-4 w-4" />
          </Button>
        ) : (
          <Button onClick={handleUpload} disabled={!file || uploading}>
            {uploading ? "上传中..." : "上传并继续"}
            {!uploading && <ArrowRight className="ml-2 h-4 w-4" />}
          </Button>
        )}
      </div>
    </div>
  )
}
