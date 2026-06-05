"use client";

/**
 * 职位详情页 — /jobs/[id]
 *
 * 与 /candidates/[id] 同构：api.get → loading/error/404 → 主信息 + 元数据卡片。
 * 工业级同 /candidates/[id] 实施：ErrorAlert + Skeleton + notFound() + a11y。
 */

import { useEffect, useState, use } from "react";
import Link from "next/link";
import { notFound, useRouter } from "next/navigation";
import { ArrowLeft, Briefcase, MapPin, DollarSign, Sparkles, AlertCircle, RefreshCw } from "lucide-react";

import { api, ApiError } from "@/lib/trpc";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorAlert } from "@/components/common/error-alert";

interface JobRead {
  id: string;
  title: string;
  department: string | null;
  description: string | null;
  requirements: string | null;
  location: string | null;
  salary_range: string | null;
  status: string;
  created_at: string;
  updated_at: string;
}

const STATUS_VARIANT: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
  open: "default",
  closed: "outline",
  paused: "secondary",
};

interface PageProps {
  params: Promise<{ id: string }>;
}

export default function JobDetailPage({ params }: PageProps) {
  const { id } = use(params);
  const router = useRouter();
  const [job, setJob] = useState<JobRead | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.get<JobRead>(`/jobs/${id}`);
      setJob(data);
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) {
        notFound();
      } else {
        setError(e instanceof Error ? e.message : "加载职位失败");
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (id) void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  if (loading) {
    return (
      <main className="container mx-auto p-6" aria-labelledby="page-title-loading">
        <h1 id="page-title-loading" className="sr-only">加载职位详情中</h1>
        <div className="mb-4 flex items-center gap-2">
          <Skeleton className="h-9 w-9" />
          <Skeleton className="h-6 w-48" />
        </div>
        <div className="grid gap-4 md:grid-cols-3">
          <Skeleton className="h-96 md:col-span-2" />
          <Skeleton className="h-96" />
        </div>
      </main>
    );
  }

  if (error) {
    return (
      <main className="container mx-auto p-6" aria-labelledby="page-title-error">
        <h1 id="page-title-error" className="sr-only">加载职位失败</h1>
        <div className="mb-4">
          <Button variant="ghost" size="sm" onClick={() => router.back()}>
            <ArrowLeft className="mr-1 h-4 w-4" />
            返回
          </Button>
        </div>
        <ErrorAlert message={error} variant="error" />
        <div className="mt-4">
          <Button variant="outline" onClick={load}>
            <RefreshCw className="mr-1 h-4 w-4" />
            重试
          </Button>
        </div>
      </main>
    );
  }

  if (!job) {
    return null;
  }

  const createdAtLocal = new Date(job.created_at).toLocaleString("zh-CN");
  const updatedAtLocal = new Date(job.updated_at).toLocaleString("zh-CN");

  return (
    <main className="container mx-auto p-6 space-y-4" aria-labelledby="page-title">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={() => router.back()}>
            <ArrowLeft className="mr-1 h-4 w-4" />
            返回
          </Button>
          <h1 id="page-title" className="text-2xl font-bold flex items-center gap-2">
            <Briefcase className="h-6 w-6" />
            {job.title}
          </h1>
          <Badge variant={STATUS_VARIANT[job.status] || "outline"}>
            {job.status}
          </Badge>
        </div>
        <Link href={`/agent?focus=msg_job_${job.id}`}>
          <Button variant="outline" size="sm">
            <Sparkles className="mr-1 h-4 w-4" />
            在助手中讨论
          </Button>
        </Link>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <Card className="md:col-span-2">
          <CardHeader>
            <CardTitle>职位描述</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {(job.department || job.location || job.salary_range) && (
              <dl className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                {job.department && (
                  <div>
                    <dt className="text-xs text-muted-foreground">部门</dt>
                    <dd className="text-sm">{job.department}</dd>
                  </div>
                )}
                {job.location && (
                  <div className="flex items-start gap-2">
                    <MapPin className="h-4 w-4 mt-0.5 text-muted-foreground shrink-0" aria-hidden />
                    <div>
                      <dt className="text-xs text-muted-foreground">工作地点</dt>
                      <dd className="text-sm">{job.location}</dd>
                    </div>
                  </div>
                )}
                {job.salary_range && (
                  <div className="flex items-start gap-2">
                    <DollarSign className="h-4 w-4 mt-0.5 text-muted-foreground shrink-0" aria-hidden />
                    <div>
                      <dt className="text-xs text-muted-foreground">薪资</dt>
                      <dd className="text-sm">{job.salary_range}</dd>
                    </div>
                  </div>
                )}
              </dl>
            )}

            {job.description && (
              <div>
                <h2 className="mb-1 text-sm font-semibold">职位描述</h2>
                <p className="text-sm text-muted-foreground whitespace-pre-wrap">{job.description}</p>
              </div>
            )}

            {job.requirements && (
              <div>
                <h2 className="mb-1 text-sm font-semibold">任职要求</h2>
                <p className="text-sm text-muted-foreground whitespace-pre-wrap">{job.requirements}</p>
              </div>
            )}

            {!job.description && !job.requirements && (
              <p className="text-sm text-muted-foreground italic">尚未填写职位描述和任职要求</p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">元数据</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-xs">
            <div>
              <dt className="text-muted-foreground">职位 ID</dt>
              <dd className="font-mono break-all">{job.id}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">创建时间</dt>
              <dd>{createdAtLocal}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">更新时间</dt>
              <dd>{updatedAtLocal}</dd>
            </div>
          </CardContent>
        </Card>
      </div>
    </main>
  );
}
