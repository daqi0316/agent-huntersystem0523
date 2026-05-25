export type JobStatus = "draft" | "active" | "paused" | "closed";
export type JobType = "full_time" | "part_time" | "contract" | "internship";

export interface JobPosition {
  id: string;
  title: string;
  department?: string;
  description?: string;
  requirements?: string;
  location?: string;
  salaryRange?: string;
  type?: JobType;
  status: JobStatus;
  createdAt: string;
  updatedAt: string;
}
