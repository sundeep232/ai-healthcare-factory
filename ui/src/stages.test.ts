import { describe, expect, it } from "vitest";
import { ApiError, errorMessage } from "./api";
import { isBusy, primaryAction, secondaryActions, stages } from "./stages";
import type { Certification, Demo, DemoStatus } from "./types";

const cert = (passed: boolean): Certification => ({
  passed,
  certified_at: "2026-10-24T00:00:00Z",
  blueprint_version: 1,
  data_seed: 3,
  summary: { pass: 1, warn: 0, fail: passed ? 0 : 1, skip: 0 },
  checks: [],
});

function demo(over: Partial<Demo> = {}): Demo {
  return {
    demo_id: "d1",
    status: "planned",
    intent: "x",
    requirements: null,
    blueprint: null,
    instance_dir: null,
    plan: null,
    outputs: {},
    data: null,
    certification: null,
    publication: null,
    failed_stage: null,
    error: null,
    events: [],
    created_at: "",
    updated_at: "",
    ...over,
  };
}

const seed = { seed: 3, as_of: "2026-10-24", targets: [], total_rows: 10, warnings: [], seeded_at: "" };
const live = { web_url: "https://x" };
const pub = { token: "t", published_at: "", share_path: "/share/t", share_url: "/share/t" };
const states = (d: Demo) => Object.fromEntries(stages(d).map((s) => [s.id, s.state]));

describe("primaryAction walks the happy path one step at a time", () => {
  const steps: [string, Demo, string | null][] = [
    ["planned", demo(), "generate"],
    ["generated", demo({ status: "generated", instance_dir: "i" }), "deploy"],
    ["deployed", demo({ status: "deployed", instance_dir: "i", outputs: live }), "seed"],
    ["seeded", demo({ status: "deployed", instance_dir: "i", outputs: live, data: seed }), "certify"],
    [
      "failed cert",
      demo({ status: "deployed", instance_dir: "i", outputs: live, data: seed, certification: cert(false) }),
      "certify",
    ],
    [
      "certified",
      demo({ status: "deployed", instance_dir: "i", outputs: live, data: seed, certification: cert(true) }),
      "publish",
    ],
    [
      "published",
      demo({
        status: "deployed",
        instance_dir: "i",
        outputs: live,
        data: seed,
        certification: cert(true),
        publication: pub,
      }),
      null,
    ],
  ];
  it.each(steps)("%s", (_name, d, expected) => {
    expect(primaryAction(d)?.key ?? null).toBe(expected);
  });
});

describe("busy and terminal states offer nothing", () => {
  it.each(["deploying", "seeding", "certifying", "destroying", "destroyed"] as DemoStatus[])("%s", (status) => {
    const d = demo({ status, instance_dir: "i", outputs: live });
    expect(primaryAction(d)).toBeNull();
    expect(secondaryActions(d)).toEqual([]);
  });
  it("knows which statuses are busy", () => {
    expect(isBusy("seeding")).toBe(true);
    expect(isBusy("deployed")).toBe(false);
  });
});

describe("failures offer the right retry", () => {
  const failed = (stage: string) => demo({ status: "failed", failed_stage: stage, instance_dir: "i", outputs: live });
  it("deploy", () => expect(primaryAction(failed("deploy"))).toMatchObject({ key: "deploy", label: "Retry deploy" }));
  it("data", () => expect(primaryAction(failed("data"))?.key).toBe("seed"));
  it("destroy retry is not offered twice", () => {
    const d = failed("destroy");
    expect(primaryAction(d)?.key).toBe("destroy");
    expect(secondaryActions(d).map((a) => a.key)).not.toContain("destroy");
  });
});

describe("dangerous actions require confirmation", () => {
  it("deploy and destroy", () => {
    expect(primaryAction(demo({ status: "generated", instance_dir: "i" }))?.confirm).toMatch(/billable/);
    const d = demo({ status: "deployed", instance_dir: "i", outputs: live });
    expect(secondaryActions(d).find((a) => a.key === "destroy")?.confirm).toMatch(/permanently deletes/);
  });
  it("unpublish is marked dangerous and only exists while published", () => {
    const base = { status: "deployed", instance_dir: "i", outputs: live, data: seed, certification: cert(true) } as const;
    expect(secondaryActions(demo(base)).map((a) => a.key)).not.toContain("unpublish");
    const withLink = secondaryActions(demo({ ...base, publication: pub }));
    expect(withLink.find((a) => a.key === "unpublish")?.danger).toBe(true);
  });
});

describe("stages", () => {
  it("marks exactly one current stage", () => {
    const d = demo({ status: "deployed", instance_dir: "i", outputs: live });
    const s = states(d);
    expect(s).toMatchObject({ plan: "done", generate: "done", deploy: "done", data: "current", certify: "todo", publish: "todo" });
    expect(Object.values(s).filter((v) => v === "current")).toHaveLength(1);
  });
  it("shows the running stage as busy", () => {
    expect(states(demo({ status: "certifying", instance_dir: "i", outputs: live, data: seed })).certify).toBe("busy");
    expect(states(demo({ status: "seeding", instance_dir: "i", outputs: live })).data).toBe("busy");
    expect(states(demo({ status: "deploying", instance_dir: "i" })).deploy).toBe("busy");
  });
  it("shows the failed stage", () => {
    const d = demo({ status: "failed", failed_stage: "data", instance_dir: "i", outputs: live });
    expect(states(d).data).toBe("failed");
    expect(states(d).deploy).toBe("done");
  });
  it("everything is done once published", () => {
    const d = demo({
      status: "deployed", instance_dir: "i", outputs: live, data: seed, certification: cert(true), publication: pub,
    });
    expect(Object.values(states(d)).every((v) => v === "done")).toBe(true);
  });
  it("a failed certification keeps certify as the current step", () => {
    const d = demo({ status: "deployed", instance_dir: "i", outputs: live, data: seed, certification: cert(false) });
    expect(states(d)).toMatchObject({ certify: "current", publish: "todo" });
  });
});

describe("errorMessage", () => {
  it("reads FastAPI error shapes", () => {
    expect(errorMessage({ detail: "nope" }, "f")).toBe("nope");
    expect(errorMessage({ detail: { stage: "apply", error: "quota" } }, "f")).toBe("apply: quota");
    expect(errorMessage({ detail: [{ msg: "too short" }, { msg: "bad" }] }, "f")).toBe("too short; bad");
    expect(errorMessage(null, "fallback")).toBe("fallback");
    expect(new ApiError(409, "x").status).toBe(409);
  });
});
