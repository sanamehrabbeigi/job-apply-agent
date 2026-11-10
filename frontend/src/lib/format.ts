import type { Run, SortKey, SortState, SourceStat } from "../types";

export type ScoreBand = "high" | "mid" | "low" | "none";

export function scoreBand(score: number | null): ScoreBand {
  if (score === null) return "none";
  if (score >= 75) return "high";
  if (score >= 50) return "mid";
  return "low";
}

export function relativeTime(iso: string | null, now: Date = new Date()): string {
  if (!iso) return "—";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "—";
  const minutes = Math.max(0, Math.round((now.getTime() - then) / 60000));
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  return days < 30 ? `${days}d ago` : new Date(iso).toLocaleDateString();
}

export const SOURCE_LABELS: Record<string, string> = {
  greenhouse: "Greenhouse",
  lever: "Lever",
  ashby: "Ashby",
  workday: "Workday",
  jsearch: "JSearch",
  adzuna: "Adzuna",
  linkedin: "LinkedIn",
};

export function sourceLabel(name: string): string {
  if (name === "scoring") return "Claude scoring";
  return SOURCE_LABELS[name] ?? name;
}

export function nextSort(current: SortState, clicked: SortKey): SortState {
  if (current.sort === clicked) return { sort: clicked, order: current.order === "desc" ? "asc" : "desc" };
  return { sort: clicked, order: clicked === "company" || clicked === "title" ? "asc" : "desc" };
}

export function describeStat(name: string, stat: SourceStat): string {
  if (name === "scoring") return stat.message ?? (stat.status === "running" ? "Scoring…" : "");
  switch (stat.status) {
    case "running":
      return "Searching…";
    case "skipped":
      return `Skipped: ${stat.reason ?? ""}`.trim();
    case "error":
      return `Error: ${stat.error ?? "unknown"}`;
    default: {
      const base = `${stat.fetched ?? 0} fetched · ${stat.relevant ?? 0} relevant · ${stat.new ?? 0} new`;
      return stat.warnings?.length ? `${base} · ${stat.warnings.length} warning(s)` : base;
    }
  }
}

export function newJobsInRun(run: Run): number {
  return Object.entries(run.sources)
    .filter(([name]) => name !== "scoring")
    .reduce((sum, [, stat]) => sum + (stat.new ?? 0), 0);
}
