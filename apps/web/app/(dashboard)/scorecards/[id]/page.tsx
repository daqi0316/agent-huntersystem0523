"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/trpc";

interface Anchor {
  id: string;
  score: number;
  anchor_text: string;
  evidence_examples: string[];
  red_flags: string[];
}

interface Dimension {
  id: string;
  name: string;
  category?: string | null;
  weight: number;
  description?: string | null;
  required: boolean;
  order_index: number;
  anchors: Anchor[];
}

interface ScorecardTemplate {
  id: string;
  job_profile_id?: string | null;
  profile_version_id?: string | null;
  name: string;
  round_type: string;
  status: string;
  total_weight: number;
  created_by: string;
  created_at: string;
  updated_at: string;
  dimensions: Dimension[];
}

const statusColors: Record<string, string> = {
  active: "bg-green-100 text-green-800 border-green-200",
  draft: "bg-yellow-100 text-yellow-800 border-yellow-200",
  archived: "bg-gray-100 text-gray-500 border-gray-200",
};

const roundTypeLabels: Record<string, string> = {
  phone_screen: "电话初筛",
  technical: "技术面",
  behavioral: "行为面",
  final: "终面",
  manager: "经理面",
};

export default function ScorecardDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [template, setTemplate] = useState<ScorecardTemplate | null>(null);
  const [loading, setLoading] = useState(true);
  const [activating, setActivating] = useState(false);
  const [archiving, setArchiving] = useState(false);

  useEffect(() => {
    async function load() {
      setLoading(true);
      try {
        const res = await api.get<{ success: boolean; data: ScorecardTemplate }>(`/scorecards/templates/${params.id}`);
        setTemplate(res.data);
      } catch {
        toast.error("加载评分卡模板失败");
      } finally {
        setLoading(false);
      }
    }
    void load();
  }, [params.id]);

  const activateTemplate = async () => {
    setActivating(true);
    try {
      const res = await api.post<{ success: boolean; data: ScorecardTemplate }>(`/scorecards/templates/${params.id}/activate`);
      setTemplate(res.data);
      toast.success("评分卡已激活");
    } catch {
      toast.error("激活失败");
    } finally {
      setActivating(false);
    }
  };

  const archiveTemplate = async () => {
    setArchiving(true);
    try {
      const res = await api.post<{ success: boolean; data: ScorecardTemplate }>(`/scorecards/templates/${params.id}/archive`);
      setTemplate(res.data);
      toast.success("评分卡已归档");
    } catch {
      toast.error("归档失败");
    } finally {
      setArchiving(false);
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

  if (!template) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>评分卡模板不存在</CardTitle>
        </CardHeader>
        <CardContent>
          <Button variant="outline" onClick={() => router.push("/dashboard/scorecards")}>
            返回列表
          </Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={() => router.push("/dashboard/scorecards")} className="text-muted-foreground">
            ← 返回
          </Button>
          <h1 className="text-2xl font-semibold tracking-tight">{template.name}</h1>
          <span className={`rounded-full border px-2 py-0.5 text-xs ${statusColors[template.status] || "bg-gray-50"}`}>
            {template.status === "active" ? "已激活" : template.status === "draft" ? "草稿" : "已归档"}
          </span>
        </div>
        <p className="text-sm text-muted-foreground">
          {roundTypeLabels[template.round_type] || template.round_type} · 权重总和 {Math.round(template.total_weight * 100)}% · 创建者 {template.created_by}
        </p>
      </div>

      <div className="flex gap-2">
        {template.status === "draft" && (
          <Button onClick={activateTemplate} disabled={activating}>
            {activating ? "激活中..." : "激活模板"}
          </Button>
        )}
        {template.status !== "archived" && (
          <Button variant="outline" onClick={archiveTemplate} disabled={archiving}>
            {archiving ? "归档中..." : "归档"}
          </Button>
        )}
      </div>

      <Card>
        <CardHeader>
          <CardTitle>基本信息</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-2 text-sm md:grid-cols-3">
          <div className="rounded-lg bg-muted p-2">
            <div className="text-xs text-muted-foreground">岗位画像</div>
            <div className="font-medium truncate">{template.job_profile_id || "未绑定"}</div>
          </div>
          <div className="rounded-lg bg-muted p-2">
            <div className="text-xs text-muted-foreground">画像版本</div>
            <div className="font-medium truncate">{template.profile_version_id || "未绑定"}</div>
          </div>
          <div className="rounded-lg bg-muted p-2">
            <div className="text-xs text-muted-foreground">维度数量</div>
            <div className="font-medium">{template.dimensions.length} 个</div>
          </div>
        </CardContent>
      </Card>

      <div className="space-y-4">
        <h2 className="text-lg font-semibold">评分维度</h2>
        {template.dimensions.map((dimension) => (
          <Card key={dimension.id}>
            <CardHeader>
              <div className="flex items-start justify-between gap-3">
                <div>
                  <CardTitle className="text-base">{dimension.name}</CardTitle>
                  {dimension.category && <p className="text-sm text-muted-foreground">{dimension.category}</p>}
                </div>
                <div className="flex items-center gap-2">
                  <Badge variant="outline">权重 {Math.round(dimension.weight * 100)}%</Badge>
                  {dimension.required && <Badge>必填</Badge>}
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-3">
              {dimension.description && <p className="text-sm text-muted-foreground">{dimension.description}</p>}

              <div>
                <h4 className="mb-2 text-sm font-medium text-muted-foreground">行为锚定</h4>
                {dimension.anchors.length === 0 ? (
                  <p className="text-sm text-muted-foreground">暂无行为锚定</p>
                ) : (
                  <div className="grid gap-2 md:grid-cols-3">
                    {dimension.anchors.map((anchor) => (
                      <div key={anchor.id} className="rounded-lg border p-3">
                        <div className="flex items-center gap-2 mb-1">
                          <Badge>{anchor.score} 分</Badge>
                        </div>
                        <p className="text-sm">{anchor.anchor_text}</p>
                        {anchor.evidence_examples.length > 0 && (
                          <div className="mt-2">
                            <div className="text-xs font-medium text-muted-foreground">证据示例：</div>
                            <ul className="list-disc pl-4 text-xs text-muted-foreground">
                              {anchor.evidence_examples.map((ex, i) => <li key={i}>{ex}</li>)}
                            </ul>
                          </div>
                        )}
                        {anchor.red_flags.length > 0 && (
                          <div className="mt-2 flex flex-wrap gap-1">
                            {anchor.red_flags.map((flag, i) => (
                              <Badge key={i} variant="destructive" className="text-xs">{flag}</Badge>
                            ))}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
