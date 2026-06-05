"use client";

/**
 * JobDetailCard — 职位详情卡片（T4）
 *
 * 与 CandidateDetailCard 同构：loading skeleton / 错误重试 / 数据展示
 * "在助手中讨论" 按钮：跳 /agent?prefill=...
 */

import {
  Briefcase,
  MapPin,
  DollarSign,
  AlertCircle,
  RefreshCw,
  Sparkles,
} from "lucide-react";
import Link from "next/link";
import { useJobDetail, type JobDetail } from "./use-job-detail";

export function JobDetailCard({ jobId }: { jobId: string }) {
  const { state, retry } = useJobDetail(jobId);

  if (state.kind === "loading" || state.kind === "idle") {
    return <JobDetailSkeleton />;
  }

  if (state.kind === "error") {
    return <JobDetailError error={state.error} code={state.code} onRetry={retry} />;
  }

  return <JobDetailBody data={state.data} />;
}

function JobDetailBody({ data }: { data: JobDetail }) {
  const prefill = encodeURIComponent(
    data.department
      ? `帮我详细分析职位 ${data.title}（${data.department}）的招聘策略`
      : `帮我详细分析职位 ${data.title} 的招聘策略`
  );

  return (
    <div className="rounded-md border bg-background/60 p-3 mt-1 space-y-2">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-foreground truncate">{data.title}</p>
          {data.department && (
            <p className="text-[11px] text-muted-foreground">{data.department}</p>
          )}
        </div>
        <span className="shrink-0 inline-flex items-center rounded-md bg-muted px-1.5 py-0.5 text-[10px] font-medium">
          {data.status}
        </span>
      </div>

      <dl className="space-y-1 text-[11px]">
        {data.location && (
          <DetailRow icon={MapPin} label="地点">
            {data.location}
          </DetailRow>
        )}
        {data.salary_range && (
          <DetailRow icon={DollarSign} label="薪资">
            {data.salary_range}
          </DetailRow>
        )}
      </dl>

      {data.description && (
        <div>
          <p className="text-[10px] text-muted-foreground mb-0.5">职位描述</p>
          <p className="text-[11px] text-foreground/80 line-clamp-3">{data.description}</p>
        </div>
      )}

      {data.requirements && (
        <div>
          <p className="text-[10px] text-muted-foreground mb-0.5">任职要求</p>
          <p className="text-[11px] text-foreground/80 line-clamp-3">{data.requirements}</p>
        </div>
      )}

      <div className="flex gap-1.5 pt-1">
        <Link
          href={`/jobs/${encodeURIComponent(data.id)}`}
          className="flex-1 text-center text-[11px] py-1 rounded-md border bg-background hover:bg-accent transition-colors"
        >
          查看完整
        </Link>
        <Link
          href={`/agent?prefill=${prefill}`}
          className="flex-1 text-center text-[11px] py-1 rounded-md bg-primary text-primary-foreground hover:bg-primary/90 transition-colors flex items-center justify-center gap-1"
        >
          <Sparkles className="h-3 w-3" />
          在助手中讨论
        </Link>
      </div>
    </div>
  );
}

function DetailRow({
  icon: Icon,
  label,
  children,
}: {
  icon: typeof Briefcase;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-start gap-1.5">
      <Icon className="h-3 w-3 mt-0.5 text-muted-foreground shrink-0" aria-hidden />
      <div className="min-w-0 flex-1">
        <dt className="text-[10px] text-muted-foreground">{label}</dt>
        <dd className="truncate">{children}</dd>
      </div>
    </div>
  );
}

function JobDetailSkeleton() {
  return (
    <div className="rounded-md border bg-background/60 p-3 mt-1 space-y-2" aria-busy>
      <div className="flex items-center justify-between">
        <div className="h-4 w-24 bg-muted rounded animate-pulse" />
        <div className="h-3 w-12 bg-muted rounded animate-pulse" />
      </div>
      <div className="space-y-1.5">
        {[60, 80, 40].map((w, i) => (
          <div key={i} className="h-3 bg-muted rounded animate-pulse" style={{ width: `${w}%` }} />
        ))}
      </div>
    </div>
  );
}

function JobDetailError({
  error,
  code,
  onRetry,
}: {
  error: string;
  code: "not_found" | "forbidden" | "unauthorized" | "server" | "network" | "unknown";
  onRetry: () => void;
}) {
  const message =
    code === "not_found"
      ? "职位不存在或已关闭"
      : code === "forbidden"
        ? "无权限查看该职位"
        : code === "unauthorized"
          ? "请先登录"
        : code === "network"
          ? "网络异常，请检查连接"
          : error;
  return (
    <div className="rounded-md border border-destructive/40 bg-destructive/5 p-3 mt-1">
      <div className="flex items-start gap-2">
        <AlertCircle className="h-3.5 w-3.5 text-destructive mt-0.5 shrink-0" />
        <div className="min-w-0 flex-1">
          <p className="text-[11px] font-medium text-destructive">加载失败</p>
          <p className="text-[10px] text-muted-foreground">{message}</p>
        </div>
      </div>
      {code !== "not_found" && (
        <button
          onClick={onRetry}
          className="mt-2 w-full flex items-center justify-center gap-1 text-[11px] py-1 rounded-md border bg-background hover:bg-accent transition-colors"
        >
          <RefreshCw className="h-3 w-3" />
          重试
        </button>
      )}
    </div>
  );
}
