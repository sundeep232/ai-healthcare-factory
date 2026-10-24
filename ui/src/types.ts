// Mirrors the API's JSON (orchestrator/schemas). Only fields the UI reads are listed.

export type DemoStatus =
  | "planned"
  | "generated"
  | "deploying"
  | "deployed"
  | "seeding"
  | "certifying"
  | "destroying"
  | "destroyed"
  | "failed";

export type CheckStatus = "pass" | "warn" | "fail" | "skip";
export type CheckCategory = "deployment" | "data" | "security";

export interface Check {
  id: string;
  category: CheckCategory;
  title: string;
  status: CheckStatus;
  summary: string;
  detail?: string; // owner-only; absent on the public share page
  evidence: Record<string, unknown>;
}

export interface Certification {
  passed: boolean;
  certified_at: string;
  blueprint_version: number;
  data_seed: number | null;
  summary: Record<CheckStatus, number>;
  checks: Check[];
}

export interface Publication {
  token: string;
  published_at: string;
  share_path: string;
  share_url: string;
}

export interface Resource {
  id: string;
  type: string;
  name: string;
  purpose: string;
  sku: string | null;
}

export interface DataPlanEntry {
  domain: string;
  target_resource_id: string;
  record_count: number;
}

export interface SeedTarget {
  resource_id: string;
  kind: "postgres" | "cosmos";
  tables: Record<string, number>;
}

export interface SeedSummary {
  seed: number;
  as_of: string;
  targets: SeedTarget[];
  total_rows: number;
  warnings: string[];
  seeded_at: string;
}

export interface DemoEvent {
  at: string;
  stage: string;
  message: string;
}

export interface Demo {
  demo_id: string;
  status: DemoStatus;
  intent: string;
  requirements: {
    demo_name: string;
    summary: string;
    target_audience: string;
    business_goals: string[];
    domains: string[];
    assumptions: string[];
    open_questions: string[];
    azure_region: string;
  } | null;
  blueprint: {
    version: number;
    instance_slug: string;
    summary: string;
    resources: (Resource & { depends_on: string[] })[];
    data_plan: DataPlanEntry[];
  } | null;
  instance_dir: string | null;
  plan: { add: number; change: number; destroy: number; resources: string[] } | null;
  outputs: Record<string, unknown>;
  data: SeedSummary | null;
  certification: Certification | null;
  publication: Publication | null;
  failed_stage: string | null;
  error: string | null;
  events: DemoEvent[];
  created_at: string;
  updated_at: string;
}

export interface DemoSummary {
  demo_id: string;
  status: DemoStatus;
  demo_name: string | null;
  instance_slug: string | null;
  resource_count: number;
  created_at: string;
  updated_at: string;
}

export interface DataPreview {
  seed: number;
  as_of: string;
  targets: Record<string, string>;
  counts: Record<string, number>;
  samples: Record<string, Record<string, unknown>[]>;
}

export interface Manifest {
  demo_id: string;
  demo_name: string;
  summary: string;
  intent: string;
  target_audience: string;
  business_goals: string[];
  region: string;
  blueprint_version: number;
  resources: Resource[];
  endpoints: { name: string; url: string }[];
  data_as_of: string | null;
  data_seed: number | null;
  domains: string[];
  tables: { name: string; rows: number }[];
  certification: {
    passed: boolean;
    certified_at: string;
    summary: Record<CheckStatus, number>;
    checks: Check[];
  };
  published_at: string;
  synthetic_data_notice: string;
}
