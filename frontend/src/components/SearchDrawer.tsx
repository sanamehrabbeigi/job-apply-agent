import { useEffect, useState } from "react";
import { api } from "../api";
import { describeStat, relativeTime, sourceLabel } from "../lib/format";
import type { LiveRun } from "../lib/runs";
import type { Run } from "../types";

export function SearchDrawer({ live, onClose }: { live: LiveRun | null; onClose: () => void }) {
  const [runs, setRuns] = useState<Run[]>([]);
  const finishedId = live?.finished?.id;

  useEffect(() => {
    api.runs(5).then(setRuns).catch(() => setRuns([]));
  }, [finishedId]);

  const current = live && (live.running || live.finished) ? live : null;
  return (
    <aside className="drawer" aria-label="Search progress">
      <header className="panel-head">
        <h2>Search</h2>
        <button className="icon" aria-label="Close" onClick={onClose}>×</button>
      </header>
      {current && (
        <section>
          <h3>{current.running ? "Running now" : "Latest run"}</h3>
          <ul className="source-list">
            {Object.entries(current.sources).map(([name, stat]) => (
              <li key={name} className={`stat-${stat.status}`}>
                <span>{sourceLabel(name)}</span>
                <span>{describeStat(name, stat)}</span>
              </li>
            ))}
          </ul>
          {current.running && current.messages.length > 0 && (
            <p className="muted">{current.messages[current.messages.length - 1]}</p>
          )}
          {current.scoring && current.running && <p>Scoring {current.scoring.done}/{current.scoring.total}…</p>}
          {current.finished?.sources.scoring && (
            <p className="muted">{describeStat("scoring", current.finished.sources.scoring)}</p>
          )}
          {current.finished?.error && <p className="error">{current.finished.error}</p>}
        </section>
      )}
      <section>
        <h3>Recent runs</h3>
        {runs.length === 0 && <p className="muted">No searches yet.</p>}
        <ul className="run-list">
          {runs.map((run) => (
            <li key={run.id}>
              <details>
                <summary>
                  {relativeTime(run.started_at)} · {run.trigger} · {run.scored} scored{run.error ? " · failed" : ""}
                </summary>
                <ul>
                  {Object.entries(run.sources).map(([name, stat]) => (
                    <li key={name}>
                      {sourceLabel(name)}: {describeStat(name, stat)}
                      {stat.warnings && stat.warnings.length > 0 && (
                        <ul>{stat.warnings.map((w) => <li key={w} className="muted">{w}</li>)}</ul>
                      )}
                    </li>
                  ))}
                </ul>
              </details>
            </li>
          ))}
        </ul>
      </section>
    </aside>
  );
}
