import { Link, Route, Routes, useLocation } from "react-router-dom";
import { DemoDetail } from "./pages/DemoDetail";
import { DemoList } from "./pages/DemoList";
import { SharePage } from "./pages/SharePage";

export function App() {
  const { pathname } = useLocation();
  const isShare = pathname.startsWith("/share/");
  return (
    <>
      {!isShare && (
        <header className="topbar">
          <Link to="/" className="brand">
            <span className="brand-mark">✚</span> Healthcare Platform Factory
          </Link>
          <span className="tagline">Describe a demo. We build it.</span>
        </header>
      )}
      <main className={isShare ? "page share" : "page"}>
        <Routes>
          <Route path="/" element={<DemoList />} />
          <Route path="/demos/:id" element={<DemoDetail />} />
          <Route path="/share/:token" element={<SharePage />} />
          <Route
            path="*"
            element={
              <div className="card">
                <h2>Page not found</h2>
                <Link to="/">Back to demos</Link>
              </div>
            }
          />
        </Routes>
      </main>
    </>
  );
}
