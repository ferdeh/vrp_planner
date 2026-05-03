import { formatNumber } from "../lib/format";

export const CLUSTER_PALETTE = [
  "#0f766e",
  "#2563eb",
  "#f59e0b",
  "#7c3aed",
  "#dc2626",
  "#0891b2",
  "#65a30d",
  "#ea580c",
];

export function getClusterColor(clusterId: string | null | undefined) {
  if (!clusterId) {
    return "#94a3b8";
  }
  let hash = 0;
  for (const char of clusterId) {
    hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
  }
  return CLUSTER_PALETTE[hash % CLUSTER_PALETTE.length];
}

export function solverModeColor(solverMode: string) {
  return solverMode === "RouteFinder ON" ? "#0f766e" : "#d97706";
}

export function formatPercent(value: number | null | undefined, maximumFractionDigits = 0) {
  if (value == null) {
    return "N/A";
  }
  return `${new Intl.NumberFormat("id-ID", { maximumFractionDigits }).format(value * 100)}%`;
}

export function shortRunLabel(value: string) {
  return new Intl.DateTimeFormat("id-ID", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

export function buildTicks(maxValue: number, count = 4) {
  const safeMax = Math.max(maxValue, 1);
  return Array.from({ length: count }, (_, index) => (safeMax / (count - 1)) * index);
}

export function emptyChart(label: string) {
  return (
    <div className="flex h-[220px] items-center justify-center rounded-[24px] border border-dashed border-slate-200 bg-slate-50 text-sm text-slate-500">
      {label}
    </div>
  );
}

export function metricLabel(value: number | null | undefined, suffix: string) {
  if (value == null) {
    return "N/A";
  }
  return `${formatNumber(value)} ${suffix}`.trim();
}
