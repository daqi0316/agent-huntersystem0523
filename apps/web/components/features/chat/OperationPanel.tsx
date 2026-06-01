"use client";

import { useState, useEffect } from "react";
import {
  X,
  AlertCircle,
  AlertTriangle,
  Loader2,
  CheckCircle,
  UserPlus,
  UserCheck,
  Archive,
  CalendarX,
  Briefcase,
  Pencil,
  XCircle as XCircleIcon,
  FileText,
  CalendarClock,
  ClipboardCheck,
  FileCheck,
} from "lucide-react";
import { api, withErrorHandling } from "@/lib/trpc";

interface OperationPanelProps {
  open: boolean;
  onClose: () => void;
  errorMessage?: string;
  operationType?: string;
  operationInput?: Record<string, unknown>;
  needsHuman?: boolean;
  onSuccess: (summary: string) => void;
}

// ── Operation type config ──

interface OpConfig {
  label: string;
  icon: typeof UserPlus;
  fields: { name: string; label: string; type: "text" | "email" | "number" | "textarea"; placeholder?: string; required?: boolean }[];
  apiPath: string;
  summaryFn: (values: Record<string, string>) => string;
}

const OP_CONFIGS: Record<string, OpConfig> = {
  create_candidate: {
    label: "创建候选人",
    icon: UserPlus,
    fields: [
      { name: "name", label: "姓名", type: "text", placeholder: "张三", required: true },
      { name: "email", label: "邮箱", type: "email", placeholder: "zhang@example.com", required: true },
      { name: "phone", label: "手机", type: "text", placeholder: "+86 138xxxx" },
      { name: "current_title", label: "当前职位", type: "text", placeholder: "高级前端工程师" },
      { name: "experience_years", label: "工作年限", type: "number", placeholder: "5" },
      { name: "skills", label: "技能（逗号分隔）", type: "textarea", placeholder: "React, TypeScript, Node.js" },
    ],
    apiPath: "/candidates",
    summaryFn: (v) => `候选人 ${v.name || ""} 创建成功`,
  },
  update_candidate: {
    label: "更新候选人",
    icon: UserCheck,
    fields: [
      { name: "candidate_id", label: "候选人 ID", type: "text", placeholder: "cand_xxx", required: true },
      { name: "name", label: "姓名", type: "text" },
      { name: "email", label: "邮箱", type: "email" },
      { name: "phone", label: "手机", type: "text" },
      { name: "current_title", label: "当前职位", type: "text" },
      { name: "experience_years", label: "工作年限", type: "number" },
      { name: "skills", label: "技能（逗号分隔）", type: "textarea" },
    ],
    apiPath: "/candidates",
    summaryFn: (v) => `候选人 ${v.name || v.candidate_id || ""} 更新成功`,
  },
  archive_candidate: {
    label: "归档候选人",
    icon: Archive,
    fields: [
      { name: "candidate_id", label: "候选人 ID", type: "text", placeholder: "cand_xxx", required: true },
      { name: "reason", label: "归档原因", type: "textarea", placeholder: "主动离职，已入职其他公司" },
    ],
    apiPath: "/candidates",
    summaryFn: (v) => `候选人 ${v.candidate_id || ""} 已归档`,
  },
  cancel_interview: {
    label: "取消面试",
    icon: CalendarX,
    fields: [
      { name: "interview_id", label: "面试 ID", type: "text", placeholder: "int_xxx", required: true },
      { name: "reason", label: "取消原因", type: "textarea", placeholder: "候选人时间冲突", required: true },
    ],
    apiPath: "/interviews",
    summaryFn: (v) => `面试 ${v.interview_id || ""} 已取消`,
  },
  create_job: {
    label: "创建职位",
    icon: Briefcase,
    fields: [
      { name: "title", label: "职位名称", type: "text", placeholder: "高级前端工程师", required: true },
      { name: "department", label: "部门", type: "text", placeholder: "技术部" },
      { name: "location", label: "工作地点", type: "text", placeholder: "北京" },
      { name: "description", label: "职位描述", type: "textarea", placeholder: "负责前端架构设计与开发..." },
      { name: "requirements", label: "任职要求", type: "textarea", placeholder: "5年+ React 经验..." },
      { name: "salary_range", label: "薪资范围", type: "text", placeholder: "25k-45k" },
    ],
    apiPath: "/jobs",
    summaryFn: (v) => `职位 "${v.title || ""}" 创建成功`,
  },
  update_job: {
    label: "更新职位",
    icon: Pencil,
    fields: [
      { name: "job_id", label: "职位 ID", type: "text", placeholder: "job_xxx", required: true },
      { name: "title", label: "职位名称", type: "text" },
      { name: "department", label: "部门", type: "text" },
      { name: "location", label: "工作地点", type: "text" },
      { name: "description", label: "职位描述", type: "textarea" },
      { name: "requirements", label: "任职要求", type: "textarea" },
      { name: "salary_range", label: "薪资范围", type: "text" },
      { name: "status", label: "状态", type: "text", placeholder: "active / closed / paused" },
    ],
    apiPath: "/jobs",
    summaryFn: (v) => `职位 "${v.title || v.job_id || ""}" 更新成功`,
  },
  close_job: {
    label: "关闭职位",
    icon: XCircleIcon,
    fields: [
      { name: "job_id", label: "职位 ID", type: "text", placeholder: "job_xxx", required: true },
    ],
    apiPath: "/jobs",
    summaryFn: (v) => `职位 ${v.job_id || ""} 已关闭`,
  },
  create_application: {
    label: "创建申请",
    icon: FileText,
    fields: [
      { name: "candidate_id", label: "候选人 ID", type: "text", placeholder: "cand_xxx", required: true },
      { name: "job_id", label: "职位 ID", type: "text", placeholder: "job_xxx", required: true },
      { name: "resume_url", label: "简历 URL", type: "text", placeholder: "https://..." },
    ],
    apiPath: "/applications",
    summaryFn: (v) => `申请记录已创建`,
  },
  update_application_status: {
    label: "更新申请状态",
    icon: ClipboardCheck,
    fields: [
      { name: "application_id", label: "申请 ID", type: "text", placeholder: "app_xxx", required: true },
      { name: "status", label: "新状态", type: "text", placeholder: "interview / offer / accepted / rejected", required: true },
      { name: "match_score", label: "匹配分数", type: "number", placeholder: "0-100" },
      { name: "ai_summary", label: "AI 评估摘要", type: "textarea", placeholder: "候选人匹配度较高，建议进入面试..." },
    ],
    apiPath: "/applications",
    summaryFn: (v) => `申请 ${v.application_id || ""} 状态已更新为 ${v.status || ""}`,
  },
  reschedule_interview: {
    label: "改期面试",
    icon: CalendarClock,
    fields: [
      { name: "interview_id", label: "面试 ID", type: "text", placeholder: "int_xxx", required: true },
      { name: "new_time", label: "新面试时间", type: "text", placeholder: "2025-07-01T10:00:00Z", required: true },
      { name: "reason", label: "改期原因", type: "textarea", placeholder: "候选人时间冲突" },
    ],
    apiPath: "/interviews",
    summaryFn: (v) => `面试 ${v.interview_id || ""} 已改期至 ${v.new_time || ""}`,
  },
  save_evaluation: {
    label: "保存评估",
    icon: FileCheck,
    fields: [
      { name: "interview_id", label: "面试 ID", type: "text", placeholder: "int_xxx", required: true },
      { name: "round", label: "轮次", type: "text", placeholder: "R1" },
      { name: "overall_score", label: "综合评分", type: "number", placeholder: "0-10" },
      { name: "verdict", label: "结论", type: "text", placeholder: "strong_hire / hire / consider / pass" },
      { name: "key_observations", label: "关键观察", type: "textarea", placeholder: "技术基础扎实，沟通清晰..." },
      { name: "red_flags", label: "风险标记", type: "textarea", placeholder: "离职原因待确认" },
      { name: "feedback", label: "综合反馈", type: "textarea", placeholder: "总体评价..." },
    ],
    apiPath: "/evaluations",
    summaryFn: (v) => `评估已保存，结论：${v.verdict || ""}`,
  },
};

const DEFAULT_OP_TYPE = "create_candidate";

// ── Field renderer ──

function FieldInput({
  field,
  value,
  onChange,
}: {
  field: OpConfig["fields"][0];
  value: string;
  onChange: (v: string) => void;
}) {
  const base =
    "w-full rounded-lg border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/20";

  if (field.type === "textarea") {
    return (
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={field.placeholder}
        rows={2}
        className={`${base} resize-none`}
      />
    );
  }
  return (
    <input
      type={field.type}
      name={field.name}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={field.placeholder}
      className={base}
    />
  );
}

// ── Main Panel ──

export function OperationPanel({
  open,
  onClose,
  errorMessage,
  operationType,
  operationInput,
  needsHuman,
  onSuccess,
}: OperationPanelProps) {
  const [opType, setOpType] = useState(operationType || DEFAULT_OP_TYPE);
  const [values, setValues] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  // Sync incoming operationInput into form values
  useEffect(() => {
    if (operationInput) {
      const mapped: Record<string, string> = {};
      for (const [k, v] of Object.entries(operationInput)) {
        if (v != null) mapped[k] = String(v);
      }
      setValues((prev) => ({ ...prev, ...mapped }));
    }
  }, [operationInput]);

  // Reset on open
  useEffect(() => {
    if (open) {
      setOpType(operationType || DEFAULT_OP_TYPE);
      setValues({});
      setSubmitError(null);
      setDone(false);
      setSubmitting(false);
    }
  }, [open, operationType]);

  const config = OP_CONFIGS[opType] || OP_CONFIGS[DEFAULT_OP_TYPE];
  const Icon = config.icon;

  const setValue = (name: string, v: string) =>
    setValues((prev) => ({ ...prev, [name]: v }));

  const logOperation = async (outputSummary: string) => {
    try {
      await api.post("/operations", {
        action: opType,
        agent_name: "human",
        status: "completed",
        output_summary: outputSummary,
        input_summary: config.summaryFn(values),
      });
    } catch {
      // Non-critical audit log — fire-and-forget
    }
  };

  const handleConfirm = async () => {
    setSubmitError(null);
    setSubmitting(true);

    const payload: Record<string, unknown> = { ...values };

    // archive is a DELETE / PATCH — handle separately
    if (opType === "archive_candidate") {
      const id = values["candidate_id"];
      if (!id) { setSubmitError("缺少候选人 ID"); setSubmitting(false); return; }
      try {
        await withErrorHandling(
          () => api.patch(`/candidates/${id}`, { archived: true, reason: values["reason"] || "" }),
          { error: "归档失败" }
        );
        await logOperation(config.summaryFn(values));
        setDone(true);
        setTimeout(() => {
          onSuccess(config.summaryFn(values));
          onClose();
        }, 1200);
      } catch (e: any) {
        setSubmitError(e.message || "归档失败");
      } finally {
        setSubmitting(false);
      }
      return;
    }

    if (opType === "cancel_interview") {
      const id = values["interview_id"];
      if (!id) { setSubmitError("缺少面试 ID"); setSubmitting(false); return; }
      try {
        await withErrorHandling(
          () => api.post(`/interviews/${id}/cancel`, { reason: values["reason"] || "" }),
          { error: "取消失败" }
        );
        await logOperation(config.summaryFn(values));
        setDone(true);
        setTimeout(() => {
          onSuccess(config.summaryFn(values));
          onClose();
        }, 1200);
      } catch (e: any) {
        setSubmitError(e.message || "取消失败");
      } finally {
        setSubmitting(false);
      }
      return;
    }

    if (opType === "update_job") {
      const id = values["job_id"];
      if (!id) { setSubmitError("缺少职位 ID"); setSubmitting(false); return; }
      const { job_id: _id, ...rest } = values;
      try {
        await withErrorHandling(
          () => api.patch(`/jobs/${id}`, rest),
          { error: "更新失败" }
        );
        await logOperation(config.summaryFn(values));
        setDone(true);
        setTimeout(() => {
          onSuccess(config.summaryFn(values));
          onClose();
        }, 1200);
      } catch (e: any) {
        setSubmitError(e.message || "更新失败");
      } finally {
        setSubmitting(false);
      }
      return;
    }

    if (opType === "close_job") {
      const id = values["job_id"];
      if (!id) { setSubmitError("缺少职位 ID"); setSubmitting(false); return; }
      try {
        await withErrorHandling(
          () => api.patch(`/jobs/${id}`, { status: "closed" }),
          { error: "关闭失败" }
        );
        await logOperation(config.summaryFn(values));
        setDone(true);
        setTimeout(() => {
          onSuccess(config.summaryFn(values));
          onClose();
        }, 1200);
      } catch (e: any) {
        setSubmitError(e.message || "关闭失败");
      } finally {
        setSubmitting(false);
      }
      return;
    }

    if (opType === "reschedule_interview") {
      const id = values["interview_id"];
      if (!id) { setSubmitError("缺少面试 ID"); setSubmitting(false); return; }
      try {
        await withErrorHandling(
          () => api.patch(`/interviews/${id}`, { new_time: values["new_time"] || "", reason: values["reason"] || "" }),
          { error: "改期失败" }
        );
        await logOperation(config.summaryFn(values));
        setDone(true);
        setTimeout(() => { onSuccess(config.summaryFn(values)); onClose(); }, 1200);
      } catch (e: any) { setSubmitError(e.message || "改期失败"); } finally { setSubmitting(false); }
      return;
    }

    if (opType === "save_evaluation") {
      const id = values["interview_id"];
      if (!id) { setSubmitError("缺少面试 ID"); setSubmitting(false); return; }
      try {
        const body: Record<string, unknown> = { interview_id: id };
        if (values["round"]) body["round"] = values["round"];
        if (values["overall_score"]) body["overall_score"] = parseFloat(values["overall_score"]);
        if (values["verdict"]) body["verdict"] = values["verdict"];
        if (values["key_observations"]) body["key_observations"] = values["key_observations"];
        if (values["red_flags"]) body["red_flags"] = values["red_flags"];
        if (values["feedback"]) body["feedback"] = values["feedback"];
        await withErrorHandling(() => api.post(`/evaluations`, body), { error: "保存失败" });
        await logOperation(config.summaryFn(values));
        setDone(true);
        setTimeout(() => { onSuccess(config.summaryFn(values)); onClose(); }, 1200);
      } catch (e: any) { setSubmitError(e.message || "保存失败"); } finally { setSubmitting(false); }
      return;
    }

    if (opType === "update_application_status") {
      const id = values["application_id"];
      if (!id) { setSubmitError("缺少申请 ID"); setSubmitting(false); return; }
      try {
        const body: Record<string, unknown> = {};
        if (values["status"]) body["status"] = values["status"];
        if (values["match_score"]) body["match_score"] = parseFloat(values["match_score"]);
        if (values["ai_summary"]) body["ai_summary"] = values["ai_summary"];
        await withErrorHandling(() => api.patch(`/applications/${id}`, body), { error: "更新失败" });
        await logOperation(config.summaryFn(values));
        setDone(true);
        setTimeout(() => { onSuccess(config.summaryFn(values)); onClose(); }, 1200);
      } catch (e: any) { setSubmitError(e.message || "更新失败"); } finally { setSubmitting(false); }
      return;
    }

    if (opType === "create_application") {
      try {
        await withErrorHandling(() => api.post(`/applications`, payload), { error: "创建失败" });
        await logOperation(config.summaryFn(values));
        setDone(true);
        setTimeout(() => { onSuccess(config.summaryFn(values)); onClose(); }, 1200);
      } catch (e: any) { setSubmitError(e.message || "创建失败"); } finally { setSubmitting(false); }
      return;
    }

    try {
      await withErrorHandling(
        () => api.post<{ success: boolean }>(config.apiPath, payload),
        { error: "操作失败" }
      );
      await logOperation(config.summaryFn(values));
      setDone(true);
      setTimeout(() => {
        onSuccess(config.summaryFn(values));
        onClose();
      }, 1200);
    } catch (e: any) {
      setSubmitError(e.message || "操作失败");
    } finally {
      setSubmitting(false);
    }
  };

  const requiredFilled = config.fields
    .filter((f) => f.required)
    .every((f) => values[f.name]?.trim());

  return (
    <div
      className={`fixed inset-y-0 right-0 z-50 w-80 bg-background border-l shadow-xl transform transition-transform duration-200 ${
        open ? "translate-x-0" : "translate-x-full"
      }`}
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b px-4 py-3">
        <div className="flex items-center gap-2">
          <Icon className="h-4 w-4 text-primary" />
          <h2 className="text-sm font-semibold">手动操作</h2>
        </div>
        <button
          onClick={onClose}
          className="rounded-md p-1 hover:bg-accent transition-colors"
        >
          <X className="h-4 w-4 text-muted-foreground" />
        </button>
      </div>

      <div className="overflow-y-auto h-[calc(100vh-4rem)] p-4 space-y-4">
        {/* Error context */}
        {errorMessage && (
          <div className="rounded-lg bg-destructive/10 text-destructive px-3 py-2 text-sm flex items-start gap-2">
            <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
            <span>{errorMessage}</span>
          </div>
        )}

        {/* Escalation context banner */}
        {needsHuman && (
          <div className="rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-600 dark:text-amber-400 px-3 py-2 text-sm flex items-start gap-2">
            <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
            <span>此操作需要人工介入，请填写完整信息后提交</span>
          </div>
        )}

        {/* Operation type tabs */}
        <div className="space-y-1.5">
          <p className="text-xs font-medium text-muted-foreground">操作类型</p>
          <div className="grid grid-cols-2 gap-1.5">
            {Object.entries(OP_CONFIGS).map(([key, cfg]) => {
              const Icon2 = cfg.icon;
              return (
                <button
                  key={key}
                  onClick={() => { setOpType(key); setValues({}); }}
                  className={`flex items-center gap-1.5 rounded-lg border px-2 py-1.5 text-xs transition-colors ${
                    opType === key
                      ? "border-primary bg-primary/5 text-primary"
                      : "border-border hover:bg-accent text-muted-foreground"
                  }`}
                >
                  <Icon2 className="h-3.5 w-3.5 shrink-0" />
                  <span className="truncate">{cfg.label}</span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Form fields */}
        <div className="space-y-3">
          <p className="text-xs font-medium text-muted-foreground">
            {config.label} — 填写信息
          </p>
          {config.fields.map((field) => (
            <div key={field.name} className="space-y-1">
              <label className="text-xs text-muted-foreground">
                {field.label}
                {field.required && <span className="text-destructive ml-0.5">*</span>}
              </label>
              <FieldInput
                field={field}
                value={values[field.name] || ""}
                onChange={(v) => setValue(field.name, v)}
              />
            </div>
          ))}
        </div>

        {/* Submit error */}
        {submitError && (
          <p className="text-xs text-destructive">{submitError}</p>
        )}

        {/* Success state */}
        {done && (
          <div className="flex flex-col items-center gap-2 py-4 text-center">
            <CheckCircle className="h-8 w-8 text-green-500" />
            <p className="text-sm font-medium">操作成功</p>
          </div>
        )}

        {/* Action buttons */}
        {!done && (
          <div className="flex gap-2 pt-2">
            <button
              onClick={onClose}
              className="flex-1 rounded-lg border bg-background px-3 py-2 text-sm hover:bg-accent transition-colors"
            >
              取消
            </button>
            <button
              onClick={handleConfirm}
              disabled={!requiredFilled || submitting}
              className="flex-1 flex items-center justify-center gap-1.5 rounded-lg bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50"
            >
              {submitting ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                "确认"
              )}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
