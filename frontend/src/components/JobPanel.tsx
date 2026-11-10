import { useEffect, useState } from "react";
import { api } from "../api";
import { sourceLabel } from "../lib/format";
import { STATUSES, type JobDetail, type JobStatus } from "../types";
import { ScoreBadge } from "./ScoreBadge";
import { TailorPanel } from "./TailorPanel";

interface JobPanelProps {
  jobId: number;
  onClose: () => void;
  onChanged: () => void;
}

export function JobPanel({ jobId, onClose, onChanged }: JobPanelProps) {
  const [job, setJob] = useState<JobDetail | null>(null);
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .job(jobId)
      .then((j) => {
        setJob(j);
        setNotes(j.notes);
      })
      .catch((e: Error) => setError(e.message));
  }, [jobId]);

  const update = async (patch: { status?: JobStatus; notes?: string }) => {
    try {
      setJob(await api.updateJob(jobId, patch));
      onChanged();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  if (!job) {
    return (
      <aside className="panel">
        <button className="icon" aria-label="Close" onClick={onClose}>×</button>
        <p className={error ? "error" : "muted"}>{error ?? "Loading…"}</p>
      </aside>
    );
  }

  return (
    <aside className="panel" aria-label="Job details">
      <header className="panel-head">
        <div>
          <h2>{job.title}</h2>
          <p>{job.company} · {job.location || "Location not listed"}{job.employment_type ? ` · ${job.employment_type}` : ""}</p>
        </div>
        <button className="icon" aria-label="Close" onClick={onClose}>×</button>
      </header>
      {error && <p className="error" role="alert">{error}</p>}

      <div className="panel-score">
        <ScoreBadge score={job.score} />
        <div>
          {job.summary && <p>{job.summary}</p>}
          {job.seniority_fit && job.seniority_fit !== "fit" && (
            <p className="muted">
              Seniority: this job looks {job.seniority_fit === "under" ? "more senior" : "more junior"} than your background.
            </p>
          )}
        </div>
      </div>
      {job.reasons.length > 0 && (
        <>
          <h3>Why you fit</h3>
          <ul>{job.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
        </>
      )}
      {job.gaps.length > 0 && (
        <>
          <h3>Gaps</h3>
          <ul>{job.gaps.map((g) => <li key={g}>{g}</li>)}</ul>
        </>
      )}

      <div className="panel-row">
        <label>
          Status{" "}
          <select value={job.status} onChange={(e) => void update({ status: e.target.value as JobStatus })}>
            {STATUSES.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </label>
        <span className="links">
          {job.links.filter((link, i, all) => all.findIndex((l) => l.source === link.source) === i).map((link) => (
            <a key={link.url} href={link.url} target="_blank" rel="noreferrer">
              Open on {sourceLabel(link.source)}
            </a>
          ))}
        </span>
      </div>
      <label className="notes">
        Notes
        <textarea
          rows={3}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          onBlur={() => {
            if (notes !== job.notes) void update({ notes });
          }}
        />
      </label>

      <TailorPanel jobId={job.id} onDone={onChanged} />

      <h3>
        Description
        {job.description_is_partial && <span className="muted"> (preview; the full posting is fetched when tailoring)</span>}
      </h3>
      <div className="description">{job.description || "No description available."}</div>
    </aside>
  );
}
