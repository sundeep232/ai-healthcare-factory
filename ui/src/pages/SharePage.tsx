import { useParams } from "react-router-dom";
import { api } from "../api";
import { CertificationSummary, CheckList, CountTable, ResourceTable, fmtDate } from "../components";
import { useLoad } from "../hooks";

/** Public, read-only view of a published demo. No admin links, no controls. */
export function SharePage() {
  const { token = "" } = useParams();
  const m = useLoad(() => api.shared(token), [token]);

  if (m.loading && !m.data) return <p className="muted">Loading…</p>;
  if (!m.data) {
    return (
      <div className="card">
        <h2>This link is not available</h2>
        <p className="muted">
          {m.error?.status === 404
            ? "The share link does not exist or was revoked by its owner."
            : (m.error?.message ?? "Something went wrong.")}
        </p>
      </div>
    );
  }
  const d = m.data;

  return (
    <>
      <section className="card hero">
        <p className="eyebrow">Healthcare demo environment</p>
        <h1>{d.demo_name}</h1>
        <p>{d.summary}</p>
        <p className="muted">
          For {d.target_audience} · {d.region} · published {fmtDate(d.published_at)}
        </p>
        <div className="notice">{d.synthetic_data_notice}</div>
      </section>

      {d.endpoints.length > 0 && (
        <section className="card">
          <h3>Try it</h3>
          <ul className="endpoints">
            {d.endpoints.map((e) => (
              <li key={e.name}>
                <span className="muted">{e.name.replace(/_url$/, "").replace(/_/g, " ")}</span>{" "}
                <a href={e.url} target="_blank" rel="noreferrer">
                  {e.url}
                </a>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="card">
        <h3>Independent verification</h3>
        <CertificationSummary summary={d.certification.summary} passed={d.certification.passed} />
        <p className="muted">
          These checks were run against the live environment on {fmtDate(d.certification.certified_at)}: data
          integrity, business rules, proof that the data is synthetic, and security posture.
        </p>
        <CheckList checks={d.certification.checks} />
      </section>

      <section className="card">
        <h3>What was built</h3>
        <ResourceTable resources={d.resources} />
      </section>

      {d.tables.length > 0 && (
        <section className="card">
          <h3>Synthetic data</h3>
          <p className="muted">
            {d.domains.join(", ").replace(/_/g, " ")}
            {d.data_as_of && ` · history as of ${d.data_as_of}`}
          </p>
          <CountTable rows={d.tables} />
        </section>
      )}

      <section className="card">
        <h3>Goals</h3>
        <ul>
          {d.business_goals.map((g) => (
            <li key={g}>{g}</li>
          ))}
        </ul>
      </section>
    </>
  );
}
