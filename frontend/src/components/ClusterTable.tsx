import { formatNumber } from "../lib/format";
import type { ClusterMetricsCluster } from "../types/api";
import { formatPercent } from "./clusterMetricsShared";

export function ClusterTable({
  clusters,
}: {
  clusters: ClusterMetricsCluster[];
}) {
  return (
    <section className="panel">
      <div className="panel-header">
        <h3 className="text-lg font-semibold text-ink">Cluster Detail</h3>
        <p className="mt-2 text-sm text-slate-500">Table ini membantu cek cluster mana yang masih bocor walau adherence global terlihat baik.</p>
      </div>
      <div className="panel-body">
        <div className="table-shell bg-white">
          <table>
            <thead>
              <tr>
                <th>Cluster ID</th>
                <th>SPBU Count</th>
                <th>Total Demand</th>
                <th>Avg Distance</th>
                <th>Cluster Leakage</th>
              </tr>
            </thead>
            <tbody>
              {clusters.map((cluster) => (
                <tr key={cluster.cluster_id}>
                  <td className="font-semibold text-ink">{cluster.cluster_id}</td>
                  <td>{formatNumber(cluster.spbu_count)}</td>
                  <td>{formatNumber(cluster.total_demand_kl)} KL</td>
                  <td>{formatNumber(cluster.avg_distance)} km</td>
                  <td>{formatPercent(cluster.cluster_leakage, 0)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}
