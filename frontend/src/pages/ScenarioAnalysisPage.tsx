import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { AppLayout } from "../components/layout/AppLayout";
import { PageHeader } from "../components/layout/PageHeader";
import {
  analysisLevelLabel,
  analysisStatusClass,
  analysisStatusLabel,
  statusClass,
  statusLabel,
} from "../lib/format";
import { listAllScenarioAnalyses } from "../services/api";

function formatDateTime(value: string) {
  return new Intl.DateTimeFormat("id-ID", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export function ScenarioAnalysisPage() {
  const analysisQuery = useQuery({
    queryKey: ["scenario-analysis-overview"],
    queryFn: listAllScenarioAnalyses,
    refetchInterval: (query) => {
      const data = query.state.data;
      return data?.items.some((item) => item.status === "processing") ? 2000 : false;
    },
    refetchIntervalInBackground: true,
    staleTime: 0,
    refetchOnMount: "always",
    refetchOnWindowFocus: true,
  });

  const items = analysisQuery.data?.items ?? [];
  const processingCount = items.filter((item) => item.status === "processing").length;
  const completedCount = items.filter((item) => item.status === "completed").length;

  return (
    <AppLayout>
      <PageHeader
        title="Scenario Analysis"
        description="Riwayat seluruh job analysis lintas scenario, termasuk status worker dan akses cepat ke hasil diagnosis."
      />

      <div className="grid gap-4 md:grid-cols-3">
        <section className="panel">
          <div className="panel-body">
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-500">Total Job</p>
            <p className="mt-3 text-3xl font-semibold text-ink">{items.length}</p>
          </div>
        </section>
        <section className="panel">
          <div className="panel-body">
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-500">On Process</p>
            <p className="mt-3 text-3xl font-semibold text-sky-700">{processingCount}</p>
          </div>
        </section>
        <section className="panel">
          <div className="panel-body">
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-500">Completed</p>
            <p className="mt-3 text-3xl font-semibold text-emerald-700">{completedCount}</p>
          </div>
        </section>
      </div>

      <section className="panel">
        <div className="panel-body">
          {analysisQuery.isLoading ? (
            <p className="text-sm text-slate-500">Memuat list scenario analysis...</p>
          ) : items.length ? (
            <div className="table-shell bg-white">
              <table>
                <thead>
                  <tr>
                    <th>Dibuat</th>
                    <th>Scenario</th>
                    <th>Tanggal</th>
                    <th>Depot</th>
                    <th>Level</th>
                    <th>Status Scenario</th>
                    <th>Status Analysis</th>
                    <th>Catatan</th>
                    <th>Detail</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((item) => (
                    <tr key={item.analysis_id}>
                      <td>{formatDateTime(item.created_at)}</td>
                      <td className="font-mono text-xs text-ink">{item.scenario_id}</td>
                      <td>{item.dispatch_date}</td>
                      <td>{item.depot_id}</td>
                      <td>{analysisLevelLabel(item.level)}</td>
                      <td>
                        <span className={`rounded-full px-3 py-1 text-xs font-semibold ${statusClass(item.scenario_status)}`}>
                          {statusLabel(item.scenario_status)}
                        </span>
                      </td>
                      <td>
                        <span className={`rounded-full px-3 py-1 text-xs font-semibold ${analysisStatusClass(item.status)}`}>
                          {analysisStatusLabel(item.status)}
                        </span>
                      </td>
                      <td>{item.message}</td>
                      <td>
                        {item.status === "processing" ? (
                          <span className="font-semibold text-sky-700">On Process</span>
                        ) : (
                          <Link
                            className="font-semibold text-sea"
                            to={`/scenarios/${item.scenario_id}?tab=analysis&analysisId=${item.analysis_id}`}
                          >
                            Lihat
                          </Link>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-sm text-slate-500">Belum ada job scenario analysis.</p>
          )}
        </div>
      </section>
    </AppLayout>
  );
}
