import { useState } from "react";
import type { Action } from "./stages";
import { STATUS_LABEL, type Stage } from "./stages";
import type { Check, CheckCategory, CheckStatus, DemoStatus, Resource } from "./types";

export function StatusBadge({ status }: { status: DemoStatus }) {
  return <span className={`badge status-${status}`}>{STATUS_LABEL[status]}</span>;
}

export function Stepper({ stages }: { stages: Stage[] }) {
  return (
    <ol className="stepper" aria-label="Progress">
      {stages.map((s, i) => (
        <li key={s.id} className={`step step-${s.state}`} aria-current={s.state === "current" ? "step" : undefined}>
          <span className="step-dot">{s.state === "done" ? "✓" : s.state === "failed" ? "!" : i + 1}</span>
          <span className="step-label">{s.label}</span>
        </li>
      ))}
    </ol>
  );
}

/** A button that asks "are you sure?" inline before running a costly or destructive action. */
export function ActionButton({
  action,
  primary,
  disabled,
  onRun,
}: {
  action: Action;
  primary?: boolean;
  disabled?: boolean;
  onRun: (a: Action) => void;
}) {
  const [asking, setAsking] = useState(false);
  const cls = action.danger ? "btn danger" : primary ? "btn primary" : "btn";
  if (asking && action.confirm) {
    return (
      <span className="confirm-box" role="alertdialog" aria-label={`Confirm ${action.label}`}>
        <span>{action.confirm}</span>
        <button
          className={action.danger ? "btn danger" : "btn primary"}
          onClick={() => {
            setAsking(false);
            onRun(action);
          }}
        >
          Yes, {action.label.toLowerCase()}
        </button>
        <button className="btn" onClick={() => setAsking(false)}>
          Cancel
        </button>
      </span>
    );
  }
  return (
    <button className={cls} disabled={disabled} onClick={() => (action.confirm ? setAsking(true) : onRun(action))}>
      {action.label}
    </button>
  );
}

export function Banner({ kind, children }: { kind: "error" | "warn" | "ok" | "info"; children: React.ReactNode }) {
  return (
    <div className={`banner banner-${kind}`} role={kind === "error" ? "alert" : "status"}>
      {children}
    </div>
  );
}

const CHECK_ICON: Record<CheckStatus, string> = { pass: "✓", warn: "!", fail: "✕", skip: "–" };
const CATEGORY_LABEL: Record<CheckCategory, string> = {
  deployment: "Deployment",
  data: "Data",
  security: "Security",
};

export function CheckList({ checks }: { checks: Check[] }) {
  const categories = (Object.keys(CATEGORY_LABEL) as CheckCategory[]).filter((c) =>
    checks.some((k) => k.category === c),
  );
  return (
    <div className="checks">
      {categories.map((cat) => (
        <section key={cat}>
          <h4>{CATEGORY_LABEL[cat]}</h4>
          <ul>
            {checks
              .filter((c) => c.category === cat)
              .map((c) => (
                <li key={c.id} className={`check check-${c.status}`}>
                  <span className="check-icon" aria-label={c.status}>
                    {CHECK_ICON[c.status]}
                  </span>
                  <div>
                    <div className="check-title">{c.title}</div>
                    <div className="muted">{c.summary}</div>
                    {c.detail && <pre className="detail">{c.detail}</pre>}
                  </div>
                </li>
              ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

export function ResourceTable({ resources }: { resources: Resource[] }) {
  return (
    <table>
      <thead>
        <tr>
          <th>Name</th>
          <th>Type</th>
          <th>SKU</th>
          <th>Purpose</th>
        </tr>
      </thead>
      <tbody>
        {resources.map((r) => (
          <tr key={r.id}>
            <td>{r.name}</td>
            <td>
              <code>{r.type}</code>
            </td>
            <td>{r.sku ?? "–"}</td>
            <td>{r.purpose}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function CountTable({ rows }: { rows: { name: string; rows: number }[] }) {
  return (
    <table className="narrow">
      <thead>
        <tr>
          <th>Table</th>
          <th className="num">Rows</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((t) => (
          <tr key={t.name}>
            <td>
              <code>{t.name}</code>
            </td>
            <td className="num">{t.rows.toLocaleString()}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function SampleTable({ rows }: { rows: Record<string, unknown>[] }) {
  const first = rows[0];
  if (!first) return <p className="muted">No rows.</p>;
  const cols = Object.keys(first);
  return (
    <div className="scroll">
      <table className="sample">
        <thead>
          <tr>
            {cols.map((c) => (
              <th key={c}>{c}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              {cols.map((c) => (
                <td key={c}>{r[c] === null ? "–" : String(r[c])}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function CertificationSummary({ summary, passed }: { summary: Record<CheckStatus, number>; passed: boolean }) {
  return (
    <div className={`verdict ${passed ? "verdict-ok" : "verdict-bad"}`}>
      <strong>{passed ? "Certified" : "Not certified"}</strong>
      <span>
        {summary.pass} passed · {summary.warn} warnings · {summary.fail} failed
        {summary.skip ? ` · ${summary.skip} not applicable` : ""}
      </span>
    </div>
  );
}

export const fmtDate = (iso: string): string => new Date(iso).toLocaleString();
