"use client";

/**
 * CurrentContextSection — 抽屉内"当前讨论上下文" + 候选人/职位 ➕ 详情（T4）
 *
 * Phase 5 交付：把 agent-store.currentContext 从"数据"变成"看得见的信息"
 * T4 增强：每个 chip 旁加 ➕ 按钮，点击展开详情卡片（抽屉内即时预览，
 * 区别于 /candidates/{id} 详情页 — 详情页是"完整信息"，这里是"快速摘要"）
 */

import { useState, useCallback } from "react";
import { Briefcase, User, Wrench, Plus, X } from "lucide-react";
import Link from "next/link";
import { cn } from "./utils";
import { CandidateDetailCard } from "./candidate-detail-card";
import { JobDetailCard } from "./job-detail-card";
import type { ChatContext } from "@ai-recruitment/agent-store";

const TOOL_LABELS: Record<string, string> = {
  get_dashboard_stats: "看板数据",
  search_candidates: "搜索候选人",
  screen_resume: "简历评估",
  generate_jd: "生成 JD",
  schedule_interview: "安排面试",
  get_schedule: "查询日程",
  get_upcoming_interviews: "即将面试",
  create_candidate: "创建候选人",
  update_candidate: "更新候选人",
  archive_candidate: "归档候选人",
  create_job: "创建职位",
  update_job: "更新职位",
  close_job: "关闭职位",
  cancel_interview: "取消面试",
  reschedule_interview: "改期面试",
  save_evaluation: "保存评估",
};

function toolLabel(name: string | undefined): string {
  if (!name) return "";
  return TOOL_LABELS[name] || name;
}

interface CurrentContextSectionProps {
  context: ChatContext;
}

type ExpandedId = { kind: "candidate" | "job"; id: string } | null;

export function CurrentContextSection({ context }: CurrentContextSectionProps) {
  const isEmpty =
    !context.recentTopic &&
    !context.lastToolUsed &&
    context.currentCandidateIds.length === 0 &&
    context.currentJobIds.length === 0;
  if (isEmpty) return null;

  const [expanded, setExpanded] = useState<ExpandedId>(null);

  const toggleCandidate = useCallback((id: string) => {
    setExpanded((cur) => (cur?.kind === "candidate" && cur.id === id ? null : { kind: "candidate", id }));
  }, []);

  const toggleJob = useCallback((id: string) => {
    setExpanded((cur) => (cur?.kind === "job" && cur.id === id ? null : { kind: "job", id }));
  }, []);

  return (
    <section
      className="rounded-lg border bg-card/50 p-3 mb-3 space-y-2"
      aria-label="当前讨论上下文"
    >
      {context.recentTopic && (
        <div>
          <p className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider mb-1">
            正在讨论
          </p>
          <p className="text-sm font-medium text-foreground line-clamp-2">
            {context.recentTopic}
          </p>
        </div>
      )}

      {context.lastToolUsed && (
        <div className="flex items-center gap-1.5">
          <Wrench className="h-3 w-3 text-muted-foreground shrink-0" />
          <span className="text-[10px] text-muted-foreground">上次：</span>
          <span className="inline-flex items-center rounded-md bg-muted px-1.5 py-0.5 text-[11px] font-medium">
            {toolLabel(context.lastToolUsed)}
          </span>
        </div>
      )}

      {(context.currentCandidateIds.length > 0 ||
        context.currentJobIds.length > 0) && (
        <div className="space-y-1.5">
          {context.currentCandidateIds.length > 0 && (
            <div className="flex items-start gap-1.5">
              <User className="h-3 w-3 text-muted-foreground shrink-0 mt-1" />
              <div className="flex-1 min-w-0 space-y-1">
                {context.currentCandidateIds.slice(0, 5).map((id) => {
                  const isExpanded = expanded?.kind === "candidate" && expanded.id === id;
                  return (
                    <div key={id} className="space-y-1">
                      <div className="flex items-center gap-1">
                        <Link
                          href={`/candidates/${encodeURIComponent(id)}`}
                          className="inline-flex items-center rounded-md bg-green-50 dark:bg-green-950/30 text-green-700 dark:text-green-300 px-1.5 py-0.5 text-[11px] font-mono hover:bg-green-100 dark:hover:bg-green-950/50 transition-colors truncate max-w-[10rem]"
                          title={`候选人 ${id}`}
                        >
                          {id}
                        </Link>
                        <ExpandToggle
                          expanded={isExpanded}
                          onClick={() => toggleCandidate(id)}
                          label={isExpanded ? "收起" : "展开详情"}
                        />
                      </div>
                      {isExpanded && <CandidateDetailCard candidateId={id} />}
                    </div>
                  );
                })}
                {context.currentCandidateIds.length > 5 && (
                  <span className="text-[10px] text-muted-foreground">
                    +{context.currentCandidateIds.length - 5}
                  </span>
                )}
              </div>
            </div>
          )}
          {context.currentJobIds.length > 0 && (
            <div className="flex items-start gap-1.5">
              <Briefcase className="h-3 w-3 text-muted-foreground shrink-0 mt-1" />
              <div className="flex-1 min-w-0 space-y-1">
                {context.currentJobIds.slice(0, 5).map((id) => {
                  const isExpanded = expanded?.kind === "job" && expanded.id === id;
                  return (
                    <div key={id} className="space-y-1">
                      <div className="flex items-center gap-1">
                        <Link
                          href={`/jobs/${encodeURIComponent(id)}`}
                          className={cn(
                            "inline-flex items-center rounded-md px-1.5 py-0.5 text-[11px] font-mono truncate max-w-[10rem]",
                            "bg-blue-50 dark:bg-blue-950/30 text-blue-700 dark:text-blue-300",
                            "hover:bg-blue-100 dark:hover:bg-blue-950/50 transition-colors"
                          )}
                          title={`职位 ${id}`}
                        >
                          {id}
                        </Link>
                        <ExpandToggle
                          expanded={isExpanded}
                          onClick={() => toggleJob(id)}
                          label={isExpanded ? "收起" : "展开详情"}
                        />
                      </div>
                      {isExpanded && <JobDetailCard jobId={id} />}
                    </div>
                  );
                })}
                {context.currentJobIds.length > 5 && (
                  <span className="text-[10px] text-muted-foreground">
                    +{context.currentJobIds.length - 5}
                  </span>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </section>
  );
}

function ExpandToggle({
  expanded,
  onClick,
  label,
}: {
  expanded: boolean;
  onClick: () => void;
  label: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      aria-expanded={expanded}
      className="inline-flex items-center justify-center h-4 w-4 rounded text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
    >
      {expanded ? <X className="h-3 w-3" /> : <Plus className="h-3 w-3" />}
    </button>
  );
}
