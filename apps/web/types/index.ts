export interface Candidate {
  id: string;
  name: string;
  email: string;
  phone?: string;
  summary?: string;
  skills: string[];
  experienceYears?: number;
  education?: string;
  currentCompany?: string;
  currentTitle?: string;
  status: "active" | "archived" | "blacklisted";
  createdAt: string;
  updatedAt: string;
}

export interface Job {
  id: string;
  title: string;
  department?: string;
  description?: string;
  requirements?: string;
  location?: string;
  salaryRange?: string;
  status: "draft" | "active" | "paused" | "closed";
  createdAt: string;
  updatedAt: string;
}

export interface Application {
  id: string;
  candidateId: string;
  jobId: string;
  status: "pending" | "screening" | "interview" | "offer" | "rejected";
  matchScore?: number;
  aiSummary?: string;
  createdAt: string;
  updatedAt: string;
}

export interface PipelineProgress {
  pipelineId: string;
  status: "running" | "completed" | "failed";
  currentStep: string;
  progress: number;
  result?: ScreeningResult;
  error?: string;
}

export interface ScreeningResult {
  applicationId: string;
  overallScore: number;
  dimensions: MatchDimension[];
  summary: string;
  passed: boolean;
}

export interface MatchDimension {
  name: string;
  score: number;
  detail?: string;
}
