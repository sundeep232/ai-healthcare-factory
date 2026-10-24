import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, ApiError } from "../api";
import {
  ActionButton,
  Banner,
  CertificationSummary,
  CheckList,
  CountTable,
  ResourceTable,
  SampleTable,
  StatusBadge,
  Stepper,
  fmtDate,
} from "../components";
import { useLoad } from "../hooks";
import { isBusy, primaryAction, secondaryActions, stages, type Action } from "../stages";
import type { DataPreview, Demo } from "../types";

export function DemoDetail() {
  const { id = "" } = useParams();
  const demo = useLoad(() => api.getDemo(id), [id], (d) => isBusy(d.status));
  const [pending, setPending] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  if (demo.loading && !demo.data) return <p className="muted">Loading…</p>;
  if (!demo.data) {
    return (
      <div className="card">
        <h2>{demo.error?.status === 404 ? "Demo not found" : "Could not load this demo"}</h2>
        <p className="muted">{demo.error?.message}</p>
        <Link to="/">Back to demos</Link>
      </div>
    );
  }
  const d = demo.data;

  async function run(action: Action) {
    setPending(true);
    setActionError(null);
    try {
      demo.set(await call(action, id));
    } catch (e) {
      setActionError(e instanceof ApiError ? e.message : String(e));
      await demo.reload(); // another tab may have changed the state
    } finally {
      setPending(false);
    }
  }

  const primary = primaryAction(d);
  const secondary = secondaryActions(d);
  const busy = isBusy(d.status);

  return (
    <>
      <div className="crumbs">
        <Link to="/">← All demos</Link>
      </div>
      <section className="card">
        <div className="row spread">
          <h2>{d.requirements?.demo_name ?? "Demo"}</h2>
          <StatusBadge status={d.status} />
        </div>
        <p className="muted">{d.blueprint?.summary ?? d.intent}</p>
        <Stepper stages={stages(d)} />

        {d.status === "failed" && d.error && (
          <Banner kind="error">
            <strong>{d.failed_stage ?? "Operation"} failed.</strong> {d.error}
          </Banner>
        )}
        {actionError && <Banner kind="error">{actionError}</Banner>}
        {busy && <Banner kind="info">Working in the background. This page refreshes on its own.</Banner>}

        <div className="actions">
          {primary && <ActionButton action={primary} primary disabled={pending} onRun={(a) => void run(a)} />}
          {secondary.map((a) => (
            <ActionButton key={a.key} action={a} disabled={pending} onRun={(x) => void run(x)} />
          ))}
        </div>
      </section>

      {d.publication && <ShareCard demo={d} />}
      {d.certification && (
        <section className="card">
          <h3>Certification</h3>
          <CertificationSummary summary={d.certification.summary} passed={d.certification.passed} />
          <p className="muted">
            Checked {fmtDate(d.certification.certified_at)} against the live instance
            {d.certification.data_seed !== null && ` (data seed ${d.certification.data_seed})`}.
          </p>
          <CheckList checks={d.certification.checks} />
        </section>
      )}

      {d.plan && (
        <section className="card">
          <h3>Terraform plan</h3>
          <p>
            <span className="pill add">+{d.plan.add} to create</span>{" "}
            <span className="pill change">~{d.plan.change} to change</span>{" "}
            <span className="pill destroy">−{d.plan.destroy} to destroy</span>
          </p>
        </section>
      )}

      {d.blueprint && (
        <section className="card">
          <h3>
            Blueprint <span className="muted">v{d.blueprint.version}</span>
          </h3>
          <ResourceTable resources={d.blueprint.resources} />
          {d.requirements && (d.requirements.open_questions.length > 0 || d.requirements.assumptions.length > 0) && (
            <div className="two-col">
              <NoteList title="Assumptions" items={d.requirements.assumptions} />
              <NoteList title="Open questions" items={d.requirements.open_questions} />
            </div>
          )}
        </section>
      )}

      <DataCard demo={d} />
      <Activity demo={d} />
    </>
  );
}

function call(action: Action, id: string): Promise<Demo> {
  switch (action.key) {
    case "generate":
      return api.generate(id);
    case "plan":
      return api.plan(id);
    case "deploy":
      return api.deploy(id);
    case "seed":
      return api.seed(id);
    case "certify":
      return api.certify(id);
    case "publish":
      return api.publish(id);
    case "unpublish":
      return api.unpublish(id);
    case "destroy":
      return api.destroy(id);
  }
}

function NoteList({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <div>
      <h4>{title}</h4>
      <ul>
        {items.map((i) => (
          <li key={i}>{i}</li>
        ))}
      </ul>
    </div>
  );
}

function ShareCard({ demo }: { demo: Demo }) {
  const pub = demo.publication!;
  const url = pub.share_url.startsWith("http") ? pub.share_url : `${window.location.origin}${pub.share_path}`;
  const [copied, setCopied] = useState(false);
  const isLocal = /^https?:\/\/(127\.0\.0\.1|localhost)(:|\/|$)/.test(url);
  return (
    <section className="card share-card">
      <h3>Share link</h3>
      <div className="row">
        <input readOnly value={url} onFocus={(e) => e.target.select()} aria-label="Share link" />
        <button
          className="btn"
          onClick={() => {
            void navigator.clipboard.writeText(url).then(() => {
              setCopied(true);
              setTimeout(() => setCopied(false), 1500);
            });
          }}
        >
          {copied ? "Copied" : "Copy"}
        </button>
        <a className="btn" href={pub.share_path} target="_blank" rel="noreferrer">
          Open
        </a>
      </div>
      <p className="muted">
        Anyone with this link can view the certification and demo description. It shows no credentials or server
        names. It stops working if you unpublish, reload the data, or destroy the demo. Published {fmtDate(pub.published_at)}.
      </p>
      {isLocal && (
        <p className="muted">
          This address only works on this computer. Run the share-only server (see the README) and set
          PUBLIC_BASE_URL to give people a link they can open.
        </p>
      )}
    </section>
  );
}

function DataCard({ demo }: { demo: Demo }) {
  const [preview, setPreview] = useState<DataPreview | null>(null);
  const [table, setTable] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  if (!demo.blueprint) return null;

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const p = await api.preview(demo.demo_id, 8);
      setPreview(p);
      setTable(Object.keys(p.samples)[0] ?? "");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  const loaded = demo.data?.targets.flatMap((t) => Object.entries(t.tables).map(([name, rows]) => ({ name, rows })));
  return (
    <section className="card">
      <h3>Synthetic data</h3>
      {demo.data && loaded ? (
        <>
          <p className="muted">
            Loaded {demo.data.total_rows.toLocaleString()} rows on {fmtDate(demo.data.seeded_at)} (seed{" "}
            {demo.data.seed}, history as of {demo.data.as_of}).
          </p>
          <CountTable rows={loaded} />
          {demo.data.warnings.map((w) => (
            <Banner key={w} kind="warn">
              {w}
            </Banner>
          ))}
        </>
      ) : (
        <p className="muted">
          Not loaded yet. You can preview exactly what would be generated, without touching Azure.
        </p>
      )}
      <div className="row">
        <button className="btn" disabled={loading} onClick={() => void load()}>
          {loading ? "Generating…" : preview ? "Regenerate preview" : "Preview sample data"}
        </button>
      </div>
      {error && <Banner kind="error">{error}</Banner>}
      {preview && (
        <>
          <div className="tabs" role="tablist">
            {Object.keys(preview.samples).map((t) => (
              <button
                key={t}
                role="tab"
                aria-selected={t === table}
                className={t === table ? "tab active" : "tab"}
                onClick={() => setTable(t)}
              >
                {t} <span className="muted">({preview.counts[t]?.toLocaleString()})</span>
              </button>
            ))}
          </div>
          <SampleTable rows={preview.samples[table] ?? []} />
        </>
      )}
    </section>
  );
}

function Activity({ demo }: { demo: Demo }) {
  const [log, setLog] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const events = [...demo.events].reverse();
  return (
    <section className="card">
      <h3>Activity</h3>
      <ul className="events">
        {events.map((e, i) => (
          <li key={i}>
            <span className="muted">{fmtDate(e.at)}</span> <code>{e.stage}</code> {e.message}
          </li>
        ))}
      </ul>
      {demo.instance_dir && (
        <div className="row">
          <button
            className="btn"
            onClick={() => {
              setError(null);
              api.logs(demo.demo_id).then((r) => setLog(r.log), (e: unknown) => setError(String(e)));
            }}
          >
            {log === null ? "Show Terraform log" : "Refresh log"}
          </button>
        </div>
      )}
      {error && <Banner kind="error">{error}</Banner>}
      {log !== null && <pre className="log">{log || "(empty)"}</pre>}
    </section>
  );
}
