import { useEffect, useState } from "react";
import { api, type JobQuery } from "../api";
import { nextSort } from "../lib/format";
import type { Counts, JobRow, SortState } from "../types";
import { DEFAULT_FILTERS, FiltersBar, type Filters } from "./FiltersBar";
import { JobPanel } from "./JobPanel";
import { JobsTable } from "./JobsTable";

export function JobsPage({ refreshKey }: { refreshKey: number }) {
  const [tab, setTab] = useState<"new" | "all">("new");
  const [sort, setSort] = useState<SortState>({ sort: "score", order: "desc" });
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS);
  const [data, setData] = useState<{ jobs: JobRow[]; counts: Counts } | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [localRefresh, setLocalRefresh] = useState(0);

  useEffect(() => {
    let cancelled = false;
    const query: JobQuery = {
      tab,
      ...sort,
      role: filters.role || undefined,
      location: filters.location || undefined,
      source: filters.source || undefined,
      status: filters.status || undefined,
      min_score: filters.minScore === "" ? undefined : Number(filters.minScore),
      hide_done: filters.hideDone,
      include_closed: filters.includeClosed,
    };
    api
      .jobs(query)
      .then((d) => {
        if (!cancelled) {
          setData(d);
          setError(null);
        }
      })
      .catch((e: Error) => {
        if (!cancelled) setError(e.message);
      });
    return () => {
      cancelled = true;
    };
  }, [tab, sort, filters, refreshKey, localRefresh]);

  const counts = data?.counts;
  return (
    <div className={selected === null ? "jobs-layout" : "jobs-layout with-panel"}>
      <section>
        <div className="tabs" role="tablist">
          <button role="tab" aria-selected={tab === "new"} className={tab === "new" ? "tab active" : "tab"} onClick={() => setTab("new")}>
            New (24h){counts && <span className="count">{counts.new_24h}</span>}
          </button>
          <button role="tab" aria-selected={tab === "all"} className={tab === "all" ? "tab active" : "tab"} onClick={() => setTab("all")}>
            All jobs{counts && <span className="count">{counts.relevant}</span>}
          </button>
        </div>
        <FiltersBar value={filters} onChange={setFilters} />
        {counts && counts.unscored > 0 && <p className="muted">{counts.unscored} job(s) waiting for a match score.</p>}
        {error && <p className="error" role="alert">{error}</p>}
        {data && (
          <JobsTable
            jobs={data.jobs}
            sort={sort}
            onSort={(key) => setSort((s) => nextSort(s, key))}
            selectedId={selected}
            onSelect={setSelected}
            emptyText={tab === "new" ? "No new jobs in the last 24 hours." : "No jobs yet. Click “Search now” to look for some."}
          />
        )}
      </section>
      {selected !== null && (
        <JobPanel key={selected} jobId={selected} onClose={() => setSelected(null)} onChanged={() => setLocalRefresh((n) => n + 1)} />
      )}
    </div>
  );
}
