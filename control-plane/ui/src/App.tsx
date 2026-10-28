import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import {
  authToken,
  clearToken,
  createEnvironment,
  deleteEnvironment,
  fetchAnalytics,
  fetchCustomers,
  fetchEnvironment,
  fetchEnvironments,
  fetchTemplates,
  login,
  type UsageRow,
} from "./api";
import type { Customer, EnvironmentDetail, EnvironmentSummary, Template } from "./types";

type View = "home" | "environments" | "create" | "templates" | "customers" | "analytics";

const nav: { id: View; label: string; icon: ReactNode }[] = [
  { id: "home", label: "Home", icon: <HomeIcon /> },
  { id: "environments", label: "Environments", icon: <BoxIcon /> },
  { id: "create", label: "Create Demo", icon: <PlusCircleIcon /> },
  { id: "templates", label: "Templates", icon: <LayersIcon /> },
  { id: "customers", label: "Customers", icon: <PeopleIcon /> },
  { id: "analytics", label: "Analytics", icon: <ChartIcon /> },
];

const RESOURCE_LABELS: Record<string, string> = {
  sql: "Azure SQL",
  portal: "Portal site",
  openai: "Azure OpenAI",
  speech: "Speech",
  communication: "Communication Services",
};

function templateResources(template: Template | undefined): string[] {
  const names = template?.definition.resources;
  return names && names.length > 0 ? names : ["sql", "portal"];
}

function resourceText(names: string[]) {
  return names.map((name) => RESOURCE_LABELS[name] ?? name).join(", ");
}

function customerLabel(name: string) {
  if (/united/i.test(name)) return "UHC";
  if (/molina/i.test(name)) return "Molina";
  if (/humana/i.test(name)) return "Humana";
  return name.split(" ")[0];
}

function shownStatus(environment: { status: string; expiresAt: string | null }) {
  if (environment.status === "Destroying" || environment.status === "Destroyed") return environment.status;
  const expired = environment.expiresAt && new Date(environment.expiresAt) < new Date() && environment.status !== "Deploying";
  if (expired) return "Expired";
  if (environment.status === "Active") return "Ready";
  return environment.status;
}

const VIEW_PATH: Record<View, string> = {
  home: "/home",
  environments: "/environments",
  create: "/create",
  templates: "/templates",
  customers: "/customers",
  analytics: "/analytics",
};

function routeFromPath(pathname: string): { view: View; environmentId: string | null } {
  const parts = pathname.split("/").filter(Boolean);
  if (parts[0] === "environments" && /^[0-9a-f-]{36}$/i.test(parts[1] ?? "")) {
    return { view: "environments", environmentId: parts[1] };
  }
  const view = (Object.keys(VIEW_PATH) as View[]).find((item) => VIEW_PATH[item] === `/${parts[0] ?? ""}`);
  return { view: view ?? "environments", environmentId: null };
}

function knownPath(pathname: string) {
  const route = routeFromPath(pathname);
  return route.environmentId ? `/environments/${route.environmentId}` : VIEW_PATH[route.view];
}

function initialPath() {
  const path = window.location.pathname;
  if (path === "/") {
    window.history.replaceState(null, "", "/environments");
    return "/environments";
  }
  const canonical = knownPath(path);
  if (canonical !== path) window.history.replaceState(null, "", canonical);
  return canonical;
}

export function App() {
  const [signedIn, setSignedIn] = useState(() => Boolean(authToken()));
  const [path, setPath] = useState(initialPath);
  const [environments, setEnvironments] = useState<EnvironmentSummary[]>([]);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [usage, setUsage] = useState<UsageRow[]>([]);
  const [totalCost, setTotalCost] = useState(0);
  const [selected, setSelected] = useState<EnvironmentDetail | null>(null);
  const [logLoading, setLogLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [customerId, setCustomerId] = useState("");
  const [templateId, setTemplateId] = useState("");
  const [memberCount, setMemberCount] = useState("");
  const [creating, setCreating] = useState(false);
  const creatingRef = useRef(false);
  const environmentsRef = useRef(environments);
  environmentsRef.current = environments;
  const route = routeFromPath(path);
  const view = route.view;
  const environmentId = route.environmentId;

  function go(next: string) {
    if (window.location.pathname === next) return;
    window.history.pushState(null, "", next);
    setPath(next);
    setError(null);
  }

  useEffect(() => {
    const onPop = () => setPath(window.location.pathname);
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  async function loadLists() {
    const [environmentRows, templateRows, customerRows, analytics] = await Promise.all([
      fetchEnvironments(),
      fetchTemplates(),
      fetchCustomers(),
      fetchAnalytics(),
    ]);
    setEnvironments(environmentRows);
    setTemplates(templateRows);
    setCustomers(customerRows);
    setUsage(analytics.rows);
    setTotalCost(analytics.totalCost);
  }

  useEffect(() => {
    if (!signedIn) return;
    loadLists().catch((err: Error) => {
      if (!authToken()) setSignedIn(false);
      else setError(err.message);
    });
  }, [signedIn]);

  const workflowRunning = environments.some((item) => item.status === "Deploying" || item.status === "Destroying");
  useEffect(() => {
    if (!signedIn || !workflowRunning) return;
    const timer = window.setInterval(() => {
      fetchEnvironments()
        .then(setEnvironments)
        .catch(() => {
          if (!authToken()) setSignedIn(false);
        });
    }, 3000);
    return () => window.clearInterval(timer);
  }, [signedIn, workflowRunning]);

  function openView(next: View) {
    go(VIEW_PATH[next]);
  }

  function openEnvironment(id: string) {
    go(`/environments/${id}`);
  }

  useEffect(() => {
    if (!signedIn || !environmentId) {
      setSelected(null);
      setLogLoading(false);
      return;
    }
    let cancelled = false;
    const summary = environmentsRef.current.find((item) => item.id === environmentId);
    setError(null);
    setLogLoading(true);
    if (summary) {
      setSelected({
        ...summary,
        secondaryColor: null,
        deployments: [],
        conversations: [],
        usage: [],
      });
    }
    fetchEnvironment(environmentId)
      .then((detail) => {
        if (!cancelled) setSelected(detail);
      })
      .catch((err: Error) => {
        if (cancelled) return;
        if (!authToken()) setSignedIn(false);
        else setError(err.message || "Could not open the deployment log");
        if (!summary) setSelected(null);
      })
      .finally(() => {
        if (!cancelled) setLogLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [signedIn, environmentId]);

  useEffect(() => {
    if (!selected || (selected.status !== "Deploying" && selected.status !== "Destroying")) return;
    const id = selected.id;
    const timer = window.setInterval(() => {
      fetchEnvironment(id)
        .then((next) => {
          setSelected((current) => (current?.id === id ? next : current));
          if (next.status !== "Deploying" && next.status !== "Destroying") {
            fetchEnvironments().then(setEnvironments).catch(() => undefined);
          }
        })
        .catch(() => {
          if (!authToken()) setSignedIn(false);
        });
    }, 3000);
    return () => window.clearInterval(timer);
  }, [selected?.id, selected?.status]);

  async function onCreate(event: FormEvent) {
    event.preventDefault();
    if (creatingRef.current) return;
    setError(null);
    const demoName = name.trim();
    if (!demoName || !customerId || !templateId) {
      setError("Name, customer, and template are required");
      return;
    }
    const selectedTemplate = templates.find((item) => item.id === templateId);
    const resources = templateResources(selectedTemplate);
    const members = Number(memberCount);
    if (resources.includes("sql") && (!Number.isInteger(members) || members < 10 || members > 1000)) {
      setError("Synthetic members must be a whole number from 10 to 1000");
      return;
    }
    creatingRef.current = true;
    setCreating(true);
    const memberNote = resources.includes("sql") ? ` Azure SQL will load ${members} synthetic members.` : "";
    const confirmed = window.confirm(`Deploy the Azure resource group for ${demoName}? It will include ${resourceText(resources)}.${memberNote}`);
    if (!confirmed) {
      creatingRef.current = false;
      setCreating(false);
      return;
    }
    try {
      const created = await createEnvironment({
        customerId,
        templateId,
        name: demoName,
        syntheticMembers: resources.includes("sql") ? members : undefined,
      });
      setName("");
      setCustomerId("");
      setTemplateId("");
      setMemberCount("");
      await loadLists();
      go(`/environments/${created.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create the demo");
    } finally {
      creatingRef.current = false;
      setCreating(false);
    }
  }

  async function onDelete(environment: EnvironmentSummary) {
    if (environment.status === "Deploying" || environment.status === "Destroying") return;
    const azure = Boolean(environment.slug) && environment.status !== "Destroyed";
    const prompt = azure
      ? `Destroy the Azure resource group for ${environment.name}? This removes that group and the Azure resources created for it.`
      : `Delete ${environment.name}?`;
    if (!window.confirm(prompt)) return;
    setError(null);
    try {
      const updated = await deleteEnvironment(environment.id);
      await loadLists();
      if (updated) {
        go(`/environments/${environment.id}`);
      } else if (environmentId === environment.id) {
        go("/environments");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete the demo");
    }
  }

  const counts = {
    Ready: environments.filter((item) => shownStatus(item) === "Ready").length,
    Deploying: environments.filter((item) => shownStatus(item) === "Deploying").length,
    Expired: environments.filter((item) => shownStatus(item) === "Expired").length,
  };

  if (!signedIn) return <Login onSuccess={() => setSignedIn(true)} />;

  return (
    <div className="app">
      <aside className="nav">
        <div className="brand">Optum</div>
        {nav.map((item) => (
          <button key={item.id} className={view === item.id && (!environmentId || item.id === "environments") ? "active" : ""} onClick={() => openView(item.id)}>
            {item.icon}
            {item.label}
          </button>
        ))}
        <button className="sign-out" onClick={() => { clearToken(); setSignedIn(false); }}>Sign out</button>
      </aside>
      <div className="workspace">
        <header className="appbar">Demo Factory</header>
        <main className="content">
          {error && <p className="error">{error}</p>}
          {environmentId && selected?.id === environmentId ? (
            <Detail item={selected} loading={logLoading} onBack={() => go("/environments")} />
          ) : environmentId ? (
            <p className="meta">Loading the deployment log…</p>
          ) : view === "home" ? (
            <>
              <div className="top"><h2>Home</h2></div>
              <div className="stats">
                <div className="stat"><span>Ready</span><strong>{counts.Ready}</strong></div>
                <div className="stat"><span>Deploying</span><strong>{counts.Deploying}</strong></div>
                <div className="stat"><span>Expired</span><strong>{counts.Expired}</strong></div>
              </div>
              <EnvironmentTable environments={environments} onOpen={openEnvironment} onDelete={onDelete} />
            </>
          ) : view === "environments" ? (
            <>
              <div className="top">
                <h2>Demo Environments</h2>
                <button className="primary" onClick={() => openView("create")}>
                  <PlusIcon /> Create Demo
                </button>
              </div>
              <EnvironmentTable environments={environments} onOpen={openEnvironment} onDelete={onDelete} />
            </>
          ) : view === "create" ? (
            <>
              <div className="top"><h2>Create Demo</h2></div>
              <p className="note">Starts a GitHub Actions workflow that creates this demo's resource group and the Azure resources named on the template. When the template includes Azure SQL, synthetic member, claim, authorization, and care-management data is loaded after Terraform. The deploy log opens when the workflow is queued.</p>
              <form className="form" onSubmit={onCreate}>
                <label>
                  Name
                  <input required value={name} onChange={(event) => setName(event.target.value)} placeholder="Enter a demo name" />
                </label>
                <label>
                  Customer
                  <select required value={customerId} onChange={(event) => setCustomerId(event.target.value)}>
                    <option value="">Select a customer</option>
                    {customers.map((customer) => (
                      <option key={customer.id} value={customer.id}>{customer.name}</option>
                    ))}
                  </select>
                </label>
                <label>
                  Template
                  <select required value={templateId} onChange={(event) => {
                    setTemplateId(event.target.value);
                    setMemberCount("");
                  }}>
                    <option value="">Select a template</option>
                    {templates.map((template) => (
                      <option key={template.id} value={template.id}>{template.name}</option>
                    ))}
                  </select>
                </label>
                {templateId && templateResources(templates.find((item) => item.id === templateId)).includes("sql") && (
                  <label>
                    Synthetic members
                    <input required type="number" min={10} max={1000} value={memberCount} onChange={(event) => setMemberCount(event.target.value)} placeholder="10 to 1000" />
                  </label>
                )}
                {templateId && <p className="note">Resources: {resourceText(templateResources(templates.find((item) => item.id === templateId)))}</p>}
                <button className="primary" type="submit" disabled={creating}>{creating ? "Deploying…" : <><PlusIcon /> Create Demo</>}</button>
              </form>
            </>
          ) : view === "templates" ? (
            <>
              <div className="top"><h2>Templates</h2></div>
              <div className="table-wrap">
                <table>
                  <thead><tr><th>Name</th><th>Channels</th><th>Resources</th><th>Status</th></tr></thead>
                  <tbody>
                    {templates.map((template) => (
                      <tr key={template.id}>
                        <td>{template.name}</td>
                        <td>{template.definition.channels?.join(", ")}</td>
                        <td>{resourceText(templateResources(template))}</td>
                        <td>{template.status}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          ) : view === "customers" ? (
            <>
              <div className="top"><h2>Customers</h2></div>
              <div className="table-wrap">
                <table>
                  <thead><tr><th>Name</th><th>Tenant</th><th>Portal</th></tr></thead>
                  <tbody>
                    {customers.map((customer) => (
                      <tr key={customer.id}>
                        <td>{customerLabel(customer.name)}</td>
                        <td>{customer.tenantId}</td>
                        <td>{customer.portalName}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          ) : (
            <>
              <div className="top"><h2>Analytics</h2></div>
              <div className="stats">
                <div className="stat"><span>Recorded cost</span><strong>${totalCost.toFixed(2)}</strong></div>
              </div>
              <div className="table-wrap">
                <table>
                  <thead><tr><th>Environment</th><th>Customer</th><th>Meter</th><th className="right">Cost</th></tr></thead>
                  <tbody>
                    {usage.map((row) => (
                      <tr key={`${row.environmentId}-${row.meter}`}>
                        <td>{row.environmentName}</td>
                        <td>{customerLabel(row.customerName)}</td>
                        <td>{row.meter}</td>
                        <td className="right">${row.cost.toFixed(2)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </main>
      </div>
    </div>
  );
}

function Login({ onSuccess }: { onSuccess: () => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      await login(username, password);
      onSuccess();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not sign in");
    }
  }

  return (
    <div className="login-page">
      <form className="login-card" onSubmit={onSubmit}>
        <div className="brand">Optum</div>
        <h2>Demo Factory</h2>
        <p className="note">Sign in to open the control plane.</p>
        {error && <p className="error">{error}</p>}
        <label>
          User ID
          <input value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" />
        </label>
        <label>
          Password
          <input value={password} onChange={(event) => setPassword(event.target.value)} type="password" autoComplete="current-password" />
        </label>
        <button className="primary" type="submit">Sign in</button>
      </form>
    </div>
  );
}

function EnvironmentTable({
  environments,
  onOpen,
  onDelete,
}: {
  environments: EnvironmentSummary[];
  onOpen: (id: string) => void;
  onDelete: (environment: EnvironmentSummary) => void;
}) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Name</th>
            <th>Customer</th>
            <th>Status</th>
            <th className="right">Actions</th>
          </tr>
        </thead>
        <tbody>
          {environments.map((environment) => {
            const status = shownStatus(environment);
            const busy = environment.status === "Deploying" || environment.status === "Destroying";
            return (
              <tr key={environment.id}>
                <td>
                  <div>{environment.name}</div>
                  {environment.portalUrl && (
                    <a className="portal-link" href={environment.portalUrl} target="_blank" rel="noreferrer">Provider portal</a>
                  )}
                </td>
                <td>{customerLabel(environment.customerName)}</td>
                <td>
                  <span className="status">
                    <span className={`dot ${status.toLowerCase()}`} />
                    {status}
                  </span>
                </td>
                <td>
                  <div className="actions">
                    <button className="icon" title={busy ? `${status} in progress` : "View deployment activity"} aria-label={`View deployment activity for ${environment.name}`} onClick={() => onOpen(environment.id)}><ActivityIcon /></button>
                    <button
                      className="icon danger"
                      title={busy ? `${status} is already running` : environment.slug && environment.status !== "Destroyed" ? "Destroy demo" : "Delete demo"}
                      aria-label={busy ? `${status} is already running` : `${environment.slug && environment.status !== "Destroyed" ? "Destroy" : "Delete"} ${environment.name}`}
                      disabled={busy}
                      onClick={() => onDelete(environment)}
                    ><TrashIcon /></button>
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function Detail({ item, loading, onBack }: { item: EnvironmentDetail; loading: boolean; onBack: () => void }) {
  const cost = item.usage.reduce((sum, row) => sum + row.cost, 0);
  const status = shownStatus(item);
  const latest = item.deployments[0];
  const logRef = useRef<HTMLElement>(null);
  useEffect(() => {
    logRef.current?.scrollIntoView({ block: "start" });
  }, [item.id]);
  useEffect(() => {
    const pre = logRef.current?.querySelector("pre");
    if (pre) pre.scrollTop = pre.scrollHeight;
  }, [latest?.log, loading]);
  return (
    <>
      <button className="back" onClick={onBack}>Back</button>
      <div className="top">
        <h2>{item.name}</h2>
        <span className="status"><span className={`dot ${status.toLowerCase()}`} />{status}</span>
      </div>
      <p className="note">{customerLabel(item.customerName)} · {item.templateName}</p>
      {item.portalUrl && (
        <p><a className="portal-link" href={item.portalUrl} target="_blank" rel="noreferrer">Open provider portal</a></p>
      )}
      <section className="panel" ref={logRef}>
        <h3>{status === "Destroying" ? "Destroy in progress" : status === "Deploying" ? "Deploy in progress" : "Deployment"}</h3>
        {(status === "Destroying" || status === "Deploying") && <p className="meta">The Terraform steps refresh every few seconds.</p>}
        {item.deployments.map((log) => (
          <p key={log.id} className="meta">{log.action} · {log.status}. {log.message}</p>
        ))}
        <pre className="deploy-log">{loading ? "Loading the Terraform log…" : (latest?.log || "Waiting for the workflow log.")}</pre>
      </section>
      <section className="panel">
        <h3>Conversations</h3>
        {item.conversations.length === 0 && <p className="meta">No conversations yet.</p>}
        {item.conversations.map((log) => (
          <p key={log.id} className="meta"><strong>{log.channel}</strong> — {log.transcript}</p>
        ))}
      </section>
      <section className="panel">
        <h3>Usage</h3>
        <p className="meta">Recorded cost ${cost.toFixed(2)}</p>
      </section>
    </>
  );
}

function HomeIcon() {
  return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M4 10.5 12 4l8 6.5V20a1 1 0 0 1-1 1h-5v-6H10v6H5a1 1 0 0 1-1-1z" /></svg>;
}
function BoxIcon() {
  return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M3 7.5 12 3l9 4.5-9 4.5L3 7.5Z" /><path d="M3 7.5V16.5L12 21l9-4.5V7.5" /><path d="M12 12v9" /></svg>;
}
function PlusCircleIcon() {
  return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><circle cx="12" cy="12" r="8" /><path d="M12 8.5v7M8.5 12h7" /></svg>;
}
function LayersIcon() {
  return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="m12 3 9 5-9 5-9-5 9-5Z" /><path d="m3 12 9 5 9-5" /><path d="m3 16.5 9 5 9-5" /></svg>;
}
function PeopleIcon() {
  return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><circle cx="9" cy="8" r="3" /><path d="M3.5 19c.6-2.8 2.8-4.5 5.5-4.5s4.9 1.7 5.5 4.5" /><circle cx="17" cy="9" r="2.2" /><path d="M16 14.6c2.2.3 3.8 1.6 4.5 4.4" /></svg>;
}
function ChartIcon() {
  return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M4 19h16" /><path d="M7 16V9" /><path d="M12 16V5" /><path d="M17 16v-4" /></svg>;
}
function PlusIcon() {
  return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4"><path d="M12 5v14M5 12h14" /></svg>;
}
function ActivityIcon() {
  return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M3 12h4l2.2-6 3.6 12L15 12h6" /></svg>;
}
function TrashIcon() {
  return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M5 7h14" /><path d="M9 7V5h6v2" /><path d="M8 7l1 12h6l1-12" /></svg>;
}
