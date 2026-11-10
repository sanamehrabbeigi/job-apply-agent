import { describe, expect, it } from "vitest";
import { applyRunEvent } from "./runs";

describe("applyRunEvent", () => {
  it("tracks a run from start to finish", () => {
    let live = applyRunEvent(null, { type: "run.started", run_id: 7, sources: ["lever", "ashby"] });
    expect(live.running).toBe(true);
    expect(live.sources.lever.status).toBe("running");
    live = applyRunEvent(live, { type: "run.source", source: "lever", stat: { status: "ok", new: 2 } });
    live = applyRunEvent(live, { type: "run.progress", message: "Wealthsimple: 3 matching" });
    live = applyRunEvent(live, { type: "run.scoring", done: 2, total: 4 });
    expect(live.sources.lever.new).toBe(2);
    expect(live.messages).toEqual(["Wealthsimple: 3 matching"]);
    expect(live.scoring).toEqual({ done: 2, total: 4 });
    const run = { id: 7, started_at: "a", finished_at: "b", trigger: "manual", sources: {}, scored: 2, error: null };
    live = applyRunEvent(live, { type: "run.finished", run });
    expect(live.running).toBe(false);
    expect(live.finished).toEqual(run);
  });

  it("ignores unrelated events", () => {
    const live = applyRunEvent(null, { type: "tailor.progress" });
    expect(live.running).toBe(false);
  });
});
