import type { SolverSettings } from "../types/api";

export function SolverRunMetrics({ settings }: { settings: SolverSettings }) {
  return (
    <section className="panel">
      <div className="panel-body">
        <p className="text-xs font-semibold uppercase tracking-[0.32em] text-sky-600">Run Metrics Preview</p>
        <div className="mt-5 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <div className="rounded-[22px] border border-slate-200 bg-white p-4 shadow-sm">
            <p className="text-xs uppercase tracking-[0.22em] text-slate-500">Mode</p>
            <p className="mt-2 text-lg font-semibold text-ink">
              {settings.use_routefinder ? "Hybrid" : "OR-Tools"}
            </p>
          </div>
          <div className="rounded-[22px] border border-slate-200 bg-white p-4 shadow-sm">
            <p className="text-xs uppercase tracking-[0.22em] text-slate-500">Cluster Mode</p>
            <p className="mt-2 text-lg font-semibold capitalize text-ink">{settings.cluster_mode}</p>
          </div>
          <div className="rounded-[22px] border border-slate-200 bg-white p-4 shadow-sm">
            <p className="text-xs uppercase tracking-[0.22em] text-slate-500">Max Cluster Size</p>
            <p className="mt-2 text-lg font-semibold text-ink">{settings.max_cluster_size}</p>
          </div>
          <div className="rounded-[22px] border border-slate-200 bg-white p-4 shadow-sm">
            <p className="text-xs uppercase tracking-[0.22em] text-slate-500">Final Solver</p>
            <p className="mt-2 text-lg font-semibold text-ink">OR-Tools</p>
          </div>
        </div>
      </div>
    </section>
  );
}
