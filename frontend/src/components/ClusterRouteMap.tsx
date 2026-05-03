import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { listNetworkNodes } from "../services/api";
import type { ClusterMetricsCluster, ClusterMetricsEdge, MasterNetworkNode } from "../types/api";
import { emptyChart, getClusterColor } from "./clusterMetricsShared";

const WIDTH = 820;
const HEIGHT = 360;
const PADDING = 36;

function resolveRawCoordinates(node: MasterNetworkNode, fallbackIndex: number) {
  if (Number.isFinite(node.layout_x) && Number.isFinite(node.layout_y)) {
    return { rawX: Number(node.layout_x), rawY: Number(node.layout_y) };
  }
  return { rawX: Number(node.lng || fallbackIndex), rawY: Number(node.lat || fallbackIndex) };
}

export function ClusterRouteMap({
  clusters,
  edges,
}: {
  clusters: ClusterMetricsCluster[];
  edges: ClusterMetricsEdge[];
}) {
  const nodeIds = useMemo(() => {
    const values = new Set<string>();
    clusters.forEach((cluster) => cluster.spbu_ids.forEach((spbuId) => values.add(spbuId)));
    edges.forEach((edge) => {
      values.add(edge.from_spbu_id);
      values.add(edge.to_spbu_id);
    });
    return Array.from(values);
  }, [clusters, edges]);

  const nodesQuery = useQuery({
    queryKey: ["cluster-route-map-nodes", nodeIds.join(",")],
    queryFn: () => listNetworkNodes(nodeIds),
    enabled: nodeIds.length > 0,
  });

  const clusterBySpbu = useMemo(() => {
    const mapping = new Map<string, string>();
    clusters.forEach((cluster) => {
      cluster.spbu_ids.forEach((spbuId) => mapping.set(spbuId, cluster.cluster_id));
    });
    return mapping;
  }, [clusters]);

  const plottedNodes = useMemo(() => {
    const rows = nodesQuery.data ?? [];
    if (!rows.length) {
      return [];
    }
    const resolved = rows.map((node, index) => {
      const { rawX, rawY } = resolveRawCoordinates(node, index + 1);
      return { node, rawX, rawY };
    });
    const minX = Math.min(...resolved.map((item) => item.rawX));
    const maxX = Math.max(...resolved.map((item) => item.rawX));
    const minY = Math.min(...resolved.map((item) => item.rawY));
    const maxY = Math.max(...resolved.map((item) => item.rawY));
    const rangeX = Math.max(maxX - minX, 1);
    const rangeY = Math.max(maxY - minY, 1);
    return resolved.map(({ node, rawX, rawY }) => ({
      node,
      x: PADDING + ((rawX - minX) / rangeX) * (WIDTH - PADDING * 2),
      y: HEIGHT - PADDING - ((rawY - minY) / rangeY) * (HEIGHT - PADDING * 2),
    }));
  }, [nodesQuery.data]);

  const nodeById = useMemo(
    () => new Map(plottedNodes.map((item) => [item.node.node_id, item])),
    [plottedNodes],
  );

  if (!clusters.length) {
    return (
      <section className="panel">
        <div className="panel-header">
          <h3 className="text-lg font-semibold text-ink">Cluster Route Map</h3>
        </div>
        <div className="panel-body">{emptyChart("Belum ada peta cluster route.")}</div>
      </section>
    );
  }

  return (
    <section className="panel">
      <div className="panel-header">
        <h3 className="text-lg font-semibold text-ink">Cluster Route Map</h3>
        <p className="mt-2 text-sm text-slate-500">Garis merah menandai perpindahan antar cluster yang masih terjadi di rute aktual.</p>
      </div>
      <div className="panel-body">
        {nodesQuery.isLoading ? (
          <div className="flex h-[360px] items-center justify-center rounded-[24px] border border-dashed border-slate-200 bg-slate-50 text-sm text-slate-500">
            Memuat node map...
          </div>
        ) : !plottedNodes.length ? (
          emptyChart("Node map belum tersedia untuk cluster ini.")
        ) : (
          <>
            <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="h-[360px] w-full rounded-[24px] border border-slate-200 bg-slate-50">
              {edges.map((edge) => {
                const from = nodeById.get(edge.from_spbu_id);
                const to = nodeById.get(edge.to_spbu_id);
                if (!from || !to) {
                  return null;
                }
                return (
                  <line
                    key={`${edge.truck_id}-${edge.from_spbu_id}-${edge.to_spbu_id}-${edge.trip_sequence}`}
                    x1={from.x}
                    y1={from.y}
                    x2={to.x}
                    y2={to.y}
                    stroke={edge.is_cross_cluster ? "#dc2626" : "#94a3b8"}
                    strokeWidth={edge.is_cross_cluster ? 3.5 : 2}
                    strokeOpacity={edge.is_cross_cluster ? 0.9 : 0.7}
                  >
                    <title>{`${edge.from_spbu_id} → ${edge.to_spbu_id}`}</title>
                  </line>
                );
              })}

              {plottedNodes.map(({ node, x, y }) => {
                const clusterId = clusterBySpbu.get(node.node_id);
                return (
                  <g key={node.node_id}>
                    <circle cx={x} cy={y} r="8" fill={getClusterColor(clusterId)} stroke="#fff" strokeWidth="2.5">
                      <title>{`${node.node_name} • ${clusterId || "Unclustered"}`}</title>
                    </circle>
                    <text x={x + 10} y={y - 10} fill="#334155" fontSize="10">
                      {node.node_code}
                    </text>
                  </g>
                );
              })}
            </svg>

            <div className="mt-4 flex flex-wrap gap-2 text-xs font-semibold text-slate-500">
              {clusters.map((cluster) => (
                <span key={cluster.cluster_id} className="inline-flex items-center gap-2 rounded-full bg-slate-50 px-3 py-1.5">
                  <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: getClusterColor(cluster.cluster_id) }} />
                  {cluster.cluster_id}
                </span>
              ))}
              <span className="inline-flex items-center gap-2 rounded-full bg-rose-50 px-3 py-1.5 text-rose-700">
                <span className="h-2.5 w-2.5 rounded-full bg-rose-600" />
                Cross-cluster edge
              </span>
            </div>
          </>
        )}
      </div>
    </section>
  );
}
