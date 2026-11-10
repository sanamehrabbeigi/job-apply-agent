import { relativeTime, sourceLabel } from "../lib/format";
import type { JobRow, SortKey, SortState } from "../types";
import { ScoreBadge } from "./ScoreBadge";

const COLUMNS: { key: SortKey | null; label: string; className?: string }[] = [
  { key: "score", label: "Match" },
  { key: "title", label: "Job" },
  { key: "company", label: "Company" },
  { key: null, label: "Location" },
  { key: "posted", label: "Posted" },
  { key: null, label: "Found on", className: "hide-narrow" },
  { key: null, label: "Status", className: "hide-narrow" },
];

interface JobsTableProps {
  jobs: JobRow[];
  sort: SortState;
  onSort: (key: SortKey) => void;
  selectedId: number | null;
  onSelect: (id: number) => void;
  emptyText: string;
}

export function JobsTable({ jobs, sort, onSort, selectedId, onSelect, emptyText }: JobsTableProps) {
  if (jobs.length === 0) return <p className="empty">{emptyText}</p>;
  return (
    <table className="jobs-table">
      <thead>
        <tr>
          {COLUMNS.map((col) => (
            <th
              key={col.label}
              className={col.className}
              aria-sort={col.key && sort.sort === col.key ? (sort.order === "asc" ? "ascending" : "descending") : undefined}
            >
              {col.key ? (
                <button className="sort" onClick={() => onSort(col.key as SortKey)}>
                  {col.label}
                  {sort.sort === col.key ? (sort.order === "asc" ? " ▲" : " ▼") : ""}
                </button>
              ) : (
                col.label
              )}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {jobs.map((job) => (
          <tr
            key={job.id}
            className={job.id === selectedId ? "selected" : undefined}
            onClick={() => onSelect(job.id)}
            onKeyDown={(e) => {
              if (e.key === "Enter") onSelect(job.id);
            }}
            tabIndex={0}
          >
            <td><ScoreBadge score={job.score} /></td>
            <td>
              <div className="job-title">{job.title}</div>
              {job.summary && <div className="job-summary">{job.summary}</div>}
            </td>
            <td>{job.company}</td>
            <td>
              {job.location_label === "Unknown" ? "Location not listed" : job.location_label || job.location}
              {job.remote && job.location_label !== "Remote (Canada)" ? " · Remote" : ""}
            </td>
            <td title={job.posted_at ?? `First seen ${job.first_seen_at}`}>{relativeTime(job.posted_at ?? job.first_seen_at)}</td>
            <td className="hide-narrow">
              {job.sources.map((s) => (
                <span key={s} className="chip">{sourceLabel(s)}</span>
              ))}
            </td>
            <td className="hide-narrow">
              <span className="status">{job.tailored_folder && job.status === "new" ? "resume ready" : job.status}</span>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
