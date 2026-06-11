"use client";

import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useSourcingHealth,
  usePlatformList,
  usePlatformAccounts,
  useUpdatePlatform,
  useCreateAccount,
} from "@/hooks/use-sourcing";
import {
  CheckCircle2,
  AlertCircle,
  Clock,
  ChevronDown,
  ChevronRight,
  Plus,
  Save,
  X,
  Loader2,
  Eye,
  EyeOff,
} from "lucide-react";
import { toast } from "sonner";

function AccountSection({ platform }: { platform: string }) {
  const [open, setOpen] = useState(false);
  const [showAdd, setShowAdd] = useState(false);
  const [newName, setNewName] = useState("");
  const [newType, setNewType] = useState("primary");
  const [newCookie, setNewCookie] = useState("");

  const { data, isLoading } = usePlatformAccounts(open ? platform : "");
  const createAccount = useCreateAccount();

  const handleAdd = async () => {
    if (!newName) return;
    await createAccount.mutateAsync({
      platform,
      data: {
        display_name: newName,
        account_type: newType,
        encrypted_cookies: newCookie || undefined,
      },
    });
    toast.success("账号已添加");
    setShowAdd(false);
    setNewName("");
    setNewCookie("");
  };

  return (
    <div className="mt-2 border-t pt-2">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1 text-xs text-muted-foreground hover:text-primary"
      >
        {open ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
        账号 ({data?.data?.length ?? "-"})
      </button>

      {open && (
        <div className="mt-2 space-y-1.5">
          {isLoading ? (
            <Skeleton className="h-8 w-full" />
          ) : (
            data?.data?.map((acct) => (
              <div key={acct.id} className="flex items-center justify-between rounded border px-2.5 py-1.5 text-xs">
                <div className="flex items-center gap-2">
                  <span className="font-medium">{acct.display_name}</span>
                  <Badge variant="outline" className="text-xs">{acct.account_type}</Badge>
                  {acct.is_active ? (
                    <CheckCircle2 className="h-3 w-3 text-green-500" />
                  ) : (
                    <X className="h-3 w-3 text-red-500" />
                  )}
                </div>
                <div className="flex items-center gap-2 text-muted-foreground">
                  <span>已用 {acct.daily_used}</span>
                  <span>失败 {acct.consecutive_failures}</span>
                  <Badge variant={acct.status === "active" ? "default" : "secondary"} className="text-xs">
                    {acct.status}
                  </Badge>
                </div>
              </div>
            ))
          )}

          {showAdd ? (
            <div className="space-y-2 rounded border p-2">
              <Input placeholder="显示名称" className="h-7 text-xs" value={newName} onChange={(e) => setNewName(e.target.value)} />
              <select className="h-7 w-full rounded border text-xs px-1" value={newType} onChange={(e) => setNewType(e.target.value)}>
                <option value="primary">primary</option>
                <option value="backup">backup</option>
                <option value="crawl">crawl</option>
              </select>
              <Input placeholder="加密 Cookie（可选）" className="h-7 text-xs" value={newCookie} onChange={(e) => setNewCookie(e.target.value)} />
              <div className="flex gap-1">
                <Button size="sm" className="h-7 text-xs" onClick={handleAdd}>
                  <Plus className="h-3 w-3 mr-1" />添加
                </Button>
                <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => setShowAdd(false)}>
                  取消
                </Button>
              </div>
            </div>
          ) : (
            <Button size="sm" variant="ghost" className="h-6 text-xs" onClick={() => setShowAdd(true)}>
              <Plus className="h-3 w-3 mr-1" />添加账号
            </Button>
          )}
        </div>
      )}
    </div>
  );
}

export default function PlatformStatus() {
  const { data: health } = useSourcingHealth();
  const { data: platformsData, isLoading } = usePlatformList();
  const updatePlatform = useUpdatePlatform();

  const [editingPlatform, setEditingPlatform] = useState<string | null>(null);
  const [editRateLimit, setEditRateLimit] = useState("");
  const [editQuota, setEditQuota] = useState("");

  const startEdit = (p: any) => {
    setEditingPlatform(p.name);
    setEditRateLimit(String(p.rate_limit ?? 3));
    setEditQuota(String(p.daily_quota_per_account ?? 300));
  };

  const saveEdit = async (platform: string) => {
    await updatePlatform.mutateAsync({
      platform,
      data: {
        rate_limit: parseInt(editRateLimit) || 3,
        daily_quota_per_account: parseInt(editQuota) || 300,
      } as any,
    });
    toast.success("配置已更新");
    setEditingPlatform(null);
  };

  const togglePlatform = async (p: any) => {
    await updatePlatform.mutateAsync({
      platform: p.name,
      data: { enabled: !p.enabled } as any,
    });
    toast.success(p.enabled ? "已禁用" : "已启用");
  };

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold tracking-tight">平台配置</h1>

      {/* Service Health */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">服务健康</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <div className="flex items-center gap-2 text-sm">
              <span className="text-muted-foreground">系统:</span>
              <Badge variant={health?.status === "ok" ? "default" : "destructive"}>
                {health?.status === "ok" ? "正常" : "降级"}
              </Badge>
            </div>
            <div className="flex items-center gap-2 text-sm">
              <span className="text-muted-foreground">排队:</span>
              <span className="font-mono text-xs">{health?.queue?.pending ?? "-"}</span>
            </div>
            <div className="flex items-center gap-2 text-sm">
              <span className="text-muted-foreground">运行中:</span>
              <span className="font-mono text-xs">{health?.queue?.running ?? "-"}</span>
            </div>
            <div className="flex items-center gap-2 text-sm">
              <span className="text-muted-foreground">平台:</span>
              <span className="font-mono text-xs">{health?.platforms?.available ?? "-"}/{health?.platforms?.total ?? "-"}</span>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Platform Configs */}
      <div className="space-y-2">
        {isLoading ? (
          Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-20 w-full rounded-md" />
          ))
        ) : (
          platformsData?.data?.map((p) => (
            <Card key={p.name}>
              <CardContent className="pt-4">
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-2">
                    {p.health_status === "healthy" || p.enabled ? (
                      <CheckCircle2 className="h-5 w-5 text-green-500 mt-0.5" />
                    ) : p.health_status === "degraded" ? (
                      <AlertCircle className="h-5 w-5 text-yellow-500 mt-0.5" />
                    ) : (
                      <Clock className="h-5 w-5 text-muted-foreground mt-0.5" />
                    )}
                    <div>
                      <p className="text-sm font-medium">{p.display_name}</p>
                      <p className="text-xs text-muted-foreground">
                        反爬 {p.anti_crawl_level}/5 · {p.category}
                        {p.health_checked_at && ` · 上次探测 ${new Date(p.health_checked_at).toLocaleString("zh-CN")}`}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge variant={p.enabled ? "default" : "secondary"}>
                      {p.enabled ? "启用" : "禁用"}
                    </Badge>
                    <Badge variant="outline" className="text-xs">
                      {p.health_status || "未知"}
                    </Badge>
                    <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => togglePlatform(p)}>
                      {p.enabled ? "禁用" : "启用"}
                    </Button>
                  </div>
                </div>

                {/* Config Editing */}
                <div className="mt-3 flex flex-wrap items-center gap-3">
                  {editingPlatform === p.name ? (
                    <>
                      <div className="flex items-center gap-1">
                        <span className="text-xs text-muted-foreground">限频(s):</span>
                        <Input className="h-7 w-16 text-xs" value={editRateLimit} onChange={(e) => setEditRateLimit(e.target.value)} />
                      </div>
                      <div className="flex items-center gap-1">
                        <span className="text-xs text-muted-foreground">日配额:</span>
                        <Input className="h-7 w-20 text-xs" value={editQuota} onChange={(e) => setEditQuota(e.target.value)} />
                      </div>
                      <Button size="sm" className="h-7 text-xs" onClick={() => saveEdit(p.name)}>
                        <Save className="h-3 w-3 mr-1" />保存
                      </Button>
                      <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => setEditingPlatform(null)}>
                        取消
                      </Button>
                    </>
                  ) : (
                    <>
                      <span className="text-xs text-muted-foreground">限频: {(p as any).rate_limit ?? 3}s</span>
                      <span className="text-xs text-muted-foreground">日配额: {(p as any).daily_quota_per_account ?? 300}</span>
                      <Button size="sm" variant="ghost" className="h-6 text-xs" onClick={() => startEdit(p)}>
                        编辑
                      </Button>
                    </>
                  )}
                </div>

                {/* Accounts */}
                <AccountSection platform={p.name} />
              </CardContent>
            </Card>
          ))
        )}
        {!isLoading && (!platformsData?.data || platformsData.data.length === 0) && (
          <p className="text-sm text-muted-foreground text-center py-8">暂无平台配置</p>
        )}
      </div>
    </div>
  );
}
