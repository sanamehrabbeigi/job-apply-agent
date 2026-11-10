import type { AppEvent, Run, SourceStat } from "../types";

export interface LiveRun {
  runId: number | null;
  running: boolean;
  sources: Record<string, SourceStat>;
  scoring: { done: number; total: number } | null;
  messages: string[];
  finished: Run | null;
}

export const emptyRun = (): LiveRun => ({
  runId: null, running: false, sources: {}, scoring: null, messages: [], finished: null,
});

export function applyRunEvent(prev: LiveRun | null, event: AppEvent): LiveRun {
  const base = prev ?? emptyRun();
  switch (event.type) {
    case "run.started": {
      const names = (event.sources as string[] | undefined) ?? [];
      const sources = Object.fromEntries(names.map((n) => [n, { status: "running" } as SourceStat]));
      return { ...emptyRun(), runId: event.run_id as number, running: true, sources };
    }
    case "run.source":
      return { ...base, sources: { ...base.sources, [event.source as string]: event.stat as SourceStat } };
    case "run.progress":
      return { ...base, messages: [...base.messages, event.message as string].slice(-30) };
    case "run.scoring":
      return { ...base, scoring: { done: event.done as number, total: event.total as number } };
    case "run.finished":
      return { ...base, running: false, finished: event.run as Run };
    default:
      return base;
  }
}
