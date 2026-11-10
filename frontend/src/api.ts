import type {
  Company, Counts, JobDetail, JobRow, JobStatus, Preferences, Profile, Run, SortKey, SortOrder, Status, TailorState,
} from "./types";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) {
    let message = response.statusText || `HTTP ${response.status}`;
    try {
      const body = await response.json();
      message = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
    } catch {
      // not JSON; keep the status text
    }
    throw new ApiError(response.status, message);
  }
  return (await response.json()) as T;
}

const sendJson = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

function upload(path: string, file: File): Promise<Profile> {
  const form = new FormData();
  form.append("file", file);
  return request<Profile>(path, { method: "POST", body: form });
}

export interface JobQuery {
  tab: "new" | "all";
  sort: SortKey;
  order: SortOrder;
  role?: string;
  location?: string;
  source?: string;
  status?: string;
  min_score?: number;
  hide_done?: boolean;
  include_closed?: boolean;
}

export function jobsQueryString(query: JobQuery): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === "" || value === false) continue;
    params.set(key, String(value));
  }
  return params.toString();
}

export const fileUrl = (path: string) => `/api/files/${path.split("/").map(encodeURIComponent).join("/")}`;

export const api = {
  jobs: (query: JobQuery) => request<{ jobs: JobRow[]; counts: Counts }>(`/api/jobs?${jobsQueryString(query)}`),
  job: (id: number) => request<JobDetail>(`/api/jobs/${id}`),
  updateJob: (id: number, patch: { status?: JobStatus; notes?: string }) =>
    request<JobDetail>(`/api/jobs/${id}`, sendJson("PATCH", patch)),
  startSearch: (sources?: string[]) =>
    request<{ started: boolean }>("/api/search", sendJson("POST", { sources: sources ?? null })),
  runs: (limit = 10) => request<Run[]>(`/api/runs?limit=${limit}`),
  status: () => request<Status>("/api/status"),
  startTailor: (jobId: number) => request<TailorState>(`/api/jobs/${jobId}/tailor`, { method: "POST" }),
  tailor: (id: string) => request<TailorState>(`/api/tailor/${id}`),
  answer: (id: string, answers: { question: string; answer: string }[]) =>
    request<TailorState>(`/api/tailor/${id}/answers`, sendJson("POST", { answers })),
  preferences: () => request<Preferences>("/api/preferences"),
  savePreferences: (prefs: Preferences) =>
    request<{ preferences: Preferences; refiltered: number }>("/api/preferences", sendJson("PUT", prefs)),
  companies: () => request<Company[]>("/api/companies"),
  saveCompanies: (companies: Company[]) => request<Company[]>("/api/companies", sendJson("PUT", companies)),
  testCompany: (company: Company) =>
    request<{ ok: boolean; jobs?: number; error?: string }>("/api/companies/test", sendJson("POST", company)),
  profile: () => request<Profile>("/api/profile"),
  uploadResume: (file: File) => upload("/api/profile/resume", file),
  uploadDocument: (file: File) => upload("/api/profile/documents", file),
  deleteDocument: (name: string) =>
    request<Profile>(`/api/profile/documents/${encodeURIComponent(name)}`, { method: "DELETE" }),
};
