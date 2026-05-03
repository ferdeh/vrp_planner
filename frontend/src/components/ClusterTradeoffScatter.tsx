import { formatNumber } from "../lib/format";
import type { ClusterMetricsHistoryItem } from "../types/api";
import { emptyChart, formatPercent, solverModeColor } from "./clusterMetricsShared";

const WIDTH = 420;
const HEIGHT = 220;
const PADDING = { top: 16, right: 18, bottom: 36, left: 56 };

export function ClusterTradeoffScatter({
  history,
}: {
  history: ClusterMetricsHistoryItem[];
}) {
  const points = history.filter((item) => item.cluster_adherence != null);
  if (!points.length) {
    return (
      <section className="panel">
        <div className="panel-header">
          <h3 className="text-lg font-semibold text-ink">Cost vs Cluster Tradeoff</h3>
        </div>
        <div className="panel-body">{emptyChart("Belum ada data tradeoff cluster.")}</div>
      </section>
    );
  }

  const maxDistance = Math.max(...points.map((item) => item.total_distance), 1);
  const maxDemand = Math.max(...points.map((item) => item.total_demand), 1);
  const innerWidth = WIDTH - PADDING.left - PADDING.right;
  const innerHeight = HEIGHT - PADDING.top - PADDING.bottom;

  return (
    <section className="panel">
      <div className="panel-header">
        <h3 className="text-lg font-semibold text-ink">Cost vs Cluster Tradeoff</h3>
        <p className="mt-2 text-sm text-slate-500">Jarak lebih rendah dengan adherence lebih tinggi berarti cluster memberi dampak baik.</p>
      </div>
      <div className="panel-body">
        <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="h-[220px] w-full">
          <line x1={PADDING.left} y1={HEIGHT - PADDING.bottom} x2={WIDTH - PADDING.right} y2={HEIGHT - PADDING.bottom} stroke="#cbd5e1" />
          <line x1={PADDING.left} y1={PADDING.top} x2={PADDING.left} y2={HEIGHT - PADDING.bottom} stroke="#cbd5e1" />

          {[0, 0.25, 0.5, 0.75, 1].map((tick) => {
            const y = PADDING.top + innerHeight * (1 - tick);
            return (
              <g key={tick}>
                <line x1={PADDING.left} y1={y} x2={WIDTH - PADDING.right} y2={y} stroke="#e2e8f0" strokeDasharray="4 6" />
                <text x={12} y={y + 4} fill="#64748b" fontSize="10">
                  {formatPercent(tick, 0)}
                </text>
              </g>
            );
          })}

          {points.map((item) => {
            const x = PADDING.left + (item.total_distance / maxDistance) * innerWidth;
            const y = PADDING.top + innerHeight * (1 - (item.cluster_adherence ?? 0));
            const radius = 8 + (item.total_demand / maxDemand) * 10;
            return (
              <circle
                key={item.scenario_id}
                cx={x}
                cy={y}
                r={radius}
                fill={solverModeColor(item.solver_mode)}
                fillOpacity="0.72"
                stroke="#fff"
                strokeWidth="2"
              >
                <title>{`${item.solver_mode} • ${formatNumber(item.total_distance)} km • ${formatPercent(item.cluster_adherence, 0)}`}</title>
              </circle>
            );
          })}

          <text x={WIDTH / 2} y={HEIGHT - 8} textAnchor="middle" fill="#64748b" fontSize="11">
            Total Distance (km)
          </text>
          <text x={-HEIGHT / 2} y={16} transform="rotate(-90)" textAnchor="middle" fill="#64748b" fontSize="11">
            Cluster Adherence
          </text>
        </svg>

        <div className="mt-4 flex flex-wrap gap-3 text-xs font-semibold text-slate-500">
          {["RouteFinder ON", "RouteFinder OFF"].map((solverMode) => (
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
