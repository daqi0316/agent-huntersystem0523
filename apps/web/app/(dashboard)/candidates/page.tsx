"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import {
  Search, ChevronLeft, ChevronRight, ExternalLink,
  User, Loader2, Upload, X, CheckCircle2,
  ArrowLeft, FileText, Calendar, Clock,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { ErrorAlert } from "@/components/common/error-alert";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import Link from "next/link";
import { api } from "@/lib/trpc";

/* ── Data Types ── */

interface CandidateItem {
  id: string;
  name: string;
  email: string;
  phone?: string;
  summary?: string;
  skills: string[];
  experience_years?: number;
  current_company?: string;
  current_title?: string;
  status: string;
  created_at: string;
}

interface ListData {
  items: CandidateItem[];
  total: number;
  skip: number;
  limit: number;
}

interface CandidateListResponse {
  success: boolean;
  data: ListData;
  items: CandidateItem[];
  total: number;
}

/* ── Resume Import Types ── */

interface ExtractedCandidate {
  name: string;
  email: string;
  phone: string;
  summary: string;
  skills: string[];
  experience_years: number | null;
  education: string;
  current_company: string;
  current_title: string;
  raw_text: string;
}

interface ExtractResponse {
  success: boolean;
  filename: string;
  text_length: number;
  candidate: ExtractedCandidate | null;
  needs_review: boolean;
}

interface ConfirmResponse {
  success: boolean;
  candidate_id: string;
  candidate_name: string;
  screening_result: Record<string, unknown> | null;
  message: string;
}

const STATUS_MAP: Record<string, { label: string; color: string }> = {
  active: { label: "初筛中", color: "bg-blue-100 text-blue-700 border-blue-200" },
  archived: { label: "已归档", color: "bg-gray-100 text-gray-700 border-gray-200" },
  blacklisted: { label: "已拒绝", color: "bg-red-100 text-red-700 border-red-200" },
};

const STATUS_OPTIONS = ["全部", "active", "archived", "blacklisted"];
const PAGE_SIZE = 5;

/* ── Helpers ── */

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/* ══════════════════════════════════════════════════════════════
   Detail Dialog
   ══════════════════════════════════════════════════════════════ */

interface TimelineEvent {
  type: string;
  title: string;
  description: string;
  timestamp: string;
  status: string;
  metadata: Record<string, unknown>;
}

interface TimelineResponse {
  success: boolean;
  data: {
    candidate_id: string;
    candidate_name: string;
    events: TimelineEvent[];
    total: number;
  };
}

function DetailDialog({ candidate, onClose }: { candidate: CandidateItem; onClose: () => void }) {
  const sc = STATUS_MAP[candidate.status] || { label: candidate.status, color: "bg-gray-100" };
  const [tab, setTab] = useState<"info" | "timeline">("info");
  const [timeline, setTimeline] = useState<TimelineEvent[]>([]);
  const [tlLoading, setTlLoading] = useState(false);

  useEffect(() => {
    if (tab === "timeline" && timeline.length === 0 && !tlLoading) {
      setTlLoading(true);
      api.get<TimelineResponse>(`/candidates/${candidate.id}/timeline`)
        .then((res) => { if (res?.success) setTimeline(res.data.events || []); })
        .catch(() => {})
        .finally(() => setTlLoading(false));
    }
  }, [tab, candidate.id, timeline.length, tlLoading]);

  const timelineIcon = (type: string) => {
    switch (type) {
      case "created": return <User className="h-4 w-4 text-blue-500" />;
      case "application": return <FileText className="h-4 w-4 text-purple-500" />;
      case "evaluation": return <CheckCircle2 className="h-4 w-4 text-green-500" />;
      case "interview": return <Calendar className="h-4 w-4 text-orange-500" />;
      case "feedback": return <CheckCircle2 className="h-4 w-4 text-emerald-500" />;
      default: return <Clock className="h-4 w-4 text-gray-400" />;
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={onClose}>
      <div className="w-full max-w-lg rounded-xl bg-white p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-bold">{candidate.name}</h2>
          <Badge className={sc.color}>{sc.label}</Badge>
        </div>

        <div className="mb-4 flex gap-2 border-b">
          <button className={`px-3 py-2 text-sm font-medium ${tab === "info" ? "border-b-2 border-blue-500 text-blue-600" : "text-muted-foreground"}`} onClick={() => setTab("info")}>基本信息</button>
          <button className={`px-3 py-2 text-sm font-medium ${tab === "timeline" ? "border-b-2 border-blue-500 text-blue-600" : "text-muted-foreground"}`} onClick={() => setTab("timeline")}>时间线</button>
        </div>

        {tab === "info" && (
          <div className="space-y-3 text-sm">
            <div className="grid grid-cols-2 gap-2">
              <div><span className="text-muted-foreground">邮箱</span><p>{candidate.email}</p></div>
              <div><span className="text-muted-foreground">电话</span><p>{candidate.phone || "-"}</p></div>
            </div>
            <div><span className="text-muted-foreground">当前职位</span><p>{candidate.current_title || "-"}</p></div>
            <div><span className="text-muted-foreground">所在公司</span><p>{candidate.current_company || "-"}</p></div>
            <div><span className="text-muted-foreground">经验</span><p>{candidate.experience_years ? `${candidate.experience_years} 年` : "-"}</p></div>
            <div>
              <span className="text-muted-foreground">技能</span>
              <div className="mt-1 flex flex-wrap gap-1">
                {candidate.skills.length > 0 ? candidate.skills.map((s) => (
                  <Badge key={s} variant="outline" className="text-xs">{s}</Badge>
                )) : <span className="text-muted-foreground">-</span>}
              </div>
            </div>
            {candidate.summary && (
              <div><span className="text-muted-foreground">简介</span><p className="mt-1">{candidate.summary}</p></div>
            )}
          </div>
        )}

        {tab === "timeline" && (
          <div className="max-h-80 space-y-0 overflow-y-auto">
            {tlLoading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
              </div>
            ) : timeline.length === 0 ? (
              <p className="py-8 text-center text-sm text-muted-foreground">暂无事件记录</p>
            ) : (
              <div className="relative pl-6">
                <div className="absolute left-[11px] top-0 h-full w-0.5 bg-border" />
                {timeline.map((ev, i) => (
                  <div key={i} className="relative pb-5">
                    <div className="absolute -left-[19px] flex h-6 w-6 items-center justify-center rounded-full border bg-white">
                      {timelineIcon(ev.type)}
                    </div>
                    <div>
                      <p className="text-sm font-medium">{ev.title}</p>
                      <p className="text-xs text-muted-foreground">{ev.description}</p>
                      <p className="mt-0.5 text-[10px] text-muted-foreground/60">
                        {ev.timestamp ? new Date(ev.timestamp).toLocaleString("zh-CN") : ""}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        <div className="mt-4 flex justify-end">
          <Button variant="outline" onClick={onClose}>关闭</Button>
        </div>
      </div>
    </div>
  );
}

/* ══════════════════════════════════════════════════════════════
   Resume Import Dialog
   ══════════════════════════════════════════════════════════════ */

function ResumeImportDialog({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [step, setStep] = useState<"upload" | "review" | "done">("upload");
  const [file, setFile] = useState<File | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [candidate, setCandidate] = useState<ExtractedCandidate | null>(null);
  const [confirmMsg, setConfirmMsg] = useState("");
  const [newSkill, setNewSkill] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const isAllowed = (f: File) =>
    ["application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/msword", "text/plain"].includes(f.type) ||
    f.name.endsWith(".doc");

  const handleFile = useCallback((f: File) => {
    if (!isAllowed(f)) { setError("仅支持 PDF、DOCX、TXT"); return; }
    if (f.size > 10 * 1024 * 1024) { setError("文件超过 10MB"); return; }
    setFile(f);
    setError(null);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault(); setDragOver(false);
    const f = e.dataTransfer.files[0];
    if (f) handleFile(f);
  }, [handleFile]);

  const handleChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (f) handleFile(f);
  }, [handleFile]);

  const fileTypeIcon = (name: string) => {
    if (name.endsWith(".pdf")) return "PDF";
    if (name.endsWith(".docx") || name.endsWith(".doc")) return "DOC";
    return "TXT";
  };

  // Upload & extract
  const handleUpload = useCallback(async () => {
    if (!file) return;
    setLoading(true); setError(null);
    try {
      const fd = new FormData(); fd.append("file", file);
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1"}/resume/extract-resume`,
        { method: "POST", body: fd }
      );
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || "解析失败");
      const data: ExtractResponse = await res.json();
      setCandidate(data.candidate || null);
      setStep("review");
    } catch (err) {
      setError(err instanceof Error ? err.message : "解析失败");
    } finally {
      setLoading(false);
    }
  }, [file]);

  // Edit candidate
  const update = (key: keyof ExtractedCandidate, value: unknown) =>
    setCandidate((p) => (p ? { ...p, [key]: value } : p));

  const addSkill = () => {
    const s = newSkill.trim();
    if (s && candidate && !candidate.skills.includes(s)) {
      setCandidate({ ...candidate, skills: [...candidate.skills, s] });
      setNewSkill("");
    }
  };

  const removeSkill = (skill: string) =>
    setCandidate((p) => (p ? { ...p, skills: p.skills.filter((s) => s !== skill) } : p));

  // Confirm create candidate
  const handleConfirm = useCallback(async () => {
    if (!candidate) return;
    setLoading(true); setError(null);
    try {
      const res = await api.post<ConfirmResponse>("/resume/confirm-resume", {
        parsed: candidate, create_candidate: true, run_screening: false,
      });
      setConfirmMsg(res.message);
      setStep("done");
      onCreated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "创建失败");
    } finally {
      setLoading(false);
    }
  }, [candidate, onCreated]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={step === "done" ? undefined : onClose}>
      <div className="mx-4 w-full max-w-2xl rounded-xl bg-white shadow-xl" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="flex items-center justify-between border-b px-6 py-4">
          <h2 className="text-lg font-semibold">导入简历</h2>
          <button onClick={onClose} className="rounded-full p-1 hover:bg-muted"><X className="h-4 w-4" /></button>
        </div>

        {error && (
          <ErrorAlert message={error} onDismiss={() => setError(null)} className="mx-6 mt-4" />
        )}

        <div className="p-6">
          {/* ── Step: upload ── */}
          {step === "upload" && (
            <div className="space-y-4">
              <div
                className={`flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed p-12 transition-colors ${
                  dragOver ? "border-primary bg-primary/5" : "border-muted-foreground/25 hover:border-muted-foreground/50"
                }`}
                onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
                onDragLeave={() => setDragOver(false)}
                onDrop={handleDrop}
                onClick={() => inputRef.current?.click()}
              >
                <Upload className="mb-4 h-8 w-8 text-muted-foreground/60" />
                <p className="text-sm font-medium">{dragOver ? "松开以上传" : "拖拽简历文件到此处，或点击选择"}</p>
                <p className="mt-1 text-xs text-muted-foreground">PDF / DOCX / TXT，最大 10MB</p>
                <input ref={inputRef} type="file" accept=".pdf,.docx,.doc,.txt" className="hidden" onChange={handleChange} />
              </div>

              {file && (
                <div className="flex items-center gap-3 rounded-lg border p-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-md bg-primary/10 text-xs font-bold text-primary">{fileTypeIcon(file.name)}</div>
                  <div className="flex-1 min-w-0">
                    <p className="truncate text-sm font-medium">{file.name}</p>
                    <p className="text-xs text-muted-foreground">{formatFileSize(file.size)}</p>
                  </div>
                  <Button variant="ghost" size="icon" onClick={() => setFile(null)}><X className="h-4 w-4" /></Button>
                </div>
              )}

              <Button className="w-full" size="lg" disabled={!file || loading} onClick={handleUpload}>
                {loading ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />解析中...</> : <><Upload className="mr-2 h-4 w-4" />上传并解析</>}
              </Button>
            </div>
          )}

          {/* ── Step: review ── */}
          {step === "review" && candidate && (
            <div className="space-y-4">
              <div className="flex items-center gap-3 rounded-lg border px-4 py-3">
                <FileText className="h-5 w-5 text-muted-foreground" />
                <span className="flex-1 text-sm text-muted-foreground">{file?.name} · 解析完成</span>
                <Button variant="ghost" size="sm" onClick={() => { setFile(null); setCandidate(null); setStep("upload"); }}>重新选择</Button>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1"><label className="text-xs font-medium text-muted-foreground">姓名</label><Input value={candidate.name} onChange={(e) => update("name", e.target.value)} /></div>
                <div className="space-y-1"><label className="text-xs font-medium text-muted-foreground">邮箱 *</label><Input value={candidate.email} onChange={(e) => update("email", e.target.value)} /></div>
                <div className="space-y-1"><label className="text-xs font-medium text-muted-foreground">电话</label><Input value={candidate.phone} onChange={(e) => update("phone", e.target.value)} /></div>
                <div className="space-y-1"><label className="text-xs font-medium text-muted-foreground">经验（年）</label><Input type="number" value={candidate.experience_years ?? ""} onChange={(e) => update("experience_years", e.target.value ? parseInt(e.target.value) : null)} /></div>
                <div className="space-y-1"><label className="text-xs font-medium text-muted-foreground">当前公司</label><Input value={candidate.current_company} onChange={(e) => update("current_company", e.target.value)} /></div>
                <div className="space-y-1"><label className="text-xs font-medium text-muted-foreground">当前职位</label><Input value={candidate.current_title} onChange={(e) => update("current_title", e.target.value)} /></div>
              </div>
              <div className="space-y-1"><label className="text-xs font-medium text-muted-foreground">教育背景</label><Input value={candidate.education} onChange={(e) => update("education", e.target.value)} /></div>
              <div className="space-y-1"><label className="text-xs font-medium text-muted-foreground">简介</label><Textarea rows={2} value={candidate.summary} onChange={(e) => update("summary", e.target.value)} /></div>
              <Separator />
              <div className="space-y-2">
                <label className="text-xs font-medium text-muted-foreground">技能标签</label>
                <div className="flex flex-wrap gap-1.5">
                  {candidate.skills.map((s) => (
                    <Badge key={s} variant="secondary" className="gap-1 pr-1">
                      {s}
                      <button onClick={() => removeSkill(s)} className="ml-0.5 rounded-full p-0.5 hover:bg-muted-foreground/20"><X className="h-3 w-3" /></button>
                    </Badge>
                  ))}
                </div>
                <div className="flex gap-2">
                  <Input placeholder="添加技能" value={newSkill} onChange={(e) => setNewSkill(e.target.value)} onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addSkill())} className="max-w-[200px]" />
                  <Button variant="outline" size="sm" onClick={addSkill}>添加</Button>
                </div>
              </div>
              <div className="flex justify-end gap-3 pt-2">
                <Button variant="outline" onClick={() => { setFile(null); setCandidate(null); setStep("upload"); }}><ArrowLeft className="mr-2 h-4 w-4" />重新选择</Button>
                <Button size="lg" disabled={loading || !candidate.email} onClick={handleConfirm}>
                  {loading ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />创建中...</> : <><CheckCircle2 className="mr-2 h-4 w-4" />确认创建</>}
                </Button>
              </div>
            </div>
          )}

          {/* ── Step: done ── */}
          {step === "done" && (
            <div className="flex flex-col items-center py-8 text-center">
              <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-emerald-100">
                <CheckCircle2 className="h-7 w-7 text-emerald-600" />
              </div>
              <p className="text-base font-semibold">{confirmMsg || "候选人创建成功"}</p>
              <p className="mt-2 text-sm text-muted-foreground">已加入候选人库，可在列表中查看</p>
              <div className="mt-6 flex gap-3">
                <Button variant="outline" onClick={onClose}>完成</Button>
                <Button onClick={() => { setFile(null); setCandidate(null); setStep("upload"); setConfirmMsg(""); }}>继续导入</Button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/* ══════════════════════════════════════════════════════════════
   Main Page
   ══════════════════════════════════════════════════════════════ */

export default function CandidatesPage() {
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("全部");
  const [page, setPage] = useState(0);
  const [detail, setDetail] = useState<CandidateItem | null>(null);
  const [showImport, setShowImport] = useState(false);
  const [items, setItems] = useState<CandidateItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const params = new URLSearchParams({ skip: String(page * PAGE_SIZE), limit: String(PAGE_SIZE) });
      if (search.trim()) params.set("search", search);
      if (statusFilter !== "全部") params.set("status", statusFilter);
      const res = await api.get<CandidateListResponse>(`/candidates?${params}`);
      const list = (res as unknown as ListData);
      setItems(list.items || []);
      setTotal(list.total || 0);
    } catch {
      setError("后端暂未连接，请启动服务后刷新");
      setItems([]); setTotal(0);
    } finally { setLoading(false); }
  }, [search, statusFilter, page]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">候选人库</h1>
          <p className="text-muted-foreground">浏览、搜索和管理候选人信息</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => setShowImport(true)}>
            <Upload className="mr-2 h-4 w-4" /> 导入简历
          </Button>
          <Link href="/screening">
            <Button><User className="mr-2 h-4 w-4" /> 初筛候选人</Button>
          </Link>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input className="pl-9" placeholder="搜索姓名、邮箱、职位..." value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(0); }} />
        </div>
        <select className="rounded-lg border bg-transparent px-3 py-2 text-sm outline-none"
          value={statusFilter} onChange={(e) => { setStatusFilter(e.target.value); setPage(0); }}>
          {STATUS_OPTIONS.map((s) => (
            <option key={s} value={s}>{s === "全部" ? "全部" : STATUS_MAP[s]?.label || s}</option>
          ))}
        </select>
      </div>

      {/* Table */}
      <Card>
        <CardContent className="p-0">
          {loading ? (
            <div className="space-y-1 p-4">
              {Array.from({ length: 5 }).map((_, i) => (
                <div key={i} className="flex items-center gap-4 py-3">
                  <Skeleton className="h-8 w-8 rounded-full" />
                  <div className="flex-1 space-y-1">
                    <Skeleton className="h-4 w-32" />
                    <Skeleton className="h-3 w-48" />
                  </div>
                  <Skeleton className="h-4 w-24 hidden md:block" />
                  <Skeleton className="h-4 w-20 hidden lg:block" />
                  <Skeleton className="h-5 w-16" />
                </div>
              ))}
            </div>
          ) : error ? (
            <ErrorAlert message={error} className="mx-auto max-w-md" />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/50">
                    <th className="px-4 py-3 text-left font-medium">姓名</th>
                    <th className="hidden px-4 py-3 text-left font-medium md:table-cell">邮箱</th>
                    <th className="hidden px-4 py-3 text-left font-medium lg:table-cell">当前职位</th>
                    <th className="px-4 py-3 text-left font-medium">状态</th>
                    <th className="px-4 py-3 text-center font-medium">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((c) => {
                    const sc = STATUS_MAP[c.status] || { label: c.status, color: "bg-gray-100" };
                    return (
                      <tr key={c.id} className="border-b transition-colors hover:bg-muted/30">
                        <td className="px-4 py-3 font-medium">{c.name}</td>
                        <td className="hidden px-4 py-3 text-muted-foreground md:table-cell">{c.email}</td>
                        <td className="hidden px-4 py-3 text-muted-foreground lg:table-cell">{c.current_title || "-"}</td>
                        <td className="px-4 py-3"><Badge className={sc.color}>{sc.label}</Badge></td>
                        <td className="px-4 py-3 text-center">
                          <Button variant="ghost" size="icon" onClick={() => setDetail(c)} title="详情"><ExternalLink className="h-4 w-4" /></Button>
                        </td>
                      </tr>
                    );
                  })}
                  {items.length === 0 && (
                    <tr><td colSpan={5} className="px-4 py-8 text-center text-muted-foreground">暂无候选人</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Pagination */}
      <div className="flex items-center justify-between text-sm">
        <span className="text-muted-foreground">共 {total} 人</span>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="icon" disabled={page === 0} onClick={() => setPage(page - 1)}><ChevronLeft className="h-4 w-4" /></Button>
          <span className="min-w-[4rem] text-center">{page + 1} / {totalPages}</span>
          <Button variant="outline" size="icon" disabled={page >= totalPages - 1} onClick={() => setPage(page + 1)}><ChevronRight className="h-4 w-4" /></Button>
        </div>
      </div>

      {/* Dialogs */}
      {detail && <DetailDialog candidate={detail} onClose={() => setDetail(null)} />}
      {showImport && <ResumeImportDialog onClose={() => setShowImport(false)} onCreated={fetchData} />}
    </div>
  );
}
