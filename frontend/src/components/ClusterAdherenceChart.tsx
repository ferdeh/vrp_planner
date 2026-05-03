import type { ClusterMetricsHistoryItem } from "../types/api";
import { buildTicks, emptyChart, formatPercent, shortRunLabel, solverModeColor } from "./clusterMetricsShared";

const WIDTH = 420;
const HEIGHT = 220;
const PADDING = { top: 16, right: 18, bottom: 44, left: 42 };

export function ClusterAdherenceChart({
  history,
}: {
  history: ClusterMetricsHistoryItem[];
}) {
  const points = history.filter((item) => item.cluster_adherence != null);
  if (!points.length) {
    return (
      <section className="panel">
        <div className="panel-header">
          <h3 className="text-lg font-semibold text-ink">Cluster Adherence Trend</h3>
        </div>
        <div className="panel-body">{emptyChart("Belum ada histori cluster adherence.")}</div>
      </section>
    );
  }

  const innerWidth = WIDTH - PADDING.left - PADDING.right;
  const innerHeight = HEIGHT - PADDING.top - PADDING.bottom;
  const ticks = buildTicks(1, 5);
  const xStep = points.length === 1 ? 0 : innerWidth / (points.length - 1);

  const series = new Map<string, Array<{ x: number; y: number; item: ClusterMetricsHistoryItem }>>();
  points.forEach((item, index) => {
    const x = PADDING.left + xStep * index;
    const y = PADDING.top + innerHeight * (1 - (item.cluster_adherence ?? 0));
    const key = item.solver_mode;
    const current = series.get(key) ?? [];
    current.push({ x, y, item });
    series.set(key, current);
  });

  return (
    <section className="panel">
      <div className="panel-header">
        <h3 className="text-lg font-semibold text-ink">Cluster Adherence Trend</h3>
        <p className="mt-2 text-sm text-slate-500">Bandingkan pola RouteFinder ON vs OFF antar rerun depot/tanggal yang sama.</p>
      </div>
      <div className="panel-body">
        <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="h-[220px] w-full">
          {ticks.map((tick) => {
            const y = PADDING.top + innerHeight * (1 - tick);
            return (
              <g key={tick}>
                <line x1={PADDING.left} y1={y} x2={WIDTH - PADDING.right} y2={y} stroke="#e2e8f0" strokeDasharray="4 6" />
                <text x={10} y={y + 4} fill="#64748b" fontSize="10">
                  {formatPercent(tick, 0)}
                </text>
              </g>
            );
          })}

          {points.map((item, index) => {
            const x = PADDING.left + xStep * index;
            return (
              <text key={item.scenario_id} x={x} y={HEIGHT - 16} textAnchor="middle" fill="#64748b" fontSize="10">
                {shortRunLabel(item.created_at)}
              </text>
            );
          })}

          {Array.from(series.entries()).map(([solverMode, items]) => {
            const path = items.map((item, index) => `${index === 0 ? "M" : "L"} ${item.x} ${item.y}`).join(" ");
            return (
              <g key={solverMode}>
                <path d={path} fill="none" stroke={solverModeColor(solverMode)} strokeWidth="3" strokeLinecap="round" />
                {items.map(({ x, y, item }) => (
                  <g key={item.scenario_id}>
                    <circle cx={x} cy={y} r="5" fill={solverModeColor(solverMode)}>
                      <title>{`${solverMode} • ${formatPercent(item.cluster_adherence, 0)}`}</title>
                    </circle>
                  </g>
                ))}
              </g>
            );
          })}
        </svg>

        <div className="mt-4 flex flex-wrap gap-3 text-xs font-semibold text-slate-500">
          {Array.from(series.keys()).map((solverMode) => (
            <span key={solverMode} className="inline-flex items-center gap-2 rounded-full bg-slate-50 px-3 py-1.5">
              <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: solverModeColor(solverMode) }} />
              {solverMode}
            </span>
          ))}
        </div>
      </div>
    </section>
  );
}
