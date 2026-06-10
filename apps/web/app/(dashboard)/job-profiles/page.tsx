"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/trpc";

interface JobProfileTemplate {
  id: string;
  code: string;
  title: string;
  level: string;
  department?: string;
  hard_requirement_count: number;
  soft_requirement_count: number;
  dimension_count: number;
}

export default function JobProfilesPage() {
  const router = useRouter();
  const [templates, setTemplates] = useState<JobProfileTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [creatingId, setCreatingId] = useState<string | null>(null);

  useEffect(() => {
    void fetchTemplates();
  }, []);

  const fetchTemplates = async () => {
    setLoading(true);
    try {
      const res = await api.get<{
        success: boolean;
        data: JobProfileTemplate[];
      }>("/job-profiles/templates/library");
      setTemplates(res.data || []);
    } catch {
      toast.error("加载岗位画像模板失败");
    } finally {
      setLoading(false);
    }
  };

  const createVersion = async (profileId: string) => {
    setCreatingId(profileId);
    try {
      await api.post(`/job-profiles/${profileId}/versions`, {
        change_reason: "从当前岗位画像生成结构化版本",
        status: "draft",
      });
      toast.success("已生成画像版本");
    } catch {
      toast.error("生成画像版本失败");
    } finally {
      setCreatingId(null);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">
          岗位画像模板库
        </h1>
        <p className="text-sm text-muted-foreground">
          将现有岗位画像沉淀为可版本化、可复用的招聘标准。
        </p>
      </div>

      {loading ? (
        <p className="text-sm text-muted-foreground">加载中...</p>
      ) : null}
      {!loading && templates.length === 0 ? (
        <p className="text-sm text-muted-foreground">暂无岗位画像模板。</p>
      ) : null}

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {templates.map((template) => (
          <Card key={template.id} className="cursor-pointer hover:border-primary/50 transition" onClick={() => router.push(`/dashboard/job-profiles/${template.id}`)}>
            <CardHeader>
              <div className="flex items-start justify-between gap-3">
                <div>
                  <CardTitle>{template.title}</CardTitle>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {template.department || "未设置部门"}
                  </p>
                </div>
                <Badge variant="outline">{template.level}</Badge>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="text-sm text-muted-foreground">
                编码：{template.code}
              </div>
              <div className="grid grid-cols-3 gap-2 text-center text-sm">
                <div className="rounded-lg bg-muted p-2">
                  <div className="font-semibold">
                    {template.hard_requirement_count}
                  </div>
                  <div className="text-xs text-muted-foreground">硬性要求</div>
                </div>
                <div className="rounded-lg bg-muted p-2">
                  <div className="font-semibold">
                    {template.soft_requirement_count}
                  </div>
                  <div className="text-xs text-muted-foreground">软性要求</div>
                </div>
                <div className="rounded-lg bg-muted p-2">
                  <div className="font-semibold">
                    {template.dimension_count}
                  </div>
                  <div className="text-xs text-muted-foreground">考察维度</div>
                </div>
              </div>
              <Button
                className="w-full"
                onClick={() => createVersion(template.id)}
                disabled={creatingId === template.id}
              >
                {creatingId === template.id ? "生成中..." : "生成结构化版本"}
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
