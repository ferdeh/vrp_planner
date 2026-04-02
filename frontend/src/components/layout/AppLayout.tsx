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
    <div className="planner-shell min-h-screen bg-transparent">
      <div className="relative z-[1] mx-auto flex min-h-screen max-w-[1480px] flex-col gap-6 px-4 py-5 xl:px-6">
        <header className="overflow-hidden rounded-[32px] border border-petroblue/10 bg-[linear-gradient(180deg,rgba(255,255,255,0.98)_0%,rgba(249,248,245,0.95)_100%)] text-petroink shadow-2xl shadow-slate-200/70">
          <div className="px-6 py-6">
            <div className="flex flex-col gap-6">
              <div className="flex flex-col gap-5 lg:flex-row lg:items-center lg:justify-between">
                <div className="min-w-0 max-w-3xl">
                  <div className="inline-flex rounded-full bg-petrolime/15 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.28em] text-petroblue">
                    Petrofin Planning
                  </div>
                  <h1 className="mt-4 text-4xl font-extrabold tracking-[-0.04em] text-petroink sm:text-[2.9rem]">
                    VRP Planner
                  </h1>
                  <p className="mt-3 max-w-2xl text-sm leading-7 text-slate-600 md:text-[15px]">
                    Optimisasi dispatch harian armada BBM dengan identitas visual Petrofin yang
                    selaras dengan portal dan master data.
                  </p>
                </div>

                <div className="flex flex-col gap-4 lg:items-end">
                  <Link to="/" className="block">
                    <img
                      src="/petrofin-logo.webp"
                      alt="Petrofin"
                      className="h-auto w-full max-w-[220px] sm:max-w-[260px]"
                    />
                  </Link>
                  <div className="flex flex-wrap items-center gap-2">
                    <a
                      href="/portal"
                      className="inline-flex min-h-11 items-center rounded-full border border-slate-200 bg-white/90 px-4 py-2 text-sm font-semibold text-slate-700 transition hover:border-petrolime/40 hover:bg-petrocloud hover:text-petroblue"
                    >
                      Back to Portal
                    </a>
                    <a
                      href="/api/v1/auth/logout-redirect"
                      className="inline-flex min-h-11 items-center rounded-full bg-gradient-to-r from-[#123b66] to-[#0a72bb] px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-sky-100 transition hover:from-[#0f3359] hover:to-[#085f9b]"
                    >
                      Logout
                    </a>
                  </div>
                </div>
              </div>

              <div className="h-px bg-slate-200/80" />

              <nav className="-mx-2 flex gap-2 overflow-x-auto px-2 pb-1 lg:mx-0 lg:flex-wrap lg:justify-start lg:px-0">
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

        <main className="space-y-6">
          {children}
        </main>

        <footer className="pb-6">
          <div className="flex flex-wrap items-center justify-between gap-4 rounded-[28px] border border-slate-200/80 bg-[linear-gradient(180deg,rgba(255,255,255,0.94)_0%,rgba(248,246,243,0.92)_100%)] px-5 py-4 shadow-sm">
            <div>
              <div className="inline-flex rounded-full bg-petrolime/15 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.26em] text-petroblue">
                Powered by NEURON
              </div>
              <p className="mt-2 text-sm leading-6 text-slate-600">
                Engine optimisasi untuk perencanaan rute, armada, dan orkestrasi dispatch.
              </p>
            </div>
            <img
              src="/neuron-footer.jpg"
              alt="Powered by NEURON"
              className="h-auto w-full max-w-[280px]"
            />
          </div>
        </footer>
      </div>
    </div>
  );
}
