"use client";

import { useState, useEffect, useCallback } from "react";
import { Search, Plus, Briefcase, MapPin, Clock, Loader2, Sparkles, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/trpc";

interface JobItem {
  id: string;
  title: string;
  department?: string;
  description?: string;
  requirements?: string;
  location?: string;
  salary_range?: string;
  status: string;
  created_at: string;
}

interface JobListResponse {
  items?: JobItem[];
  total?: number;
  data?: { items: JobItem[]; total: number };
}

interface CreatePayload {
  title: string;
  department?: string;
  description?: string;
  requirements?: string;
  location?: string;
  salary_range?: string;
}

const STATUS_MAP: Record<string, { label: string; color: string }> = {
  draft: { label: "草稿", color: "bg-gray-100 text-gray-700 border-gray-200" },
  active: { label: "招聘中", color: "bg-green-100 text-green-700 border-green-200" },
  paused: { label: "已暂停", color: "bg-yellow-100 text-yellow-700 border-yellow-200" },
  closed: { label: "已关闭", color: "bg-red-100 text-red-700 border-red-200" },
};

function DetailDialog({ job, onClose }: { job: JobItem; onClose: () => void }) {
  const sc = STATUS_MAP[job.status] || { label: job.status, color: "bg-gray-100" };
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={onClose}>
      <div className="w-full max-w-2xl rounded-xl bg-white p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between">
          <div>
            <h2 className="text-lg font-bold">{job.title}</h2>
            <p className="text-sm text-muted-foreground">{job.department || "-"} · {job.location || "-"}</p>
          </div>
          <Badge className={sc.color}>{sc.label}</Badge>
        </div>
        <div className="space-y-4 text-sm">
          <div className="flex flex-wrap gap-4 text-muted-foreground">
            {job.location && <span className="flex items-center gap-1"><MapPin className="h-3 w-3" />{job.location}</span>}
            <span className="flex items-center gap-1"><Clock className="h-3 w-3" />{new Date(job.created_at).toLocaleDateString("zh-CN")}</span>
            {job.salary_range && <span>{job.salary_range}</span>}
          </div>
          <div>
            <h4 className="mb-1 font-medium">职位描述</h4>
            <p className="text-muted-foreground">{job.description || "暂无"}</p>
          </div>
          <div>
            <h4 className="mb-1 font-medium">任职要求</h4>
            <p className="text-muted-foreground">{job.requirements || "暂无"}</p>
          </div>
        </div>
        <div className="mt-4 flex justify-end">
          <Button variant="outline" onClick={onClose}>关闭</Button>
        </div>
      </div>
    </div>
  );
}

function CreateDialog({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [title, setTitle] = useState("");
  const [dept, setDept] = useState("");
  const [loc, setLoc] = useState("");
  const [desc, setDesc] = useState("");
  const [reqs, setReqs] = useState("");
  const [salary, setSalary] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [aiLoading, setAiLoading] = useState(false);

  const handleAiGenerate = () => {
    setAiLoading(true);
    setTimeout(() => {
      setDesc("负责公司核心产品的开发和维护，参与技术架构设计和优化，编写高质量代码并确保系统稳定运行。");
      setReqs("3年以上相关开发经验，精通主流编程语言，具有良好的系统设计能力和团队协作精神。");
      setAiLoading(false);
    }, 1000);
  };

  const handleSubmit = async () => {
    if (!title.trim() || !dept.trim()) return;
    setSubmitting(true);
    try {
      const payload: CreatePayload = { title: title.trim(), department: dept.trim() };
      if (loc.trim()) payload.location = loc.trim();
      if (desc.trim()) payload.description = desc.trim();
      if (reqs.trim()) payload.requirements = reqs.trim();
      if (salary.trim()) payload.salary_range = salary.trim();
      await api.post("/jobs", payload);
      onCreated();
      onClose();
    } catch {
      // backend offline — close silently
      onClose();
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={onClose}>
      <div className="w-full max-w-xl rounded-xl bg-white p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <h2 className="mb-4 text-lg font-bold">创建职位</h2>
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-xs font-medium">职位名称 *</label>
              <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="高级前端工程师" />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium">部门 *</label>
              <Input value={dept} onChange={(e) => setDept(e.target.value)} placeholder="技术部" />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-xs font-medium">地点</label>
              <Input value={loc} onChange={(e) => setLoc(e.target.value)} placeholder="北京" />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium">薪资范围</label>
              <Input value={salary} onChange={(e) => setSalary(e.target.value)} placeholder="25k-45k" />
            </div>
          </div>
          <div>
            <div className="mb-1 flex items-center justify-between">
              <label className="text-xs font-medium">职位描述</label>
              <Button variant="ghost" size="sm" onClick={handleAiGenerate} disabled={aiLoading}>
                {aiLoading ? <Loader2 className="h-3 w-3 animate-spin" /> : <Sparkles className="h-3 w-3" />}
              </Button>
            </div>
            <textarea className="w-full rounded-lg border bg-transparent p-2 text-sm outline-none focus:ring-2 focus:ring-blue-500" rows={3}
              value={desc} onChange={(e) => setDesc(e.target.value)} />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium">任职要求</label>
            <textarea className="w-full rounded-lg border bg-transparent p-2 text-sm outline-none focus:ring-2 focus:ring-blue-500" rows={3}
              value={reqs} onChange={(e) => setReqs(e.target.value)} />
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="outline" onClick={onClose}>取消</Button>
            <Button onClick={handleSubmit} disabled={submitting || !title.trim() || !dept.trim()}>
              {submitting ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : null} 创建
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function JobsPage() {
  const [search, setSearch] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [detail, setDetail] = useState<JobItem | null>(null);
  const [items, setItems] = useState<JobItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ skip: "0", limit: "50" });
      if (search.trim()) params.set("search", search);
      const res = await api.get<JobListResponse>(`/jobs?${params}`);
      const list = res.data || res;
      setItems(list.items || []);
    } catch {
      setError("后端暂未连接，请启动服务后刷新");
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [search]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const filtered = search.trim()
    ? items.filter((j) => j.title.toLowerCase().includes(search.toLowerCase()) || (j.department || "").toLowerCase().includes(search.toLowerCase()))
    : items;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">职位管理</h1>
          <p className="text-muted-foreground">管理和发布招聘职位</p>
        </div>
        <Button onClick={() => setShowCreate(true)}>
          <Plus className="mr-2 h-4 w-4" /> 创建职位
        </Button>
      </div>
      <div className="relative">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input className="pl-9" placeholder="搜索职位名称、部门..." value={search}
          onChange={(e) => setSearch(e.target.value)} />
      </div>
      {loading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Card key={i}>
              <CardHeader className="pb-2">
                <Skeleton className="h-5 w-32" />
                <Skeleton className="h-4 w-24 mt-1" />
              </CardHeader>
              <CardContent className="space-y-2">
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-4 w-20" />
                <div className="flex gap-2 mt-2">
                  <Skeleton className="h-5 w-16" />
                  <Skeleton className="h-5 w-16" />
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      ) : error ? (
        <div className="flex items-center justify-center gap-2 py-12 text-sm text-red-600">
          <AlertCircle className="h-4 w-4" /> {error}
        </div>
      ) : filtered.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12">
            <Briefcase className="mb-2 h-12 w-12 text-muted-foreground/40" />
            <p className="text-muted-foreground">暂无职位</p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((job) => {
            const sc = STATUS_MAP[job.status] || { label: job.status, color: "bg-gray-100" };
            return (
              <Card key={job.id} className="cursor-pointer transition-shadow hover:shadow-md" onClick={() => setDetail(job)}>
                <CardHeader className="pb-2">
                  <div className="flex items-start justify-between">
                    <CardTitle className="text-base">{job.title}</CardTitle>
                    <Badge className={sc.color}>{sc.label}</Badge>
                  </div>
                  <CardDescription>{job.department || "-"}</CardDescription>
                </CardHeader>
                <CardContent className="space-y-2">
                  <div className="flex items-center gap-3 text-xs text-muted-foreground">
                    {job.location && <span className="flex items-center gap-1"><MapPin className="h-3 w-3" />{job.location}</span>}
                    <span className="flex items-center gap-1"><Clock className="h-3 w-3" />{new Date(job.created_at).toLocaleDateString("zh-CN")}</span>
                  </div>
                  {job.salary_range && <span className="text-xs text-muted-foreground">{job.salary_range}</span>}
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
      {showCreate && <CreateDialog onClose={() => setShowCreate(false)} onCreated={fetchData} />}
      {detail && <DetailDialog job={detail} onClose={() => setDetail(null)} />}
    </div>
  );
}
