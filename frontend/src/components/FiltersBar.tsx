import { useEffect, useState } from "react";
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
  search: string;
  postedWithin: string; // days, "" = any time
}

export const DEFAULT_FILTERS: Filters = {
  role: "", location: "", source: "", status: "", minScore: "", hideDone: true, includeClosed: false,
  search: "", postedWithin: "",
};

/** Search box that only updates the list after typing pauses, so each keystroke isn't a request. */
function SearchBox({ value, onChange }: { value: string; onChange: (text: string) => void }) {
  const [text, setText] = useState(value);
  useEffect(() => setText(value), [value]);
  useEffect(() => {
    if (text === value) return;
    const timer = window.setTimeout(() => onChange(text), 300);
    return () => window.clearTimeout(timer);
  }, [text, value, onChange]);
  return (
    <label className="search">
      Search
      <input type="search" placeholder="e.g. Power BI, fintech, hybrid" value={text} onChange={(e) => setText(e.target.value)} />
    </label>
  );
}

export function FiltersBar({ value, onChange }: { value: Filters; onChange: (filters: Filters) => void }) {
  const set = <K extends keyof Filters>(key: K, v: Filters[K]) => onChange({ ...value, [key]: v });
  return (
    <div className="filters">
      <SearchBox value={value.search} onChange={(text) => onChange({ ...value, search: text })} />
      <label>
        Posted within
        <select value={value.postedWithin} onChange={(e) => set("postedWithin", e.target.value)}>
          <option value="">Any time</option>
          <option value="1">24 hours</option>
          <option value="3">3 days</option>
          <option value="7">7 days</option>
          <option value="30">30 days</option>
        </select>
      </label>
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
