"use client";

/**
 * P2a-2: 寻源工作台首页
 *
 * 布局: 左上 QuickCreateForm + RecentTasks
 *       右上 PlatformStatusCards
 */
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Search, Loader2, Plus, CheckCircle2, AlertCircle, Clock } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "sonner";
import { useCreateTask, useTaskList, useSourcingHealth, sourcingKeys } from "@/hooks/use-sourcing";
import { useQueryClient } from "@tanstack/react-query";

/* ── QuickCreate ── */

function QuickCreateForm() {
  const [keyword, setKeyword] = useState("");
  const createTask = useCreateTask();
  const queryClient = useQueryClient();

  const handleCreate = async () => {
    if (!keyword.trim()) return;
    const result = await createTask.mutateAsync({
      org_id: "default",
      created_by: "sourcing-ui",
      keyword: keyword.trim(),
      platforms: ["boss_zhipin"],
    });
    if (result?.success) {
      toast.success("任务已创建");
      setKeyword("");
      queryClient.invalidateQueries({ queryKey: sourcingKeys.tasks.all });
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">快速创建任务</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex gap-2">
          <Input
            placeholder="输入关键词，如 Python 工程师"
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleCreate()}
          />
          <Button onClick={handleCreate} disabled={createTask.isPending || !keyword.trim()}>
            {createTask.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Search className="h-4 w-4" />
            )}
            <span className="ml-1">搜索</span>
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

/* ── RecentTasks ── */

function RecentTasks() {
  const { data, isLoading } = useTaskList({ page: 1, page_size: 5 });

  const statusBadge = (status: string) => {
    const map: Record<string, { label: string; variant: "default" | "secondary" | "outline" | "destructive" }> = {
      pending: { label: "排队中", variant: "outline" },
      running: { label: "运行中", variant: "secondary" },
      completed: { label: "已完成", variant: "default" },
      partial: { label: "部分完成", variant: "default" },
      failed: { label: "失败", variant: "destructive" },
      cancelled: { label: "已取消", variant: "outline" },
    };
    const m = map[status] || { label: status, variant: "outline" as const };
    return <Badge variant={m.variant}>{m.label}</Badge>;
  };

  return (
    <Card className="flex-1">
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="text-base">最近任务</CardTitle>
        <Link href="/sourcing/tasks" className="text-sm text-primary hover:underline">
          查看全部
        </Link>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        ) : (
          <div className="space-y-2">
            {data?.data?.map((task) => (
              <Link
                key={task.id}
                href={`/sourcing/tasks/${task.id}`}
                className="flex items-center justify-between rounded-md p-2 hover:bg-accent transition-colors"
              >
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate">{task.keyword}</p>
                  <p className="text-xs text-muted-foreground">
                    {task.total_found} 条 · 去重 {task.after_dedup}
                  </p>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  {statusBadge(task.status)}
                </div>
              </Link>
            ))}
            {data?.data?.length === 0 && (
              <p className="text-sm text-muted-foreground text-center py-4">暂无任务</p>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

/* ── PlatformStatusCards ── */

function PlatformStatusCards() {
  const { data: health } = useSourcingHealth();

  const statusIcon = (service: string) => {
    if (service === "ok") return <CheckCircle2 className="h-4 w-4 text-green-500" />;
    if (service?.startsWith("error")) return <AlertCircle className="h-4 w-4 text-red-500" />;
    return <Clock className="h-4 w-4 text-muted-foreground" />;
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">平台状态</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">数据库</span>
            <div className="flex items-center gap-1.5">
              {statusIcon(health?.services?.database ?? "")}
              <span>{health?.services?.database === "ok" ? "正常" : health?.services?.database || "检查中"}</span>
            </div>
          </div>
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">Redis</span>
            <div className="flex items-center gap-1.5">
              {statusIcon(health?.services?.redis ?? "")}
              <span>{health?.services?.redis === "ok" ? "正常" : health?.services?.redis || "检查中"}</span>
            </div>
          </div>
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">队列等待</span>
            <span className="font-mono text-xs">{health?.queue?.pending ?? "-"}</span>
          </div>
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">运行中</span>
            <span className="font-mono text-xs">{health?.queue?.running ?? "-"}</span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

/* ── Page ── */

export default function SourcingDashboard() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">寻源工作台</h1>
        <p className="text-sm text-muted-foreground mt-1">
          创建采集任务，从各平台获取候选人
        </p>
      </div>

      <QuickCreateForm />

      <div className="flex gap-4">
        <RecentTasks />
        <div className="w-72 shrink-0">
          <PlatformStatusCards />
        </div>
      </div>
    </div>
  );
}
