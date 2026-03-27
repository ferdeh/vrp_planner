import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { MetricCard } from "../components/cards/MetricCard";
import { AppLayout } from "../components/layout/AppLayout";
import { PageHeader } from "../components/layout/PageHeader";
import { ScenariosTable } from "../components/tables/ScenariosTable";
import { listScenarios } from "../services/api";

export function DashboardPage() {
  const [selectedScenarioIds, setSelectedScenarioIds] = useState<string[]>([]);
  const scenariosQuery = useQuery({
    queryKey: ["scenarios"],
    queryFn: listScenarios,
  });

  const items = scenariosQuery.data?.items ?? [];
  const summary = scenariosQuery.data?.summary;

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
          {scenariosQuery.isLoading ? (
            <p className="text-sm text-slate-500">Memuat scenario...</p>
          ) : items.length ? (
            <ScenariosTable
              items={items.slice(0, 5)}
              selectedIds={selectedScenarioIds}
              onSelectionChange={setSelectedScenarioIds}
            />
          ) : (
            <p className="text-sm text-slate-500">Belum ada scenario. Mulai dari optimisasi baru.</p>
          )}
        </div>
      </section>
    </AppLayout>
  );
}
