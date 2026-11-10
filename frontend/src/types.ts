export type JobStatus = "new" | "saved" | "applied" | "interview" | "offer" | "rejected";
export const STATUSES: JobStatus[] = ["new", "saved", "applied", "interview", "offer", "rejected"];
export type SortKey = "score" | "posted" | "company" | "title";
export type SortOrder = "asc" | "desc";
export interface SortState {
  sort: SortKey;
  order: SortOrder;
}

export interface JobRow {
  id: number;
  title: string;
  company: string;
  location: string;
  location_label: string;
  remote: boolean | null;
  posted_at: string | null;
  first_seen_at: string;
  last_seen_at: string;
  score: number | null;
  summary: string | null;
  seniority_fit: "under" | "fit" | "over" | null;
  status: JobStatus;
  closed: boolean;
  tailored_folder: string | null;
  sources: string[];
}

export interface JobLink {
  source: string;
  url: string;
}

export interface JobDetail extends JobRow {
  description: string;
  description_is_partial: boolean;
  reasons: string[];
  gaps: string[];
  notes: string;
  employment_type: string;
  links: JobLink[];
  tailored_files?: string[];
}

export interface Counts {
  relevant: number;
  unscored: number;
  new_24h: number;
}

export interface SourceStat {
  status: "running" | "ok" | "partial" | "error" | "skipped" | "limited";
  fetched?: number;
  relevant?: number;
  new?: number;
  warnings?: string[];
  error?: string;
  reason?: string;
  scored?: number;
  failed?: number;
  message?: string;
}

export interface Run {
  id: number;
  started_at: string;
  finished_at: string | null;
  trigger: string;
  sources: Record<string, SourceStat>;
  scored: number;
  error: string | null;
}

export interface TailorResult {
  match_score: number;
  job_title: string;
  company: string;
  missing_keywords: string[];
  files: string[];
  warnings: string[];
  folder: string;
}

export interface TailorState {
  id: string;
  job_id: number;
  state: "running" | "waiting" | "done" | "error";
  questions: string[];
  progress: string[];
  result: TailorResult | null;
  error: string | null;
}

export interface SourcePrefs {
  enabled: boolean;
  interval_hours: number;
  budget?: number;
  budget_period?: "day" | "month";
  [key: string]: unknown;
}

export interface Preferences {
  resume_path: string;
  role_terms: string[];
  locations: { cities: Record<string, string[]>; remote_canada: boolean; include_unknown: boolean };
  excluded_companies: string[];
  sources: Record<string, SourcePrefs>;
  models: { scoring: string; tailoring: string | null };
  scoring: { batch_size: number; concurrency: number };
  target_score: number;
  schedule: { enabled: boolean };
}

export type Ats = "greenhouse" | "lever" | "ashby" | "workday";

export interface Company {
  name: string;
  ats: Ats;
  enabled: boolean;
  board?: string;
  host?: string;
  tenant?: string;
  site?: string;
}

export interface Profile {
  resume: { path: string; name: string; exists: boolean };
  documents: { name: string; size: number }[];
}

export interface QuotaInfo {
  used: number;
  budget: number;
  period: string;
  resets: string;
}

export interface Status {
  resume: boolean;
  auth_warning: string | null;
  keys: { jsearch: boolean; adzuna: boolean };
  libreoffice: boolean;
  quota: Record<string, QuotaInfo>;
  search_running: boolean;
  schedule_enabled: boolean;
  last_run: Run | null;
  counts: Counts;
}

export interface AppEvent {
  type: string;
  [key: string]: unknown;
}
