import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, ApiError } from "../api";
import { Banner, StatusBadge, fmtDate } from "../components";
import { useLoad } from "../hooks";
import { isBusy } from "../stages";

const EXAMPLES = [
  "A claims dashboard for payer executives showing denial rates, paid amounts and top providers.",
  "A prior authorization demo for the utilization management team with turnaround times and care plans.",
  "A member 360 demo for care managers combining coverage, claims history and care-management notes.",
];

export function DemoList() {
  const navigate = useNavigate();
  const [intent, setIntent] = useState("");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const demos = useLoad(() => api.listDemos(), [], (list) => list.some((d) => isBusy(d.status)), 5000);

  const tooShort = intent.trim().length < 10;

  async function create() {
    setCreating(true);
    setError(null);
    try {
      const demo = await api.createDemo(intent.trim());
      navigate(`/demos/${demo.demo_id}`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
      setCreating(false);
    }
  }

  const readOnlyServer = demos.error?.status === 404 || demos.error?.status === 405;

  if (readOnlyServer) {
    return (
      <div className="card">
        <h2>Read-only share server</h2>
        <p className="muted">
          This server only hosts published demos. Open a share link you were given, or use the factory on its
          private address to create and manage demos.
        </p>
      </div>
    );
  }

  return (
    <>
      <section className="card">
        <h2>Describe the demo you need</h2>
        <p className="muted">
          Plain English is fine. The factory plans the Azure resources first and shows them to you; nothing is
          deployed until you confirm. All data is synthetic.
        </p>
        <textarea
          value={intent}
          onChange={(e) => setIntent(e.target.value)}
          placeholder="e.g. A claims dashboard for payer executives with 12 months of history…"
          rows={4}
          maxLength={4000}
          disabled={creating}
          aria-label="Demo intent"
        />
        <div className="chips">
          {EXAMPLES.map((ex) => (
            <button key={ex} className="chip" disabled={creating} onClick={() => setIntent(ex)}>
              {ex.split(" ").slice(0, 5).join(" ")}…
            </button>
          ))}
        </div>
        {error && <Banner kind="error">{error}</Banner>}
        <div className="row">
          <button className="btn primary" disabled={creating || tooShort} onClick={() => void create()}>
            {creating ? "Planning… (about 30 seconds)" : "Plan this demo"}
          </button>
          {tooShort && intent.length > 0 && <span className="muted">Add a few more words.</span>}
        </div>
      </section>

      <section className="card">
        <h2>Your demos</h2>
        {demos.loading && <p className="muted">Loading…</p>}
        {demos.error && !demos.data && <Banner kind="error">{demos.error.message}</Banner>}
        {demos.data && demos.data.length === 0 && <p className="muted">No demos yet. Describe one above.</p>}
        {demos.data && demos.data.length > 0 && (
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Status</th>
                <th>Resources</th>
                <th>Updated</th>
              </tr>
            </thead>
            <tbody>
              {demos.data.map((d) => (
                <tr key={d.demo_id}>
                  <td>
                    <Link to={`/demos/${d.demo_id}`}>{d.demo_name ?? d.demo_id}</Link>
                  </td>
                  <td>
                    <StatusBadge status={d.status} />
                  </td>
                  <td>{d.resource_count}</td>
                  <td>{fmtDate(d.updated_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </>
  );
}
