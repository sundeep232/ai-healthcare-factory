import type { DataPreview, Demo, DemoSummary, Manifest } from "./types";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

/** FastAPI errors are `{detail: string}` or `{detail: {stage, error}}` or validation lists. */
export function errorMessage(body: unknown, fallback: string): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((d) => (d as { msg?: string }).msg ?? JSON.stringify(d)).join("; ");
  }
  if (detail && typeof detail === "object") {
    const d = detail as { stage?: string; error?: string };
    if (d.error) return d.stage ? `${d.stage}: ${d.error}` : d.error;
    return JSON.stringify(detail);
  }
  return fallback;
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  let resp: Response;
  try {
    resp = await fetch(path, {
      method,
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, "Cannot reach the factory API. Is it running?");
  }
  const text = await resp.text();
  let parsed: unknown = null;
  try {
    parsed = text ? JSON.parse(text) : null;
  } catch {
    /* not JSON (e.g. an HTML 404 from a share-only server) */
  }
  if (!resp.ok) {
    throw new ApiError(resp.status, errorMessage(parsed, `Request failed (HTTP ${resp.status})`));
  }
  return parsed as T;
}

const demo = (id: string) => `/api/demos/${encodeURIComponent(id)}`;

export const api = {
  listDemos: () => request<DemoSummary[]>("GET", "/api/demos"),
  createDemo: (intent: string) => request<Demo>("POST", "/api/demos", { intent }),
  getDemo: (id: string) => request<Demo>("GET", demo(id)),
  generate: (id: string) => request<Demo>("POST", `${demo(id)}/generate`),
  plan: (id: string) => request<Demo>("POST", `${demo(id)}/plan`),
  deploy: (id: string) => request<Demo>("POST", `${demo(id)}/deploy`, { confirm: true }),
  seed: (id: string) => request<Demo>("POST", `${demo(id)}/seed`, {}),
  certify: (id: string) => request<Demo>("POST", `${demo(id)}/certify`),
  publish: (id: string) => request<Demo>("POST", `${demo(id)}/publish`),
  unpublish: (id: string) => request<Demo>("DELETE", `${demo(id)}/publish`),
  destroy: (id: string) => request<Demo>("POST", `${demo(id)}/destroy`, { confirm: true }),
  preview: (id: string, sample = 5) =>
    request<DataPreview>("POST", `${demo(id)}/data/preview?sample=${sample}`, {}),
  logs: (id: string) => request<{ log: string }>("GET", `${demo(id)}/logs?tail=300`),
  shared: (token: string) => request<Manifest>("GET", `/api/shared/${encodeURIComponent(token)}`),
};
