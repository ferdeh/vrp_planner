import { formatNumber } from "../../lib/format";
import type { ScenarioDetailResponse } from "../../types/api";

type MetricConfig = {
  key: string;
  title: string;
  unit: string;
  value: (scenario: ScenarioDetailResponse, truckLabel: string) => number;
};

const metricConfigs: MetricConfig[] = [
  {
    key: "load",
    title: "Load per Mobil",
    unit: "KL",
    value: (scenario, truckLabel) =>
      scenario.route_details.find((route) => (route.no_polisi || route.truck_id) === truckLabel)?.total_load ?? 0,
  },
  {
    key: "utilization",
    title: "Utilisasi per Mobil",
    unit: "%",
    value: (scenario, truckLabel) =>
      scenario.route_details.find((route) => (route.no_polisi || route.truck_id) === truckLabel)?.utilization_percent ?? 0,
  },
  {
    key: "distance",
    title: "Jarak per Mobil",
    unit: "km",
    value: (scenario, truckLabel) =>
      scenario.route_details.find((route) => (route.no_polisi || route.truck_id) === truckLabel)?.route_distance ?? 0,
  },
  {
    key: "time",
    title: "Waktu Tempuh per Mobil",
    unit: "min",
    value: (scenario, truckLabel) =>
      scenario.route_details.find((route) => (route.no_polisi || route.truck_id) === truckLabel)?.route_time ?? 0,
  },
];

const scenarioColorClasses = [
  "from-sky-500 to-cyan-500",
  "from-emerald-500 to-teal-500",
  "from-violet-500 to-indigo-500",
  "from-amber-500 to-orange-500",
  "from-rose-500 to-pink-500",
  "from-slate-500 to-slate-700",
];

function shortScenarioLabel(scenario: ScenarioDetailResponse) {
  return `${scenario.dispatch_date} • ${scenario.scenario_id.slice(0, 8)}`;
}

function ComparisonMetricChart({
  scenarios,
  metric,
}: {
  scenarios: ScenarioDetailResponse[];
  metric: MetricConfig;
}) {
  const truckLabels = Array.from(
    new Set(
      scenarios.flatMap((scenario) =>
        scenario.route_details.map((route) => route.no_polisi || route.truck_id),
      ),
    ),
  );

  const maxValue = Math.max(
    1,
    ...truckLabels.flatMap((truckLabel) =>
      scenarios.map((scenario) => metric.value(scenario, truckLabel)),
    ),
  );

  return (
    <div className="rounded-[24px] border border-slate-200/80 bg-slate-50/90 p-5 shadow-sm">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h3 className="text-sm font-semibold uppercase tracking-[0.2em] text-slate-500">{metric.title}</h3>
        <span className="rounded-full bg-white px-3 py-1 text-xs font-semibold text-slate-500 shadow-sm">
          Unit {metric.unit}
        </span>
      </div>

      <div className="mb-4 flex flex-wrap gap-2">
        {scenarios.map((scenario, index) => (
          <div
            key={scenario.scenario_id}
            className="flex items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-1 text-xs text-slate-600 shadow-sm"
          >
            <span
              className={`inline-flex h-2.5 w-2.5 rounded-full bg-gradient-to-r ${
                scenarioColorClasses[index % scenarioColorClasses.length]
              }`}
            />
            <span className="font-semibold">{shortScenarioLabel(scenario)}</span>
          </div>
        ))}
      </div>

      <div className="space-y-5">
        {truckLabels.map((truckLabel) => (
          <div key={`${metric.key}-${truckLabel}`} className="space-y-2">
            <div className="text-sm font-semibold text-ink">{truckLabel}</div>
            <div className="space-y-2">
              {scenarios.map((scenario, index) => {
                const rawValue = metric.value(scenario, truckLabel);
                const width = rawValue > 0 ? Math.max((rawValue / maxValue) * 100, 8) : 0;
                return (
                  <div key={`${metric.key}-${truckLabel}-${scenario.scenario_id}`} className="grid gap-3 md:grid-cols-[160px_1fr_88px] md:items-center">
                    <div className="text-xs font-medium text-slate-500">{shortScenarioLabel(scenario)}</div>
                    <div className="h-3 rounded-full bg-white shadow-inner">
                      {rawValue > 0 ? (
                        <div
                          className={`h-3 rounded-full bg-gradient-to-r ${
                            scenarioColorClasses[index % scenarioColorClasses.length]
                          }`}
                          style={{ width: `${width}%` }}
                        />
                      ) : (
                        <div className="h-3 rounded-full border border-dashed border-slate-200 bg-transparent" />
                      )}
                    </div>
                    <div className="text-right text-xs font-semibold text-slate-600">
                      {rawValue > 0 ? `${formatNumber(rawValue)} ${metric.unit}` : "-"}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function ScenarioFleetComparisonCharts({
  scenarios,
}: {
  scenarios: ScenarioDetailResponse[];
}) {
  if (!scenarios.length) {
    return null;
  }

  return (
    <section className="panel">
      <div className="panel-header">
        <h2 className="text-xl font-semibold text-ink">Grafik Armada Comparison</h2>
        <p className="mt-2 text-sm text-slate-500">
          Mobil yang sama digabung dalam baris yang sama, dengan warna berbeda untuk tiap scenario.
        </p>
      </div>
      <div className="panel-body grid gap-4 xl:grid-cols-2">
        {metricConfigs.map((metric) => (
          <ComparisonMetricChart key={metric.key} scenarios={scenarios} metric={metric} />
        ))}
      </div>
    </section>
  );
}
