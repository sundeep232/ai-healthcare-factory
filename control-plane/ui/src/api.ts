import type { Customer, EnvironmentDetail, EnvironmentSummary, Template } from "./types";

const apiBase = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");
export const TOKEN_KEY = "demo-factory-token";

function url(path: string) {
  return `${apiBase}${path}`;
}

export function authToken() {
  return sessionStorage.getItem(TOKEN_KEY) ?? "";
}

export function saveToken(token: string) {
  sessionStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  sessionStorage.removeItem(TOKEN_KEY);
}

function headers(extra: Record<string, string> = {}) {
  const result: Record<string, string> = { ...extra };
  const token = authToken();
  if (token) result.Authorization = `Bearer ${token}`;
  return result;
}

async function readError(response: Response, fallback: string) {
  if (response.status === 401) clearToken();
  const detail = await response.json().catch(() => ({}));
  return new Error(detail.detail ?? fallback);
}

export async function login(username: string, password: string) {
  const response = await fetch(url("/api/login"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!response.ok) throw await readError(response, "Could not sign in");
  const body = (await response.json()) as { token: string };
  saveToken(body.token);
}

async function get<T>(path: string): Promise<T> {
  const response = await fetch(url(path), { headers: headers() });
  if (!response.ok) throw await readError(response, `${response.status} ${response.statusText}`);
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
  const response = await fetch(url(`/api/environments/${id}`), { method: "DELETE", headers: headers() });
  if (!response.ok) throw await readError(response, "Could not delete the environment");
}

export async function createEnvironment(body: { customerId: string; templateId: string; name: string }) {
  const response = await fetch(url("/api/environments"), {
    method: "POST",
    headers: headers({ "Content-Type": "application/json" }),
    body: JSON.stringify(body),
  });
  if (!response.ok) throw await readError(response, "Could not create the environment");
  return response.json() as Promise<EnvironmentDetail>;
}
