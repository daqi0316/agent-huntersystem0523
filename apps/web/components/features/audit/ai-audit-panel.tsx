"use client";

import { useEffect, useState, useMemo } from "react";
import {
  Brain, Filter, RefreshCw, Loader2, X, Download, ChevronLeft, ChevronRight, FileText,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorAlert } from "@/components/common/error-alert";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
const TOKEN_KEY = "ai-recruitment-token";

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
}

interface AiAuditRecord {
  id: string;
  candidate_id: string;
  application_id: string | null;
  decision_type: string;
  model_name: string;
  prompt_version: string | null;
  input_refs: Record<string, unknown>;
  output_summary: string;
  cited_standard_version_ids: string[];
  cited_evidence_ref_ids: string[];
  confidence: number | null;
  human_confirmed: boolean;
  confirmed_by: string | null;
  confirmed_at: string;
  created_at: string;
}

interface AiAuditResponse {
  items: AiAuditRecord[];
  total: number;
}

const DECISION_TYPE_OPTIONS = [
  { value: "", label: "全部" },
  { value: "screening", label: "简历筛选" },
  { value: "scorecard_assist", label: "评分卡辅助" },
  { value: "rejection_suggest", label: "拒绝建议" },
  { value: "offer_risk", label: "Offer 风险" },
  { value: "onboarding_risk", label: "入职风险" },
  { value: "profile_suggestion", label: "画像建议" },
];

const DECISION_TYPE_COLORS: Record<string, string> = {
  screening: "bg-blue-100 text-blue-700 border-blue-300",
  scorecard_assist: "bg-purple-100 text-purple-700 border-purple-300",
  rejection_suggest: "bg-red-100 text-red-700 border-red-300",
  offer_risk: "bg-amber-100 text-amber-700 border-amber-300",
  onboarding_risk: "bg-orange-100 text-orange-700 border-orange-300",
  profile_suggestion: "bg-teal-100 text-teal-700 border-teal-300",
};

const DECISION_TYPE_LABELS: Record<string, string> = {
  screening: "简历筛选",
  scorecard_assist: "评分卡辅助",
  rejection_suggest: "拒绝建议",
  offer_risk: "Offer 风险",
  onboarding_risk: "入职风险",
  profile_suggestion: "画像建议",
};

function formatTime(iso: string): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("zh-CN", {
      year: "numeric", month: "2-digit", day: "2-digit",
      hour: "2-digit", minute: "2-digit", second: "2-digit",
    });
  } catch { return iso; }
}

function confidenceLevel(val: number | null): { label: string; color: string } {
  if (val === null) return { label: "—", color: "bg-gray-100 text-gray-500" };
  if (val >= 0.8) return { label: `高 (${(val * 100).toFixed(0)}%)`, color: "bg-green-100 text-green-700" };
  if (val >= 0.5) return { label: `中 (${(val * 100).toFixed(0)}%)`, color: "bg-yellow-100 text-yellow-700" };
  return { label: `低 (${(val * 100).toFixed(0)}%)`, color: "bg-red-100 text-red-700" };
}

function exportToCSV(items: AiAuditRecord[]): void {
  const headers = ["时间", "决策类型", "模型", "置信度", "Prompt 版本", "人工确认", "输出摘要"];
  const rows = items.map((r) => [
    formatTime(r.created_at),
    DECISION_TYPE_LABELS[r.decision_type] || r.decision_type,
    r.model_name,
    r.confidence !== null ? String(r.confidence) : "",
    r.prompt_version || "",
    r.human_confirmed ? "是" : "否",
    r.output_summary.slice(0, 200),
  ]);
  const csv = [headers, ...rows]
    .map((row) => row.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(","))
    .join("\n");
  const blob = new Blob(["\ufeff" + csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `ai_audit_${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

function DecisionTypeBadge({ type }: { type: string }) {
  const label = DECISION_TYPE_LABELS[type] || type;
  const color = DECISION_TYPE_COLORS[type] || "";
  return (
    <Badge variant="outline" className={`text-xs ${color}`}>
      {label}
    </Badge>
  );
}

export default function AiAuditPanel() {
  const [records, setRecords] = useState<AiAuditRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [typeFilter, setTypeFilter] = useState<string>("");
  const [fromDate, setFromDate] = useState<string>("");
  const [toDate, setToDate] = useState<string>("");
  const [minConfidence, setMinConfidence] = useState<string>("");
  const [skip, setSkip] = useState(0);
  const [detail, setDetail] = useState<AiAuditRecord | null>(null);
  const limit = 50;

  const queryString = useMemo(() => {
    const params = new URLSearchParams({ limit: String(limit), offset: String(skip) });
    if (typeFilter) params.set("decision_type", typeFilter);
    if (minConfidence) params.set("min_confidence", minConfidence);
    if (fromDate) params.set("from_date", fromDate);
    if (toDate) params.set("to_date", toDate);
    return params.toString();
  }, [typeFilter, minConfidence, fromDate, toDate, skip]);

  const load = async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    else setLoading(true);
    setError(null);
    try {
      const token = getToken();
      if (!token) { setError("未登录"); return; }
      const res = await fetch(`${API_BASE}/audit/ai-audits?${queryString}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: AiAuditResponse = await res.json();
      setRecords(data.items || []);
      setTotal(data.total || 0);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载 AI 决策审计失败");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => { load(); }, [queryString]);

  const filtersActive = typeFilter !== "" || minConfidence !== "" || fromDate !== "" || toDate !== "";
  const hasNext = skip + limit < total;
  const hasPrev = skip > 0;
  const confidenceValue = minConfidence ? Number(minConfidence) : undefined;

  return (
    <>
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="flex items-center gap-2 text-base">
              <Brain className="h-4 w-4" />
              AI 决策审计
              {total > 0 && (
                <span className="text-xs font-normal text-muted-foreground">({total} 总计)</span>
              )}
            </CardTitle>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => exportToCSV(records)}
                disabled={records.length === 0}
              >
                <Download className="mr-1 h-3 w-3" />
                导出 CSV
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => load(true)}
                disabled={refreshing}
              >
                {refreshing ? <Loader2 className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />}
              </Button>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2 pt-3">
            <Filter className="h-3 w-3 text-muted-foreground" />
            <select
              value={typeFilter}
              onChange={(e) => { setTypeFilter(e.target.value); setSkip(0); }}
              className="rounded border border-input bg-background px-2 py-1 text-xs"
              aria-label="按决策类型过滤"
            >
              {DECISION_TYPE_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>

            <span className="text-xs text-muted-foreground">置信度 &ge;</span>
            <select
              value={minConfidence}
              onChange={(e) => { setMinConfidence(e.target.value); setSkip(0); }}
              className="rounded border border-input bg-background px-2 py-1 text-xs"
              aria-label="最低置信度"
            >
              <option value="">全部</option>
              <option value="0.8">≥ 80%</option>
              <option value="0.5">≥ 50%</option>
              <option value="0.3">≥ 30%</option>
            </select>

            <span className="text-xs text-muted-foreground">从</span>
            <input
              type="date"
              value={fromDate}
              onChange={(e) => { setFromDate(e.target.value); setSkip(0); }}
              className="rounded border border-input bg-background px-2 py-1 text-xs"
            />
            <span className="text-xs text-muted-foreground">至</span>
            <input
              type="date"
              value={toDate}
              onChange={(e) => { setToDate(e.target.value); setSkip(0); }}
              className="rounded border border-input bg-background px-2 py-1 text-xs"
            />

            {filtersActive && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => { setTypeFilter(""); setMinConfidence(""); setFromDate(""); setToDate(""); setSkip(0); }}
                className="h-6 px-2 text-xs"
              >
                清除
              </Button>
            )}
          </div>
        </CardHeader>

        <CardContent>
          {error && <ErrorAlert message={error} variant="error" />}

          {loading ? (
            <div className="space-y-2">
              {Array.from({ length: 5 }).map((_, i) => (
                <Skeleton key={i} className="h-10 w-full" />
              ))}
            </div>
          ) : records.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
              <Brain className="mb-2 h-8 w-8 opacity-50" />
              <p className="text-sm">
                {filtersActive ? "当前过滤条件下无记录" : "暂无 AI 决策审计记录"}
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="border-b text-left text-xs text-muted-foreground">
                  <tr>
                    <th className="px-2 py-2 font-medium">时间</th>
                    <th className="px-2 py-2 font-medium">决策类型</th>
                    <th className="px-2 py-2 font-medium">模型</th>
                    <th className="px-2 py-2 font-medium">置信度</th>
                    <th className="px-2 py-2 font-medium">引用标准</th>
                    <th className="px-2 py-2 font-medium">人工确认</th>
                    <th className="px-2 py-2 font-medium text-right">详情</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {records.map((r) => {
                    const cl = confidenceLevel(r.confidence);
                    return (
                      <tr key={r.id} className="hover:bg-muted/30">
                        <td className="px-2 py-2 font-mono text-xs">
                          {formatTime(r.created_at)}
                        </td>
                        <td className="px-2 py-2">
                          <DecisionTypeBadge type={r.decision_type} />
                        </td>
                        <td className="px-2 py-2 text-xs text-muted-foreground">
                          {r.model_name}
                        </td>
                        <td className="px-2 py-2">
                          <Badge variant="outline" className={`text-xs ${cl.color}`}>
                            {cl.label}
                          </Badge>
                        </td>
                        <td className="px-2 py-2 font-mono text-xs text-muted-foreground">
                          {r.cited_standard_version_ids.length > 0
                            ? `${r.cited_standard_version_ids.length} 个`
                            : "—"}
                        </td>
                        <td className="px-2 py-2">
                          {r.human_confirmed ? (
                            <span className="text-xs text-green-600">✓ 已确认</span>
                          ) : (
                            <span className="text-xs text-muted-foreground">待确认</span>
                          )}
                        </td>
                        <td className="px-2 py-2 text-right">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => setDetail(r)}
                            className="h-6 px-2 text-xs"
                          >
                            查看
                          </Button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {!loading && records.length > 0 && (
            <div className="mt-4 flex items-center justify-between text-xs text-muted-foreground">
              <span>
                显示 {skip + 1}-{Math.min(skip + limit, total)} 共 {total}
              </span>
              <div className="flex items-center gap-1">
                <Button variant="outline" size="sm" onClick={() => setSkip(Math.max(0, skip - limit))} disabled={!hasPrev}>
                  <ChevronLeft className="h-3 w-3" />
                  上一页
                </Button>
                <Button variant="outline" size="sm" onClick={() => setSkip(skip + limit)} disabled={!hasNext}>
                  下一页
                  <ChevronRight className="h-3 w-3" />
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {detail && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
          onClick={() => setDetail(null)}
        >
          <div
            className="max-h-[80vh] w-full max-w-3xl overflow-y-auto rounded-lg bg-white p-6"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-lg font-semibold">AI 决策审计详情</h2>
              <button
                onClick={() => setDetail(null)}
                className="text-muted-foreground hover:text-foreground"
                aria-label="关闭"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <dl className="space-y-3 text-sm">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <dt className="text-xs text-muted-foreground">ID</dt>
                  <dd className="font-mono text-xs">{detail.id}</dd>
                </div>
                <div>
                  <dt className="text-xs text-muted-foreground">时间</dt>
                  <dd className="font-mono text-xs">{formatTime(detail.created_at)}</dd>
                </div>
                <div>
                  <dt className="text-xs text-muted-foreground">决策类型</dt>
                  <dd><DecisionTypeBadge type={detail.decision_type} /></dd>
                </div>
                <div>
                  <dt className="text-xs text-muted-foreground">置信度</dt>
                  <dd>
                    <Badge variant="outline" className={`text-xs ${confidenceLevel(detail.confidence).color}`}>
                      {confidenceLevel(detail.confidence).label}
                    </Badge>
                  </dd>
                </div>
                <div>
                  <dt className="text-xs text-muted-foreground">模型</dt>
                  <dd className="font-mono text-xs">{detail.model_name}</dd>
                </div>
                <div>
                  <dt className="text-xs text-muted-foreground">Prompt 版本</dt>
                  <dd className="font-mono text-xs">{detail.prompt_version || "—"}</dd>
                </div>
                <div>
                  <dt className="text-xs text-muted-foreground">Candidate ID</dt>
                  <dd className="font-mono text-xs">{detail.candidate_id}</dd>
                </div>
                <div>
                  <dt className="text-xs text-muted-foreground">Application ID</dt>
                  <dd className="font-mono text-xs">{detail.application_id || "—"}</dd>
                </div>
                <div>
                  <dt className="text-xs text-muted-foreground">人工确认</dt>
                  <dd className="text-xs">
                    {detail.human_confirmed ? (
                      <span className="text-green-600">✓ 已确认{detail.confirmed_by ? ` (${detail.confirmed_by})` : ""}</span>
                    ) : "待确认"}
                  </dd>
                </div>
                {detail.confirmed_at && (
                  <div>
                    <dt className="text-xs text-muted-foreground">确认时间</dt>
                    <dd className="font-mono text-xs">{formatTime(detail.confirmed_at)}</dd>
                  </div>
                )}
              </div>

              <div>
                <dt className="text-xs text-muted-foreground">输出摘要</dt>
                <dd className="rounded bg-muted/30 p-3 text-xs whitespace-pre-wrap">
                  {detail.output_summary}
                </dd>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <dt className="text-xs text-muted-foreground">引用标准版本 ({detail.cited_standard_version_ids.length})</dt>
                  <dd className="max-h-32 overflow-y-auto rounded bg-muted/30 p-2 font-mono text-xs">
                    {detail.cited_standard_version_ids.length > 0
                      ? detail.cited_standard_version_ids.map((v) => (
                          <div key={v} className="truncate">{v}</div>
                        ))
                      : "—"}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs text-muted-foreground">引用证据 ({detail.cited_evidence_ref_ids.length})</dt>
                  <dd className="max-h-32 overflow-y-auto rounded bg-muted/30 p-2 font-mono text-xs">
                    {detail.cited_evidence_ref_ids.length > 0
                      ? detail.cited_evidence_ref_ids.map((v) => (
                          <div key={v} className="truncate">{v}</div>
                        ))
                      : "—"}
                  </dd>
                </div>
              </div>

              <div>
                <dt className="text-xs text-muted-foreground">输入引用 (raw JSON)</dt>
                <dd className="overflow-x-auto rounded bg-muted/30 p-3 font-mono text-xs">
                  <pre>{JSON.stringify(detail.input_refs, null, 2)}</pre>
                </dd>
              </div>
            </dl>

            <div className="mt-4 flex justify-end">
              <Button variant="outline" onClick={() => setDetail(null)}>关闭</Button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
