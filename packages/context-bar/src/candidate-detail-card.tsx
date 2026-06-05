"use client";

/**
 * CandidateDetailCard — 候选人详情卡片（T4）
 *
 * 工业级 / 全局规划：
 *  - 三态：loading skeleton / 错误重试 / 数据展示
 *  - 数据源：useCandidateDetail hook（包内 fetch + 缓存 + AbortSignal）
 *  - "在助手中继续讨论"按钮：跳 /agent?prefill=... 预填消息
 *  - 完整字段缺失降级：每个字段独立 null 检查
 *  - 移动端 overflow-safe：max-height + overflow-y-auto
 */

import {
  Mail,
  Phone,
  Briefcase,
  GraduationCap,
  Clock,
  AlertCircle,
  RefreshCw,
  Sparkles,
} from "lucide-react";
import Link from "next/link";
import { useCandidateDetail, type CandidateDetail } from "./use-candidate-detail";

interface CandidateDetailCardProps {
  candidateId: string;
}

export function CandidateDetailCard({ candidateId }: CandidateDetailCardProps) {
  const { state, retry } = useCandidateDetail(candidateId);

  if (state.kind === "loading" || state.kind === "idle") {
    return <CandidateDetailSkeleton />;
  }

  if (state.kind === "error") {
    return <CandidateDetailError error={state.error} code={state.code} onRetry={retry} />;
  }

  return <CandidateDetailBody data={state.data} />;
}

function CandidateDetailBody({ data }: { data: CandidateDetail }) {
  const prefill = encodeURIComponent(
    data.current_title
      ? `帮我详细分析候选人 ${data.name} 的 ${data.current_title} 经验`
      : `帮我详细分析候选人 ${data.name} 的背景`
  );

  return (
    <div className="rounded-md border bg-background/60 p-3 mt-1 space-y-2">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-foreground truncate">{data.name}</p>
          {data.current_title && (
            <p className="text-[11px] text-muted-foreground">
              {data.current_title}
              {data.current_company ? ` · ${data.current_company}` : ""}
            </p>
          )}
        </div>
        <span className="shrink-0 inline-flex items-center rounded-md bg-muted px-1.5 py-0.5 text-[10px] font-medium">
          {data.status}
        </span>
      </div>

      <dl className="space-y-1 text-[11px]">
        <DetailRow icon={Mail} label="邮箱">
          <a href={`mailto:${data.email}`} className="hover:underline truncate">
            {data.email}
          </a>
        </DetailRow>
        {data.phone && (
          <DetailRow icon={Phone} label="电话">
            {data.phone}
          </DetailRow>
        )}
        {data.experience_years !== null && (
          <DetailRow icon={Clock} label="经验">
            {data.experience_years} 年
          </DetailRow>
        )}
        {data.education && (
          <DetailRow icon={GraduationCap} label="教育">
            <span className="truncate">{data.education}</span>
          </DetailRow>
        )}
      </dl>

      {data.summary && (
        <p className="text-[11px] text-muted-foreground line-clamp-3">{data.summary}</p>
      )}

      {data.skills.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {data.skills.slice(0, 5).map((skill) => (
            <span
              key={skill}
              className="inline-flex items-center rounded-md bg-secondary px-1.5 py-0.5 text-[10px] font-medium text-secondary-foreground"
            >
              {skill}
            </span>
          ))}
          {data.skills.length > 5 && (
            <span className="text-[10px] text-muted-foreground self-center">
              +{data.skills.length - 5}
            </span>
          )}
        </div>
      )}

      <div className="flex gap-1.5 pt-1">
        <Link
          href={`/candidates/${encodeURIComponent(data.id)}`}
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
  icon: typeof Mail;
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

function CandidateDetailSkeleton() {
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

function CandidateDetailError({
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
      ? "候选人不存在或已删除"
      : code === "forbidden"
        ? "无权限查看该候选人"
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
