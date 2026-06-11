"use client";

/**
 * P2a-5: 寻源候选人列表页
 */
import { useState, useCallback } from "react";
import Link from "next/link";
import { Search, ChevronLeft, ChevronRight, ExternalLink, Merge } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useSourcingCandidateList,
  useTaskList,
  useMergeCandidates,
  type SourcingCandidate,
} from "@/hooks/use-sourcing";
import { useSearchParams } from "next/navigation";

type FpGroup = { fingerprint: string; candidates: SourcingCandidate[] };

function groupByFingerprint(candidates: SourcingCandidate[]): FpGroup[] {
  const groups = new Map<string, SourcingCandidate[]>();
  for (const c of candidates) {
    if (c.dedup_fingerprint) {
      const arr = groups.get(c.dedup_fingerprint) || [];
      arr.push(c);
      groups.set(c.dedup_fingerprint, arr);
    }
  }
  return Array.from(groups.entries())
    .filter(([, arr]) => arr.length >= 2)
    .map(([fingerprint, arr]) => ({ fingerprint, candidates: arr }));
}

export default function SourcingCandidateList() {
  const searchParams = useSearchParams();
  const initialTaskId = searchParams.get("task_id") || "";

  const [page, setPage] = useState(1);
  const [taskFilter, setTaskFilter] = useState(initialTaskId);
  const [skillFilter, setSkillFilter] = useState("");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const mergeMutation = useMergeCandidates();

  const { data, isLoading } = useSourcingCandidateList({
    task_id: taskFilter || undefined,
    skill: skillFilter || undefined,
    page,
    page_size: 20,
  });

  const { data: tasksData } = useTaskList({ page: 1, page_size: 100 });

  const totalPages = data ? Math.ceil(data.total / 20) : 1;
  const candidates = data?.data || [];

  const fpGroups = groupByFingerprint(candidates);
  const fpFingerprints = new Set(fpGroups.map((g) => g.fingerprint));

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const canMerge = (() => {
    if (selectedIds.size < 2) return false;
    // 检查选中的候选人是否有相同 fingerprint
    const selected = candidates.filter((c) => selectedIds.has(c.id));
    const fps = selected.map((c) => c.dedup_fingerprint).filter(Boolean);
    return new Set(fps).size === 1; // 所有选中的有同一个 fingerprint
  })();

  const handleMerge = useCallback(() => {
    const selected = candidates.filter((c) => selectedIds.has(c.id));
    if (selected.length < 2) return;
    const fp = selected[0].dedup_fingerprint;
    if (!fp) return;
    const sameFp = selected.filter((c) => c.dedup_fingerprint === fp);
    if (sameFp.length < 2) return;
    const [primary, ...rest] = sameFp;
    mergeMutation.mutate(
      { primary_id: primary.id, merge_ids: rest.map((c) => c.id) },
      {
        onSuccess: () => {
          setSelectedIds(new Set());
        },
      }
    );
  }, [candidates, selectedIds, mergeMutation]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold tracking-tight">寻源候选人</h1>
        <div className="flex items-center gap-2">
          {canMerge && (
            <Button size="sm" onClick={handleMerge} disabled={mergeMutation.isPending}>
              <Merge className="h-3.5 w-3.5 mr-1" />
              合并选中 ({selectedIds.size})
            </Button>
          )}
          <span className="text-sm text-muted-foreground">
            共 {data?.total ?? "-"} 条
          </span>
        </div>
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="pt-4">
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-1">
              <span className="text-xs text-muted-foreground">任务:</span>
              <select
                className="h-8 rounded-md border border-input bg-background px-2 text-xs max-w-[200px]"
                value={taskFilter}
                onChange={(e) => { setTaskFilter(e.target.value); setPage(1); }}
              >
                <option value="">全部任务</option>
                {tasksData?.data?.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.keyword}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex items-center gap-1">
              <span className="text-xs text-muted-foreground">技能:</span>
              <Input
                placeholder="过滤技能"
                className="h-8 w-32 text-xs"
                value={skillFilter}
                onChange={(e) => { setSkillFilter(e.target.value); setPage(1); }}
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* List */}
      <div className="space-y-2">
        {isLoading ? (
          Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-20 w-full rounded-md" />
          ))
        ) : (
          candidates.map((c) => {
            const isMultiSource = fpFingerprints.has(c.dedup_fingerprint || "");
            return (
              <div key={c.id} className="flex items-start gap-2">
                {isMultiSource && (
                  <input
                    type="checkbox"
                    checked={selectedIds.has(c.id)}
                    onChange={() => toggleSelect(c.id)}
                    className="mt-3.5 h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                  />
                )}
                <Link
                  href={`/candidates/${c.id}`}
                  className={`flex-1 flex items-start justify-between rounded-md border p-3 hover:bg-accent/50 transition-colors ${isMultiSource ? "border-yellow-300 dark:border-yellow-700" : ""}`}
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-medium">{c.name}</p>
                      {isMultiSource && (
                        <Badge className="bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400 text-xs">待合并</Badge>
                      )}
                      {c.experience_years != null && (
                        <span className="text-xs text-muted-foreground">{c.experience_years} 年经验</span>
                      )}
                    </div>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      {c.current_title}{c.current_title && c.current_company ? " · " : ""}{c.current_company}
                    </p>
                    {c.skills && c.skills.length > 0 && (
                      <div className="flex flex-wrap gap-1 mt-1.5">
                        {c.skills.slice(0, 6).map((s) => (
                          <Badge key={s} variant="secondary" className="text-xs">{s}</Badge>
                        ))}
                        {c.skills.length > 6 && (
                          <span className="text-xs text-muted-foreground">+{c.skills.length - 6}</span>
                        )}
                      </div>
                    )}
                  </div>
                  <div className="flex items-center gap-2 shrink-0 ml-3">
                    {c.source_platforms?.map((p) => (
                      <Badge key={p} variant="outline" className="text-xs">{p}</Badge>
                    ))}
                  </div>
                </Link>
              </div>
            );
          })
        )}
        {!isLoading && candidates.length === 0 && (
          <p className="text-sm text-muted-foreground text-center py-8">
            {taskFilter ? "该任务暂无候选人" : "暂无寻源候选人"}
          </p>
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
