import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { formatNumber } from "../../lib/format";
import { listEffectiveEdges, listNetworkNodes } from "../../services/api";
import type { MasterEffectiveEdge, MasterNetworkNode, RouteDetailResponse } from "../../types/api";

type GraphNodeKind = "depot" | "order" | "spbu" | "poi" | "missing";

type GraphNode = {
  id: string;
  label: string;
  sublabel: string;
  kind: GraphNodeKind;
  x: number;
  y: number;
  isActive: boolean;
  isRouteNode: boolean;
};

type GraphEdge = {
  id: string;
  fromNodeId: string;
  toNodeId: string;
  canonicalKey: string;
  distanceKm: number | null;
  source: string | null;
  roadCategory: string | null;
};

type OverlaySegment = {
  id: string;
  fromNodeId: string;
  toNodeId: string;
  canonicalKey: string;
  truckId: string;
  truckLabel: string;
  color: string;
  laneIndex: number;
  laneCount: number;
  legLabel: string;
  isReturn: boolean;
};

type TruckLegendItem = {
  truckId: string;
  truckLabel: string;
  color: string;
};

type GraphModel = {
  width: number;
  height: number;
  nodes: GraphNode[];
  edges: GraphEdge[];
  segments: OverlaySegment[];
  truckLegend: TruckLegendItem[];
};

const TRUCK_COLORS = [
  "#ef4444",
  "#2563eb",
  "#10b981",
  "#f59e0b",
  "#8b5cf6",
  "#ec4899",
  "#06b6d4",
  "#84cc16",
  "#f97316",
  "#14b8a6",
];

const VIEW_WIDTH = 1600;
const VIEW_HEIGHT = 980;
const VIEW_PADDING = 120;
const NODE_RADIUS = 18;
const EDGE_INSET = 20;
const OVERLAY_EDGE_INSET = 34;
const OVERLAY_OFFSET = 10;
const OVERLAY_GAP = 7;
const MIN_ZOOM = 0.45;
const MAX_ZOOM = 3.6;

function parsePath(path: string | null | undefined) {
  if (!path) {
    return [];
  }
  return path
    .split("->")
    .map((item) => item.trim())
    .filter(Boolean);
}

function canonicalEdgeKey(fromNodeId: string, toNodeId: string) {
  return [fromNodeId, toNodeId].sort().join("::");
}

function hasLayout(node: MasterNetworkNode) {
  return Number.isFinite(node.layout_x) && Number.isFinite(node.layout_y);
}

function nodeKind(node: MasterNetworkNode, depotId: string, orderNodeIds: Set<string>): GraphNodeKind {
  if (node.node_id === depotId || node.node_type === "DEPOT") {
    return "depot";
  }
  if (orderNodeIds.has(node.node_id)) {
    return "order";
  }
  if (node.node_type === "SPBU") {
    return "spbu";
  }
  if (!node.is_active) {
    return "missing";
  }
  return "poi";
}

function nodeFill(kind: GraphNodeKind) {
  if (kind === "depot") return "#bdd312";
  if (kind === "order") return "#ffffff";
  if (kind === "spbu") return "#dff1ff";
  if (kind === "poi") return "#d9f4ef";
  return "#f8fafc";
}

function nodeStroke(kind: GraphNodeKind) {
  if (kind === "depot") return "#8cab0d";
  if (kind === "order") return "#0c7ac0";
  if (kind === "spbu") return "#57a9db";
  if (kind === "poi") return "#2aa59b";
  return "#cbd5e1";
}

function nodeTag(kind: GraphNodeKind) {
  if (kind === "depot") return "DEPOT";
  if (kind === "order") return "ORDER";
  if (kind === "spbu") return "SPBU";
  if (kind === "poi") return "POI";
  return "NODE";
}

function laneOffset(segment: OverlaySegment) {
  const centered = segment.laneIndex - (segment.laneCount - 1) / 2;
  return OVERLAY_OFFSET + centered * OVERLAY_GAP;
}

function buildGraphModel(args: {
  routes: RouteDetailResponse[];
  nodes: MasterNetworkNode[];
  edges: MasterEffectiveEdge[];
  depotId: string;
  orderSpbuIds: string[];
}): GraphModel {
  const { routes, nodes, edges, depotId, orderSpbuIds } = args;
  const orderNodeIds = new Set(orderSpbuIds);
  const relevantNodeIds = new Set<string>([depotId, ...orderSpbuIds]);
  const routeNodeIds = new Set<string>([depotId]);
  const pathEdgeKeys = new Set<string>();
  const truckLegend: TruckLegendItem[] = [];

  const overlayDrafts: Array<Omit<OverlaySegment, "laneIndex" | "laneCount">> = [];

  routes.forEach((route, routeIndex) => {
    const truckId = route.truck_id;
    const truckLabel = route.no_polisi || route.truck_id;
    const color = TRUCK_COLORS[routeIndex % TRUCK_COLORS.length];
    truckLegend.push({ truckId, truckLabel, color });

    const addPath = (pathNodeIds: string[], legLabel: string, isReturn: boolean) => {
      if (pathNodeIds.length < 2) {
        return;
      }
      pathNodeIds.forEach((nodeId) => {
        relevantNodeIds.add(nodeId);
        routeNodeIds.add(nodeId);
      });
      pathNodeIds.slice(0, -1).forEach((fromNodeId, index) => {
        const toNodeId = pathNodeIds[index + 1];
        const canonicalKey = canonicalEdgeKey(fromNodeId, toNodeId);
        pathEdgeKeys.add(canonicalKey);
        overlayDrafts.push({
          id: `${truckId}-${legLabel}-${fromNodeId}-${toNodeId}-${index}`,
          fromNodeId,
          toNodeId,
          canonicalKey,
          truckId,
          truckLabel,
          color,
          legLabel,
          isReturn,
        });
      });
    };

    route.stops.forEach((stop) => {
      relevantNodeIds.add(stop.spbu_id);
      routeNodeIds.add(stop.spbu_id);
      addPath(
        parsePath(stop.travel_path),
        stop.stop_kind === "delivery" ? stop.spbu_name || stop.spbu_id : stop.stop_kind,
        false,
      );
    });

    addPath(parsePath(route.return_path), "return", true);
  });

  const nodeById = new Map(nodes.map((node) => [node.node_id, node]));
  const relevantNodes = Array.from(relevantNodeIds).map((nodeId, index) => {
    const existing = nodeById.get(nodeId);
    if (existing) {
      return existing;
    }
    return {
      node_id: nodeId,
      node_code: nodeId,
      node_name: nodeId,
      node_type: nodeId === depotId ? "DEPOT" : "POI",
      lat: 0,
      lng: 0,
      layout_x: VIEW_PADDING + index * 44,
      layout_y: VIEW_HEIGHT - VIEW_PADDING - 80,
      truck_category: null,
      is_active: false,
      supply_depot_ids: [],
    } satisfies MasterNetworkNode;
  });

  const useLayout = relevantNodes.filter(hasLayout).length >= 2;
  const rawPositions = relevantNodes.map((node, index) => ({
    nodeId: node.node_id,
    rawX:
      useLayout && Number.isFinite(node.layout_x)
        ? Number(node.layout_x)
        : node.lng !== 0
          ? node.lng
          : index + 1,
    rawY:
      useLayout && Number.isFinite(node.layout_y)
        ? Number(node.layout_y)
        : node.lat !== 0
          ? -node.lat
          : index + 1,
  }));

  const minX = Math.min(...rawPositions.map((item) => item.rawX));
  const maxX = Math.max(...rawPositions.map((item) => item.rawX));
  const minY = Math.min(...rawPositions.map((item) => item.rawY));
  const maxY = Math.max(...rawPositions.map((item) => item.rawY));
  const rangeX = Math.max(1, maxX - minX);
  const rangeY = Math.max(1, maxY - minY);
  const usableWidth = VIEW_WIDTH - VIEW_PADDING * 2;
  const usableHeight = VIEW_HEIGHT - VIEW_PADDING * 2;

  const graphNodes = relevantNodes.map((node) => {
    const raw = rawPositions.find((item) => item.nodeId === node.node_id);
    const x = raw ? VIEW_PADDING + ((raw.rawX - minX) / rangeX) * usableWidth : VIEW_WIDTH / 2;
    const y = raw ? VIEW_PADDING + ((raw.rawY - minY) / rangeY) * usableHeight : VIEW_HEIGHT / 2;
    return {
      id: node.node_id,
      label: node.node_name || node.node_code || node.node_id,
      sublabel: node.node_code || node.node_id,
      kind: nodeKind(node, depotId, orderNodeIds),
      x,
      y,
      isActive: node.is_active,
      isRouteNode: routeNodeIds.has(node.node_id),
    } satisfies GraphNode;
  });

  const graphNodeById = new Map(graphNodes.map((node) => [node.id, node]));
  const graphEdges = new Map<string, GraphEdge>();

  edges.forEach((edge) => {
    const canonicalKey = canonicalEdgeKey(edge.from_node_id, edge.to_node_id);
    if (!pathEdgeKeys.has(canonicalKey)) {
      return;
    }
    if (!graphNodeById.has(edge.from_node_id) || !graphNodeById.has(edge.to_node_id)) {
      return;
    }
    if (!graphEdges.has(canonicalKey)) {
      graphEdges.set(canonicalKey, {
        id: canonicalKey,
        fromNodeId: edge.from_node_id,
        toNodeId: edge.to_node_id,
        canonicalKey,
        distanceKm: edge.distance_km ?? null,
        source: edge.source ?? null,
        roadCategory: edge.road_category ?? null,
      });
    }
  });

  pathEdgeKeys.forEach((canonicalKey) => {
    if (graphEdges.has(canonicalKey)) {
      return;
    }
    const [fromNodeId, toNodeId] = canonicalKey.split("::");
    if (!graphNodeById.has(fromNodeId) || !graphNodeById.has(toNodeId)) {
      return;
    }
    graphEdges.set(canonicalKey, {
      id: canonicalKey,
      fromNodeId,
      toNodeId,
      canonicalKey,
      distanceKm: null,
      source: "PATH",
      roadCategory: null,
    });
  });

  const trucksByEdge = new Map<string, string[]>();
  overlayDrafts.forEach((segment) => {
    const existing = trucksByEdge.get(segment.canonicalKey) ?? [];
    if (!existing.includes(segment.truckId)) {
      existing.push(segment.truckId);
      trucksByEdge.set(segment.canonicalKey, existing);
    }
  });

  const segments = overlayDrafts.map((segment) => {
    const trucksOnEdge = trucksByEdge.get(segment.canonicalKey) ?? [segment.truckId];
    return {
      ...segment,
      laneIndex: Math.max(0, trucksOnEdge.indexOf(segment.truckId)),
      laneCount: trucksOnEdge.length,
    };
  });

  return {
    width: VIEW_WIDTH,
    height: VIEW_HEIGHT,
    nodes: graphNodes,
    edges: Array.from(graphEdges.values()),
    segments,
    truckLegend,
  };
}

function clampZoom(value: number) {
  return Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, value));
}

function edgePoints(from: GraphNode, to: GraphNode, offset: number, inset = EDGE_INSET) {
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  const length = Math.hypot(dx, dy) || 1;
  const unitX = dx / length;
  const unitY = dy / length;
  const normalX = -unitY;
  const normalY = unitX;
  return {
    x1: from.x + unitX * inset + normalX * offset,
    y1: from.y + unitY * inset + normalY * offset,
    x2: to.x - unitX * inset + normalX * offset,
    y2: to.y - unitY * inset + normalY * offset,
    midX: (from.x + to.x) / 2 + normalX * offset,
    midY: (from.y + to.y) / 2 + normalY * offset,
  };
}

function renderError(error: unknown) {
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return "Gagal memuat graph masterdata.";
}

export function RouteMap({
  routes,
  depotId,
  orderSpbuIds = [],
}: {
  routes: RouteDetailResponse[];
  depotId: string;
  orderSpbuIds?: string[];
}) {
  const relevantNodeIds = useMemo(() => {
    const ids = new Set<string>([depotId, ...orderSpbuIds]);
    routes.forEach((route) => {
      route.stops.forEach((stop) => {
        ids.add(stop.spbu_id);
        parsePath(stop.travel_path).forEach((nodeId) => ids.add(nodeId));
      });
      parsePath(route.return_path).forEach((nodeId) => ids.add(nodeId));
    });
    return Array.from(ids).sort();
  }, [depotId, orderSpbuIds, routes]);

  const nodeIdsKey = relevantNodeIds.join(",");
  const nodesQuery = useQuery({
    queryKey: ["route-map-master-nodes", nodeIdsKey],
    queryFn: () => listNetworkNodes(relevantNodeIds),
    enabled: relevantNodeIds.length > 0,
    staleTime: 60_000,
  });
  const edgesQuery = useQuery({
    queryKey: ["route-map-master-edges", nodeIdsKey],
    queryFn: () => listEffectiveEdges(relevantNodeIds),
    enabled: relevantNodeIds.length > 0,
    staleTime: 60_000,
  });

  const graph = useMemo(() => {
    if (!nodesQuery.data || !edgesQuery.data) {
      return null;
    }
    return buildGraphModel({
      routes,
      nodes: nodesQuery.data,
      edges: edgesQuery.data,
      depotId,
      orderSpbuIds,
    });
  }, [depotId, edgesQuery.data, nodesQuery.data, orderSpbuIds, routes]);

  const graphNodeLookup = useMemo(
    () => new Map((graph?.nodes ?? []).map((node) => [node.id, node])),
    [graph?.nodes],
  );
  const containerRef = useRef<HTMLDivElement | null>(null);
  const dragRef = useRef<{ x: number; y: number; panX: number; panY: number } | null>(null);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [activeTruckId, setActiveTruckId] = useState<string | null>(null);
  const [isBaseEdgeFocusActive, setIsBaseEdgeFocusActive] = useState(false);
  const activeTruckNodeIds = useMemo(() => {
    if (!graph || !activeTruckId) {
      return null;
    }
    const ids = new Set<string>();
    graph.segments.forEach((segment) => {
      if (segment.truckId !== activeTruckId) {
        return;
      }
      ids.add(segment.fromNodeId);
      ids.add(segment.toNodeId);
    });
    return ids;
  }, [activeTruckId, graph]);

  useEffect(() => {
    setZoom(1);
    setPan({ x: 0, y: 0 });
    setActiveTruckId(null);
    setIsBaseEdgeFocusActive(false);
  }, [routes, depotId]);

  if (!routes.length) {
    return (
      <section className="rounded-[28px] border border-slate-200 bg-white p-6 text-sm text-slate-500">
        Route map belum tersedia karena tidak ada route aktif.
      </section>
    );
  }

  if (nodesQuery.isError || edgesQuery.isError) {
    return (
      <section className="rounded-[32px] border border-rose-200 bg-rose-50 p-6 text-sm text-rose-700">
        {renderError(nodesQuery.error ?? edgesQuery.error)}
      </section>
    );
  }

  if (nodesQuery.isLoading || edgesQuery.isLoading) {
    return (
      <section className="rounded-[32px] border border-slate-200 bg-white p-6 text-sm text-slate-500">
        Menyiapkan graph node dan edge dari masterdata SPBU...
      </section>
    );
  }

  if (!graph) {
    return (
      <section className="rounded-[32px] border border-slate-200 bg-white p-6 text-sm text-slate-500">
        Menunggu data graph route...
      </section>
    );
  }

  if (!graph.edges.length || !graph.nodes.length) {
    return (
      <section className="rounded-[32px] border border-amber-200 bg-amber-50 p-6 text-sm text-amber-700">
        Graph masterdata berhasil dimuat, tetapi edge route yang cocok dengan path truck belum ditemukan.
      </section>
    );
  }

  const handlePointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    dragRef.current = {
      x: event.clientX,
      y: event.clientY,
      panX: pan.x,
      panY: pan.y,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
  };

  const handlePointerMove = (event: React.PointerEvent<HTMLDivElement>) => {
    if (!dragRef.current) {
      return;
    }
    setPan({
      x: dragRef.current.panX + (event.clientX - dragRef.current.x),
      y: dragRef.current.panY + (event.clientY - dragRef.current.y),
    });
  };

  const handlePointerUp = (event: React.PointerEvent<HTMLDivElement>) => {
    dragRef.current = null;
    event.currentTarget.releasePointerCapture(event.pointerId);
  };

  const handleWheel = (event: React.WheelEvent<HTMLDivElement>) => {
    const container = containerRef.current;
    if (!container || !graph) {
      return;
    }
    event.preventDefault();

    const rect = container.getBoundingClientRect();
    const pointerX = ((event.clientX - rect.left) / rect.width) * graph.width;
    const pointerY = ((event.clientY - rect.top) / rect.height) * graph.height;
    const zoomIntensity = event.ctrlKey || event.metaKey ? 0.0045 : 0.0018;
    const scale = Math.exp(-event.deltaY * zoomIntensity);
    const nextZoom = clampZoom(Number((zoom * scale).toFixed(3)));

    if (nextZoom === zoom) {
      return;
    }

    const worldX = (pointerX - pan.x) / zoom;
    const worldY = (pointerY - pan.y) / zoom;
    const nextPanX = pointerX - worldX * nextZoom;
    const nextPanY = pointerY - worldY * nextZoom;

    setZoom(nextZoom);
    setPan({ x: nextPanX, y: nextPanY });
  };

  const resetView = () => {
    setZoom(1);
    setPan({ x: 0, y: 0 });
  };

  return (
    <section className="rounded-[32px] border border-slate-200 bg-[linear-gradient(145deg,_rgba(255,255,255,0.98),_rgba(247,250,252,0.96))] p-5 shadow-sm">
      <div className="mb-4 flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
        <div className="max-w-4xl">
          <h3 className="text-lg font-semibold text-ink">Route Map</h3>
          <p className="mt-1 text-sm text-slate-500">
            Base edge diambil dari masterdata SPBU, lalu pergerakan setiap truck ditampilkan sebagai garis warna
            ter-offset di samping edge yang sama.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => setZoom((current) => clampZoom(Number((current - 0.2).toFixed(2))))}
            className="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-600 shadow-sm transition hover:border-sky-300 hover:text-sky-700"
          >
            Zoom Out
          </button>
          <button
            type="button"
            onClick={() => setZoom((current) => clampZoom(Number((current + 0.2).toFixed(2))))}
            className="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-600 shadow-sm transition hover:border-sky-300 hover:text-sky-700"
          >
            Zoom In
          </button>
          <button
            type="button"
            onClick={resetView}
            className="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-600 shadow-sm transition hover:border-sky-300 hover:text-sky-700"
          >
            Reset
          </button>
          <span className="rounded-full bg-slate-100 px-3 py-2 text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">
            Zoom {Math.round(zoom * 100)}%
          </span>
        </div>
      </div>

      <div className="mb-4 grid gap-3 md:grid-cols-4">
        <div className="rounded-[24px] border border-slate-200 bg-slate-50 px-4 py-3">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Node Aktif</p>
          <p className="mt-2 text-2xl font-semibold text-ink">{graph.nodes.length}</p>
        </div>
        <div className="rounded-[24px] border border-slate-200 bg-slate-50 px-4 py-3">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Edge Masterdata</p>
          <p className="mt-2 text-2xl font-semibold text-ink">{graph.edges.length}</p>
        </div>
        <div className="rounded-[24px] border border-slate-200 bg-slate-50 px-4 py-3">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Truck Overlay</p>
          <p className="mt-2 text-2xl font-semibold text-ink">{graph.truckLegend.length}</p>
        </div>
        <div className="rounded-[24px] border border-slate-200 bg-slate-50 px-4 py-3">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Order Node</p>
          <p className="mt-2 text-2xl font-semibold text-ink">{orderSpbuIds.length}</p>
        </div>
      </div>

      <div className="mb-4 flex flex-wrap gap-2 text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">
        <button
          type="button"
          onClick={() => {
            setIsBaseEdgeFocusActive((current) => {
              const next = !current;
              if (next) {
                setActiveTruckId(null);
              }
              return next;
            });
          }}
          className={
            isBaseEdgeFocusActive
              ? "rounded-full border border-slate-900 bg-slate-900 px-3 py-2 text-slate-100"
              : "rounded-full border border-slate-200 bg-slate-100 px-3 py-2 text-slate-500"
          }
        >
          Base Edge Masterdata
        </button>
        <span className="rounded-full bg-slate-900 px-3 py-2 text-slate-100">Overlay Pergerakan Truck</span>
        <span className="rounded-full bg-sky-50 px-3 py-2 text-sky-700">Order / SPBU Tujuan</span>
        <span className="rounded-full bg-lime-100 px-3 py-2 text-lime-700">Depot</span>
      </div>

      <div className="mb-4 flex flex-wrap gap-2">
        {graph.truckLegend.map((item) => (
          <button
            key={item.truckId}
            type="button"
            onClick={() => {
              setIsBaseEdgeFocusActive(false);
              setActiveTruckId((current) => (current === item.truckId ? null : item.truckId));
            }}
            className={
              activeTruckId === item.truckId
                ? "rounded-full border border-slate-900 bg-slate-900 px-3 py-2 text-xs font-semibold uppercase tracking-[0.14em] text-white shadow-sm"
                : "rounded-full border border-slate-200 bg-white px-3 py-2 text-xs font-semibold uppercase tracking-[0.14em] text-slate-600 shadow-sm"
            }
          >
            <span className="mr-2 inline-block h-2.5 w-2.5 rounded-full align-middle" style={{ backgroundColor: item.color }} />
            {item.truckLabel}
          </button>
        ))}
      </div>

      <div
        ref={containerRef}
        className="relative h-[74vh] min-h-[620px] overflow-hidden rounded-[28px] border border-slate-200 bg-[#f5f9fb]"
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerLeave={handlePointerUp}
        onWheel={handleWheel}
      >
        <div className="pointer-events-none absolute left-4 top-4 z-10 rounded-2xl bg-white/90 px-4 py-3 text-xs text-slate-600 shadow-lg backdrop-blur">
          Drag untuk pan. Gunakan scroll / gesture trackpad untuk zoom, atau tombol zoom di atas.
        </div>

        <svg width="100%" height="100%" viewBox={`0 0 ${graph.width} ${graph.height}`} preserveAspectRatio="xMidYMid meet">
          <defs>
            {graph.truckLegend.map((item) => (
              <marker
                key={`arrow-${item.truckId}`}
                id={`arrow-${item.truckId}`}
                markerUnits="userSpaceOnUse"
                markerWidth="7"
                markerHeight="7"
                refX="6.2"
                refY="3.5"
                orient="auto"
              >
                <path d="M0,0.4 L6.2,3.5 L0,6.6 L1.35,3.5 z" fill={item.color} />
              </marker>
            ))}
          </defs>

          <g transform={`translate(${pan.x} ${pan.y}) scale(${zoom})`}>
            {graph.edges.map((edge) => {
              const from = graphNodeLookup.get(edge.fromNodeId);
              const to = graphNodeLookup.get(edge.toNodeId);
              if (!from || !to) {
                return null;
              }

              const base = edgePoints(from, to, 0);
              const baseStroke = isBaseEdgeFocusActive ? "#475569" : "#aabcca";
              const baseStrokeWidth = isBaseEdgeFocusActive ? 5.2 : 4;
              const baseOpacity = isBaseEdgeFocusActive ? 0.98 : 0.86;
              const label = [
                edge.roadCategory,
                edge.distanceKm !== null ? `${formatNumber(edge.distanceKm)} km` : null,
              ]
                .filter(Boolean)
                .join(" · ");

              return (
                <g key={edge.id}>
                  <line
                    x1={base.x1}
                    y1={base.y1}
                    x2={base.x2}
                    y2={base.y2}
                    stroke={baseStroke}
                    strokeWidth={baseStrokeWidth}
                    strokeOpacity={baseOpacity}
                    strokeLinecap="round"
                  />
                  <line
                    x1={base.x1}
                    y1={base.y1}
                    x2={base.x2}
                    y2={base.y2}
                    stroke="#ffffff"
                    strokeWidth={1.2}
                    strokeOpacity={0.7}
                    strokeLinecap="round"
                  />
                  {label ? (
                    <g transform={`translate(${base.midX} ${base.midY - 10})`}>
                      <rect
                        x={-56}
                        y={-10}
                        width="112"
                        height="20"
                        rx="10"
                        fill="rgba(255,255,255,0.92)"
                        stroke="rgba(170,188,202,0.55)"
                      />
                      <text
                        x="0"
                        y="4"
                        fontSize="10"
                        fontWeight="700"
                        textAnchor="middle"
                        fill={isBaseEdgeFocusActive ? "#334155" : "#526173"}
                      >
                        {label}
                      </text>
                    </g>
                  ) : null}
                </g>
              );
            })}

            {graph.segments.map((segment) => {
              const from = graphNodeLookup.get(segment.fromNodeId);
              const to = graphNodeLookup.get(segment.toNodeId);
              if (!from || !to) {
                return null;
              }
              const dimmed =
                isBaseEdgeFocusActive || (activeTruckId !== null && activeTruckId !== segment.truckId);
              const overlay = edgePoints(from, to, laneOffset(segment), OVERLAY_EDGE_INSET);
              const overlayStroke = isBaseEdgeFocusActive ? "#cbd5e1" : segment.color;
              return (
                <g key={segment.id} opacity={isBaseEdgeFocusActive ? 0.32 : dimmed ? 0.12 : 1}>
                  <line
                    x1={overlay.x1}
                    y1={overlay.y1}
                    x2={overlay.x2}
                    y2={overlay.y2}
                    stroke={overlayStroke}
                    strokeWidth={segment.isReturn ? 3.6 : 4.6}
                    strokeLinecap="round"
                    strokeDasharray={segment.isReturn ? "10 8" : undefined}
                    markerEnd={`url(#arrow-${segment.truckId})`}
                  />
                </g>
              );
            })}

            {graph.nodes.map((node, index) => {
              const dimmed = activeTruckNodeIds !== null && !activeTruckNodeIds.has(node.id);
              const labelOffset = index % 2 === 0 ? -30 : 38;
              return (
                <g key={node.id} opacity={dimmed ? 0.45 : 1}>
                  {node.kind === "order" ? (
                    <circle cx={node.x} cy={node.y} r={NODE_RADIUS + 7} fill="rgba(12,122,192,0.12)" />
                  ) : null}
                  <circle
                    cx={node.x}
                    cy={node.y}
                    r={NODE_RADIUS}
                    fill={nodeFill(node.kind)}
                    stroke={nodeStroke(node.kind)}
                    strokeWidth={node.kind === "order" ? 3.5 : 2.4}
                  />
                  <text
                    x={node.x}
                    y={node.y + 4}
                    fontSize="9"
                    fontWeight="800"
                    textAnchor="middle"
                    fill={node.kind === "depot" ? "#294200" : "#173047"}
                  >
                    {nodeTag(node.kind)}
                  </text>
                  <text
                    x={node.x}
                    y={node.y + labelOffset}
                    fontSize="12"
                    fontWeight="700"
                    textAnchor="middle"
                    fill="#173047"
                  >
                    {node.label}
                  </text>
                  <text
                    x={node.x}
                    y={node.y + labelOffset + 15}
                    fontSize="10"
                    textAnchor="middle"
                    fill={node.isActive ? "#667a8d" : "#94a3b8"}
                  >
                    {node.sublabel}
                  </text>
                </g>
              );
            })}
          </g>
        </svg>
      </div>
    </section>
  );
}
