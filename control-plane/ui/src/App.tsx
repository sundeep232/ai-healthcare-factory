import { useEffect, useState, type FormEvent, type ReactNode } from "react";
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

function customerLabel(name: string) {
  if (/united/i.test(name)) return "UHC";
  if (/molina/i.test(name)) return "Molina";
  if (/humana/i.test(name)) return "Humana";
  return name.split(" ")[0];
}

function shownStatus(environment: { status: string; expiresAt: string | null }) {
  const expired = environment.expiresAt && new Date(environment.expiresAt) < new Date() && environment.status !== "Deploying";
  if (expired) return "Expired";
  if (environment.status === "Active") return "Ready";
  return environment.status;
}

export function App() {
  const [signedIn, setSignedIn] = useState(() => Boolean(authToken()));
  const [view, setView] = useState<View>("environments");
  const [environments, setEnvironments] = useState<EnvironmentSummary[]>([]);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [usage, setUsage] = useState<UsageRow[]>([]);
  const [totalCost, setTotalCost] = useState(0);
  const [selected, setSelected] = useState<EnvironmentDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [customerId, setCustomerId] = useState("");
  const [templateId, setTemplateId] = useState("");

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
    setCustomerId((current) => current || customerRows[0]?.id || "");
    setTemplateId((current) => current || templateRows[0]?.id || "");
  }

  useEffect(() => {
    if (!signedIn) return;
    loadLists().catch((err: Error) => {
      if (!authToken()) setSignedIn(false);
      else setError(err.message);
    });
  }, [signedIn]);

  function openView(next: View) {
    setView(next);
    setSelected(null);
    setError(null);
  }

  async function openEnvironment(id: string) {
    setError(null);
    setSelected(await fetchEnvironment(id));
  }

  async function onCreate(event: FormEvent) {
    event.preventDefault();
    setError(null);
    await createEnvironment({ customerId, templateId, name: name || "New demo" });
    setName("");
    await loadLists();
    setView("environments");
  }

  async function onCopy(environment: EnvironmentSummary) {
    setError(null);
    if (!environment.templateId) return;
    await createEnvironment({
      customerId: environment.customerId,
      templateId: environment.templateId,
      name: `${environment.name} copy`,
    });
    await loadLists();
    setView("environments");
    setSelected(null);
  }

  async function onDelete(environment: EnvironmentSummary) {
    if (!window.confirm(`Delete ${environment.name}?`)) return;
    setError(null);
    await deleteEnvironment(environment.id);
    if (selected?.id === environment.id) setSelected(null);
    await loadLists();
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
          <button key={item.id} className={view === item.id && !selected ? "active" : ""} onClick={() => openView(item.id)}>
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
          {selected ? (
            <Detail item={selected} onBack={() => setSelected(null)} />
          ) : view === "home" ? (
            <>
              <div className="top"><h2>Home</h2></div>
              <div className="stats">
                <div className="stat"><span>Ready</span><strong>{counts.Ready}</strong></div>
                <div className="stat"><span>Deploying</span><strong>{counts.Deploying}</strong></div>
                <div className="stat"><span>Expired</span><strong>{counts.Expired}</strong></div>
              </div>
              <EnvironmentTable environments={environments} onOpen={openEnvironment} onCopy={onCopy} onDelete={onDelete} />
            </>
          ) : view === "environments" ? (
            <>
              <div className="top">
                <h2>Demo Environments</h2>
                <button className="primary" onClick={() => openView("create")}>
                  <PlusIcon /> Create Demo
                </button>
              </div>
              <EnvironmentTable environments={environments} onOpen={openEnvironment} onCopy={onCopy} onDelete={onDelete} />
            </>
          ) : view === "create" ? (
            <>
              <div className="top"><h2>Create Demo</h2></div>
              <p className="note">Registers the demo in the control plane. The tenant resource group is created later.</p>
              <form className="form" onSubmit={onCreate}>
                <label>
                  Name
                  <input value={name} onChange={(event) => setName(event.target.value)} placeholder="Molina Demo" />
                </label>
                <label>
                  Customer
                  <select value={customerId} onChange={(event) => setCustomerId(event.target.value)}>
                    {customers.map((customer) => (
                      <option key={customer.id} value={customer.id}>{customer.name}</option>
                    ))}
                  </select>
                </label>
                <label>
                  Template
                  <select value={templateId} onChange={(event) => setTemplateId(event.target.value)}>
                    {templates.map((template) => (
                      <option key={template.id} value={template.id}>{template.name}</option>
                    ))}
                  </select>
                </label>
                <button className="primary" type="submit"><PlusIcon /> Create Demo</button>
              </form>
            </>
          ) : view === "templates" ? (
            <>
              <div className="top"><h2>Templates</h2></div>
              <div className="table-wrap">
                <table>
                  <thead><tr><th>Name</th><th>Channels</th><th>Status</th></tr></thead>
                  <tbody>
                    {templates.map((template) => (
                      <tr key={template.id}>
                        <td>{template.name}</td>
                        <td>{template.definition.channels?.join(", ")}</td>
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
  onCopy,
  onDelete,
}: {
  environments: EnvironmentSummary[];
  onOpen: (id: string) => void;
  onCopy: (environment: EnvironmentSummary) => void;
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
            return (
              <tr key={environment.id}>
                <td>{environment.name}</td>
                <td>{customerLabel(environment.customerName)}</td>
                <td>
                  <span className="status">
                    <span className={`dot ${status.toLowerCase()}`} />
                    {status}
                  </span>
                </td>
                <td>
                  <div className="actions">
                    <button className="icon" aria-label={`Open ${environment.name}`} onClick={() => onOpen(environment.id)}><PlayIcon /></button>
                    <button className="icon" aria-label={`Copy ${environment.name}`} onClick={() => onCopy(environment)}><CopyIcon /></button>
                    <button className="icon danger" aria-label={`Delete ${environment.name}`} onClick={() => onDelete(environment)}><TrashIcon /></button>
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

function Detail({ item, onBack }: { item: EnvironmentDetail; onBack: () => void }) {
  const cost = item.usage.reduce((sum, row) => sum + row.cost, 0);
  const status = shownStatus(item);
  return (
    <>
      <button className="back" onClick={onBack}>Back</button>
      <div className="top">
        <h2>{item.name}</h2>
        <span className="status"><span className={`dot ${status.toLowerCase()}`} />{status}</span>
      </div>
      <p className="note">{customerLabel(item.customerName)} · {item.templateName}</p>
      <section className="panel">
        <h3>Deployment</h3>
        {item.deployments.map((log) => (
          <p key={log.id} className="meta">{log.action} · {log.status}. {log.message}</p>
        ))}
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
function PlayIcon() {
  return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="m8 6 10 6-10 6V6Z" /></svg>;
}
function CopyIcon() {
  return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><rect x="8" y="8" width="11" height="11" rx="2" /><path d="M5 15V6a2 2 0 0 1 2-2h9" /></svg>;
}
function TrashIcon() {
  return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M5 7h14" /><path d="M9 7V5h6v2" /><path d="M8 7l1 12h6l1-12" /></svg>;
}
