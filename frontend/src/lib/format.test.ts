import { describe, expect, it } from "vitest";
import type { Run } from "../types";
import { describeStat, newJobsInRun, nextSort, relativeTime, scoreBand, sourceLabel } from "./format";

describe("format helpers", () => {
  it("bands scores", () => {
    expect(scoreBand(null)).toBe("none");
    expect(scoreBand(75)).toBe("high");
    expect(scoreBand(50)).toBe("mid");
    expect(scoreBand(49)).toBe("low");
  });

  it("formats relative time", () => {
    const now = new Date("2026-11-09T12:00:00Z");
    expect(relativeTime(null, now)).toBe("—");
    expect(relativeTime("2026-11-09T11:59:40Z", now)).toBe("just now");
    expect(relativeTime("2026-11-09T11:15:00Z", now)).toBe("45m ago");
    expect(relativeTime("2026-11-09T07:00:00Z", now)).toBe("5h ago");
    expect(relativeTime("2026-11-06T12:00:00Z", now)).toBe("3d ago");
    expect(relativeTime("not a date", now)).toBe("—");
  });

  it("labels sources", () => {
    expect(sourceLabel("linkedin")).toBe("LinkedIn");
    expect(sourceLabel("scoring")).toBe("Claude scoring");
    expect(sourceLabel("other")).toBe("other");
  });

  it("toggles sort order and picks sensible defaults", () => {
    expect(nextSort({ sort: "score", order: "desc" }, "score")).toEqual({ sort: "score", order: "asc" });
    expect(nextSort({ sort: "score", order: "desc" }, "company")).toEqual({ sort: "company", order: "asc" });
    expect(nextSort({ sort: "company", order: "asc" }, "posted")).toEqual({ sort: "posted", order: "desc" });
  });

  it("describes source stats", () => {
    expect(describeStat("lever", { status: "ok", fetched: 5, relevant: 2, new: 1 })).toBe("5 fetched · 2 relevant · 1 new");
    expect(describeStat("jsearch", { status: "skipped", reason: "no API key" })).toBe("Skipped: no API key");
    expect(describeStat("ashby", { status: "error", error: "boom" })).toBe("Error: boom");
    expect(describeStat("ashby", { status: "partial", fetched: 1, relevant: 1, new: 0, warnings: ["x"] })).toBe(
      "1 fetched · 1 relevant · 0 new · 1 warning(s)",
    );
    expect(describeStat("scoring", { status: "ok", message: "Scored 3 job(s)." })).toBe("Scored 3 job(s).");
  });

  it("counts new jobs in a run", () => {
    const run: Run = {
      id: 1, started_at: "", finished_at: "", trigger: "manual", scored: 0, error: null,
      sources: { lever: { status: "ok", new: 2 }, ashby: { status: "ok", new: 3 }, scoring: { status: "ok" } },
    };
    expect(newJobsInRun(run)).toBe(5);
  });
});
