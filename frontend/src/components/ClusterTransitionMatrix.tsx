import type { ClusterMetricsCluster, ClusterMetricsEdge } from "../types/api";
import { emptyChart } from "./clusterMetricsShared";

export function ClusterTransitionMatrix({
  clusters,
  edges,
}: {
  clusters: ClusterMetricsCluster[];
  edges: ClusterMetricsEdge[];
}) {
  if (!clusters.length) {
    return (
      <section className="panel">
        <div className="panel-header">
          <h3 className="text-lg font-semibold text-ink">Cross Cluster Matrix</h3>
        </div>
        <div className="panel-body">{emptyChart("Belum ada matrix transisi antar cluster.")}</div>
      </section>
    );
  }

  const clusterIds = clusters.map((cluster) => cluster.cluster_id);
  const counts = new Map<string, number>();
  let maxValue = 0;

  for (const edge of edges) {
    if (!edge.from_cluster || !edge.to_cluster) {
      continue;
    }
    const key = `${edge.from_cluster}::${edge.to_cluster}`;
    const nextValue = (counts.get(key) ?? 0) + 1;
    counts.set(key, nextValue);
    maxValue = Math.max(maxValue, nextValue);
  }

  return (
    <section className="panel">
      <div className="panel-header">
        <h3 className="text-lg font-semibold text-ink">Cross Cluster Matrix</h3>
        <p className="mt-2 text-sm text-slate-500">Sel merah di luar diagonal menunjukkan leakage tertinggi.</p>
      </div>
      <div className="panel-body">
        <div className="table-shell bg-transparent shadow-none">
          <table>
            <thead>
              <tr>
                <th>From \\ To</th>
                {clusterIds.map((clusterId) => (
                  <th key={clusterId}>{clusterId}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {clusterIds.map((fromCluster) => (
                <tr key={fromCluster}>
                  <td className="font-semibold text-ink">{fromCluster}</td>
                  {clusterIds.map((toCluster) => {
                    const value = counts.get(`${fromCluster}::${toCluster}`) ?? 0;
                    const intensity = maxValue === 0 ? 0 : value / maxValue;
                    const isDiagonal = fromCluster === toCluster;
                    return (
                      <td
                        key={`${fromCluster}-${toCluster}`}
                        className="text-center font-semibold"
                        style={{
                          backgroundColor: isDiagonal
                            ? `rgba(15, 118, 110, ${0.12 + intensity * 0.18})`
                            : `rgba(220, 38, 38, ${0.06 + intensity * 0.48})`,
                        }}
                      >
                        {value}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}
