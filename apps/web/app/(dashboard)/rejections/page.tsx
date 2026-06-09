"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/trpc";

interface AnalyticsItem {
  key: string;
  label: string;
  count: number;
  percentage: number;
}

interface RejectionAnalytics {
  total: number;
  by_reason: AnalyticsItem[];
  by_stage: AnalyticsItem[];
  by_job_profile: AnalyticsItem[];
  by_preventable_by: AnalyticsItem[];
}

interface PreventableItem extends AnalyticsItem {
  suggested_action: string;
}

const actionMap: Record<string, string> = {
  sourcing: "优化寻访关键词和渠道准入",
  screening: "前置初筛追问和硬性条件校验",
  scorecard: "调整评分卡维度或行为锚定",
  compensation: "提前校准薪酬预期和预算边界",
  process: "优化跟进节奏和流程 SLA",
  none: "记录为不可预防原因，持续观察样本",
};

export default function RejectionsPage() {
  const [analytics, setAnalytics] = useState<RejectionAnalytics | null>(null);
  const [preventableItems, setPreventableItems] = useState<PreventableItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    void fetchAnalytics();
  }, []);

  const fetchAnalytics = async () => {
    setLoading(true);
    try {
      const res = await api.get<{ success: boolean; data: RejectionAnalytics }>(
        "/rejections/analytics/distribution",
      );
      setAnalytics(res.data);
      const preventable = await api.get<{
        success: boolean;
        data: { total: number; items: PreventableItem[] };
      }>("/rejections/analytics/preventable");
      setPreventableItems(preventable.data.items || []);
    } catch {
      toast.error("加载淘汰原因分析失败");
    } finally {
      setLoading(false);
    }
  };

  const renderList = (items: AnalyticsItem[]) => (
    <div className="space-y-3">
      {items.length === 0 ? (
        <p className="text-sm text-muted-foreground">暂无数据</p>
      ) : null}
      {items.map((item) => (
        <div key={item.key} className="rounded-lg border p-3">
          <div className="flex items-center justify-between gap-3">
            <div className="font-medium">{item.label}</div>
            <Badge variant="outline">{item.count}</Badge>
          </div>
          <div className="mt-2 h-2 rounded-full bg-muted">
            <div
              className="h-2 rounded-full bg-primary"
              style={{ width: `${Math.round(item.percentage * 100)}%` }}
            />
          </div>
          <div className="mt-1 text-xs text-muted-foreground">
            {Math.round(item.percentage * 100)}%
          </div>
        </div>
      ))}
    </div>
  );

  const preventableDisplayItems: PreventableItem[] = preventableItems.length
    ? preventableItems
    : analytics?.by_preventable_by.map((item) => ({
        ...item,
        suggested_action: actionMap[item.key] || "复盘对应环节并形成改进动作",
      })) || [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">淘汰原因分析</h1>
        <p className="text-sm text-muted-foreground">
          按原因、阶段、岗位画像和可预防动作分析候选人淘汰分布。
        </p>
      </div>

      {loading ? (
        <p className="text-sm text-muted-foreground">加载中...</p>
      ) : null}

      {analytics ? (
        <>
          <Card>
            <CardHeader>
              <CardTitle>总览</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-3xl font-semibold">{analytics.total}</div>
              <div className="text-sm text-muted-foreground">
                结构化淘汰记录
              </div>
            </CardContent>
          </Card>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>按原因</CardTitle>
              </CardHeader>
              <CardContent>{renderList(analytics.by_reason)}</CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>按阶段</CardTitle>
              </CardHeader>
              <CardContent>{renderList(analytics.by_stage)}</CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>按岗位画像</CardTitle>
              </CardHeader>
              <CardContent>{renderList(analytics.by_job_profile)}</CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>可预防动作</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {preventableDisplayItems.map((item) => (
                  <div key={item.key} className="rounded-lg border p-3">
                    <div className="flex items-center justify-between gap-3">
                      <div className="font-medium">{item.label}</div>
                      <Badge>{item.count}</Badge>
                    </div>
                    <p className="mt-2 text-sm text-muted-foreground">
                      {item.suggested_action}
                    </p>
                  </div>
                ))}
              </CardContent>
            </Card>
          </div>
        </>
      ) : null}
    </div>
  );
}
