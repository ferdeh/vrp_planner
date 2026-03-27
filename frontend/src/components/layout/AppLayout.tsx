import { useState } from "react";
import { Link, NavLink } from "react-router-dom";

const navigation = [
  { to: "/", label: "Dashboard" },
  { to: "/new-optimization", label: "Optimisasi Baru" },
  { to: "/scenarios", label: "Scenario" },
  { to: "/user-guide", label: "Panduan User" },
  { to: "/settings", label: "Settings" },
];

export function AppLayout({ children }: { children: React.ReactNode }) {
  const [sidebarOpen, setSidebarOpen] = useState(true);

  return (
    <div className="min-h-screen bg-transparent">
      <div
        className={`mx-auto grid min-h-screen max-w-[1480px] gap-6 px-4 py-5 xl:px-6 ${
          sidebarOpen ? "lg:grid-cols-[290px_1fr]" : "lg:grid-cols-[1fr]"
        }`}
      >
        {sidebarOpen ? (
          <aside className="overflow-hidden rounded-[32px] border border-petroblue/10 bg-[linear-gradient(180deg,#ffffff_0%,#f7faf8_100%)] text-petroink shadow-2xl shadow-slate-200/70">
            <div className="border-b border-slate-200/80 bg-[radial-gradient(circle_at_top_left,rgba(184,210,17,0.18),transparent_34%),radial-gradient(circle_at_top_right,rgba(11,115,191,0.12),transparent_38%),linear-gradient(180deg,#ffffff_0%,#f7faf8_100%)] px-6 py-6">
              <div className="mb-4 flex items-start justify-between gap-3">
                <div className="inline-flex rounded-full border border-petrolime/40 bg-petrolime/10 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.28em] text-petroblue">
                  Petrofin Dispatch
                </div>
                <button
                  type="button"
                  onClick={() => setSidebarOpen(false)}
                  className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-petroink transition hover:border-petrolime hover:text-petroblue"
                >
                  Hide Menu
                </button>
              </div>
              <Link to="/" className="block">
                <img
                  src="/petrofin-logo.png"
                  alt="Petrofin"
                  className="h-auto w-full max-w-[260px]"
                />
              </Link>
              <p className="mt-4 text-sm leading-6 text-slate-600">
                VRP planner untuk dispatch harian armada BBM berbasis OR-Tools.
              </p>
            </div>
            <nav className="flex flex-col gap-2 px-4 py-5">
              {navigation.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) =>
                    `rounded-2xl px-4 py-3 text-sm font-semibold transition ${
                      isActive
                        ? "bg-gradient-to-r from-petrolime/85 to-lime-300 text-petroink shadow-lg shadow-lime-100"
                        : "text-slate-600 hover:bg-petrocloud hover:text-petroblue"
                    }`
                  }
                >
                  {item.label}
                </NavLink>
              ))}
            </nav>
          </aside>
        ) : null}
        <main className="space-y-6 pb-6">
          <div className="flex items-center justify-between">
            <button
              type="button"
              onClick={() => setSidebarOpen((current) => !current)}
              className="btn-secondary"
            >
              {sidebarOpen ? "Hide Menu" : "Show Menu"}
            </button>
          </div>
          {children}
        </main>
      </div>
    </div>
  );
}
