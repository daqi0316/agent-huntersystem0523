"use client";

import { useState, useEffect, useCallback } from "react";
import { Sparkles, X, Eye, RefreshCw, ArrowUpRight } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/trpc";

interface Recommendation {
  id: string;
  type: string;
  title: string;
  description: string;
  candidate_id: string | null;
  job_id: string | null;
  score: number | null;
  reason: string | null;
  read: boolean;
  created_at: string;
}

interface RecommendationResponse {
  success: boolean;
  data: Recommendation[];
  total: number;
}

const scoreColor = (score: number | null): string => {
  if (score === null) return "text-muted-foreground";
  if (score >= 80) return "text-green-600";
  if (score >= 60) return "text-amber-600";
  return "text-muted-foreground";
};

const scoreBadgeVariant = (score: number | null): "success" | "warning" | "secondary" => {
  if (score === null) return "secondary";
  if (score >= 70) return "success";
  return "warning";
};

export default function RecommendationSection() {
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchRecommendations = useCallback(async () => {
    try {
      const res = await api.get<RecommendationResponse>("/recommendations?limit=10");
      if (res && res.success) {
        setRecommendations(res.data);
      }
    } catch {
      setError("无法加载推荐");
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchUnreadCount = useCallback(async () => {
    try {
      const res = await api.get<{ count: number }>("/recommendations/unread-count");
      if (res) {
        setUnreadCount(res.count);
      }
    } catch {
      /* silent */
    }
  }, []);

  useEffect(() => {
    fetchRecommendations();
    fetchUnreadCount();
  }, [fetchRecommendations, fetchUnreadCount]);

  const handleDismiss = async (id: string) => {
    const ok = await api.post<{ success: boolean }>(`/recommendations/${id}/dismiss`, {});
    if (ok?.success) {
      setRecommendations((prev) => prev.filter((r) => r.id !== id));
    }
  };

  const handleMarkRead = async (id: string) => {
    const ok = await api.post<{ success: boolean }>(`/recommendations/${id}/read`, {});
    if (ok?.success) {
      setRecommendations((prev) =>
        prev.map((r) => (r.id === id ? { ...r, read: true } : r)),
      );
      setUnreadCount((prev) => Math.max(0, prev - 1));
    }
  };

  const handleRefresh = async () => {
    setLoading(true);
    await fetchRecommendations();
    await fetchUnreadCount();
  };

  const handleMarkAllRead = async () => {
    const ok = await api.post<{ success: boolean }>("/recommendations/read-all", {});
    if (ok?.success) {
      setRecommendations((prev) => prev.map((r) => ({ ...r, read: true })));
      setUnreadCount(0);
    }
  };

  if (loading) {
    return (
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <Skeleton className="h-5 w-32" />
            <Skeleton className="h-6 w-16 rounded-full" />
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-16 w-full" />
          ))}
        </CardContent>
      </Card>
    );
  }

  if (error && recommendations.length === 0) {
    return null;
  }

  const visible = recommendations.filter((r) => !r.read).slice(0, 5);
  const showEmpty = visible.length === 0 && !loading;

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-violet-500" />
            <CardTitle className="text-base">智能推荐</CardTitle>
            {unreadCount > 0 && (
              <Badge variant="default" className="ml-1">
                {unreadCount}
              </Badge>
            )}
          </div>
          <div className="flex items-center gap-1">
            {unreadCount > 0 && (
              <Button variant="ghost" size="sm" onClick={handleMarkAllRead} className="h-7 text-xs">
                <Eye className="mr-1 h-3 w-3" />
                全部已读
              </Button>
            )}
            <Button variant="ghost" size="icon" onClick={handleRefresh} className="h-7 w-7">
              <RefreshCw className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {showEmpty ? (
          <div className="flex flex-col items-center justify-center py-6 text-center text-sm text-muted-foreground">
            <Sparkles className="mb-2 h-5 w-5 opacity-30" />
            <p>暂无新的推荐</p>
            <p className="text-xs">系统将定期扫描匹配候选人</p>
          </div>
        ) : (
          <div className="space-y-2">
            {visible.map((rec) => (
              <div
                key={rec.id}
                className="group relative flex items-start gap-3 rounded-lg border p-3 transition-colors hover:bg-accent/50"
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="truncate text-sm font-medium">
                      {rec.title}
                    </span>
                    {rec.score !== null && (
                      <Badge variant={scoreBadgeVariant(rec.score)} className="shrink-0 text-[10px]">
                        {rec.score}分
                      </Badge>
                    )}
                  </div>
                  {rec.reason && (
                    <p className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">
                      {rec.reason}
                    </p>
                  )}
                </div>
                <div className="flex shrink-0 items-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100">
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => handleMarkRead(rec.id)}
                    className="h-7 w-7"
                    title="标记已读"
                  >
                    <Eye className="h-3.5 w-3.5" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => handleDismiss(rec.id)}
                    className="h-7 w-7"
                    title="忽略"
                  >
                    <X className="h-3.5 w-3.5" />
                  </Button>
                </div>
              </div>
            ))}
            {recommendations.length > 5 && (
              <div className="pt-1 text-center">
                <span className="text-xs text-muted-foreground">
                  还有 {recommendations.length - 5} 条推荐
                </span>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
