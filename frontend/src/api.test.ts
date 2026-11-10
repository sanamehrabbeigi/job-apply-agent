import { describe, expect, it } from "vitest";
import { fileUrl, jobsQueryString } from "./api";

describe("api helpers", () => {
  it("builds job queries without empty values", () => {
    const qs = jobsQueryString({ tab: "new", sort: "score", order: "desc", role: undefined, min_score: 70, hide_done: true, include_closed: false });
    expect(qs).toBe("tab=new&sort=score&order=desc&min_score=70&hide_done=true");
  });

  it("encodes file paths segment by segment", () => {
    expect(fileUrl("2026-11-09_Acme/Jane Doe.pdf")).toBe("/api/files/2026-11-09_Acme/Jane%20Doe.pdf");
  });
});
