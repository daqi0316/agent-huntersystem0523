"use client";

import { useState } from "react";
import { Shield, FileText, Filter } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorAlert } from "@/components/common/error-alert";
import AuditPanel from "@/components/features/audit/audit-panel";
import { api } from "@/lib/trpc";

interface AuditStats {
  total_operations: number;
  system_errors: number;
  by_agent: { agent_name: string; count: number }[];
  by_error_category: { category: string; count: number }[];
}

export default function AuditPage() {
  const [stats, setStats] = useState<AuditStats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  if (loading === false && !stats && !error) {
    // trigger load
  }

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-3xl font-bold">
            <Shield className="h-7 w-7" />
            审计中心
          </h1>
          <p className="text-muted-foreground">
            操作日志查询与系统健康监控
          </p>
        </div>
      </div>

      <AuditStatsBanner />

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-3">
          <AuditPanel />
        </div>
      </div>
    </div>
  );
}

function AuditStatsBanner() {
  const [stats, setStats] = useState<AuditStats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useState(() => {
    api
      .get<AuditStats>("/audit/stats")
      .then((s) => setStats(s))
      .catch((e) => setError(e instanceof Error ? e.message : "加载统计失败"))
      .finally(() => setLoading(false));
    return null;
  });

  return (
    <div className="grid gap-4 md:grid-cols-3">
      {error && <ErrorAlert message={error} variant="error" />}

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
            <FileText className="h-4 w-4" />
            总操作数
          </CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <Skeleton className="h-8 w-20" />
          ) : (
            <p className="text-3xl font-bold">{stats?.total_operations ?? 0}</p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
            <Filter className="h-4 w-4 text-red-500" />
            系统错误
          </CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <Skeleton className="h-8 w-20" />
          ) : (
            <p className="text-3xl font-bold text-red-600">
              {stats?.system_errors ?? 0}
            </p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium text-muted-foreground">
            错误分类分布
          </CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <Skeleton className="h-8 w-full" />
          ) : (
            <div className="space-y-1 text-xs">
              {(stats?.by_error_category || []).map((c) => (
                <div key={c.category} className="flex items-center justify-between">
                  <span className="font-mono">{c.category}</span>
                  <span className="font-mono text-muted-foreground">{c.count}</span>
                </div>
              ))}
              {(stats?.by_error_category || []).length === 0 && (
                <p className="text-muted-foreground">暂无数据</p>
              )}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
