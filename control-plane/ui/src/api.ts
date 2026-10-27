import type { Customer, EnvironmentDetail, EnvironmentSummary, Template } from "./types";

const apiBase = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

function url(path: string) {
  return `${apiBase}${path}`;
}

async function get<T>(path: string): Promise<T> {
  const response = await fetch(url(path));
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}

export function fetchEnvironments() {
  return get<EnvironmentSummary[]>("/api/environments");
}

export function fetchEnvironment(id: string) {
  return get<EnvironmentDetail>(`/api/environments/${id}`);
}

export function fetchTemplates() {
  return get<Template[]>("/api/templates");
}

export function fetchCustomers() {
  return get<Customer[]>("/api/customers");
}

export type UsageRow = {
  environmentId: string;
  environmentName: string;
  customerName: string;
  meter: string;
  quantity: number;
  cost: number;
  recordedAt: string;
};

export function fetchAnalytics() {
  return get<{ totalCost: number; rows: UsageRow[] }>("/api/analytics");
}

export async function deleteEnvironment(id: string) {
  const response = await fetch(url(`/api/environments/${id}`), { method: "DELETE" });
  if (!response.ok) {
    throw new Error("Could not delete the environment");
  }
}

export async function createEnvironment(body: { customerId: string; templateId: string; name: string }) {
  const response = await fetch(url("/api/environments"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(detail.detail ?? "Could not create the environment");
  }
  return response.json() as Promise<EnvironmentDetail>;
}
