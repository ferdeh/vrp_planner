import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MetricCard } from "../components/cards/MetricCard";
import { AppLayout } from "../components/layout/AppLayout";
import { PageHeader } from "../components/layout/PageHeader";
import { ScenariosTable } from "../components/tables/ScenariosTable";
import { deleteScenarios, listScenarios } from "../services/api";

export function DashboardPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [selectedScenarioIds, setSelectedScenarioIds] = useState<string[]>([]);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const queuedScenarioId = typeof location.state === "object" && location.state && "queuedScenarioId" in location.state
    ? String(location.state.queuedScenarioId ?? "")
    : "";
  const scenariosQuery = useQuery({
    queryKey: ["scenarios"],
    queryFn: listScenarios,
    staleTime: 0,
    refetchOnMount: "always",
    refetchOnWindowFocus: true,
    refetchInterval: 2000,
    refetchIntervalInBackground: true,
  });
  const deleteMutation = useMutation({
    mutationFn: deleteScenarios,
    onSuccess: async (result) => {
      setActionMessage(`${result.deleted_count} scenario berhasil dihapus.`);
      setSelectedScenarioIds([]);
      await queryClient.invalidateQueries({ queryKey: ["scenarios"] });
    },
    onError: () => {
      setActionMessage("Delete scenario gagal dijalankan.");
    },
  });

  const items = scenariosQuery.data?.items ?? [];
  const summary = scenariosQuery.data?.summary;
  const queuedScenarioStillProcessing = items.some(
    (item) => item.scenario_id === queuedScenarioId && item.status === "processing",
  );

  const dismissQueuedMessage = () => {
    navigate(location.pathname, { replace: true });
  };

  const handleCompare = () => {
    if (selectedScenarioIds.length > 4) {
      setActionMessage("Compare dibatasi maksimum 4 scenario.");
      return;
    }
    navigate(`/scenarios/compare?ids=${selectedScenarioIds.join(",")}`);
  };

  return (
    <AppLayout>
      <PageHeader
        title="Dashboard Dispatch"
        description="Ringkasan historis optimisasi harian dan indikator kebutuhan armada."
        action={
          <Link className="btn-primary" to="/new-optimization">
            Jalankan Optimisasi Baru
          </Link>
        }
      />

      <div className="grid gap-4 md:grid-cols-3">
        <MetricCard label="Total Scenario" value={summary?.total_scenarios ?? 0} />
        <MetricCard label="Scenario Feasible" value={summary?.feasible_scenarios ?? 0} />
        <MetricCard label="Rata-rata Truck Aktif" value={summary?.average_active_trucks ?? 0} />
      </div>

      <section className="panel overflow-hidden">
        <div className="panel-header">
          <h2 className="text-xl font-semibold text-ink">Riwayat Terbaru</h2>
        </div>
        <div className="panel-body">
          {queuedScenarioId ? (
            <div className="mb-4 flex items-center justify-between gap-3 rounded-[20px] border border-sky-200 bg-sky-50 px-4 py-3 text-sm text-sky-700">
              <span>
                {queuedScenarioStillProcessing
                  ? "Optimisasi sedang berjalan di background. Detail scenario akan berubah menjadi Lihat saat selesai."
                  : "Optimisasi selesai diproses. Detail scenario sudah bisa dibuka."}
              </span>
              <button type="button" className="font-semibold text-sky-800" onClick={dismissQueuedMessage}>
                Tutup
              </button>
            </div>
          ) : null}
          <div className="mb-4 flex flex-wrap gap-3">
            <button
              type="button"
              className="btn-secondary"
              disabled={selectedScenarioIds.length < 2}
              onClick={handleCompare}
            >
              Compare
            </button>
            <button
              type="button"
              className="btn-secondary"
              disabled={selectedScenarioIds.length < 1 || deleteMutation.isPending}
              onClick={() => deleteMutation.mutate(selectedScenarioIds)}
            >
              {deleteMutation.isPending ? "Deleting..." : "Delete"}
            </button>
          </div>
          {actionMessage ? (
            <div className="mb-4 rounded-[20px] border border-sky-200 bg-sky-50 px-4 py-3 text-sm text-sky-700">
              {actionMessage}
            </div>
          ) : null}
          {scenariosQuery.isLoading ? (
            <p className="text-sm text-slate-500">Memuat scenario...</p>
          ) : items.length ? (
            <ScenariosTable
              items={items.slice(0, 5)}
              selectedIds={selectedScenarioIds}
              onSelectionChange={(ids) => {
                setSelectedScenarioIds(ids);
                setActionMessage(null);
              }}
            />
          ) : (
            <p className="text-sm text-slate-500">Belum ada scenario. Mulai dari optimisasi baru.</p>
          )}
        </div>
      </section>
    </AppLayout>
  );
}
