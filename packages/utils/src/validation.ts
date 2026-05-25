import { z } from "zod";

export const EmailSchema = z.string().email("请输入有效的邮箱地址");

export const PaginationSchema = z.object({
  page: z.coerce.number().int().min(1).default(1),
  perPage: z.coerce.number().int().min(1).max(100).default(20),
});

export const CandidateCreateSchema = z.object({
  name: z.string().min(1, "姓名不能为空").max(100),
  email: EmailSchema,
  phone: z.string().optional(),
  summary: z.string().optional(),
  skills: z.array(z.string()).default([]),
  experienceYears: z.number().int().min(0).optional(),
  education: z.string().optional(),
  currentCompany: z.string().optional(),
  currentTitle: z.string().optional(),
});

export const JobCreateSchema = z.object({
  title: z.string().min(1, "职位名称不能为空").max(200),
  department: z.string().optional(),
  description: z.string().optional(),
  requirements: z.string().optional(),
  location: z.string().optional(),
  salaryRange: z.string().optional(),
});
