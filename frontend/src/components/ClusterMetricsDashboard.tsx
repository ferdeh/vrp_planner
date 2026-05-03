import axios from "axios";
import { useQuery } from "@tanstack/react-query";
import { ClusterAdherenceChart } from "./ClusterAdherenceChart";
import { ClusterKpiCards } from "./ClusterKpiCards";
import { ClusterRouteMap } from "./ClusterRouteMap";
import { ClusterSizeHistogram } from "./ClusterSizeHistogram";
import { ClusterTable } from "./ClusterTable";
import { ClusterTradeoffScatter } from "./ClusterTradeoffScatter";
import { ClusterTransitionMatrix } from "./ClusterTransitionMatrix";
import { TruckPurityChart } from "./TruckPurityChart";
import { getClusterMetrics } from "../services/api";

export function ClusterMetricsDashboard({
  scenarioId,
}: {
  scenarioId: string;
}) {
  const clusterMetricsQuery = useQuery({
    queryKey: ["scenario-cluster-metrics", scenarioId],
    queryFn: () => getClusterMetrics(scenarioId),
    enabled: Boolean(scenarioId),
    retry: false,
  });

  if (clusterMetricsQuery.isLoading) {
    return <section className="panel p-6 text-sm text-slate-500">Memuat cluster metrics...</section>;
  }

  if (clusterMetricsQuery.isError) {
    const message = axios.isAxiosError(clusterMetricsQuery.error)
      ? ((clusterMetricsQuery.error.response?.data as { detail?: string } | undefined)?.detail ??
        "Gagal memuat cluster metrics.")
      : "Gagal memuat cluster metrics.";
    return <section className="panel p-6 text-sm text-rose-600">{message}</section>;
  }

  if (!clusterMetricsQuery.data?.has_cluster_data) {
    return (
      <section className="panel">
        <div className="panel-body flex min-h-[240px] items-center justify-center text-center">
          <div>
            <p className="text-xl font-semibold text-ink">No cluster data available.</p>
            <p className="mt-2 text-sm text-slate-500">Enable RouteFinder Clustering and rerun scenario.</p>
          </div>
        </div>
      </section>
    );
  }

  const metrics = clusterMetricsQuery.data;

  return (
    <div className="space-y-6">
      <ClusterKpiCards summary={metrics.summary} />

      <section className="grid gap-6 xl:grid-cols-3">
        <ClusterAdherenceChart history={metrics.history} />
        <ClusterTradeoffScatter history={metrics.history} />
        <ClusterSizeHistogram clusters={metrics.clusters} />
      </section>

      <section className="grid gap-6 xl:grid-cols-2">
        <ClusterTransitionMatrix clusters={metrics.clusters} edges={metrics.edges} />
        <TruckPurityChart truckMetrics={metrics.truck_metrics} />
      </section>

      <section className="grid gap-6 xl:grid-cols-[1.5fr,1fr]">
        <ClusterRouteMap clusters={metrics.clusters} edges={metrics.edges} />
        <ClusterTable clusters={metrics.clusters} />
      </section>
    </div>
  );
}
