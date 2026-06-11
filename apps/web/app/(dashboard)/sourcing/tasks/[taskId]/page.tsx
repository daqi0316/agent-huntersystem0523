"use client";

/**
 * P2b-3: 任务详情页（WebSocket 实时进度 + API 轮询兜底）
 */
import { useState, useMemo } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  ArrowLeft,
  Loader2,
  Play,
  XCircle,
  Clock,
  CheckCircle2,
  AlertCircle,
  ExternalLink,
  Wifi,
  WifiOff,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useTaskDetail,
  useTaskLogs,
  useCancelTask,
  useDispatchTask,
  useSourcingCandidateList,
} from "@/hooks/use-sourcing";
import { useSourcingTaskWS } from "@/hooks/use-sourcing-ws";
import { toast } from "sonner";

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

const logStatusIcon = (status: string) => {
  switch (status) {
    case "success": return <CheckCircle2 className="h-4 w-4 text-green-500" />;
    case "failed": return <AlertCircle className="h-4 w-4 text-red-500" />;
    case "captcha": return <AlertCircle className="h-4 w-4 text-yellow-500" />;
    case "banned": return <XCircle className="h-4 w-4 text-red-500" />;
    case "running": return <Loader2 className="h-4 w-4 animate-spin text-blue-500" />;
    default: return <Clock className="h-4 w-4 text-muted-foreground" />;
  }
};

export default function TaskDetail() {
  const params = useParams();
  const taskId = params.taskId as string;
  const [candidatePage, setCandidatePage] = useState(1);

  const { data: taskData, isLoading: taskLoading } = useTaskDetail(taskId);
  const { data: logsData } = useTaskLogs(taskId);
  const { data: candidatesData } = useSourcingCandidateList({
    task_id: taskId,
    page: candidatePage,
    page_size: 5,
  });

  const cancelMutation = useCancelTask();
  const dispatchMutation = useDispatchTask();

  const { connected, taskProgress, platformProgress } = useSourcingTaskWS(taskId);

  const task = useMemo(() => {
    const api = taskData?.data;
    if (!api) return api;
    const ws = taskProgress;
    if (!ws) return api;
    return {
      ...api,
      status: ws.status || api.status,
      total_found: ws.total_found ?? api.total_found,
      after_dedup: ws.after_dedup ?? api.after_dedup,
    };
  }, [taskData, taskProgress]);

  const handleCancel = async () => {
    const result = await cancelMutation.mutateAsync(taskId);
    if (result?.success) toast.success("已取消");
  };

  const handleDispatch = async () => {
    const result = await dispatchMutation.mutateAsync(taskId);
    if (result?.success) toast.success("已投递");
  };

  if (taskLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }

  if (!task) {
    return (
      <div className="text-center py-12">
        <p className="text-muted-foreground">任务不存在</p>
        <Link href="/sourcing/tasks">
          <Button variant="link">返回列表</Button>
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <Link
            href="/sourcing/tasks"
            className="text-sm text-muted-foreground hover:text-primary flex items-center gap-1 mb-2"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            返回列表
          </Link>
          <h1 className="text-2xl font-bold tracking-tight">{task.keyword}</h1>
          <div className="flex items-center gap-3 mt-1 text-sm text-muted-foreground">
            <span>平台: {task.platforms?.join(", ") || "未指定"}</span>
            <span>原始 {task.total_found}</span>
            <span>去重 {task.after_dedup}</span>
            <span>新增 {task.new_this_run}</span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {statusBadge(task.status)}
          {task.status === "pending" && (
            <Button size="sm" onClick={handleDispatch}>
              <Play className="h-3.5 w-3.5 mr-1" />
              投递
            </Button>
          )}
          {(task.status === "pending" || task.status === "running") && (
            <Button size="sm" variant="destructive" onClick={handleCancel}>
              <XCircle className="h-3.5 w-3.5 mr-1" />
              取消
            </Button>
          )}
        </div>
      </div>

      {/* WS Status */}
      <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
        {connected ? (
          <><Wifi className="h-3 w-3 text-green-500" /> 实时连接</>
        ) : task.status === "running" || task.status === "pending" ? (
          <><WifiOff className="h-3 w-3 text-yellow-500" /> 等待连接</>
        ) : null}
      </div>

      {/* Platform Progress */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">平台进度</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {(() => {
              const apiProgress = task.progress as Record<string, any> || {};
              const platformNames = Object.keys(apiProgress).length > 0
                ? Object.keys(apiProgress)
                : (task.platforms ?? []);
              return platformNames.map((platform) => {
                const wsProg: Record<string, any> = platformProgress?.[platform] || {};
                const apiProg = apiProgress[platform] || {};
                const mergedStatus = wsProg.status || apiProg.status || "pending";
                const isRunning = mergedStatus === "running";
                return (
                <div key={platform} className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    {mergedStatus === "completed" ? (
                      <CheckCircle2 className="h-4 w-4 text-green-500" />
                    ) : mergedStatus === "failed" || mergedStatus === "error" ? (
                      <AlertCircle className="h-4 w-4 text-red-500" />
                    ) : isRunning ? (
                      <Loader2 className="h-4 w-4 animate-spin text-blue-500" />
                    ) : (
                      <Clock className="h-4 w-4 text-muted-foreground" />
                    )}
                    <span className="text-sm">{platform}</span>
                  </div>
                  <div className="flex items-center gap-3 text-xs text-muted-foreground">
                    <span>{mergedStatus === "completed" ? "已完成" : mergedStatus === "failed" ? "失败" : isRunning ? "采集中..." : mergedStatus === "not_implemented" ? "未实现" : "等待中"}</span>
                    {(wsProg.found ?? apiProg.found) !== undefined && <span>找到 {wsProg.found ?? apiProg.found} 条</span>}
                    {(wsProg.error ?? apiProg.error) && <span className="text-red-500">{wsProg.error || apiProg.error}</span>}
                  </div>
                </div>
              )});
            })()}
          </div>
        </CardContent>
      </Card>

      {/* Crawl Logs */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">采集日志</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {logsData?.data?.map((log) => (
              <div
                key={log.id}
                className="flex items-start gap-3 rounded-md border p-2.5 text-sm"
              >
                {logStatusIcon(log.status)}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{log.platform}</span>
                    <Badge variant="outline" className="text-xs">
                      {log.status}
                    </Badge>
                  </div>
                  <div className="flex flex-wrap gap-x-4 gap-y-1 mt-1 text-xs text-muted-foreground">
                    {log.candidates_found > 0 && <span>采集 {log.candidates_found} 条</span>}
                    {log.duration_seconds > 0 && <span>耗时 {log.duration_seconds.toFixed(1)}s</span>}
                    {log.proxy_used && <span>代理 {log.proxy_used}</span>}
                    {log.captcha_solved && <span className="text-yellow-600">触发了验证码</span>}
                    {log.retry_count > 0 && <span>重试 {log.retry_count} 次</span>}
                    {log.error_message && (
                      <span className="text-red-500 w-full truncate">{log.error_message}</span>
                    )}
                  </div>
                </div>
              </div>
            ))}
            {(!logsData?.data || logsData.data.length === 0) && (
              <p className="text-xs text-muted-foreground text-center py-4">暂无日志</p>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Candidate Preview */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-base">候选人预览</CardTitle>
          <Link href={`/sourcing/candidates?task_id=${taskId}`}>
            <Button size="sm" variant="outline">
              <ExternalLink className="h-3.5 w-3.5 mr-1" />
              查看全部
            </Button>
          </Link>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {candidatesData?.data?.map((c) => (
              <Link
                key={c.id}
                href={`/candidates/${c.id}`}
                className="flex items-center justify-between rounded-md border p-2.5 hover:bg-accent/50 transition-colors"
              >
                <div>
                  <p className="text-sm font-medium">{c.name}</p>
                  <p className="text-xs text-muted-foreground">
                    {c.current_title} · {c.current_company}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  {c.source_platforms?.map((p) => (
                    <Badge key={p} variant="secondary" className="text-xs">{p}</Badge>
                  ))}
                </div>
              </Link>
            ))}
            {(!candidatesData?.data || candidatesData.data.length === 0) && (
              <p className="text-xs text-muted-foreground text-center py-4">
                {task.status === "completed" ? "暂无候选人" : "等待采集完成"}
              </p>
            )}
          </div>
          {candidatesData && candidatesData.total > 5 && (
            <div className="flex items-center justify-between mt-3 text-xs text-muted-foreground">
              <span>共 {candidatesData.total} 条</span>
              <div className="flex gap-1">
                <Button
                  size="sm"
                  variant="outline"
                  className="h-7 text-xs"
                  disabled={candidatePage <= 1}
                  onClick={() => setCandidatePage((p) => Math.max(1, p - 1))}
                >
                  上一页
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  className="h-7 text-xs"
                  disabled={candidatePage * 5 >= candidatesData.total}
                  onClick={() => setCandidatePage((p) => p + 1)}
                >
                  下一页
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
