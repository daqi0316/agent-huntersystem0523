"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/trpc";

interface SalaryBand {
  base_min?: number | null;
  base_max?: number | null;
  total_min?: number | null;
  total_max?: number | null;
  currency: string;
  period: string;
}

interface JobProfile {
  id: string;
  code: string;
  title: string;
  level: string;
  department?: string | null;
  description?: string | null;
  hard_requirements: string[];
  soft_requirements: string[];
  evaluation_dimensions: { dimension: string; weight: number; must_have?: string | null; key_questions?: string[]; scoring_guide?: { score: number; evidence: string }[]; red_flags?: string[] }[];
  salary_band: SalaryBand;
  interview_focus: string[];
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

interface ProfileVersion {
  id: string;
  version: number;
  status: string;
  change_reason?: string | null;
  created_by: string;
  created_at: string;
  effective_from?: string | null;
  activated_at?: string | null;
  requirements: { type: string; label: string; category?: string | null; must_have: boolean; order_index: number }[];
  dimensions: { name: string; weight: number; description?: string | null; order_index: number }[];
}

const statusColors: Record<string, string> = {
  active: "bg-green-100 text-green-800 border-green-200",
  draft: "bg-yellow-100 text-yellow-800 border-yellow-200",
  archived: "bg-gray-100 text-gray-500 border-gray-200",
};

export default function JobProfileDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const profileId = params.id;

  const [profile, setProfile] = useState<JobProfile | null>(null);
  const [versions, setVersions] = useState<ProfileVersion[]>([]);
  const [loading, setLoading] = useState(true);
  const [activatingId, setActivatingId] = useState<string | null>(null);
  const [creatingVersion, setCreatingVersion] = useState(false);

  useEffect(() => {
    async function load() {
      setLoading(true);
      try {
        const [profileRes, versionsRes] = await Promise.all([
          api.get<{ success: boolean; data: JobProfile }>(`/job-profiles/${profileId}`),
          api.get<{ success: boolean; data: ProfileVersion[] }>(`/job-profiles/${profileId}/versions`),
        ]);
        setProfile(profileRes.data);
        setVersions(versionsRes.data || []);
      } catch {
        toast.error("加载岗位画像失败");
      } finally {
        setLoading(false);
      }
    }
    void load();
  }, [profileId]);

  const createVersion = async () => {
    setCreatingVersion(true);
    try {
      const res = await api.post<{ success: boolean; data: ProfileVersion }>(`/job-profiles/${profileId}/versions`, {
        change_reason: "手动创建新版本",
        status: "draft",
      });
      setVersions((prev) => [res.data, ...prev]);
      toast.success("已创建新版本");
    } catch {
      toast.error("创建版本失败");
    } finally {
      setCreatingVersion(false);
    }
  };

  const activateVersion = async (versionId: string) => {
    setActivatingId(versionId);
    try {
      await api.post(`/job-profiles/${profileId}/versions/${versionId}/activate`, {});
      setVersions((prev) =>
        prev.map((v) => ({
          ...v,
          status: v.id === versionId ? "active" : v.status === "active" ? "archived" : v.status,
        })),
      );
      toast.success("版本已激活");
    } catch {
      toast.error("激活版本失败");
    } finally {
      setActivatingId(null);
    }
  };

  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-48 w-full" />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }

  if (!profile) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>岗位画像不存在</CardTitle>
        </CardHeader>
        <CardContent>
          <Button variant="outline" onClick={() => router.push("/dashboard/job-profiles")}>
            返回列表
          </Button>
        </CardContent>
      </Card>
    );
  }

  const activeVersion = versions.find((v) => v.status === "active");

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm" onClick={() => router.push("/dashboard/job-profiles")} className="text-muted-foreground">
              ← 返回
            </Button>
            <h1 className="text-2xl font-semibold tracking-tight">{profile.title}</h1>
            <Badge>{profile.level}</Badge>
            {profile.is_active ? <Badge variant="outline">启用</Badge> : <Badge variant="outline">停用</Badge>}
          </div>
          <p className="text-sm text-muted-foreground">
            编码：{profile.code} · {profile.department || "未设置部门"}
          </p>
        </div>
        <Button onClick={createVersion} disabled={creatingVersion}>
          {creatingVersion ? "创建中..." : "创建新版本"}
        </Button>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>岗位需求</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <h3 className="text-sm font-medium text-muted-foreground mb-2">硬性要求</h3>
              {profile.hard_requirements.length === 0 ? (
                <p className="text-sm text-muted-foreground">暂无</p>
              ) : (
                <ul className="list-disc pl-5 space-y-1">
                  {profile.hard_requirements.map((req, i) => (
                    <li key={i} className="text-sm">{req}</li>
                  ))}
                </ul>
              )}
            </div>
            <div>
              <h3 className="text-sm font-medium text-muted-foreground mb-2">软性要求</h3>
              {profile.soft_requirements.length === 0 ? (
                <p className="text-sm text-muted-foreground">暂无</p>
              ) : (
                <ul className="list-disc pl-5 space-y-1">
                  {profile.soft_requirements.map((req, i) => (
                    <li key={i} className="text-sm">{req}</li>
                  ))}
                </ul>
              )}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>薪酬带宽</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <div className="grid grid-cols-2 gap-2">
              <div className="rounded-lg bg-muted p-2">
                <div className="text-xs text-muted-foreground">基础薪资下限</div>
                <div className="font-semibold">{profile.salary_band.base_min ?? "未设置"}</div>
              </div>
              <div className="rounded-lg bg-muted p-2">
                <div className="text-xs text-muted-foreground">基础薪资上限</div>
                <div className="font-semibold">{profile.salary_band.base_max ?? "未设置"}</div>
              </div>
              <div className="rounded-lg bg-muted p-2">
                <div className="text-xs text-muted-foreground">总包下限</div>
                <div className="font-semibold">{profile.salary_band.total_min ?? "未设置"}</div>
              </div>
              <div className="rounded-lg bg-muted p-2">
                <div className="text-xs text-muted-foreground">总包上限</div>
                <div className="font-semibold">{profile.salary_band.total_max ?? "未设置"}</div>
              </div>
            </div>
            <div className="text-xs text-muted-foreground">
              {profile.salary_band.currency} / {profile.salary_band.period}
            </div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>面试考察维度</CardTitle>
        </CardHeader>
        <CardContent>
          {profile.evaluation_dimensions.length === 0 ? (
            <p className="text-sm text-muted-foreground">暂无考察维度</p>
          ) : (
            <div className="space-y-3">
              {profile.evaluation_dimensions.map((dim, i) => (
                <div key={i} className="rounded-lg border p-3">
                  <div className="flex items-center justify-between gap-2">
                    <div className="font-medium">{dim.dimension}</div>
                    <Badge variant="outline">权重 {Math.round(dim.weight * 100)}%</Badge>
                  </div>
                  {dim.must_have && <p className="mt-1 text-sm text-muted-foreground">{dim.must_have}</p>}
                  {dim.key_questions && dim.key_questions.length > 0 && (
                    <div className="mt-2">
                      <div className="text-xs font-medium text-muted-foreground">关键问题：</div>
                      <ul className="list-disc pl-5 text-sm">
                        {dim.key_questions.map((q, qi) => <li key={qi}>{q}</li>)}
                      </ul>
                    </div>
                  )}
                  {dim.red_flags && dim.red_flags.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1">
                      {dim.red_flags.map((flag, fi) => (
                        <Badge key={fi} variant="destructive" className="text-xs">{flag}</Badge>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>版本记录</CardTitle>
        </CardHeader>
        <CardContent>
          {versions.length === 0 ? (
            <div className="text-center py-6 text-sm text-muted-foreground">
              暂无版本记录
              <div className="mt-2">
                <Button size="sm" onClick={createVersion} disabled={creatingVersion}>
                  创建第一个版本
                </Button>
              </div>
            </div>
          ) : (
            <div className="space-y-3">
              {versions.map((version) => (
                <div key={version.id} className="flex items-center justify-between rounded-lg border p-3">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="font-medium">v{version.version}</span>
                      <span className={`rounded-full border px-2 py-0.5 text-xs ${statusColors[version.status] || "bg-gray-50"}`}>
                        {version.status === "active" ? "当前激活" : version.status === "draft" ? "草稿" : "已归档"}
                      </span>
                    </div>
                    {version.change_reason && (
                      <p className="text-sm text-muted-foreground">{version.change_reason}</p>
                    )}
                    <div className="flex gap-4 text-xs text-muted-foreground">
                      <span>{version.requirements.length} 项要求</span>
                      <span>{version.dimensions.length} 个维度</span>
                      {version.created_by && <span>创建者：{version.created_by}</span>}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {version.status === "draft" && (
                      <Button size="sm" onClick={() => activateVersion(version.id)} disabled={activatingId === version.id}>
                        {activatingId === version.id ? "激活中..." : "激活"}
                      </Button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
