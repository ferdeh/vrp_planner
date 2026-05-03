import { formatNumber } from "../lib/format";
import type { ClusterTruckMetric } from "../types/api";
import { emptyChart, formatPercent, getClusterColor } from "./clusterMetricsShared";

export function TruckPurityChart({
  truckMetrics,
}: {
  truckMetrics: ClusterTruckMetric[];
}) {
  if (!truckMetrics.length) {
    return (
      <section className="panel">
        <div className="panel-header">
          <h3 className="text-lg font-semibold text-ink">Truck Purity</h3>
        </div>
        <div className="panel-body">{emptyChart("Belum ada purity per truck.")}</div>
      </section>
    );
  }

  return (
    <section className="panel">
      <div className="panel-header">
        <h3 className="text-lg font-semibold text-ink">Truck Purity</h3>
        <p className="mt-2 text-sm text-slate-500">Semakin tinggi purity ratio, semakin konsisten truck melayani satu cluster dominan.</p>
      </div>
      <div className="panel-body">
        <div className="space-y-4">
          {truckMetrics.map((metric) => {
            const width = Math.max(metric.purity_ratio * 100, metric.total_nodes > 0 ? 8 : 0);
            return (
              <div key={metric.truck_id} className="space-y-2">
                <div className="flex items-center justify-between gap-3 text-sm">
                  <div>
                    <p className="font-semibold text-ink">{metric.no_polisi || metric.truck_id}</p>
                    <p className="text-slate-500">
                      {metric.dominant_cluster || "Unclustered"} · {formatNumber(metric.total_nodes)} node
                    </p>
                  </div>
                  <span className="text-slate-500">{formatPercent(metric.purity_ratio, 0)}</span>
                </div>
                <div className="h-4 rounded-full bg-slate-100 shadow-inner">
                  <div
                    className="h-4 rounded-full"
                    style={{
                      width: `${width}%`,
                      background: `linear-gradient(90deg, ${getClusterColor(metric.dominant_cluster)}, rgba(15, 23, 42, 0.18))`,
                    }}
                    title={`${metric.dominant_cluster_nodes}/${metric.total_nodes} node di cluster dominan`}
                  />
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
