import { useQueries } from "@tanstack/react-query";
import { Link, useLocation } from "react-router-dom";
import { ScenarioFleetComparisonCharts } from "../components/cards/ScenarioFleetComparisonCharts";
import { AppLayout } from "../components/layout/AppLayout";
import { PageHeader } from "../components/layout/PageHeader";
import { formatCurrency, formatNumber, statusClass } from "../lib/format";
import { getScenario } from "../services/api";

function useScenarioIds() {
  const location = useLocation();
  const params = new URLSearchParams(location.search);
  const ids = (params.get("ids") ?? "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  return Array.from(new Set(ids));
}

function getTotalUnservedDemand(scenario: { unserved_orders: Array<{ demand_kl: number }> }) {
  return scenario.unserved_orders.reduce((sum, item) => sum + item.demand_kl, 0);
}

function formatDepotOperationWindow(scenario: {
  total_depot_operation_time_minutes: number;
  depot_operation_start?: string | null;
  depot_operation_end?: string | null;
}) {
  if (!scenario.depot_operation_start || !scenario.depot_operation_end) {
    return "Tidak ada operasi depot";
  }

  return `${scenario.depot_operation_start} - ${scenario.depot_operation_end} (${formatNumber(scenario.total_depot_operation_time_minutes)} min)`;
}

export function ScenarioComparePage() {
  const scenarioIds = useScenarioIds();
  const scenarioQueries = useQueries({
    queries: scenarioIds.map((scenarioId) => ({
      queryKey: ["scenario", scenarioId],
      queryFn: () => getScenario(scenarioId),
      enabled: Boolean(scenarioId),
    })),
  });

  const isLoading = scenarioQueries.some((query) => query.isLoading);
  const scenarios = scenarioQueries
    .map((query) => query.data)
    .filter((item): item is NonNullable<typeof item> => Boolean(item));

  return (
    <AppLayout>
      <PageHeader
        title="Scenario Compare"
        description="Dashboard perbandingan summary dan grafik armada untuk scenario yang dipilih."
        action={
          <Link className="btn-secondary" to="/scenarios">
            Kembali ke Scenario List
          </Link>
        }
      />

      {scenarioIds.length < 2 ? (
        <section className="panel">
          <div className="panel-body text-sm text-slate-500">
            Pilih minimal 2 scenario dari daftar scenario untuk melakukan compare.
          </div>
        </section>
      ) : isLoading ? (
        <section className="panel">
          <div className="panel-body text-sm text-slate-500">Memuat data compare scenario...</div>
        </section>
      ) : (
        <>
          <section className="panel">
            <div className="panel-header">
              <h2 className="text-xl font-semibold text-ink">Summary Comparison</h2>
            </div>
            <div className="panel-body overflow-x-auto">
              <table>
                <thead>
                  <tr>
                    <th>Metric</th>
                    {scenarios.map((scenario) => (
                      <th key={scenario.scenario_id}>
                        <div className="space-y-2">
                          <div className="font-mono text-[11px] normal-case tracking-normal text-slate-500">
                            {scenario.scenario_id}
                          </div>
                          <div>{scenario.dispatch_date}</div>
                          <div className="text-[11px] normal-case tracking-normal text-slate-500">
                            Depot {scenario.depot_id}
                          </div>
                        </div>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td>Status</td>
                    {scenarios.map((scenario) => (
                      <td key={`${scenario.scenario_id}-status`}>
                        <span className={`rounded-full px-3 py-1 text-xs font-semibold ${statusClass(scenario.status)}`}>
                          {scenario.status}
                        </span>
                      </td>
                    ))}
                  </tr>
                  <tr>
                    <td>Active Truck</td>
                    {scenarios.map((scenario) => (
                      <td key={`${scenario.scenario_id}-active-truck`}>{scenario.active_truck_count}</td>
                    ))}
                  </tr>
                  <tr>
                    <td>Demand Delivered</td>
                    {scenarios.map((scenario) => (
                      <td key={`${scenario.scenario_id}-delivered`}>
                        {formatNumber(scenario.total_delivered_demand)} KL
                      </td>
                    ))}
                  </tr>
                  <tr>
                    <td>Unserved Orders</td>
                    {scenarios.map((scenario) => (
                      <td key={`${scenario.scenario_id}-unserved-orders`}>
                        {scenario.total_unserved_orders}
                      </td>
                    ))}
                  </tr>
                  <tr>
                    <td>Unserved Demand</td>
                    {scenarios.map((scenario) => (
                      <td key={`${scenario.scenario_id}-unserved-demand`}>
                        {formatNumber(getTotalUnservedDemand(scenario))} KL
                      </td>
                    ))}
                  </tr>
                  <tr>
                    <td>Penalty</td>
                    {scenarios.map((scenario) => (
                      <td key={`${scenario.scenario_id}-penalty`}>
                        {formatCurrency(scenario.total_penalty)}
                      </td>
                    ))}
                  </tr>
                  <tr>
                    <td>Total Cost</td>
                    {scenarios.map((scenario) => (
                      <td key={`${scenario.scenario_id}-cost`}>{formatCurrency(scenario.total_cost)}</td>
                    ))}
                  </tr>
                  <tr>
                    <td>Total Distance</td>
                    {scenarios.map((scenario) => (
                      <td key={`${scenario.scenario_id}-distance`}>
                        {formatNumber(scenario.total_distance)} km
                      </td>
                    ))}
                  </tr>
                  <tr>
                    <td>Total Time</td>
                    {scenarios.map((scenario) => (
                      <td key={`${scenario.scenario_id}-time`}>
                        {formatNumber(scenario.total_time)} min
                      </td>
                    ))}
                  </tr>
                  <tr>
                    <td>Depot Operation</td>
                    {scenarios.map((scenario) => (
                      <td key={`${scenario.scenario_id}-depot-operation`}>
                        {formatDepotOperationWindow(scenario)}
                      </td>
                    ))}
                  </tr>
                  <tr>
                    <td>Runtime</td>
                    {scenarios.map((scenario) => (
                      <td key={`${scenario.scenario_id}-runtime`}>
                        {formatNumber(scenario.solver_runtime_seconds)} s
                      </td>
                    ))}
                  </tr>
                </tbody>
              </table>
            </div>
          </section>

          <ScenarioFleetComparisonCharts scenarios={scenarios} />
        </>
      )}
    </AppLayout>
  );
}
