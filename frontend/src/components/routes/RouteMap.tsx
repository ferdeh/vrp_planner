import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { renderToStaticMarkup } from "react-dom/server";
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
  labelX: number;
  labelY: number;
  labelAnchor: "start" | "end";
  labelWidth: number;
  isActive: boolean;
  isRouteNode: boolean;
  hasLo: boolean;
};

type GraphEdge = {
  id: string;
  fromNodeId: string;
  toNodeId: string;
  canonicalKey: string;
  distanceKm: number | null;
  source: string | null;
  roadCategory: string | null;
  isRouteEdge: boolean;
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

type GraphLayoutMode = "coordinates" | "hierarchical";

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
const NODE_MIN_DISTANCE = 112;
const LABEL_HEIGHT = 36;
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

function hasGeoCoordinate(node: MasterNetworkNode) {
  return Number.isFinite(node.lng) && Number.isFinite(node.lat) && (node.lng !== 0 || node.lat !== 0);
}

function fallbackRawCoordinate(node: MasterNetworkNode, index: number) {
  if (hasLayout(node)) {
    return {
      rawX: Number(node.layout_x),
      rawY: Number(node.layout_y),
    };
  }
  return {
    rawX: index + 1,
    rawY: index + 1,
  };
}

function estimateLabelWidth(node: Pick<GraphNode, "label" | "sublabel">) {
  const longestLine = Math.max(node.label.length, node.sublabel.length);
  return Math.min(240, Math.max(112, longestLine * 7.2 + 28));
}

// Keep lat/lng as the base projection, then nudge only the SVG marker positions when coordinates collide.
function separateOverlappingNodes(nodes: GraphNode[]) {
  const separated = nodes.map((node) => ({ ...node }));
  const minDistance = NODE_MIN_DISTANCE;
  const minX = VIEW_PADDING / 2;
  const maxX = VIEW_WIDTH - VIEW_PADDING / 2;
  const minY = VIEW_PADDING / 2;
  const maxY = VIEW_HEIGHT - VIEW_PADDING / 2;

  for (let iteration = 0; iteration < 90; iteration += 1) {
    let moved = false;
    for (let firstIndex = 0; firstIndex < separated.length; firstIndex += 1) {
      for (let secondIndex = firstIndex + 1; secondIndex < separated.length; secondIndex += 1) {
        const first = separated[firstIndex];
        const second = separated[secondIndex];
        const dx = second.x - first.x;
        const dy = second.y - first.y;
        const distance = Math.hypot(dx, dy);
        if (distance >= minDistance) {
          continue;
        }

        const stableAngle =
          distance > 0
            ? Math.atan2(dy, dx)
            : ((first.id.charCodeAt(0) + second.id.charCodeAt(second.id.length - 1)) % 360) * (Math.PI / 180);
        const push = (minDistance - distance) / 2 + 0.4;
        const pushX = Math.cos(stableAngle) * push;
        const pushY = Math.sin(stableAngle) * push;

        first.x = Math.min(maxX, Math.max(minX, first.x - pushX));
        first.y = Math.min(maxY, Math.max(minY, first.y - pushY));
        second.x = Math.min(maxX, Math.max(minX, second.x + pushX));
        second.y = Math.min(maxY, Math.max(minY, second.y + pushY));
        moved = true;
      }
    }
    if (!moved) {
      break;
    }
  }

  return separated;
}

function boxesOverlap(
  first: { x: number; y: number; width: number; height: number },
  second: { x: number; y: number; width: number; height: number },
) {
  const gap = 8;
  return !(
    first.x + first.width + gap < second.x ||
    second.x + second.width + gap < first.x ||
    first.y + first.height + gap < second.y ||
    second.y + second.height + gap < first.y
  );
}

function addReadableLabels(nodes: GraphNode[]) {
  const placedBoxes: Array<{ x: number; y: number; width: number; height: number }> = [];
  const minX = 24;
  const maxX = VIEW_WIDTH - 24;
  const minY = 24;
  const maxY = VIEW_HEIGHT - 24;

  return [...nodes]
    .sort((first, second) => first.y - second.y || first.x - second.x)
    .map((node, index) => {
      const labelWidth = estimateLabelWidth(node);
      const side = index % 2 === 0 ? 1 : -1;
      const candidateOffsets = [
        { dx: side * 58, dy: -42, anchor: side > 0 ? "start" : "end" },
        { dx: side * 66, dy: 18, anchor: side > 0 ? "start" : "end" },
        { dx: -side * 58, dy: -42, anchor: side > 0 ? "end" : "start" },
        { dx: -side * 66, dy: 18, anchor: side > 0 ? "end" : "start" },
        { dx: side * 92, dy: -84, anchor: side > 0 ? "start" : "end" },
        { dx: -side * 92, dy: 62, anchor: side > 0 ? "end" : "start" },
        { dx: side * 128, dy: -4, anchor: side > 0 ? "start" : "end" },
        { dx: -side * 128, dy: -4, anchor: side > 0 ? "end" : "start" },
      ] satisfies Array<{ dx: number; dy: number; anchor: "start" | "end" }>;

      let selected = candidateOffsets[0];
      let selectedBox: { x: number; y: number; width: number; height: number } | null = null;

      for (const candidate of candidateOffsets) {
        const labelX = Math.min(maxX, Math.max(minX, node.x + candidate.dx));
        const labelY = Math.min(maxY, Math.max(minY, node.y + candidate.dy));
        const boxX = candidate.anchor === "start" ? labelX - 12 : labelX - labelWidth + 12;
        const box = {
          x: Math.min(maxX - labelWidth, Math.max(minX, boxX)),
          y: Math.min(maxY - LABEL_HEIGHT, Math.max(minY, labelY - 18)),
          width: labelWidth,
          height: LABEL_HEIGHT,
        };
        if (!placedBoxes.some((placed) => boxesOverlap(box, placed))) {
          selected = candidate;
          selectedBox = box;
          break;
        }
      }

      const fallbackLabelX = Math.min(maxX, Math.max(minX, node.x + selected.dx));
      const fallbackLabelY = Math.min(maxY, Math.max(minY, node.y + selected.dy));
      const box =
        selectedBox ??
        {
          x:
            selected.anchor === "start"
              ? Math.min(maxX - labelWidth, Math.max(minX, fallbackLabelX - 12))
              : Math.min(maxX - labelWidth, Math.max(minX, fallbackLabelX - labelWidth + 12)),
          y: Math.min(maxY - LABEL_HEIGHT, Math.max(minY, fallbackLabelY - 18)),
          width: labelWidth,
          height: LABEL_HEIGHT,
        };
      placedBoxes.push(box);

      return {
        ...node,
        labelX: selected.anchor === "start" ? box.x + 12 : box.x + box.width - 12,
        labelY: box.y + 18,
        labelAnchor: selected.anchor,
        labelWidth,
      };
    })
    .sort((first, second) => nodes.findIndex((node) => node.id === first.id) - nodes.findIndex((node) => node.id === second.id));
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

function isNodeRelatedToDepot(node: MasterNetworkNode, depotId: string, orderNodeIds: Set<string>, routeNodeIds: Set<string>) {
  if (node.node_id === depotId) {
    return true;
  }
  if (orderNodeIds.has(node.node_id) || routeNodeIds.has(node.node_id)) {
    return true;
  }
  return node.supply_depot_ids.includes(depotId);
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

function mapRawPositionsToView(rawPositions: Array<{ nodeId: string; rawX: number; rawY: number }>) {
  if (!rawPositions.length) {
    return new Map<string, { x: number; y: number }>();
  }

  const minX = Math.min(...rawPositions.map((item) => item.rawX));
  const maxX = Math.max(...rawPositions.map((item) => item.rawX));
  const minY = Math.min(...rawPositions.map((item) => item.rawY));
  const maxY = Math.max(...rawPositions.map((item) => item.rawY));
  const rangeX = Math.max(1, maxX - minX);
  const rangeY = Math.max(1, maxY - minY);
  const usableWidth = VIEW_WIDTH - VIEW_PADDING * 2;
  const usableHeight = VIEW_HEIGHT - VIEW_PADDING * 2;

  return new Map(
    rawPositions.map((item) => [
      item.nodeId,
      {
        x: VIEW_PADDING + ((item.rawX - minX) / rangeX) * usableWidth,
        y: VIEW_PADDING + ((item.rawY - minY) / rangeY) * usableHeight,
      },
    ]),
  );
}

function buildCoordinatePositions(nodes: MasterNetworkNode[]) {
  const rawPositions = nodes.map((node, index) => ({
    nodeId: node.node_id,
    ...(hasGeoCoordinate(node)
      ? {
          rawX: node.lng,
          rawY: -node.lat,
        }
      : fallbackRawCoordinate(node, index)),
  }));

  return mapRawPositionsToView(rawPositions);
}

function buildHierarchicalPositions(args: {
  nodes: MasterNetworkNode[];
  depotId: string;
  links: Array<{ fromNodeId: string; toNodeId: string }>;
}) {
  const { nodes, depotId, links } = args;
  if (!nodes.length) {
    return new Map<string, { x: number; y: number }>();
  }

  const nodeById = new Map(nodes.map((node) => [node.node_id, node]));
  const adjacency = new Map<string, string[]>();

  const ensureAdjacency = (nodeId: string) => {
    if (!adjacency.has(nodeId)) {
      adjacency.set(nodeId, []);
    }
    return adjacency.get(nodeId)!;
  };

  const compareNodeIds = (firstId: string, secondId: string) => {
    const first = nodeById.get(firstId);
    const second = nodeById.get(secondId);
    if (!first || !second) {
      return firstId.localeCompare(secondId);
    }
    if (first.node_type !== second.node_type) {
      if (first.node_type === "DEPOT") return -1;
      if (second.node_type === "DEPOT") return 1;
    }
    return (first.node_code || first.node_name || first.node_id).localeCompare(
      second.node_code || second.node_name || second.node_id,
    );
  };

  nodes.forEach((node) => ensureAdjacency(node.node_id));
  links.forEach(({ fromNodeId, toNodeId }) => {
    if (!nodeById.has(fromNodeId) || !nodeById.has(toNodeId) || fromNodeId === toNodeId) {
      return;
    }
    const fromList = ensureAdjacency(fromNodeId);
    if (!fromList.includes(toNodeId)) {
      fromList.push(toNodeId);
    }
    const toList = ensureAdjacency(toNodeId);
    if (!toList.includes(fromNodeId)) {
      toList.push(fromNodeId);
    }
  });
  adjacency.forEach((neighbors) => neighbors.sort(compareNodeIds));

  const rootId =
    (nodeById.has(depotId) && depotId) ||
    nodes.find((node) => node.node_type === "DEPOT")?.node_id ||
    nodes[0]?.node_id;
  if (!rootId) {
    return buildCoordinatePositions(nodes);
  }

  const levelById = new Map<string, number>([[rootId, 0]]);
  const parentById = new Map<string, string>();
  const queue = [rootId];
  const visited = new Set<string>([rootId]);

  while (queue.length > 0) {
    const currentId = queue.shift()!;
    const currentLevel = levelById.get(currentId) ?? 0;
    (adjacency.get(currentId) ?? []).forEach((neighborId) => {
      if (visited.has(neighborId)) {
        return;
      }
      visited.add(neighborId);
      parentById.set(neighborId, currentId);
      levelById.set(neighborId, currentLevel + 1);
      queue.push(neighborId);
    });
  }

  const childrenById = new Map<string, string[]>();
  parentById.forEach((parentId, childId) => {
    const children = childrenById.get(parentId) ?? [];
    children.push(childId);
    children.sort(compareNodeIds);
    childrenById.set(parentId, children);
  });

  const unitWidth = 190;
  const siblingGap = 44;
  const levelGap = 210;
  const subtreeWidthCache = new Map<string, number>();

  const computeSubtreeWidth = (nodeId: string): number => {
    const cached = subtreeWidthCache.get(nodeId);
    if (cached != null) {
      return cached;
    }
    const children = childrenById.get(nodeId) ?? [];
    if (!children.length) {
      subtreeWidthCache.set(nodeId, unitWidth);
      return unitWidth;
    }

    let width = 0;
    children.forEach((childId, index) => {
      width += computeSubtreeWidth(childId);
      if (index > 0) {
        width += siblingGap;
      }
    });
    const finalWidth = Math.max(unitWidth, width);
    subtreeWidthCache.set(nodeId, finalWidth);
    return finalWidth;
  };

  const rawPositions: Array<{ nodeId: string; rawX: number; rawY: number }> = [];
  let maxAssignedY = 0;

  const assignTreePosition = (nodeId: string, centerX: number) => {
    const level = levelById.get(nodeId) ?? 0;
    rawPositions.push({
      nodeId,
      rawX: centerX,
      rawY: level * levelGap,
    });
    maxAssignedY = Math.max(maxAssignedY, level * levelGap);

    const children = childrenById.get(nodeId) ?? [];
    if (!children.length) {
      return;
    }

    const totalChildrenWidth = children.reduce((sum, childId, index) => {
      return sum + computeSubtreeWidth(childId) + (index > 0 ? siblingGap : 0);
    }, 0);

    let cursorX = centerX - totalChildrenWidth / 2;
    children.forEach((childId) => {
      const childWidth = computeSubtreeWidth(childId);
      assignTreePosition(childId, cursorX + childWidth / 2);
      cursorX += childWidth + siblingGap;
    });
  };

  assignTreePosition(rootId, computeSubtreeWidth(rootId) / 2);

  const remainder = nodes
    .filter((node) => !visited.has(node.node_id))
    .sort((first, second) => compareNodeIds(first.node_id, second.node_id));

  if (remainder.length) {
    const columns = Math.max(1, Math.ceil(Math.sqrt(remainder.length)));
    remainder.forEach((node, index) => {
      rawPositions.push({
        nodeId: node.node_id,
        rawX: (index % columns) * unitWidth,
        rawY: maxAssignedY + levelGap + Math.floor(index / columns) * 170,
      });
    });
  }

  return mapRawPositionsToView(rawPositions);
}

function buildGraphModel(args: {
  routes: RouteDetailResponse[];
  nodes: MasterNetworkNode[];
  edges: MasterEffectiveEdge[];
  depotId: string;
  orderSpbuIds: string[];
  layoutMode: GraphLayoutMode;
}): GraphModel {
  const { routes, nodes, edges, depotId, orderSpbuIds, layoutMode } = args;
  const orderNodeIds = new Set(orderSpbuIds);
  const fallbackNodeIds = new Set<string>([depotId, ...orderSpbuIds]);
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
        fallbackNodeIds.add(nodeId);
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
      fallbackNodeIds.add(stop.spbu_id);
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
  const depotRelatedNodes = nodes.filter((node) => isNodeRelatedToDepot(node, depotId, orderNodeIds, routeNodeIds));
  const depotRelatedNodeIds = new Set(depotRelatedNodes.map((node) => node.node_id));

  const missingFallbackNodes = Array.from(fallbackNodeIds)
    .filter((nodeId) => !depotRelatedNodeIds.has(nodeId))
    .map((nodeId, index) => {
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

  const relevantNodes = [...depotRelatedNodes, ...missingFallbackNodes];
  const relevantNodeIds = new Set(relevantNodes.map((node) => node.node_id));
  const layoutLinks = new Map<string, { fromNodeId: string; toNodeId: string }>();

  edges.forEach((edge) => {
    if (!relevantNodeIds.has(edge.from_node_id) || !relevantNodeIds.has(edge.to_node_id)) {
      return;
    }
    const canonicalKey = canonicalEdgeKey(edge.from_node_id, edge.to_node_id);
    if (!layoutLinks.has(canonicalKey)) {
      layoutLinks.set(canonicalKey, {
        fromNodeId: edge.from_node_id,
        toNodeId: edge.to_node_id,
      });
    }
  });

  pathEdgeKeys.forEach((canonicalKey) => {
    const [fromNodeId, toNodeId] = canonicalKey.split("::");
    if (!relevantNodeIds.has(fromNodeId) || !relevantNodeIds.has(toNodeId) || layoutLinks.has(canonicalKey)) {
      return;
    }
    layoutLinks.set(canonicalKey, { fromNodeId, toNodeId });
  });

  const projectedPositions =
    layoutMode === "hierarchical"
      ? buildHierarchicalPositions({
          nodes: relevantNodes,
          depotId,
          links: Array.from(layoutLinks.values()),
        })
      : buildCoordinatePositions(relevantNodes);

  const graphNodes = relevantNodes.map((node) => {
    const projected = projectedPositions.get(node.node_id);
    const x = projected?.x ?? VIEW_WIDTH / 2;
    const y = projected?.y ?? VIEW_HEIGHT / 2;
    return {
      id: node.node_id,
      label: node.node_name || node.node_code || node.node_id,
      sublabel: node.node_code || node.node_id,
      kind: nodeKind(node, depotId, orderNodeIds),
      x,
      y,
      labelX: x,
      labelY: y,
      labelAnchor: "start",
      labelWidth: 140,
      isActive: node.is_active,
      isRouteNode: routeNodeIds.has(node.node_id),
      hasLo: orderNodeIds.has(node.node_id),
    } satisfies GraphNode;
  });
  const separatedGraphNodes = addReadableLabels(separateOverlappingNodes(graphNodes));

  const graphNodeById = new Map(separatedGraphNodes.map((node) => [node.id, node]));
  const graphEdges = new Map<string, GraphEdge>();

  edges.forEach((edge) => {
    const canonicalKey = canonicalEdgeKey(edge.from_node_id, edge.to_node_id);
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
        isRouteEdge: pathEdgeKeys.has(canonicalKey),
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
      isRouteEdge: true,
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
    nodes: separatedGraphNodes,
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

function HandIcon({ active: _active }: { active: boolean }) {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" aria-hidden="true">
      <path
        d="M8.75 11.25V5.75a1.75 1.75 0 1 1 3.5 0v4m0 1.5V4.75a1.75 1.75 0 1 1 3.5 0v7m0-.75v-4a1.75 1.75 0 1 1 3.5 0v7.25a6 6 0 0 1-6 6h-1.3a5.9 5.9 0 0 1-4.95-2.68l-2-3.08a1.75 1.75 0 1 1 2.94-1.9l.81 1.26V9.5a1.75 1.75 0 1 1 3.5 0v1.75"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function SelectZoomIcon({ active: _active }: { active: boolean }) {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" aria-hidden="true">
      <rect
        x="4.5"
        y="4.5"
        width="9"
        height="9"
        rx="1.8"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeDasharray="2.2 2.2"
      />
      <circle cx="15.5" cy="15.5" r="3.4" stroke="currentColor" strokeWidth="1.7" />
      <path d="M18 18l2 2" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
    </svg>
  );
}

function PrintIcon({ active }: { active: boolean }) {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" aria-hidden="true">
      <path
        d="M7 8V4.75h10V8m-10 8v3.25h10V16m-11.5-1.25h13A1.75 1.75 0 0 0 20.25 13V9.75A1.75 1.75 0 0 0 18.5 8h-13a1.75 1.75 0 0 0-1.75 1.75V13A1.75 1.75 0 0 0 5.5 14.75Z"
        stroke={active ? "#0f172a" : "#475569"}
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="17.25" cy="11.25" r="0.9" fill={active ? "#0f172a" : "#475569"} />
    </svg>
  );
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
  const [layoutMode, setLayoutMode] = useState<GraphLayoutMode>("coordinates");
  const nodesQuery = useQuery({
    queryKey: ["route-map-master-nodes", "depot-related-base-map"],
    queryFn: () => listNetworkNodes(),
    staleTime: 60_000,
  });
  const edgesQuery = useQuery({
    queryKey: ["route-map-master-edges", "depot-related-base-map"],
    queryFn: () => listEffectiveEdges(),
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
      layoutMode,
    });
  }, [depotId, edgesQuery.data, layoutMode, nodesQuery.data, orderSpbuIds, routes]);

  const graphNodeLookup = useMemo(
    () => new Map((graph?.nodes ?? []).map((node) => [node.id, node])),
    [graph?.nodes],
  );
  const containerRef = useRef<HTMLDivElement | null>(null);
  const dragRef = useRef<{ x: number; y: number; panX: number; panY: number } | null>(null);
  const selectZoomRef = useRef<{ x: number; y: number; canvasX: number; canvasY: number } | null>(null);
  const logoDataUrlRef = useRef<string | null>(null);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [isHandToolActive, setIsHandToolActive] = useState(false);
  const [isSelectZoomActive, setIsSelectZoomActive] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [selectionBox, setSelectionBox] = useState<{ left: number; top: number; width: number; height: number } | null>(null);
  const [isPrintingPdf, setIsPrintingPdf] = useState(false);
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
  }, [layoutMode]);

  useEffect(() => {
    setZoom(1);
    setPan({ x: 0, y: 0 });
    setLayoutMode("coordinates");
    setIsHandToolActive(false);
    setIsSelectZoomActive(false);
    setIsDragging(false);
    setSelectionBox(null);
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
        Menyiapkan base map node dan edge dari masterdata SPBU...
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
        Graph masterdata berhasil dimuat, tetapi node atau edge yang related dengan depot belum ditemukan.
      </section>
    );
  }

  const safeZoom = Math.max(zoom, 0.0001);
  const inverseZoom = 1 / safeZoom;

  const zoomAtCanvasPoint = (nextZoom: number, canvasX: number, canvasY: number) => {
    if (nextZoom === zoom) {
      return;
    }
    const worldX = (canvasX - pan.x) / zoom;
    const worldY = (canvasY - pan.y) / zoom;
    setZoom(nextZoom);
    setPan({
      x: canvasX - worldX * nextZoom,
      y: canvasY - worldY * nextZoom,
    });
  };

  const zoomBy = (delta: number) => {
    const nextZoom = clampZoom(Number((zoom + delta).toFixed(2)));
    zoomAtCanvasPoint(nextZoom, graph.width / 2, graph.height / 2);
  };

  const fitToCanvasBox = (startCanvasX: number, startCanvasY: number, endCanvasX: number, endCanvasY: number) => {
    const minCanvasX = Math.min(startCanvasX, endCanvasX);
    const maxCanvasX = Math.max(startCanvasX, endCanvasX);
    const minCanvasY = Math.min(startCanvasY, endCanvasY);
    const maxCanvasY = Math.max(startCanvasY, endCanvasY);

    const startWorldX = (minCanvasX - pan.x) / zoom;
    const endWorldX = (maxCanvasX - pan.x) / zoom;
    const startWorldY = (minCanvasY - pan.y) / zoom;
    const endWorldY = (maxCanvasY - pan.y) / zoom;

    const worldMinX = Math.min(startWorldX, endWorldX);
    const worldMaxX = Math.max(startWorldX, endWorldX);
    const worldMinY = Math.min(startWorldY, endWorldY);
    const worldMaxY = Math.max(startWorldY, endWorldY);
    const worldWidth = Math.max(1, worldMaxX - worldMinX);
    const worldHeight = Math.max(1, worldMaxY - worldMinY);
    const padding = 72;
    const availableWidth = Math.max(1, graph.width - padding * 2);
    const availableHeight = Math.max(1, graph.height - padding * 2);
    const nextZoom = clampZoom(
      Number((Math.min(availableWidth / worldWidth, availableHeight / worldHeight)).toFixed(3)),
    );

    const nextPanX = padding + (availableWidth - worldWidth * nextZoom) / 2 - worldMinX * nextZoom;
    const nextPanY = padding + (availableHeight - worldHeight * nextZoom) / 2 - worldMinY * nextZoom;

    setZoom(nextZoom);
    setPan({ x: nextPanX, y: nextPanY });
  };

  const handlePointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    if (event.button !== 0) {
      return;
    }
    const container = containerRef.current;
    if (isSelectZoomActive && container) {
      const rect = container.getBoundingClientRect();
      const canvasX = ((event.clientX - rect.left) / rect.width) * graph.width;
      const canvasY = ((event.clientY - rect.top) / rect.height) * graph.height;
      selectZoomRef.current = {
        x: event.clientX,
        y: event.clientY,
        canvasX,
        canvasY,
      };
      setSelectionBox({
        left: event.clientX - rect.left,
        top: event.clientY - rect.top,
        width: 0,
        height: 0,
      });
      event.currentTarget.setPointerCapture(event.pointerId);
      return;
    }
    if (!isHandToolActive) {
      return;
    }
    dragRef.current = {
      x: event.clientX,
      y: event.clientY,
      panX: pan.x,
      panY: pan.y,
    };
    setIsDragging(true);
    event.currentTarget.setPointerCapture(event.pointerId);
  };

  const handlePointerMove = (event: React.PointerEvent<HTMLDivElement>) => {
    const container = containerRef.current;
    if (selectZoomRef.current && container) {
      const rect = container.getBoundingClientRect();
      const startLeft = selectZoomRef.current.x - rect.left;
      const startTop = selectZoomRef.current.y - rect.top;
      const currentLeft = event.clientX - rect.left;
      const currentTop = event.clientY - rect.top;
      setSelectionBox({
        left: Math.min(startLeft, currentLeft),
        top: Math.min(startTop, currentTop),
        width: Math.abs(currentLeft - startLeft),
        height: Math.abs(currentTop - startTop),
      });
      return;
    }
    if (!dragRef.current) {
      return;
    }
    setPan({
      x: dragRef.current.panX + (event.clientX - dragRef.current.x),
      y: dragRef.current.panY + (event.clientY - dragRef.current.y),
    });
  };

  const handlePointerUp = (event: React.PointerEvent<HTMLDivElement>) => {
    const container = containerRef.current;
    if (selectZoomRef.current && container) {
      const rect = container.getBoundingClientRect();
      const endCanvasX = ((event.clientX - rect.left) / rect.width) * graph.width;
      const endCanvasY = ((event.clientY - rect.top) / rect.height) * graph.height;
      const selectionWidth = Math.abs(endCanvasX - selectZoomRef.current.canvasX);
      const selectionHeight = Math.abs(endCanvasY - selectZoomRef.current.canvasY);
      if (selectionWidth >= graph.width * 0.03 && selectionHeight >= graph.height * 0.03) {
        fitToCanvasBox(selectZoomRef.current.canvasX, selectZoomRef.current.canvasY, endCanvasX, endCanvasY);
      }
      selectZoomRef.current = null;
      setSelectionBox(null);
      if (event.currentTarget.hasPointerCapture(event.pointerId)) {
        event.currentTarget.releasePointerCapture(event.pointerId);
      }
      return;
    }
    if (!dragRef.current) {
      return;
    }
    dragRef.current = null;
    setIsDragging(false);
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
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
    zoomAtCanvasPoint(nextZoom, pointerX, pointerY);
  };

  const resetView = () => {
    setZoom(1);
    setPan({ x: 0, y: 0 });
  };

  const getLogoDataUrl = async () => {
    if (logoDataUrlRef.current) {
      return logoDataUrlRef.current;
    }
    const response = await fetch("/petrofin-logo.png");
    if (!response.ok) {
      throw new Error("Gagal memuat logo print.");
    }
    const blob = await response.blob();
    const dataUrl = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader();
      reader.onloadend = () => {
        if (typeof reader.result === "string") {
          resolve(reader.result);
          return;
        }
        reject(new Error("Gagal membaca logo print."));
      };
      reader.onerror = () => reject(new Error("Gagal membaca logo print."));
      reader.readAsDataURL(blob);
    });
    logoDataUrlRef.current = dataUrl;
    return dataUrl;
  };

  const buildPdfFromJpeg = (jpegBytes: Uint8Array, width: number, height: number) => {
    const encoder = new TextEncoder();
    const contentStream = encoder.encode(`q\n${width} 0 0 ${height} 0 0 cm\n/Im0 Do\nQ\n`);
    const segments: Uint8Array[] = [];
    const offsets: number[] = [];
    let position = 0;

    const pushText = (text: string) => {
      const bytes = encoder.encode(text);
      segments.push(bytes);
      position += bytes.length;
    };

    const pushBytes = (bytes: Uint8Array) => {
      segments.push(bytes);
      position += bytes.length;
    };

    pushText("%PDF-1.4\n");

    offsets[1] = position;
    pushText("1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n");

    offsets[2] = position;
    pushText("2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n");

    offsets[3] = position;
    pushText(
      `3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${width} ${height}] /Resources << /XObject << /Im0 4 0 R >> >> /Contents 5 0 R >>\nendobj\n`,
    );

    offsets[4] = position;
    pushText(
      `4 0 obj\n<< /Type /XObject /Subtype /Image /Width ${width} /Height ${height} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length ${jpegBytes.length} >>\nstream\n`,
    );
    pushBytes(jpegBytes);
    pushText("\nendstream\nendobj\n");

    offsets[5] = position;
    pushText(`5 0 obj\n<< /Length ${contentStream.length} >>\nstream\n`);
    pushBytes(contentStream);
    pushText("endstream\nendobj\n");

    const xrefStart = position;
    pushText("xref\n0 6\n0000000000 65535 f \n");
    for (let objectIndex = 1; objectIndex <= 5; objectIndex += 1) {
      pushText(`${String(offsets[objectIndex] ?? 0).padStart(10, "0")} 00000 n \n`);
    }
    pushText("trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n");
    pushText(`${xrefStart}\n%%EOF`);

    return new Blob(
      segments.map((segment) => segment.buffer.slice(segment.byteOffset, segment.byteOffset + segment.byteLength) as ArrayBuffer),
      { type: "application/pdf" },
    );
  };

  const exportRouteMapPdf = async () => {
    try {
      setIsPrintingPdf(true);
      const logoDataUrl = await getLogoDataUrl();
      const padding = 80;
      const headerHeight = 124;

      let minX = Number.POSITIVE_INFINITY;
      let minY = Number.POSITIVE_INFINITY;
      let maxX = Number.NEGATIVE_INFINITY;
      let maxY = Number.NEGATIVE_INFINITY;

      const includeBounds = (left: number, top: number, right: number, bottom: number) => {
        minX = Math.min(minX, left);
        minY = Math.min(minY, top);
        maxX = Math.max(maxX, right);
        maxY = Math.max(maxY, bottom);
      };

      graph.nodes.forEach((node) => {
        const labelBoxX = node.labelAnchor === "start" ? node.labelX - 12 : node.labelX - node.labelWidth + 12;
        const labelBoxY = node.labelY - 18;
        const maxRadius = node.hasLo ? NODE_RADIUS + 11 : node.kind === "order" ? NODE_RADIUS + 7 : NODE_RADIUS;
        includeBounds(node.x * zoom - maxRadius, node.y * zoom - maxRadius, node.x * zoom + maxRadius, node.y * zoom + maxRadius);
        includeBounds(
          node.x * zoom + (labelBoxX - node.x),
          node.y * zoom + (labelBoxY - node.y),
          node.x * zoom + (labelBoxX - node.x) + node.labelWidth,
          node.y * zoom + (labelBoxY - node.y) + LABEL_HEIGHT,
        );
      });

      graph.edges.forEach((edge) => {
        const from = graphNodeLookup.get(edge.fromNodeId);
        const to = graphNodeLookup.get(edge.toNodeId);
        if (!from || !to) {
          return;
        }
        const isFocusLayer = isBaseEdgeFocusActive;
        const label = [edge.roadCategory, edge.distanceKm !== null ? `${formatNumber(edge.distanceKm)} km` : null]
          .filter(Boolean)
          .join(" · ");
        if (!label || (!edge.isRouteEdge && !isFocusLayer)) {
          return;
        }
        const base = edgePoints(from, to, 0);
        includeBounds(base.midX * zoom - 56, (base.midY - 10) * zoom - 10, base.midX * zoom + 56, (base.midY - 10) * zoom + 10);
      });

      if (!Number.isFinite(minX) || !Number.isFinite(minY) || !Number.isFinite(maxX) || !Number.isFinite(maxY)) {
        throw new Error("Tidak ada konten route map untuk diprint.");
      }

      const exportWidth = Math.max(960, Math.ceil(maxX - minX + padding * 2));
      const exportHeight = Math.max(720, Math.ceil(maxY - minY + padding * 2 + headerHeight));
      const exportPanX = padding - minX;
      const exportPanY = padding + headerHeight - minY;

      const exportSvgMarkup = renderToStaticMarkup(
        <svg xmlns="http://www.w3.org/2000/svg" width={exportWidth} height={exportHeight} viewBox={`0 0 ${exportWidth} ${exportHeight}`}>
          <rect x="0" y="0" width={exportWidth} height={exportHeight} fill="#f8fbff" />
          <rect x="26" y="26" width={exportWidth - 52} height={exportHeight - 52} rx="30" fill="#ffffff" stroke="#d8e2ee" />
          <image href={logoDataUrl} x="54" y="40" width="166" height="52" preserveAspectRatio="xMidYMid meet" />
          <text x="244" y="62" fontSize="28" fontWeight="700" fill="#173047">
            Route Map
          </text>
          <text x="244" y="92" fontSize="14" fill="#667a8d">
            Layout {layoutMode === "hierarchical" ? "Hierarchical" : "Coordinate"} · Zoom {Math.round(zoom * 100)}%
          </text>
          <defs>
            {graph.truckLegend.map((item) => (
              <marker
                key={`print-arrow-${item.truckId}`}
                id={`print-arrow-${item.truckId}`}
                viewBox="0 0 7 7"
                markerUnits="userSpaceOnUse"
                markerWidth={7 * inverseZoom}
                markerHeight={7 * inverseZoom}
                refX="6.2"
                refY="3.5"
                orient="auto"
              >
                <path d="M0,0.4 L6.2,3.5 L0,6.6 L1.35,3.5 z" fill={item.color} />
              </marker>
            ))}
          </defs>
          <g transform={`translate(${exportPanX} ${exportPanY}) scale(${zoom})`}>
            {!isBaseEdgeFocusActive ? graph.edges.map((edge) => renderBaseEdge(edge)) : null}
            {graph.segments.map((segment) => {
              const from = graphNodeLookup.get(segment.fromNodeId);
              const to = graphNodeLookup.get(segment.toNodeId);
              if (!from || !to) {
                return null;
              }
              const dimmed = isBaseEdgeFocusActive || (activeTruckId !== null && activeTruckId !== segment.truckId);
              const overlay = edgePoints(from, to, laneOffset(segment), OVERLAY_EDGE_INSET);
              const overlayStroke = isBaseEdgeFocusActive ? "#cbd5e1" : segment.color;
              return (
                <g key={`print-${segment.id}`} opacity={isBaseEdgeFocusActive ? 0.32 : dimmed ? 0.12 : 1}>
                  <line
                    x1={overlay.x1}
                    y1={overlay.y1}
                    x2={overlay.x2}
                    y2={overlay.y2}
                    stroke={overlayStroke}
                    strokeWidth={segment.isReturn ? 3.6 : 4.6}
                    strokeLinecap="round"
                    strokeDasharray={segment.isReturn ? "10 8" : undefined}
                    markerEnd={`url(#print-arrow-${segment.truckId})`}
                    vectorEffect="non-scaling-stroke"
                  />
                </g>
              );
            })}
            {isBaseEdgeFocusActive ? graph.edges.map((edge) => renderBaseEdge(edge, true)) : null}
            {graph.nodes.filter((node) => node.kind !== "depot").map((node) => renderNode(node))}
            {graph.nodes.filter((node) => node.kind === "depot").map((node) => renderNode(node))}
          </g>
        </svg>,
      );

      const svgBlob = new Blob([exportSvgMarkup], { type: "image/svg+xml;charset=utf-8" });
      const svgUrl = URL.createObjectURL(svgBlob);

      try {
        const image = await new Promise<HTMLImageElement>((resolve, reject) => {
          const nextImage = new Image();
          nextImage.onload = () => resolve(nextImage);
          nextImage.onerror = () => reject(new Error("Gagal merender canvas print."));
          nextImage.src = svgUrl;
        });

        const canvas = document.createElement("canvas");
        canvas.width = exportWidth;
        canvas.height = exportHeight;
        const context = canvas.getContext("2d");
        if (!context) {
          throw new Error("Canvas print tidak tersedia.");
        }
        context.fillStyle = "#ffffff";
        context.fillRect(0, 0, exportWidth, exportHeight);
        context.drawImage(image, 0, 0, exportWidth, exportHeight);

        const jpegDataUrl = canvas.toDataURL("image/jpeg", 0.94);
        const jpegBytes = Uint8Array.from(atob(jpegDataUrl.split(",")[1]), (char) => char.charCodeAt(0));
        const pdfBlob = buildPdfFromJpeg(jpegBytes, exportWidth, exportHeight);
        const downloadUrl = URL.createObjectURL(pdfBlob);

        try {
          const link = document.createElement("a");
          link.href = downloadUrl;
          link.download = `route-map-${depotId}-${Math.round(zoom * 100)}pct.pdf`;
          document.body.appendChild(link);
          link.click();
          link.remove();
        } finally {
          URL.revokeObjectURL(downloadUrl);
        }
      } finally {
        URL.revokeObjectURL(svgUrl);
      }
    } finally {
      setIsPrintingPdf(false);
    }
  };

  const renderBaseEdge = (edge: GraphEdge, forceFocusLayer = false) => {
    const from = graphNodeLookup.get(edge.fromNodeId);
    const to = graphNodeLookup.get(edge.toNodeId);
    if (!from || !to) {
      return null;
    }

    const isFocusLayer = forceFocusLayer || isBaseEdgeFocusActive;
    const base = edgePoints(from, to, 0);
    const baseStroke = isFocusLayer ? "#020617" : "#94a3b8";
    const baseStrokeWidth = isFocusLayer ? 5.4 : edge.isRouteEdge ? 4 : 2.8;
    const baseOpacity = isFocusLayer ? 0.98 : edge.isRouteEdge ? 0.76 : 0.34;
    const label = [
      edge.roadCategory,
      edge.distanceKm !== null ? `${formatNumber(edge.distanceKm)} km` : null,
    ]
      .filter(Boolean)
      .join(" · ");

    return (
      <g key={`${forceFocusLayer ? "focus-" : ""}${edge.id}`}>
        <line
          x1={base.x1}
          y1={base.y1}
          x2={base.x2}
          y2={base.y2}
          stroke={baseStroke}
          strokeWidth={baseStrokeWidth}
          strokeOpacity={baseOpacity}
          strokeLinecap="round"
          vectorEffect="non-scaling-stroke"
        />
        {!isFocusLayer ? (
          <line
            x1={base.x1}
            y1={base.y1}
            x2={base.x2}
            y2={base.y2}
            stroke="#ffffff"
            strokeWidth={edge.isRouteEdge ? 1.2 : 0.8}
            strokeOpacity={edge.isRouteEdge ? 0.7 : 0.36}
            strokeLinecap="round"
            vectorEffect="non-scaling-stroke"
          />
        ) : null}
        {label && (edge.isRouteEdge || isFocusLayer) ? (
          <g transform={`translate(${base.midX} ${base.midY - 10}) scale(${inverseZoom})`}>
            <rect
              x={-56}
              y={-10}
              width="112"
              height="20"
              rx="10"
              fill="rgba(255,255,255,0.92)"
              stroke={isFocusLayer ? "rgba(15,23,42,0.4)" : "rgba(170,188,202,0.55)"}
            />
            <text
              x="0"
              y="4"
              fontSize="10"
              fontWeight="700"
              textAnchor="middle"
              fill={isFocusLayer ? "#020617" : "#526173"}
            >
              {label}
            </text>
          </g>
        ) : null}
      </g>
    );
  };

  const renderNode = (node: GraphNode) => {
    const dimmed = !isBaseEdgeFocusActive && activeTruckNodeIds !== null && !activeTruckNodeIds.has(node.id);
    const renderedFill = isBaseEdgeFocusActive && node.kind !== "depot" ? "#f8fafc" : nodeFill(node.kind);
    const renderedStroke = isBaseEdgeFocusActive && node.kind !== "depot" ? "#94a3b8" : nodeStroke(node.kind);
    const renderedStrokeWidth = isBaseEdgeFocusActive && node.kind !== "depot" ? 2.2 : node.kind === "order" ? 3.5 : 2.4;
    const labelBoxX = node.labelAnchor === "start" ? node.labelX - 12 : node.labelX - node.labelWidth + 12;
    const labelBoxY = node.labelY - 18;
    const connectorEndX = node.labelAnchor === "start" ? labelBoxX : labelBoxX + node.labelWidth;
    const relativeLabelX = node.labelX - node.x;
    const relativeLabelY = node.labelY - node.y;
    const relativeLabelBoxX = labelBoxX - node.x;
    const relativeLabelBoxY = labelBoxY - node.y;
    const relativeConnectorEndX = connectorEndX - node.x;

    return (
      <g key={node.id} opacity={dimmed ? 0.45 : 1} transform={`translate(${node.x} ${node.y}) scale(${inverseZoom})`}>
        {node.hasLo ? (
          <>
            <circle cx="0" cy="0" r={NODE_RADIUS + 11} fill="rgba(250,204,21,0.2)" />
            <circle
              cx="0"
              cy="0"
              r={NODE_RADIUS + 10}
              fill="none"
              stroke="#facc15"
              strokeWidth={5}
              strokeOpacity={0.9}
            />
          </>
        ) : node.kind === "order" ? (
          <circle cx="0" cy="0" r={NODE_RADIUS + 7} fill="rgba(12,122,192,0.12)" />
        ) : null}
        <circle
          cx="0"
          cy="0"
          r={NODE_RADIUS}
          fill={renderedFill}
          stroke={renderedStroke}
          strokeWidth={renderedStrokeWidth}
        />
        {!node.hasLo ? (
          <text
            x="0"
            y="4"
            fontSize="9"
            fontWeight="800"
            textAnchor="middle"
            fill={isBaseEdgeFocusActive ? "#475569" : node.kind === "depot" ? "#294200" : "#173047"}
          >
            {nodeTag(node.kind)}
          </text>
        ) : null}
        <line
          x1="0"
          y1="0"
          x2={relativeConnectorEndX}
          y2={relativeLabelY}
          stroke="rgba(100,116,139,0.42)"
          strokeWidth={1.2}
          strokeDasharray="4 4"
        />
        <rect
          x={relativeLabelBoxX}
          y={relativeLabelBoxY}
          width={node.labelWidth}
          height={LABEL_HEIGHT}
          rx={12}
          fill="rgba(255,255,255,0.88)"
          stroke={node.hasLo ? "rgba(250,204,21,0.7)" : "rgba(148,163,184,0.45)"}
          strokeWidth={node.hasLo ? 1.5 : 1}
        />
        <text
          x={relativeLabelX}
          y={relativeLabelY - 4}
          fontSize="11"
          fontWeight="700"
          textAnchor={node.labelAnchor}
          fill="#173047"
        >
          {node.label}
        </text>
        <text
          x={relativeLabelX}
          y={relativeLabelY + 11}
          fontSize="9.5"
          textAnchor={node.labelAnchor}
          fill={node.isActive ? "#667a8d" : "#94a3b8"}
        >
          {node.sublabel}
        </text>
      </g>
    );
  };

  return (
    <section className="rounded-[32px] border border-slate-200 bg-[linear-gradient(145deg,_rgba(255,255,255,0.98),_rgba(247,250,252,0.96))] p-5 shadow-sm">
      <div className="mb-4">
        <div className="max-w-4xl">
          <h3 className="text-lg font-semibold text-ink">Route Map</h3>
          <p className="mt-1 text-sm text-slate-500">
            Base map menampilkan node dan edge masterdata yang related dengan depot. SPBU yang punya LO pada hari
            ini diberi halo kuning, lalu pergerakan truck ditampilkan sebagai garis warna ter-offset.
          </p>
        </div>
      </div>

      <div className="mb-4 grid gap-3 md:grid-cols-4">
        <div className="rounded-[24px] border border-slate-200 bg-slate-50 px-4 py-3">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Node Base Map</p>
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
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">SPBU Dengan LO</p>
          <p className="mt-2 text-2xl font-semibold text-ink">{new Set(orderSpbuIds).size}</p>
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
        <span className="rounded-full bg-amber-50 px-3 py-2 text-amber-700">Halo Kuning = SPBU Dengan LO</span>
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
        className={`relative h-[74vh] min-h-[620px] overflow-hidden rounded-[28px] border border-slate-200 bg-[#f5f9fb] ${
          isSelectZoomActive ? "cursor-crosshair" : isHandToolActive ? (isDragging ? "cursor-grabbing" : "cursor-grab") : "cursor-default"
        }`}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerLeave={handlePointerUp}
        onPointerCancel={handlePointerUp}
        onWheel={handleWheel}
      >
        <div
          className="absolute right-4 top-4 z-20 flex max-w-[58rem] flex-col items-end gap-2"
          onPointerDown={(event) => event.stopPropagation()}
          onWheel={(event) => event.stopPropagation()}
          data-map-control="true"
        >
          <div className="flex flex-wrap justify-end gap-2">
            <button
              type="button"
              onClick={() => setLayoutMode("hierarchical")}
              className={
                layoutMode === "hierarchical"
                  ? "rounded-full border border-slate-900 bg-slate-900 px-4 py-2 text-sm font-semibold text-white shadow-sm transition"
                  : "rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-600 shadow-sm transition hover:border-sky-300 hover:text-sky-700"
              }
            >
              Re-layout by Hierarchical
            </button>
            <button
              type="button"
              onClick={() => setLayoutMode("coordinates")}
              className={
                layoutMode === "coordinates"
                  ? "rounded-full border border-slate-900 bg-slate-900 px-4 py-2 text-sm font-semibold text-white shadow-sm transition"
                  : "rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-600 shadow-sm transition hover:border-sky-300 hover:text-sky-700"
              }
            >
              Re-layout by Coordinate
            </button>
            <button
              type="button"
              onClick={() => {
                void exportRouteMapPdf();
              }}
              disabled={isPrintingPdf}
              className={
                isPrintingPdf
                  ? "inline-flex items-center gap-2 rounded-full border border-slate-200 bg-slate-100 px-4 py-2 text-sm font-semibold text-slate-400 shadow-sm"
                  : "inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-600 shadow-sm transition hover:border-sky-300 hover:text-sky-700"
              }
              title="Export canvas ke PDF"
            >
              <PrintIcon active={isPrintingPdf} />
              {isPrintingPdf ? "Preparing PDF..." : "Print PDF"}
            </button>
          </div>
          <div className="flex flex-wrap items-center justify-end gap-2">
            <button
              type="button"
              onClick={() =>
                setIsSelectZoomActive((current) => {
                  const next = !current;
                  setIsHandToolActive(false);
                  setSelectionBox(null);
                  selectZoomRef.current = null;
                  return next;
                })
              }
              className={
                isSelectZoomActive
                  ? "inline-flex h-11 w-11 items-center justify-center rounded-full border border-slate-900 bg-slate-900 text-white shadow-sm transition"
                  : "inline-flex h-11 w-11 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-600 shadow-sm transition hover:border-sky-300 hover:text-sky-700"
              }
              aria-pressed={isSelectZoomActive}
              aria-label="Select Zoom"
              title="Aktifkan select to zoom"
            >
              <SelectZoomIcon active={isSelectZoomActive} />
            </button>
            <button
              type="button"
              onClick={() =>
                setIsHandToolActive((current) => {
                  const next = !current;
                  setIsSelectZoomActive(false);
                  setSelectionBox(null);
                  selectZoomRef.current = null;
                  return next;
                })
              }
              className={
                isHandToolActive
                  ? "inline-flex h-11 w-11 items-center justify-center rounded-full border border-slate-900 bg-slate-900 text-white shadow-sm transition"
                  : "inline-flex h-11 w-11 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-600 shadow-sm transition hover:border-sky-300 hover:text-sky-700"
              }
              aria-pressed={isHandToolActive}
              aria-label="Hand"
              title="Aktifkan mode hand untuk drag canvas"
            >
              <HandIcon active={isHandToolActive} />
            </button>
            <button
              type="button"
              onClick={() => zoomBy(-0.2)}
              className="inline-flex h-11 w-11 items-center justify-center rounded-full border border-slate-200 bg-white text-xl font-semibold text-slate-600 shadow-sm transition hover:border-sky-300 hover:text-sky-700"
              aria-label="Zoom Out"
              title="Zoom Out"
            >
              -
            </button>
            <button
              type="button"
              onClick={() => zoomBy(0.2)}
              className="inline-flex h-11 w-11 items-center justify-center rounded-full border border-slate-200 bg-white text-xl font-semibold text-slate-600 shadow-sm transition hover:border-sky-300 hover:text-sky-700"
              aria-label="Zoom In"
              title="Zoom In"
            >
              +
            </button>
            <button
              type="button"
              onClick={resetView}
              className="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-600 shadow-sm transition hover:border-sky-300 hover:text-sky-700"
            >
              Reset
            </button>
            <span className="rounded-full bg-slate-100 px-3 py-2 text-xs font-semibold uppercase tracking-[0.16em] text-slate-500 shadow-sm">
              Zoom {Math.round(zoom * 100)}%
            </span>
          </div>
        </div>

        {selectionBox ? (
          <div
            className="pointer-events-none absolute z-10 rounded-[20px] border-2 border-sky-500 bg-sky-200/20 shadow-[0_0_0_1px_rgba(255,255,255,0.45)_inset]"
            style={{
              left: selectionBox.left,
              top: selectionBox.top,
              width: selectionBox.width,
              height: selectionBox.height,
            }}
          />
        ) : null}

        <svg width="100%" height="100%" viewBox={`0 0 ${graph.width} ${graph.height}`} preserveAspectRatio="xMidYMid meet">
          <defs>
            {graph.truckLegend.map((item) => (
              <marker
                key={`arrow-${item.truckId}`}
                id={`arrow-${item.truckId}`}
                viewBox="0 0 7 7"
                markerUnits="userSpaceOnUse"
                markerWidth={7 * inverseZoom}
                markerHeight={7 * inverseZoom}
                refX="6.2"
                refY="3.5"
                orient="auto"
              >
                <path d="M0,0.4 L6.2,3.5 L0,6.6 L1.35,3.5 z" fill={item.color} />
              </marker>
            ))}
          </defs>

          <g transform={`translate(${pan.x} ${pan.y}) scale(${zoom})`}>
            {!isBaseEdgeFocusActive ? graph.edges.map((edge) => renderBaseEdge(edge)) : null}

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
                    vectorEffect="non-scaling-stroke"
                  />
                </g>
              );
            })}

            {isBaseEdgeFocusActive ? graph.edges.map((edge) => renderBaseEdge(edge, true)) : null}

            {graph.nodes.filter((node) => node.kind !== "depot").map((node) => renderNode(node))}
            {graph.nodes.filter((node) => node.kind === "depot").map((node) => renderNode(node))}
          </g>
        </svg>
      </div>
    </section>
  );
}
