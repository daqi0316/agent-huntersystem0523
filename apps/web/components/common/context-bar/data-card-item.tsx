"use client";

import {
  Users,
  BarChart3,
  FileSearch,
  ClipboardCheck,
  FileText,
  Calendar,
  Layers,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { DataCard, DataCardType } from "@/stores/agent-store";

const TYPE_ICON: Record<DataCardType, typeof Users> = {
  candidate_list: Users,
  dashboard_stats: BarChart3,
  search_result: FileSearch,
  evaluation: ClipboardCheck,
  jd: FileText,
  interview_schedule: Calendar,
  other: Layers,
};

const TYPE_LABEL: Record<DataCardType, string> = {
  candidate_list: "候选人",
  dashboard_stats: "看板",
  search_result: "搜索",
  evaluation: "评估",
  jd: "JD",
  interview_schedule: "面试",
  other: "其它",
};

function timeAgo(iso: string): string {
  if (!iso) return "";
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "刚刚";
  if (mins < 60) return `${mins}分钟前`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}小时前`;
  return `${Math.floor(hrs / 24)}天前`;
}

function renderPayloadPreview(card: DataCard): React.ReactNode {
  const { type, payload } = card;
  if (type === "candidate_list" && Array.isArray(payload)) {
    return (
      <ul className="mt-1 space-y-0.5">
        {payload.slice(0, 3).map((p: any, i: number) => (
          <li key={i} className="text-xs text-muted-foreground truncate">
            · {p.name}
            {p.current_title ? ` · ${p.current_title}` : ""}
          </li>
        ))}
        {payload.length > 3 && (
          <li className="text-xs text-muted-foreground">
            等 {payload.length - 3} 人…
          </li>
        )}
      </ul>
    );
  }
  if (type === "dashboard_stats" && payload && typeof payload === "object") {
    const d = payload as Record<string, unknown>;
    return (
      <div className="mt-1 grid grid-cols-3 gap-1 text-xs">
        {typeof d.total_candidates === "number" && (
          <div className="rounded bg-muted px-2 py-1 text-center">
            <div className="font-semibold">{d.total_candidates}</div>
            <div className="text-muted-foreground text-[10px]">候选人</div>
          </div>
        )}
        {typeof d.total_jobs === "number" && (
          <div className="rounded bg-muted px-2 py-1 text-center">
            <div className="font-semibold">{d.total_jobs}</div>
            <div className="text-muted-foreground text-[10px]">职位</div>
          </div>
        )}
        {typeof d.active_interviews === "number" && (
          <div className="rounded bg-muted px-2 py-1 text-center">
            <div className="font-semibold">{d.active_interviews}</div>
            <div className="text-muted-foreground text-[10px]">面试</div>
          </div>
        )}
      </div>
    );
  }
  if (type === "evaluation" && payload && typeof payload === "object") {
    const d = payload as Record<string, unknown>;
    if (typeof d.overall_score === "number") {
      return (
        <div className="mt-1 text-xs">
          <span className="text-lg font-bold">{d.overall_score}</span>
          <span className="text-muted-foreground"> / 100</span>
        </div>
      );
    }
  }
  return null;
}

interface DataCardItemProps {
  card: DataCard;
  active: boolean;
  expanded: boolean;
  onClick: () => void;
  draggable?: boolean;
  onDragStart?: (e: React.DragEvent) => void;
  onDragOver?: (e: React.DragEvent) => void;
  onDrop?: (e: React.DragEvent) => void;
  onDragEnd?: (e: React.DragEvent) => void;
  isDragOver?: boolean;
}

export function DataCardItem({
  card,
  active,
  expanded,
  onClick,
  draggable = false,
  onDragStart,
  onDragOver,
  onDrop,
  onDragEnd,
  isDragOver = false,
}: DataCardItemProps) {
  const Icon = TYPE_ICON[card.type];
  return (
    <button
      onClick={onClick}
      draggable={draggable}
      onDragStart={onDragStart}
      onDragOver={onDragOver}
      onDrop={onDrop}
      onDragEnd={onDragEnd}
      className={cn(
        "w-full text-left rounded-lg border p-3 transition-colors",
        active
          ? "border-primary bg-primary/5"
          : card.isRead
            ? "border-border bg-card hover:bg-accent"
            : "border-primary/30 bg-card hover:bg-accent",
        draggable && "cursor-grab active:cursor-grabbing",
        isDragOver && "border-dashed border-primary bg-primary/5"
      )}
    >
      <div className="flex items-start gap-2">
        <div
          className={cn(
            "flex h-7 w-7 shrink-0 items-center justify-center rounded-md",
            active ? "bg-primary/20" : "bg-muted"
          )}
        >
          <Icon className="h-3.5 w-3.5" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2">
            <p className="text-sm font-medium truncate">{card.title}</p>
            <span className="text-[10px] text-muted-foreground shrink-0">
              {TYPE_LABEL[card.type]}
            </span>
          </div>
          {card.summary && (
            <p className="text-xs text-muted-foreground truncate mt-0.5">
              {card.summary}
            </p>
          )}
          {expanded && renderPayloadPreview(card)}
          <p className="text-[10px] text-muted-foreground/60 mt-1">
            {timeAgo(card.createdAt)}
            {!card.isRead && (
              <span className="ml-2 inline-flex h-1.5 w-1.5 rounded-full bg-destructive align-middle" />
            )}
          </p>
        </div>
      </div>
    </button>
  );
}
