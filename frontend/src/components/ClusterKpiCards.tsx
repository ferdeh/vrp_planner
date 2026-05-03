import { formatNumber } from "../lib/format";
import type { ClusterMetricsSummary } from "../types/api";
import { formatPercent } from "./clusterMetricsShared";

type KpiConfig = {
  key: string;
  label: string;
  value: string;
  tone: "good" | "bad" | "neutral";
  tooltip?: string;
  featured?: boolean;
};

function toneClass(tone: KpiConfig["tone"]) {
  if (tone === "good") {
    return "border-emerald-200 bg-emerald-50/70 text-emerald-700";
  }
  if (tone === "bad") {
    return "border-rose-200 bg-rose-50/70 text-rose-700";
  }
  return "border-slate-200 bg-slate-50/80 text-slate-600";
}

export function ClusterKpiCards({
  summary,
}: {
  summary: ClusterMetricsSummary;
}) {
  const adherence = summary.cluster_adherence ?? null;
  const utilization = summary.truck_utilization ?? null;

  const items: KpiConfig[] = [
    {
      key: "cluster_adherence",
      label: "Cluster Adherence",
      value: formatPercent(adherence, 0),
      tone: adherence != null && adherence >= 0.8 ? "good" : "bad",
      tooltip: "Cluster Adherence = percentage of route movements within same cluster",
      featured: true,
    },
    {
      key: "cross_cluster_moves",
      label: "Cross Cluster Moves",
      value: formatNumber(summary.cross_cluster_moves),
      tone: summary.cross_cluster_moves <= 3 ? "good" : "bad",
    },
    {
      key: "total_distance",
      label: "Total Distance",
      value: `${formatNumber(summary.total_distance)} km`,
      tone: "neutral",
    },
    {
      key: "total_trips",
      label: "Total Trips",
      value: formatNumber(summary.total_trips),
      tone: "neutral",
    },
    {
      key: "truck_utilization",
      label: "Truck Utilization",
      value: formatPercent(utilization == null ? null : utilization / 100, 0),
      tone: utilization != null && utilization >= 75 ? "good" : "neutral",
    },
  ];

  return (
    <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
      {items.map((item) => (
        <div
          key={item.key}
          className={`rounded-[24px] border p-5 shadow-sm ${toneClass(item.tone)} ${
            item.featured ? "xl:col-span-1" : ""
          }`}
          title={item.tooltip}
        >
          <div className="flex items-start justify-between gap-3">
            <p className="text-[11px] font-semibold uppercase tracking-[0.24em]">{item.label}</p>
            {item.tooltip ? (
              <span className="inline-flex h-6 w-6 items-center justify-center rounded-full bg-white/80 text-xs font-bold text-slate-500">
                ?
              </span>
            ) : null}
          </div>
          <p className="mt-4 text-3xl font-semibold text-ink">{item.value}</p>
          {item.featured ? (
            <p className="mt-2 text-sm text-slate-500">
              Prioritaskan KPI ini untuk menilai apakah rute makin lokal.
            </p>
          ) : null}
        </div>
      ))}
    </section>
  );
}
