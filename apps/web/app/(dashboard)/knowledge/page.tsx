"use client";

import { useState } from "react";
import {
  Library, Upload, Search, MessageSquare, Loader2, BookOpen, FileText, CheckCircle2, AlertCircle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/trpc";

interface SourceResult {
  id: string;
  title: string;
  content: string;
  score: number;
}

interface QAItem {
  question: string;
  answer: string;
  sources: SourceResult[];
  timestamp: number;
}

export default function KnowledgePage() {
  // Document upload
  const [docTitle, setDocTitle] = useState("");
  const [docContent, setDocContent] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState<{
    success: boolean;
    message: string;
  } | null>(null);

  // Q&A
  const [query, setQuery] = useState("");
  const [qaHistory, setQaHistory] = useState<QAItem[]>([]);
  const [qaLoading, setQaLoading] = useState(false);

  const handleUpload = async () => {
    if (!docTitle.trim() || !docContent.trim()) return;

    setUploading(true);
    setUploadResult(null);

    try {
      await api.post("/knowledge/documents/ingest", {
        title: docTitle,
        content: docContent,
      });
      setUploadResult({ success: true, message: "文档上传成功，已索引到知识库" });
      setDocTitle("");
      setDocContent("");
    } catch (err) {
      setUploadResult({
        success: false,
        message: err instanceof Error ? err.message : "上传失败",
      });
    } finally {
      setUploading(false);
    }
  };

  const handleQuery = async () => {
    if (!query.trim()) return;

    setQaLoading(true);
    const question = query;
    setQuery("");

    try {
      const res = await api.post<{
        success: boolean;
        answer: string;
        sources: SourceResult[];
      }>("/knowledge/query", { query: question, top_k: 5 });

      setQaHistory((prev) => [
        {
          question,
          answer: res.answer,
          sources: res.sources || [],
          timestamp: Date.now(),
        },
        ...prev,
      ]);
    } catch (err) {
      setQaHistory((prev) => [
        {
          question,
          answer: `查询失败: ${err instanceof Error ? err.message : "请稍后重试"}`,
          sources: [],
          timestamp: Date.now(),
        },
        ...prev,
      ]);
    } finally {
      setQaLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">知识库</h1>
          <p className="text-muted-foreground mt-1">
            RAG 知识库问答 — 上传文档，AI 基于内容回答
          </p>
        </div>
      </div>

      <Tabs defaultValue="qa" className="space-y-4">
        <TabsList>
          <TabsTrigger value="qa">
            <MessageSquare className="h-4 w-4 mr-2" />
            知识问答
          </TabsTrigger>
          <TabsTrigger value="docs">
            <BookOpen className="h-4 w-4 mr-2" />
            文档管理
          </TabsTrigger>
        </TabsList>

        {/* Q&A Tab */}
        <TabsContent value="qa" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Search className="h-5 w-5" />
                知识库问答
              </CardTitle>
              <CardDescription>
                基于已上传文档内容，使用 RAG (检索增强生成) 技术回答您的问题
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="flex gap-2">
                <Input
                  placeholder="输入您的问题，例如：我们的面试流程是怎样的？"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleQuery()}
                  disabled={qaLoading}
                />
                <Button onClick={handleQuery} disabled={qaLoading || !query.trim()}>
                  {qaLoading ? (
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  ) : (
                    <Search className="h-4 w-4 mr-2" />
                  )}
                  问
                </Button>
              </div>
            </CardContent>
          </Card>

          {qaLoading && (
            <Card>
              <CardContent className="py-8">
                <div className="flex items-center justify-center gap-3 text-muted-foreground">
                  <Loader2 className="h-5 w-5 animate-spin" />
                  <span>正在检索知识库并生成回答...</span>
                </div>
              </CardContent>
            </Card>
          )}

          {qaHistory.length === 0 && !qaLoading && (
            <Card>
              <CardContent className="py-12">
                <div className="flex flex-col items-center gap-3 text-muted-foreground">
                  <MessageSquare className="h-12 w-12 opacity-20" />
                  <p>暂无问答记录</p>
                  <p className="text-sm">上传文档后在知识问答页面提问</p>
                </div>
              </CardContent>
            </Card>
          )}

          <div className="space-y-3">
            {qaHistory.map((qa) => (
              <Card key={qa.timestamp}>
                <CardHeader>
                  <div className="flex items-start gap-3">
                    <div className="h-8 w-8 rounded-full bg-primary/10 flex items-center justify-center flex-shrink-0">
                      <MessageSquare className="h-4 w-4 text-primary" />
                    </div>
                    <div>
                      <p className="font-medium text-sm">问题</p>
                      <p className="text-sm mt-1">{qa.question}</p>
                    </div>
                  </div>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="flex items-start gap-3">
                    <div className="h-8 w-8 rounded-full bg-green-100 dark:bg-green-900 flex items-center justify-center flex-shrink-0">
                      <FileText className="h-4 w-4 text-green-600 dark:text-green-300" />
                    </div>
                    <div className="min-w-0">
                      <p className="font-medium text-sm">回答</p>
                      <p className="text-sm mt-1 whitespace-pre-wrap">{qa.answer}</p>
                    </div>
                  </div>
                  {qa.sources.length > 0 && (
                    <div className="ml-11">
                      <p className="text-xs text-muted-foreground mb-2">来源文档:</p>
                      <div className="flex flex-wrap gap-2">
                        {qa.sources.map((src) => (
                          <Badge key={src.id} variant="secondary" className="text-xs">
                            {src.title}
                            <span className="ml-1 opacity-60">
                              ({Math.round(src.score * 100)}%)
                            </span>
                          </Badge>
                        ))}
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>
            ))}
          </div>
        </TabsContent>

        {/* Document Management Tab */}
        <TabsContent value="docs" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Upload className="h-5 w-5" />
                上传文档
              </CardTitle>
              <CardDescription>
                添加招聘相关的文档内容（公司介绍、面试流程、考核标准等）
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <label className="text-sm font-medium">文档标题</label>
                <Input
                  placeholder="例如：前端团队面试指南"
                  value={docTitle}
                  onChange={(e) => setDocTitle(e.target.value)}
                  disabled={uploading}
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">文档内容</label>
                <textarea
                  className="flex min-h-[200px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                  placeholder="在此粘贴或输入文档内容（支持 Markdown 格式）..."
                  value={docContent}
                  onChange={(e) => setDocContent(e.target.value)}
                  disabled={uploading}
                />
              </div>
              <Button
                onClick={handleUpload}
                disabled={uploading || !docTitle.trim() || !docContent.trim()}
              >
                {uploading ? (
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                ) : (
                  <Upload className="h-4 w-4 mr-2" />
                )}
                {uploading ? "上传中..." : "上传并索引"}
              </Button>

              {uploadResult && (
                <div
                  className={`flex items-center gap-2 text-sm p-3 rounded-lg ${
                    uploadResult.success
                      ? "bg-green-50 text-green-700 dark:bg-green-950 dark:text-green-300"
                      : "bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-300"
                  }`}
                >
                  {uploadResult.success ? (
                    <CheckCircle2 className="h-4 w-4" />
                  ) : (
                    <AlertCircle className="h-4 w-4" />
                  )}
                  {uploadResult.message}
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">使用提示</CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="space-y-2 text-sm text-muted-foreground">
                <li className="flex items-start gap-2">
                  <Library className="h-4 w-4 mt-0.5 flex-shrink-0" />
                  <span>上传的文档会自动分块、向量化后存入 Qdrant 向量数据库</span>
                </li>
                <li className="flex items-start gap-2">
                  <Search className="h-4 w-4 mt-0.5 flex-shrink-0" />
                  <span>提问时，系统会在知识库中检索最相关的内容片段</span>
                </li>
                <li className="flex items-start gap-2">
                  <FileText className="h-4 w-4 mt-0.5 flex-shrink-0" />
                  <span>AI 仅根据检索到的文档内容回答，不编造信息</span>
                </li>
              </ul>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
