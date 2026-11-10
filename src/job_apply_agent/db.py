"""Local SQLite database (``data/app.db``): jobs, where each was found, search runs, quotas."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import timedelta
from pathlib import Path
from typing import Any

from .jobs import JobPosting
from .timeutil import iso, parse_datetime

SCHEMA_VERSION = 1
STALE_DAYS = 21
STATUSES = ("new", "saved", "applied", "interview", "offer", "rejected")

SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS jobs (
  id INTEGER PRIMARY KEY,
  dedupe_key TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL,
  company TEXT NOT NULL DEFAULT '',
  location TEXT NOT NULL DEFAULT '',
  location_label TEXT NOT NULL DEFAULT '',
  remote INTEGER,
  country TEXT NOT NULL DEFAULT '',
  employment_type TEXT NOT NULL DEFAULT '',
  description TEXT NOT NULL DEFAULT '',
  description_is_partial INTEGER NOT NULL DEFAULT 0,
  posted_at TEXT,
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  first_run_id INTEGER,
  relevant INTEGER NOT NULL DEFAULT 0,
  closed INTEGER NOT NULL DEFAULT 0,
  score INTEGER,
  summary TEXT,
  reasons TEXT NOT NULL DEFAULT '[]',
  gaps TEXT NOT NULL DEFAULT '[]',
  seniority_fit TEXT,
  scored_at TEXT,
  score_model TEXT,
  profile_hash TEXT,
  status TEXT NOT NULL DEFAULT 'new',
  notes TEXT NOT NULL DEFAULT '',
  tailored_folder TEXT,
  status_updated_at TEXT
);
CREATE INDEX IF NOT EXISTS jobs_listing ON jobs (relevant, closed, score);
CREATE TABLE IF NOT EXISTS job_links (
  id INTEGER PRIMARY KEY,
  job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  source TEXT NOT NULL,
  external_id TEXT NOT NULL,
  board TEXT NOT NULL DEFAULT '',
  url TEXT NOT NULL,
  canonical_url TEXT NOT NULL DEFAULT '',
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  missed_runs INTEGER NOT NULL DEFAULT 0,
  UNIQUE (source, external_id)
);
CREATE INDEX IF NOT EXISTS job_links_canonical ON job_links (canonical_url);
CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  trigger TEXT NOT NULL,
  sources TEXT NOT NULL DEFAULT '{}',
  scored INTEGER NOT NULL DEFAULT 0,
  error TEXT
);
CREATE TABLE IF NOT EXISTS quota (
  source TEXT NOT NULL,
  period TEXT NOT NULL,
  calls INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (source, period)
);
CREATE TABLE IF NOT EXISTS source_state (
  source TEXT PRIMARY KEY,
  last_attempt_at TEXT,
  last_success_at TEXT
);
"""

LIST_COLUMNS = (
    "j.id, j.title, j.company, j.location, j.location_label, j.remote, j.posted_at, j.first_seen_at, "
    "j.last_seen_at, j.score, j.summary, j.seniority_fit, j.status, j.closed, j.tailored_folder"
)
SOURCES_SUBQUERY = "(SELECT GROUP_CONCAT(DISTINCT l.source) FROM job_links l WHERE l.job_id = j.id) AS sources"
NEW_SQL = (
    "(j.posted_at >= ? OR (j.posted_at IS NULL AND j.first_seen_at >= ? "
    "AND j.first_run_id IS NOT NULL AND j.first_run_id != ?))"
)
SORTS = {
    "score": "j.score IS NULL, j.score {o}, COALESCE(j.posted_at, j.first_seen_at) DESC",
    "posted": "COALESCE(j.posted_at, j.first_seen_at) {o}",
    "company": "j.company COLLATE NOCASE {o}",
    "title": "j.title COLLATE NOCASE {o}",
}
UPDATABLE = ("status", "notes", "tailored_folder")


def _job(row: sqlite3.Row) -> dict[str, Any]:
    job = dict(row)
    if job.get("remote") is not None:
        job["remote"] = bool(job["remote"])
    for key in ("closed", "description_is_partial", "relevant"):
        if key in job:
            job[key] = bool(job[key])
    for key in ("reasons", "gaps"):
        if key in job:
            job[key] = json.loads(job[key] or "[]")
    if "sources" in job:
        job["sources"] = sorted(set(job["sources"].split(","))) if job["sources"] else []
    return job


def _run(row: sqlite3.Row) -> dict[str, Any]:
    run = dict(row)
    run["sources"] = json.loads(run["sources"] or "{}")
    return run


def _shift(now: str, **delta) -> str:
    parsed = parse_datetime(now)
    assert parsed is not None, f"bad timestamp {now!r}"
    return iso(parsed - timedelta(**delta))


class Database:
    def __init__(self, path: Path | str):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock:
            self._conn.execute("PRAGMA foreign_keys = ON")
            if self.path != ":memory:":
                self._conn.execute("PRAGMA journal_mode = WAL")
            self._conn.executescript(SCHEMA)
            if self._conn.execute("SELECT version FROM schema_version").fetchone() is None:
                self._conn.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # --- low-level helpers -------------------------------------------------------------

    def _write(self, sql: str, args: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._conn.execute(sql, args)
            self._conn.commit()
            return cur

    def _all(self, sql: str, args: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, args).fetchall()

    def _one(self, sql: str, args: tuple = ()) -> sqlite3.Row | None:
        with self._lock:
            return self._conn.execute(sql, args).fetchone()

    # --- runs and source state ---------------------------------------------------------

    def start_run(self, trigger: str, now: str) -> int:
        return int(self._write("INSERT INTO runs (started_at, trigger) VALUES (?, ?)", (now, trigger)).lastrowid)

    def finish_run(self, run_id: int, *, sources: dict, scored: int, error: str | None, now: str) -> None:
        self._write(
            "UPDATE runs SET finished_at = ?, sources = ?, scored = ?, error = ? WHERE id = ?",
            (now, json.dumps(sources), scored, error, run_id),
        )

    def get_run(self, run_id: int) -> dict[str, Any] | None:
        row = self._one("SELECT * FROM runs WHERE id = ?", (run_id,))
        return _run(row) if row else None

    def list_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        return [_run(r) for r in self._all("SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,))]

    def first_run_id(self) -> int | None:
        row = self._one("SELECT MIN(id) AS id FROM runs")
        return row["id"] if row else None

    def mark_source_attempt(self, source: str, now: str, success: bool) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO source_state (source, last_attempt_at) VALUES (?, ?) "
                "ON CONFLICT(source) DO UPDATE SET last_attempt_at = excluded.last_attempt_at",
                (source, now),
            )
            if success:
                self._conn.execute("UPDATE source_state SET last_success_at = ? WHERE source = ?", (now, source))
            self._conn.commit()

    def source_states(self) -> dict[str, dict[str, str | None]]:
        rows = self._all("SELECT source, last_attempt_at, last_success_at FROM source_state")
        return {r["source"]: {"last_attempt_at": r["last_attempt_at"], "last_success_at": r["last_success_at"]}
                for r in rows}

    # --- jobs ---------------------------------------------------------------------------

    def has_link(self, source: str, external_id: str) -> bool:
        return self._one("SELECT 1 FROM job_links WHERE source = ? AND external_id = ?",
                         (source, external_id)) is not None

    def upsert_posting(
        self,
        p: JobPosting,
        *,
        dedupe_key: str,
        canonical_url: str,
        relevant: bool,
        location_label: str,
        run_id: int | None,
        now: str,
    ) -> tuple[int, bool]:
        """Insert or update a posting. Returns (job_id, created_new_job)."""
        external_id = p.external_id or canonical_url or p.url
        with self._lock:
            c = self._conn
            row = c.execute("SELECT job_id FROM job_links WHERE source = ? AND external_id = ?",
                            (p.source, external_id)).fetchone()
            if row:
                job_id = row["job_id"]
                c.execute(
                    "UPDATE job_links SET last_seen_at = ?, missed_runs = 0, url = ? WHERE source = ? AND external_id = ?",
                    (now, p.url, p.source, external_id),
                )
                self._merge_job(job_id, p, relevant, location_label, now)
                c.commit()
                return job_id, False
            row = c.execute("SELECT id FROM jobs WHERE dedupe_key = ?", (dedupe_key,)).fetchone()
            if row is None and canonical_url:
                row = c.execute("SELECT job_id AS id FROM job_links WHERE canonical_url = ?", (canonical_url,)).fetchone()
            if row:
                job_id = row["id"]
                self._insert_link(job_id, p, external_id, canonical_url, now)
                self._merge_job(job_id, p, relevant, location_label, now)
                c.commit()
                return job_id, False
            cur = c.execute(
                "INSERT INTO jobs (dedupe_key, title, company, location, location_label, remote, country, "
                "employment_type, description, description_is_partial, posted_at, first_seen_at, last_seen_at, "
                "first_run_id, relevant) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    dedupe_key, p.title, p.company, p.location, location_label if relevant else "",
                    None if p.remote is None else int(p.remote), p.country, p.employment_type, p.description,
                    int(p.description_is_partial or not p.description), p.posted_at, now, now, run_id, int(relevant),
                ),
            )
            job_id = int(cur.lastrowid)
            self._insert_link(job_id, p, external_id, canonical_url, now)
            c.commit()
            return job_id, True

    def _insert_link(self, job_id: int, p: JobPosting, external_id: str, canonical_url: str, now: str) -> None:
        self._conn.execute(
            "INSERT INTO job_links (job_id, source, external_id, board, url, canonical_url, first_seen_at, last_seen_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (job_id, p.source, external_id, p.board, p.url, canonical_url, now, now),
        )

    def _merge_job(self, job_id: int, p: JobPosting, relevant: bool, label: str, now: str) -> None:
        old = self._conn.execute(
            "SELECT description, description_is_partial, relevant, posted_at FROM jobs WHERE id = ?", (job_id,)
        ).fetchone()
        new_full = bool(p.description) and not p.description_is_partial
        replace = bool(p.description) and (
            not old["description"]
            or (old["description_is_partial"] and new_full)
            or (new_full and len(p.description) > len(old["description"]))
        )
        fields: dict[str, Any] = {"last_seen_at": now, "closed": 0}
        if replace:
            fields["description"] = p.description
            fields["description_is_partial"] = int(not new_full)
        if not old["posted_at"] and p.posted_at:
            fields["posted_at"] = p.posted_at
        if relevant and not old["relevant"]:
            fields["relevant"] = 1
            fields["location_label"] = label
        assignments = ", ".join(f"{key} = ?" for key in fields)
        self._conn.execute(f"UPDATE jobs SET {assignments} WHERE id = ?", (*fields.values(), job_id))

    def mark_missing(self, source: str, board: str, seen_ids: set[str]) -> int:
        """Count a missed run for this board's links not in ``seen_ids``; close jobs missed twice.

        Returns the number of jobs closed by this call."""
        with self._lock:
            c = self._conn
            rows = c.execute("SELECT id, external_id FROM job_links WHERE source = ? AND board = ?",
                             (source, board)).fetchall()
            missing = [(r["id"],) for r in rows if r["external_id"] not in seen_ids]
            c.executemany("UPDATE job_links SET missed_runs = missed_runs + 1 WHERE id = ?", missing)
            cur = c.execute(
                "UPDATE jobs SET closed = 1 WHERE closed = 0 AND id IN "
                "(SELECT job_id FROM job_links WHERE source = ? AND board = ? AND missed_runs >= 2) "
                "AND NOT EXISTS (SELECT 1 FROM job_links l WHERE l.job_id = jobs.id AND l.missed_runs < 2)",
                (source, board),
            )
            c.commit()
            return cur.rowcount

    def jobs_to_score(self, profile_hash: str) -> list[dict[str, Any]]:
        rows = self._all(
            "SELECT id, title, company, location, description FROM jobs WHERE relevant = 1 AND closed = 0 "
            "AND (score IS NULL OR profile_hash IS NOT ?) ORDER BY first_seen_at DESC, id DESC",
            (profile_hash,),
        )
        return [dict(r) for r in rows]

    def save_score(self, job_id: int, *, score: int, summary: str, reasons: list[str], gaps: list[str],
                   seniority_fit: str, model: str, profile_hash: str, now: str) -> None:
        self._write(
            "UPDATE jobs SET score = ?, summary = ?, reasons = ?, gaps = ?, seniority_fit = ?, score_model = ?, "
            "profile_hash = ?, scored_at = ? WHERE id = ?",
            (score, summary, json.dumps(reasons), json.dumps(gaps), seniority_fit, model, profile_hash, now, job_id),
        )

    def list_jobs(
        self,
        *,
        now: str,
        tab: str = "all",
        sort: str = "score",
        order: str = "desc",
        role: str | None = None,
        location: str | None = None,
        source: str | None = None,
        status: str | None = None,
        min_score: int | None = None,
        include_closed: bool = False,
        hide_done: bool = False,
    ) -> list[dict[str, Any]]:
        where = ["j.relevant = 1"]
        args: list[Any] = []
        if not include_closed:
            where.append("j.closed = 0 AND j.last_seen_at >= ?")
            args.append(_shift(now, days=STALE_DAYS))
        if tab == "new":
            cutoff = _shift(now, hours=24)
            where.append(NEW_SQL)
            args += [cutoff, cutoff, self.first_run_id() or -1]
        if role:
            where.append("LOWER(j.title) LIKE ?")
            args.append(f"%{role.lower()}%")
        if location:
            where.append("j.location_label = ?")
            args.append(location)
        if source:
            where.append("EXISTS (SELECT 1 FROM job_links l WHERE l.job_id = j.id AND l.source = ?)")
            args.append(source)
        if status:
            where.append("j.status = ?")
            args.append(status)
        if hide_done:
            where.append("j.status NOT IN ('applied', 'rejected')")
        if min_score is not None:
            where.append("j.score >= ?")
            args.append(min_score)
        direction = "ASC" if order == "asc" else "DESC"
        order_by = SORTS.get(sort, SORTS["score"]).format(o=direction)
        sql = (f"SELECT {LIST_COLUMNS}, {SOURCES_SUBQUERY} FROM jobs j WHERE {' AND '.join(where)} "
               f"ORDER BY {order_by} LIMIT 1000")
        return [_job(r) for r in self._all(sql, tuple(args))]

    def get_job(self, job_id: int) -> dict[str, Any] | None:
        row = self._one(f"SELECT j.*, {SOURCES_SUBQUERY} FROM jobs j WHERE j.id = ?", (job_id,))
        if row is None:
            return None
        job = _job(row)
        job["links"] = [
            {"source": r["source"], "url": r["url"]}
            for r in self._all("SELECT source, url FROM job_links WHERE job_id = ? ORDER BY id", (job_id,))
        ]
        return job

    def update_job(self, job_id: int, **fields: Any) -> dict[str, Any] | None:
        unknown = set(fields) - set(UPDATABLE)
        if unknown:
            raise ValueError(f"Can't update: {', '.join(sorted(unknown))}")
        if "status" in fields and fields["status"] not in STATUSES:
            raise ValueError(f"Unknown status {fields['status']!r}")
        if self._one("SELECT 1 FROM jobs WHERE id = ?", (job_id,)) is None:
            return None
        if fields:
            assignments = ", ".join(f"{key} = ?" for key in fields)
            self._write(f"UPDATE jobs SET {assignments} WHERE id = ?", (*fields.values(), job_id))
        return self.get_job(job_id)

    def all_jobs_for_refilter(self) -> list[dict[str, Any]]:
        rows = self._all("SELECT id, title, company, location, remote, country, relevant, location_label FROM jobs")
        return [_job(r) for r in rows]

    def set_relevance(self, job_id: int, relevant: bool, location_label: str) -> None:
        self._write("UPDATE jobs SET relevant = ?, location_label = ? WHERE id = ?",
                    (int(relevant), location_label if relevant else "", job_id))

    def counts(self, now: str) -> dict[str, int]:
        visible = "j.relevant = 1 AND j.closed = 0 AND j.last_seen_at >= ?"
        stale = _shift(now, days=STALE_DAYS)
        cutoff = _shift(now, hours=24)
        relevant = self._one(f"SELECT COUNT(*) AS n FROM jobs j WHERE {visible}", (stale,))["n"]
        unscored = self._one(f"SELECT COUNT(*) AS n FROM jobs j WHERE {visible} AND j.score IS NULL", (stale,))["n"]
        new_24h = self._one(f"SELECT COUNT(*) AS n FROM jobs j WHERE {visible} AND {NEW_SQL}",
                            (stale, cutoff, cutoff, self.first_run_id() or -1))["n"]
        return {"relevant": relevant, "unscored": unscored, "new_24h": new_24h}

    # --- quota --------------------------------------------------------------------------

    def quota_used(self, source: str, period: str) -> int:
        row = self._one("SELECT calls FROM quota WHERE source = ? AND period = ?", (source, period))
        return int(row["calls"]) if row else 0

    def quota_add(self, source: str, period: str, n: int = 1) -> None:
        self._write(
            "INSERT INTO quota (source, period, calls) VALUES (?, ?, ?) "
            "ON CONFLICT(source, period) DO UPDATE SET calls = calls + excluded.calls",
            (source, period, n),
        )
