export type CandidateStatus = "active" | "archived" | "blacklisted";

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
  status: CandidateStatus;
  createdAt: string;
  updatedAt: string;
}

export interface MatchResult {
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
