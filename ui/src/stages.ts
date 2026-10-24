import type { Demo, DemoStatus } from "./types";

export type ActionKey =
  | "generate"
  | "plan"
  | "deploy"
  | "seed"
  | "certify"
  | "publish"
  | "unpublish"
  | "destroy";

export interface Action {
  key: ActionKey;
  label: string;
  /** Needs an explicit confirmation because it creates or deletes cloud resources. */
  confirm?: string;
  danger?: boolean;
}

export type StageState = "done" | "current" | "todo" | "busy" | "failed";

export interface Stage {
  id: "plan" | "generate" | "deploy" | "data" | "certify" | "publish";
  label: string;
  state: StageState;
}

const DESTROY: Action = {
  key: "destroy",
  label: "Destroy",
  danger: true,
  confirm: "This permanently deletes every Azure resource of this demo, including its data.",
};

const BUSY: DemoStatus[] = ["deploying", "seeding", "certifying", "destroying"];

export const isBusy = (status: DemoStatus): boolean => BUSY.includes(status);

export const isLive = (demo: Demo): boolean => Object.keys(demo.outputs).length > 0;

/** Where the demo is on the road from intent to share link. */
export function stages(demo: Demo): Stage[] {
  const s = demo.status;
  const generated = !!demo.instance_dir;
  const deployed = s === "deployed" || s === "seeding" || s === "certifying" || (s === "failed" && isLive(demo));
  const seeded = !!demo.data;
  const certified = !!demo.certification?.passed;
  const published = !!demo.publication;

  const failedAt = s === "failed" ? demo.failed_stage : null;
  const failedStage: Stage["id"] | null =
    failedAt === "data" ? "data" : failedAt === "deploy" ? "deploy" : failedAt === "generate" ? "generate" : null;

  const raw: [Stage["id"], string, boolean, boolean][] = [
    ["plan", "Plan", true, false],
    ["generate", "Generate", generated, s === "planned"],
    ["deploy", "Deploy", deployed, s === "generated" || s === "deploying"],
    ["data", "Data", seeded, (s === "deployed" && !seeded) || s === "seeding"],
    ["certify", "Certify", certified, (s === "deployed" && seeded && !certified) || s === "certifying"],
    ["publish", "Publish", published, s === "deployed" && certified && !published],
  ];
  const busyStage: Stage["id"] | null =
    s === "deploying" ? "deploy" : s === "seeding" ? "data" : s === "certifying" ? "certify" : null;

  let currentSeen = false;
  return raw.map(([id, label, done, current]) => {
    let state: StageState;
    if (id === failedStage) state = "failed";
    else if (id === busyStage) state = "busy";
    else if (done) state = "done";
    else if (current && !currentSeen) state = "current";
    else state = "todo";
    if (state === "current") currentSeen = true;
    return { id, label, state };
  });
}

/** The most useful next click for this demo (null while something is running). */
export function primaryAction(demo: Demo): Action | null {
  const s = demo.status;
  if (isBusy(s) || s === "destroyed") return null;
  const deploy: Action = {
    key: "deploy",
    label: "Deploy to Azure",
    confirm: "Deploying creates billable Azure resources in your subscription.",
  };
  if (s === "planned") return { key: "generate", label: "Generate Terraform" };
  if (s === "generated") return deploy;
  if (s === "failed") {
    if (demo.failed_stage === "deploy") return { ...deploy, label: "Retry deploy" };
    if (demo.failed_stage === "data") return { key: "seed", label: "Retry data load" };
    if (demo.failed_stage === "destroy") {
      return { ...DESTROY, label: "Retry destroy" };
    }
    return { key: "generate", label: "Regenerate Terraform" };
  }
  // deployed
  if (!demo.data) return { key: "seed", label: "Load synthetic data" };
  if (!demo.certification) return { key: "certify", label: "Certify" };
  if (!demo.certification.passed) return { key: "certify", label: "Certify again" };
  if (!demo.publication) return { key: "publish", label: "Publish share link" };
  return null;
}

/** Everything else that is allowed right now. */
export function secondaryActions(demo: Demo): Action[] {
  const s = demo.status;
  if (isBusy(s) || s === "destroyed") return [];
  const out: Action[] = [];
  if (s === "generated" || (s === "failed" && !!demo.instance_dir)) out.push({ key: "plan", label: "Preview changes (plan)" });
  if (s === "generated" || s === "failed") out.push({ key: "generate", label: "Regenerate" });
  if (s === "deployed") {
    if (demo.data) out.push({ key: "seed", label: "Reload data" });
    if (demo.certification && demo.certification.passed) out.push({ key: "certify", label: "Certify again" });
    if (demo.publication) {
      out.push({ key: "publish", label: "Refresh share page" });
      out.push({ key: "unpublish", label: "Unpublish", danger: true });
    }
  }
  const retryingDestroy = s === "failed" && demo.failed_stage === "destroy"; // already the primary action
  if ((s === "deployed" || (s === "failed" && isLive(demo))) && !retryingDestroy) out.push(DESTROY);
  return out;
}

export const STATUS_LABEL: Record<DemoStatus, string> = {
  planned: "Planned",
  generated: "Ready to deploy",
  deploying: "Deploying…",
  deployed: "Deployed",
  seeding: "Loading data…",
  certifying: "Certifying…",
  destroying: "Destroying…",
  destroyed: "Destroyed",
  failed: "Failed",
};
