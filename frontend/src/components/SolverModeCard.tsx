import type { SolverSettings } from "../types/api";

export function SolverModeCard({ settings }: { settings: SolverSettings }) {
  const hybrid = settings.use_routefinder;

  return (
    <section className="panel">
      <div className="panel-body space-y-4">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.32em] text-sky-600">Solver Mode</p>
            <h2 className="mt-3 text-2xl font-semibold text-ink">
              {hybrid ? "Hybrid: RouteFinder Clustering + OR-Tools" : "OR-Tools Only"}
            </h2>
            <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-600">
              RouteFinder hanya menyusun cluster SPBU. OR-Tools tetap menjadi final optimizer untuk vehicle assignment,
              multi-trip, dan route akhir.
            </p>
          </div>

          <div className={`rounded-[22px] border px-4 py-3 text-sm font-semibold ${
            hybrid
              ? "border-emerald-200 bg-emerald-50 text-emerald-700"
              : "border-slate-200 bg-slate-50 text-slate-600"
          }`}>
            {hybrid ? "Clustering enabled" : "Clustering disabled"}
          </div>
        </div>

        <div className="rounded-[24px] border border-amber-200 bg-amber-50/80 p-4 text-sm leading-6 text-amber-900">
          RouteFinder only structures the problem into SPBU clusters. OR-Tools remains the only final solver.
        </div>
      </div>
    </section>
  );
}
