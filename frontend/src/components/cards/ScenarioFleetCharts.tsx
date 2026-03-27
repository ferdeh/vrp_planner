import { formatNumber } from "../../lib/format";
import type { RouteDetailResponse } from "../../types/api";

type MetricConfig = {
  key: string;
  title: string;
  unit: string;
  colorClass: string;
  value: (route: RouteDetailResponse) => number;
};

const metricConfigs: MetricConfig[] = [
  {
    key: "load",
    title: "Load per Mobil",
    unit: "KL",
    colorClass: "from-sky-500 to-cyan-500",
    value: (route) => route.total_load,
  },
  {
    key: "utilization",
    title: "Utilisasi per Mobil",
    unit: "%",
    colorClass: "from-emerald-500 to-teal-500",
    value: (route) => route.utilization_percent,
  },
  {
    key: "distance",
    title: "Jarak per Mobil",
    unit: "km",
    colorClass: "from-violet-500 to-indigo-500",
    value: (route) => route.route_distance,
  },
  {
    key: "time",
    title: "Waktu Tempuh per Mobil",
    unit: "min",
    colorClass: "from-amber-500 to-orange-500",
    value: (route) => route.route_time,
  },
];

function MetricChart({
  title,
  unit,
  colorClass,
  routes,
  getValue,
}: {
  title: string;
  unit: string;
  colorClass: string;
  routes: RouteDetailResponse[];
  getValue: (route: RouteDetailResponse) => number;
}) {
  const maxValue = Math.max(...routes.map(getValue), 1);

  return (
    <div className="rounded-[24px] border border-slate-200/80 bg-slate-50/90 p-5 shadow-sm">
      <div className="mb-4 flex items-center justify-between gap-3">
        <h3 className="text-sm font-semibold uppercase tracking-[0.2em] text-slate-500">{title}</h3>
        <span className="rounded-full bg-white px-3 py-1 text-xs font-semibold text-slate-500 shadow-sm">
          Unit {unit}
        </span>
      </div>
      <div className="space-y-4">
        {routes.map((route) => {
          const rawValue = getValue(route);
          const width = Math.max((rawValue / maxValue) * 100, rawValue > 0 ? 8 : 0);
          const label = route.no_polisi || route.truck_id;

          return (
            <div key={`${title}-${route.truck_id}`} className="space-y-2">
              <div className="flex items-center justify-between gap-3 text-sm">
                <span className="font-semibold text-ink">{label}</span>
                <span className="text-slate-500">
                  {formatNumber(rawValue)} {unit}
                </span>
              </div>
              <div className="h-3 rounded-full bg-white shadow-inner">
                <div
                  className={`h-3 rounded-full bg-gradient-to-r ${colorClass}`}
                  style={{ width: `${width}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function ScenarioFleetCharts({
  routes,
  title = "Grafik Armada",
  subtitle,
}: {
  routes: RouteDetailResponse[];
  title?: string;
  subtitle?: string;
}) {
  if (!routes.length) {
    return null;
  }

  return (
    <section className="panel">
      <div className="panel-header">
        <h2 className="text-xl font-semibold text-ink">{title}</h2>
        {subtitle ? <p className="mt-2 text-sm text-slate-500">{subtitle}</p> : null}
      </div>
      <div className="panel-body grid gap-4 xl:grid-cols-2">
        {metricConfigs.map((metric) => (
          <MetricChart
            key={metric.key}
            title={metric.title}
            unit={metric.unit}
            colorClass={metric.colorClass}
            routes={routes}
            getValue={metric.value}
          />
        ))}
      </div>
    </section>
  );
}
