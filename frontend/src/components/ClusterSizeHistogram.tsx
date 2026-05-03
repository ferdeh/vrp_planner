import { formatNumber } from "../lib/format";
import type { ClusterMetricsCluster } from "../types/api";
import { emptyChart } from "./clusterMetricsShared";

export function ClusterSizeHistogram({
  clusters,
}: {
  clusters: ClusterMetricsCluster[];
}) {
  if (!clusters.length) {
    return (
      <section className="panel">
        <div className="panel-header">
          <h3 className="text-lg font-semibold text-ink">Cluster Size Distribution</h3>
        </div>
        <div className="panel-body">{emptyChart("Belum ada distribusi ukuran cluster.")}</div>
      </section>
    );
  }

  const bins = Array.from(
    clusters.reduce((accumulator, cluster) => {
      accumulator.set(cluster.spbu_count, (accumulator.get(cluster.spbu_count) ?? 0) + 1);
      return accumulator;
    }, new Map<number, number>()),
  ).sort((left, right) => left[0] - right[0]);
  const maxFrequency = Math.max(...bins.map(([, value]) => value), 1);

  return (
    <section className="panel">
      <div className="panel-header">
        <h3 className="text-lg font-semibold text-ink">Cluster Size Distribution</h3>
        <p className="mt-2 text-sm text-slate-500">Pastikan ukuran cluster tidak terlalu berat di satu sisi jaringan.</p>
      </div>
      <div className="panel-body">
        <div className="space-y-4">
          {bins.map(([clusterSize, frequency]) => {
            const width = (frequency / maxFrequency) * 100;
            return (
              <div key={clusterSize} className="space-y-2">
                <div className="flex items-center justify-between gap-3 text-sm">
                  <span className="font-semibold text-ink">{clusterSize} SPBU</span>
                  <span className="text-slate-500">{formatNumber(frequency)} cluster</span>
                </div>
                <div className="h-4 rounded-full bg-slate-100 shadow-inner">
                  <div
                    className="h-4 rounded-full bg-gradient-to-r from-sky-600 via-cyan-500 to-emerald-400"
                    style={{ width: `${Math.max(width, 10)}%` }}
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
