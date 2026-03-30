import { Link, NavLink } from "react-router-dom";

const navigation = [
  { to: "/", label: "Dashboard" },
  { to: "/new-optimization", label: "Optimisasi Baru" },
  { to: "/scenarios", label: "Scenario" },
  { to: "/scenario-analysis", label: "Scenario Analysis" },
  { to: "/user-guide", label: "Panduan User" },
  { to: "/settings", label: "Settings" },
];

export function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-transparent">
      <div className="mx-auto flex min-h-screen max-w-[1480px] flex-col gap-6 px-4 py-5 xl:px-6">
        <header className="overflow-hidden rounded-[32px] border border-petroblue/10 bg-[linear-gradient(180deg,#ffffff_0%,#f7faf8_100%)] text-petroink shadow-2xl shadow-slate-200/70">
          <div className="border-b border-slate-200/80 bg-[radial-gradient(circle_at_top_left,rgba(184,210,17,0.18),transparent_34%),radial-gradient(circle_at_top_right,rgba(11,115,191,0.12),transparent_38%),linear-gradient(180deg,#ffffff_0%,#f7faf8_100%)] px-6 py-6">
            <div className="flex flex-col gap-5 lg:flex-row lg:items-center lg:justify-between">
              <div className="min-w-0">
                <div className="inline-flex rounded-full border border-petrolime/40 bg-petrolime/10 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.28em] text-petroblue">
                  Petrofin Dispatch
                </div>
                <Link to="/" className="mt-4 block">
                  <img
                    src="/petrofin-logo.png"
                    alt="Petrofin"
                    className="h-auto w-full max-w-[220px] sm:max-w-[260px]"
                  />
                </Link>
                <p className="mt-4 max-w-2xl text-sm leading-6 text-slate-600">
                  VRP planner untuk dispatch harian armada BBM berbasis OR-Tools.
                </p>
              </div>

              <nav className="-mx-2 flex gap-2 overflow-x-auto px-2 pb-1 lg:mx-0 lg:max-w-[60%] lg:flex-wrap lg:justify-end lg:px-0">
                {navigation.map((item) => (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    className={({ isActive }) =>
                      `whitespace-nowrap rounded-full px-4 py-3 text-sm font-semibold transition ${
                        isActive
                          ? "bg-gradient-to-r from-petrolime/85 to-lime-300 text-petroink shadow-lg shadow-lime-100"
                          : "border border-transparent bg-white/80 text-slate-600 hover:border-petrolime/40 hover:bg-petrocloud hover:text-petroblue"
                      }`
                    }
                  >
                    {item.label}
                  </NavLink>
                ))}
              </nav>
            </div>
          </div>
        </header>

        <main className="space-y-6 pb-6">
          {children}
        </main>
      </div>
    </div>
  );
}
