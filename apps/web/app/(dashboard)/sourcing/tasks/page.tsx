"use client";

/**
 * P2a-3: 任务列表页
 * 轮询 5s + 状态/平台/关键词筛选 + 分页
 */
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Search,
  ChevronLeft,
  ChevronRight,
  Loader2,
  Play,
  XCircle,
  RefreshCw,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useTaskList,
  useCancelTask,
  useDispatchTask,
  type SourcingTask,
} from "@/hooks/use-sourcing";
import { toast } from "sonner";
import { useQueryClient } from "@tanstack/react-query";
import { formatDistanceToNow } from "date-fns";
import { zhCN } from "date-fns/locale";

const STATUS_OPTIONS = [
  { value: "", label: "全部" },
  { value: "pending", label: "排队中" },
  { value: "running", label: "运行中" },
  { value: "completed", label: "已完成" },
  { value: "partial", label: "部分完成" },
  { value: "failed", label: "失败" },
  { value: "cancelled", label: "已取消" },
];

function TaskRow({ task, onCancel, onDispatch }: {
  task: SourcingTask;
  onCancel: (id: string) => void;
  onDispatch: (id: string) => void;
}) {
  const statusMap: Record<string, { label: string; variant: "default" | "secondary" | "outline" | "destructive" }> = {
    pending: { label: "排队中", variant: "outline" },
    running: { label: "运行中", variant: "secondary" },
    completed: { label: "已完成", variant: "default" },
    partial: { label: "部分完成", variant: "default" },
    failed: { label: "失败", variant: "destructive" },
    cancelled: { label: "已取消", variant: "outline" },
  };
  const sb = statusMap[task.status] || { label: task.status, variant: "outline" as const };

  return (
    <div className="flex items-center gap-4 rounded-md border p-3 hover:bg-accent/50 transition-colors">
      <div className="flex-1 min-w-0">
        <Link
          href={`/sourcing/tasks/${task.id}`}
          className="text-sm font-medium hover:text-primary truncate block"
        >
          {task.keyword}
        </Link>
        <div className="flex items-center gap-3 mt-1 text-xs text-muted-foreground">
          <span>{task.platforms?.join(", ") || "未指定"}</span>
          <span>原始 {task.total_found}</span>
          <span>去重 {task.after_dedup}</span>
          <span>新增 {task.new_this_run}</span>
          {task.completed_at && (
            <span>
              {formatDistanceToNow(new Date(task.completed_at), { addSuffix: true, locale: zhCN })}
            </span>
          )}
        </div>
      </div>
      <Badge variant={sb.variant}>{sb.label}</Badge>
      <div className="flex items-center gap-1 shrink-0">
        {task.status === "pending" && (
          <Button size="sm" variant="ghost" onClick={() => onDispatch(task.id)} title="投递">
            <Play className="h-3.5 w-3.5" />
          </Button>
        )}
        {(task.status === "pending" || task.status === "running") && (
          <Button size="sm" variant="ghost" onClick={() => onCancel(task.id)} title="取消">
            <XCircle className="h-3.5 w-3.5 text-destructive" />
          </Button>
        )}
      </div>
    </div>
  );
}

export default function TaskList() {
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState("");
  const [keyword, setKeyword] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const router = useRouter();
  const queryClient = useQueryClient();

  const { data, isLoading } = useTaskList({
    status_filter: statusFilter || undefined,
    keyword: keyword || undefined,
    page,
    page_size: 20,
  });

  const cancelMutation = useCancelTask();
  const dispatchMutation = useDispatchTask();

  const handleCancel = async (id: string) => {
    const result = await cancelMutation.mutateAsync(id);
    if (result?.success) toast.success("已取消");
  };

  const handleDispatch = async (id: string) => {
    const result = await dispatchMutation.mutateAsync(id);
    if (result?.success) toast.success("已投递到队列");
  };

  const handleSearch = () => {
    setKeyword(searchInput.trim());
    setPage(1);
  };

  const totalPages = data ? Math.ceil(data.total / 20) : 1;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold tracking-tight">任务列表</h1>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => queryClient.invalidateQueries({ queryKey: ["sourcing", "tasks"] })}
          >
            <RefreshCw className="h-3.5 w-3.5 mr-1" />
            刷新
          </Button>
          <Link href="/sourcing">
            <Button size="sm">
              <Search className="h-3.5 w-3.5 mr-1" />
              新建任务
            </Button>
          </Link>
        </div>
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="pt-4">
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-1">
              <span className="text-xs text-muted-foreground">状态:</span>
              <select
                className="h-8 rounded-md border border-input bg-background px-2 text-xs"
                value={statusFilter}
                onChange={(e) => { setStatusFilter(e.target.value); setPage(1); }}
              >
                {STATUS_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
            </div>
            <div className="flex items-center gap-1 flex-1 max-w-xs">
              <Input
                placeholder="搜索关键词"
                className="h-8 text-xs"
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSearch()}
              />
              <Button size="sm" variant="ghost" className="h-8" onClick={handleSearch}>
                <Search className="h-3.5 w-3.5" />
              </Button>
            </div>
            <div className="text-xs text-muted-foreground ml-auto">
              共 {data?.total ?? "-"} 条
            </div>
          </div>
        </CardContent>
      </Card>

      {/* List */}
      <div className="space-y-2">
        {isLoading ? (
          Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-16 w-full rounded-md" />
          ))
        ) : (
          data?.data?.map((task) => (
            <TaskRow
              key={task.id}
              task={task}
              onCancel={handleCancel}
              onDispatch={handleDispatch}
            />
          ))
        )}
        {!isLoading && data?.data?.length === 0 && (
          <p className="text-sm text-muted-foreground text-center py-8">暂无任务</p>
        )}
      </div>

      {/* Pagination */}
      <div className="flex items-center justify-between">
        <span className="text-xs text-muted-foreground">
          第 {page}/{totalPages} 页
        </span>
        <div className="flex items-center gap-1">
          <Button
            size="sm"
            variant="outline"
            disabled={page <= 1}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
          >
            <ChevronLeft className="h-3.5 w-3.5" />
            上一页
          </Button>
          <Button
            size="sm"
            variant="outline"
            disabled={page >= totalPages}
            onClick={() => setPage((p) => p + 1)}
          >
            下一页
            <ChevronRight className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>
    </div>
  );
}
