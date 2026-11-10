import { newJobsInRun, relativeTime } from "../lib/format";
import type { LiveRun } from "../lib/runs";
import type { Status } from "../types";

export type Page = "jobs" | "settings";

interface TopBarProps {
  page: Page;
  onNavigate: (page: Page) => void;
  status: Status | null;
  live: LiveRun | null;
  onSearch: () => void;
  onShowRuns: () => void;
}

export function TopBar({ page, onNavigate, status, live, onSearch, onShowRuns }: TopBarProps) {
  const running = Boolean(live?.running || status?.search_running);
  const last = live?.finished ?? status?.last_run ?? null;
  const summary = running
    ? "Searching…"
    : last
      ? `Last run ${relativeTime(last.finished_at ?? last.started_at)} · ${newJobsInRun(last)} new`
      : "No searches yet";
  return (
    <header className="topbar">
      <div className="brand">Job Agent</div>
      <nav className="nav">
        <button className={page === "jobs" ? "nav-link active" : "nav-link"} onClick={() => onNavigate("jobs")}>
          Jobs
        </button>
        <button className={page === "settings" ? "nav-link active" : "nav-link"} onClick={() => onNavigate("settings")}>
          Settings
        </button>
      </nav>
      <div className="topbar-right">
        <button className="link-button" onClick={onShowRuns}>{summary}</button>
        <button className="primary" onClick={onSearch} disabled={running}>
          {running ? "Searching…" : "Search now"}
        </button>
      </div>
    </header>
  );
}

interface SetupBannersProps {
  status: Status;
  onOpenSettings: () => void;
  onRescore: () => void;
}

export function SetupBanners({ status, onOpenSettings, onRescore }: SetupBannersProps) {
  return (
    <>
      {!status.resume && (
        <div className="banner">
          Add your master resume so jobs get match scores.{" "}
          <button className="link-button" onClick={onOpenSettings}>Open Settings</button>
        </div>
      )}
      {status.auth_warning && <div className="banner banner-warn">{status.auth_warning}</div>}
      {status.outdated_scores > 0 && !status.search_running && (
        <div className="banner">
          {status.outdated_scores} job(s) were scored against an older version of your resume or profile.{" "}
          <button className="link-button" onClick={onRescore}>Re-score them</button>
          <span className="muted"> (uses Claude: about one request per 5 jobs)</span>
        </div>
      )}
    </>
  );
}
