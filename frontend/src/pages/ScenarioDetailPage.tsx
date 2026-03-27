import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useParams } from "react-router-dom";
import { SummaryCard } from "../components/cards/SummaryCard";
import { ScenarioFleetCharts } from "../components/cards/ScenarioFleetCharts";
import { AppLayout } from "../components/layout/AppLayout";
import { PageHeader } from "../components/layout/PageHeader";
import { RouteCard } from "../components/routes/RouteCard";
import { RouteIllustration } from "../components/routes/RouteIllustration";
import { formatCurrency, formatNumber, statusClass } from "../lib/format";
import { getScenario } from "../services/api";

type DetailTab = "summary" | "route-graph" | "route-detail" | "others";

export function ScenarioDetailPage() {
  const params = useParams();
  const scenarioId = params.scenarioId ?? "";
  const [activeTab, setActiveTab] = useState<DetailTab>("summary");
  const detailQuery = useQuery({
    queryKey: ["scenario", scenarioId],
    queryFn: () => getScenario(scenarioId),
    enabled: Boolean(scenarioId),
  });

  const detail = detailQuery.data;
  const totalUnservedDemand = detail
    ? detail.unserved_orders.reduce((sum, item) => sum + item.demand_kl, 0)
    : 0;

  return (
    <AppLayout>
      <PageHeader
        title="Scenario Detail"
        description="Ringkasan hasil solver, komposisi truck, stop order, dan parameter yang dipakai."
      />

      {detailQuery.isLoading || !detail ? (
        <section className="panel p-6 text-sm text-slate-500">Memuat detail scenario...</section>
      ) : (
        <>
          <section className="panel">
            <div className="panel-body space-y-6">
              <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                <div>
                  <p className="text-sm text-slate-500">Scenario ID</p>
                  <p className="font-mono text-sm text-ink">{detail.scenario_id}</p>
                </div>
                <span className={`rounded-full px-4 py-2 text-sm font-semibold ${statusClass(detail.status)}`}>
                  {detail.status}
                </span>
              </div>

              <div className="flex flex-wrap gap-3">
                {[
                  { key: "summary", label: "Scenario Summary" },
                  { key: "route-graph", label: "Route Grafik" },
                  { key: "route-detail", label: "Route per MT" },
                  { key: "others", label: "Lainnya" },
                ].map((tab) => (
                  <button
                    key={tab.key}
                    type="button"
                    onClick={() => setActiveTab(tab.key as DetailTab)}
                    className={
                      activeTab === tab.key
                        ? "inline-flex items-center justify-center rounded-full border border-sky-500 bg-gradient-to-r from-sky-600 to-cyan-500 px-5 py-2.5 text-sm font-semibold text-white shadow-lg shadow-sky-200"
                        : "inline-flex items-center justify-center rounded-full border border-slate-200 bg-white px-5 py-2.5 text-sm font-semibold text-slate-600 shadow-sm transition hover:border-sky-300 hover:text-sky-700"
                    }
                  >
                    {tab.label}
                  </button>
                ))}
              </div>
            </div>
          </section>

          {activeTab === "summary" ? (
            <>
              <section className="panel">
                <div className="panel-body space-y-6">
                  <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-7">
                    <SummaryCard title="Active Truck" value={String(detail.active_truck_count)} />
                    <SummaryCard title="Demand Delivered" value={`${formatNumber(detail.total_delivered_demand)} KL`} />
                    <SummaryCard
                      title="Unserved Orders"
                      value={String(detail.total_unserved_orders)}
                      subtitle={`${formatNumber(totalUnservedDemand)} KL`}
                    />
                    <SummaryCard title="Penalty" value={formatCurrency(detail.total_penalty)} />
                    <SummaryCard title="Total Cost" value={formatCurrency(detail.total_cost)} />
                    <SummaryCard
                      title="Depot Operation"
                      value={`${formatNumber(detail.total_depot_operation_time_minutes)} min`}
                      subtitle={
                        detail.depot_operation_start && detail.depot_operation_end
                          ? `${detail.depot_operation_start} - ${detail.depot_operation_end}`
                          : "Tidak ada operasi depot"
                      }
                    />
                    <SummaryCard title="Runtime" value={`${detail.solver_runtime_seconds}s`} />
                  </div>

                  <div className="grid gap-4 md:grid-cols-3">
                    {detail.active_truck_type_summary.map((item) => (
                      <SummaryCard
                        key={item.truck_type}
                        title={item.truck_type}
                        value={`${item.active_count} truck`}
                        subtitle={`Capacity aktif ${formatNumber(item.total_capacity_kl)} KL`}
                      />
                    ))}
                  </div>
                </div>
              </section>

              <ScenarioFleetCharts routes={detail.route_details} />
            </>
          ) : null}

          {activeTab === "route-graph" ? (
            <section className="panel">
              <div className="panel-header">
                <h2 className="text-xl font-semibold text-ink">Route Grafik</h2>
              </div>
              <div className="panel-body">
                {detail.route_details.length ? (
                  <RouteIllustration routes={detail.route_details} />
                ) : (
                  <p className="text-sm text-slate-500">Tidak ada route aktif.</p>
                )}
              </div>
            </section>
          ) : null}

          {activeTab === "route-detail" ? (
            <section className="panel">
              <div className="panel-header">
                <h2 className="text-xl font-semibold text-ink">Route per MT</h2>
              </div>
              <div className="panel-body space-y-4">
                {detail.route_details.length ? (
                  detail.route_details.map((route) => <RouteCard key={route.truck_id} route={route} />)
                ) : (
                  <p className="text-sm text-slate-500">Tidak ada route aktif.</p>
                )}
              </div>
            </section>
          ) : null}

          {activeTab === "others" ? (
            <>
              <section className="grid gap-6 lg:grid-cols-2">
                <div className="panel">
                  <div className="panel-header">
                    <h2 className="text-xl font-semibold text-ink">Unserved Orders</h2>
                  </div>
                  <div className="panel-body">
                    {detail.unserved_orders.length ? (
                      <div className="space-y-3">
                        {detail.unserved_orders.map((item) => (
                          <div key={item.order_id} className="rounded-3xl border border-rose-200 bg-rose-50 p-4">
                            <p className="font-semibold text-rose-700">
                              {item.order_id} · {item.spbu_id}
                            </p>
                            <p className="mt-1 text-sm text-rose-600">
                              {formatNumber(item.demand_kl)} KL · {item.reason}
                            </p>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-sm text-slate-500">Semua order terlayani.</p>
                    )}
                  </div>
                </div>

                <div className="panel">
                  <div className="panel-header">
                    <h2 className="text-xl font-semibold text-ink">Preprocessing Notes</h2>
                  </div>
                  <div className="panel-body">
                    {detail.preprocessing_notes.length ? (
                      <div className="space-y-3">
                        {detail.preprocessing_notes.map((note) => (
                          <div key={note.code + note.message} className="rounded-3xl border border-amber-200 bg-amber-50 p-4">
                            <p className="font-semibold text-amber-700">{note.code}</p>
                            <p className="mt-1 text-sm text-amber-600">{note.message}</p>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-sm text-slate-500">Tidak ada catatan preprocessing.</p>
                    )}
                  </div>
                </div>
              </section>

              <section className="grid gap-6 lg:grid-cols-2">
                <div className="panel">
                  <div className="panel-header">
                    <h2 className="text-xl font-semibold text-ink">Input Orders</h2>
                  </div>
                  <div className="panel-body space-y-3">
                    {detail.input_orders.map((order) => (
                      <div key={order.order_id} className="rounded-3xl border border-slate-200 bg-slate-50 p-4">
                        <p className="font-semibold text-ink">
                          {order.order_id} · {order.spbu_id}
                        </p>
                        <p className="mt-1 text-sm text-slate-500">
                          {order.product_type} · {formatNumber(order.demand_kl)} KL · {order.time_window_start} - {order.time_window_end}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="panel">
                  <div className="panel-header">
                    <h2 className="text-xl font-semibold text-ink">Config Snapshot</h2>
                  </div>
                  <div className="panel-body">
                    <pre className="overflow-x-auto rounded-3xl bg-ink p-4 text-xs text-white">
                      {JSON.stringify(detail.objective_config, null, 2)}
                    </pre>
                  </div>
                </div>
              </section>
            </>
          ) : null}
        </>
      )}
    </AppLayout>
  );
}
