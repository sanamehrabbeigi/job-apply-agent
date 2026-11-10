import { useEffect, useState, type ChangeEvent } from "react";
import { api } from "../api";
import { SOURCE_LABELS } from "../lib/format";
import type { Ats, Company, Preferences, Profile, SourcePrefs, Status } from "../types";

const ATS_OPTIONS: Ats[] = ["greenhouse", "lever", "ashby", "workday"];
const toLines = (items: string[]) => items.join("\n");
const fromLines = (text: string) => text.split("\n").map((s) => s.trim()).filter(Boolean);

interface LinesFieldProps {
  label: string;
  value: string[];
  onChange: (value: string[]) => void;
  rows?: number;
  hint?: string;
}

function LinesField({ label, value, onChange, rows = 4, hint }: LinesFieldProps) {
  const [text, setText] = useState(toLines(value));
  useEffect(() => setText(toLines(value)), [value]);
  return (
    <label className="field">
      {label}
      {hint && <span className="hint">{hint}</span>}
      <textarea rows={rows} value={text} onChange={(e) => setText(e.target.value)} onBlur={() => onChange(fromLines(text))} />
    </label>
  );
}

export function SettingsPage({ onSaved }: { onSaved: () => void }) {
  const [prefs, setPrefs] = useState<Preferences | null>(null);
  const [companies, setCompanies] = useState<Company[]>([]);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [status, setStatus] = useState<Status | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tests, setTests] = useState<Record<number, string>>({});

  useEffect(() => {
    Promise.all([api.preferences(), api.companies(), api.profile(), api.status()])
      .then(([p, c, pr, s]) => {
        setPrefs(p);
        setCompanies(c);
        setProfile(pr);
        setStatus(s);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  if (!prefs || !profile) return <p className={error ? "error" : "muted"}>{error ?? "Loading settings…"}</p>;

  const act = async (action: () => Promise<string>) => {
    setError(null);
    setMessage(null);
    try {
      setMessage(await action());
      onSaved();
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const update = (patch: Partial<Preferences>) => setPrefs({ ...prefs, ...patch });
  const updateSource = (name: string, patch: Partial<SourcePrefs>) =>
    setPrefs({ ...prefs, sources: { ...prefs.sources, [name]: { ...prefs.sources[name], ...patch } } });
  const updateCompany = (index: number, patch: Partial<Company>) =>
    setCompanies(companies.map((c, i) => (i === index ? { ...c, ...patch } : c)));
  const testCompany = async (index: number) => {
    setTests((t) => ({ ...t, [index]: "Testing…" }));
    try {
      const result = await api.testCompany(companies[index]);
      setTests((t) => ({ ...t, [index]: result.ok ? `OK: ${result.jobs} open jobs` : `Failed: ${result.error}` }));
    } catch (e) {
      setTests((t) => ({ ...t, [index]: `Failed: ${(e as Error).message}` }));
    }
  };
  const onFile = (handler: (file: File) => Promise<string>) => (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (file) void act(() => handler(file));
  };

  return (
    <div className="settings">
      {message && <div className="banner">{message}</div>}
      {error && <div className="banner banner-error" role="alert">{error}</div>}

      <section className="card">
        <h2>Resume and profile</h2>
        <p>
          Master resume: {profile.resume.exists ? <strong>{profile.resume.name}</strong> : <em>not added yet</em>}
        </p>
        <label className="field">
          Upload resume (.docx, .pdf, .md or .txt)
          <input type="file" accept=".docx,.pdf,.md,.txt" onChange={onFile(async (file) => {
            setProfile(await api.uploadResume(file));
            setPrefs(await api.preferences());
            return "Resume saved. Jobs will be re-scored on the next search.";
          })} />
        </label>
        <h3>Profile documents</h3>
        <p className="hint">Extra details the agent may use: full work history, projects, certificates.</p>
        <ul className="doc-list">
          {profile.documents.map((doc) => (
            <li key={doc.name}>
              {doc.name} <span className="muted">({Math.max(1, Math.ceil(doc.size / 1024))} KB)</span>
              {doc.name !== "answers.md" && (
                <button className="link-button" onClick={() => void act(async () => {
                  setProfile(await api.deleteDocument(doc.name));
                  return `Removed ${doc.name}.`;
                })}>Remove</button>
              )}
            </li>
          ))}
        </ul>
        <label className="field">
          Add a document
          <input type="file" accept=".docx,.pdf,.md,.markdown,.txt" onChange={onFile(async (file) => {
            setProfile(await api.uploadDocument(file));
            return `Added ${file.name}. Jobs will be re-scored on the next search.`;
          })} />
        </label>
      </section>

      <section className="card">
        <h2>What to look for</h2>
        <LinesField label="Job title terms (one per line)" hint="A job is considered when its title contains one of these."
          value={prefs.role_terms} rows={8} onChange={(v) => update({ role_terms: v })} />
        {Object.entries(prefs.locations.cities).map(([label, cities]) => (
          <LinesField key={label} label={`${label}: city names`} value={cities} rows={3}
            onChange={(v) => update({ locations: { ...prefs.locations, cities: { ...prefs.locations.cities, [label]: v } } })} />
        ))}
        <label className="check">
          <input type="checkbox" checked={prefs.locations.remote_canada}
            onChange={(e) => update({ locations: { ...prefs.locations, remote_canada: e.target.checked } })} />
          Include remote jobs open to Canada
        </label>
        <label className="check">
          <input type="checkbox" checked={prefs.locations.include_unknown}
            onChange={(e) => update({ locations: { ...prefs.locations, include_unknown: e.target.checked } })} />
          Include jobs with no location listed
        </label>
        <LinesField label="Companies to exclude (one per line)" value={prefs.excluded_companies} rows={3}
          onChange={(v) => update({ excluded_companies: v })} />
      </section>

      <section className="card">
        <h2>Sources and schedule</h2>
        <label className="check">
          <input type="checkbox" checked={prefs.schedule.enabled} onChange={(e) => update({ schedule: { enabled: e.target.checked } })} />
          Search automatically while the app is open
        </label>
        <table className="sources-table">
          <thead>
            <tr><th>Source</th><th>On</th><th>Every (hours)</th><th>Free quota</th></tr>
          </thead>
          <tbody>
            {Object.entries(prefs.sources).map(([name, cfg]) => {
              const quota = status?.quota[name];
              const missingKey = (name === "jsearch" && !status?.keys.jsearch) || (name === "adzuna" && !status?.keys.adzuna);
              return (
                <tr key={name}>
                  <td>
                    {SOURCE_LABELS[name] ?? name}
                    {missingKey && <span className="hint"> · no API key in data/.env</span>}
                  </td>
                  <td>
                    <input type="checkbox" aria-label={`Enable ${name}`} checked={cfg.enabled}
                      onChange={(e) => updateSource(name, { enabled: e.target.checked })} />
                  </td>
                  <td>
                    <input type="number" min={0.25} step={0.25} value={cfg.interval_hours}
                      onChange={(e) => updateSource(name, { interval_hours: Number(e.target.value) })} />
                  </td>
                  <td>{quota ? `${quota.used}/${quota.budget} this ${quota.period} (resets ${quota.resets})` : "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>

      <section className="card">
        <h2>Claude</h2>
        <label className="field">
          Scoring model
          <input value={prefs.models.scoring} onChange={(e) => update({ models: { ...prefs.models, scoring: e.target.value } })} />
        </label>
        <label className="field">
          Tailoring model (leave empty for your account default)
          <input value={prefs.models.tailoring ?? ""}
            onChange={(e) => update({ models: { ...prefs.models, tailoring: e.target.value || null } })} />
        </label>
        <label className="field">
          Target match score for tailoring
          <input type="number" min={0} max={100} value={prefs.target_score}
            onChange={(e) => update({ target_score: Number(e.target.value) })} />
        </label>
        {status && !status.libreoffice && (
          <p className="hint">LibreOffice isn't installed, so tailored resumes are saved as Word and Markdown (no PDF).</p>
        )}
      </section>

      <div className="row">
        <button className="primary" onClick={() => void act(async () => {
          const result = await api.savePreferences(prefs);
          setPrefs(result.preferences);
          return result.refiltered ? `Saved. ${result.refiltered} job(s) re-checked against the new filters.` : "Saved.";
        })}>Save settings</button>
      </div>

      <section className="card">
        <h2>Company career sites</h2>
        <table className="companies-table">
          <thead>
            <tr><th>Name</th><th>System</th><th>Board / Workday site</th><th>On</th><th></th></tr>
          </thead>
          <tbody>
            {companies.map((c, i) => (
              <tr key={i}>
                <td><input aria-label="Company name" value={c.name} onChange={(e) => updateCompany(i, { name: e.target.value })} /></td>
                <td>
                  <select aria-label="Hiring system" value={c.ats} onChange={(e) => updateCompany(i, { ats: e.target.value as Ats })}>
                    {ATS_OPTIONS.map((a) => <option key={a} value={a}>{SOURCE_LABELS[a]}</option>)}
                  </select>
                </td>
                <td>
                  {c.ats === "workday" ? (
                    <div className="workday-fields">
                      <input aria-label="Workday host" placeholder="td.wd3.myworkdayjobs.com" value={c.host ?? ""} onChange={(e) => updateCompany(i, { host: e.target.value })} />
                      <input aria-label="Workday tenant" placeholder="td" value={c.tenant ?? ""} onChange={(e) => updateCompany(i, { tenant: e.target.value })} />
                      <input aria-label="Workday site" placeholder="TD_Bank_Careers" value={c.site ?? ""} onChange={(e) => updateCompany(i, { site: e.target.value })} />
                    </div>
                  ) : (
                    <input aria-label="Board name" value={c.board ?? ""} onChange={(e) => updateCompany(i, { board: e.target.value })} />
                  )}
                </td>
                <td>
                  <input type="checkbox" aria-label={`Enable ${c.name}`} checked={c.enabled} onChange={(e) => updateCompany(i, { enabled: e.target.checked })} />
                </td>
                <td>
                  <div className="row">
                    <button onClick={() => void testCompany(i)}>Test</button>
                    <button className="link-button" onClick={() => setCompanies(companies.filter((_, j) => j !== i))}>Remove</button>
                    {tests[i] && <span className="hint">{tests[i]}</span>}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="row">
          <button onClick={() => setCompanies([...companies, { name: "", ats: "greenhouse", board: "", enabled: true }])}>Add company</button>
          <button className="primary" onClick={() => void act(async () => {
            setCompanies(await api.saveCompanies(companies));
            return "Companies saved.";
          })}>Save companies</button>
        </div>
      </section>
    </div>
  );
}
