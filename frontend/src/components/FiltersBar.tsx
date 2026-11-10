import { SOURCE_LABELS } from "../lib/format";
import { STATUSES } from "../types";

export interface Filters {
  role: string;
  location: string;
  source: string;
  status: string;
  minScore: string;
  hideDone: boolean;
  includeClosed: boolean;
}

export const DEFAULT_FILTERS: Filters = {
  role: "", location: "", source: "", status: "", minScore: "", hideDone: true, includeClosed: false,
};

export function FiltersBar({ value, onChange }: { value: Filters; onChange: (filters: Filters) => void }) {
  const set = <K extends keyof Filters>(key: K, v: Filters[K]) => onChange({ ...value, [key]: v });
  return (
    <div className="filters">
      <label>
        Role
        <select value={value.role} onChange={(e) => set("role", e.target.value)}>
          <option value="">All</option>
          <option value="analyst">Analyst</option>
          <option value="scientist">Scientist</option>
          <option value="engineer">Engineer</option>
        </select>
      </label>
      <label>
        Location
        <select value={value.location} onChange={(e) => set("location", e.target.value)}>
          <option value="">All</option>
          <option value="Toronto/GTA">Toronto/GTA</option>
          <option value="Remote (Canada)">Remote (Canada)</option>
          <option value="Ottawa">Ottawa</option>
          <option value="Unknown">Unknown</option>
        </select>
      </label>
      <label>
        Source
        <select value={value.source} onChange={(e) => set("source", e.target.value)}>
          <option value="">All</option>
          {Object.entries(SOURCE_LABELS).map(([key, label]) => (
            <option key={key} value={key}>{label}</option>
          ))}
        </select>
      </label>
      <label>
        Status
        <select value={value.status} onChange={(e) => set("status", e.target.value)}>
          <option value="">All</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
      </label>
      <label>
        Min score
        <input type="number" min={0} max={100} value={value.minScore} onChange={(e) => set("minScore", e.target.value)} />
      </label>
      <label className="check">
        <input type="checkbox" checked={value.hideDone} onChange={(e) => set("hideDone", e.target.checked)} />
        Hide applied/rejected
      </label>
      <label className="check">
        <input type="checkbox" checked={value.includeClosed} onChange={(e) => set("includeClosed", e.target.checked)} />
        Show closed
      </label>
    </div>
  );
}
