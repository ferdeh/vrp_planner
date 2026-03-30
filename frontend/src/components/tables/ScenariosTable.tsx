import { Link } from "react-router-dom";
import { formatCurrency, formatNumber, statusClass, statusLabel } from "../../lib/format";
import type { ScenarioListItem } from "../../types/api";

export function ScenariosTable({
  items,
  selectedIds,
  onSelectionChange,
}: {
  items: ScenarioListItem[];
  selectedIds: string[];
  onSelectionChange: (ids: string[]) => void;
}) {
  const allSelected = items.length > 0 && items.every((item) => selectedIds.includes(item.scenario_id));

  const toggleAll = () => {
    if (allSelected) {
      onSelectionChange([]);
      return;
    }
    onSelectionChange(items.map((item) => item.scenario_id));
  };

  const toggleOne = (scenarioId: string) => {
    if (selectedIds.includes(scenarioId)) {
      onSelectionChange(selectedIds.filter((item) => item !== scenarioId));
      return;
    }
    onSelectionChange([...selectedIds, scenarioId]);
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-3 rounded-[24px] border border-slate-200/80 bg-slate-50/90 px-4 py-3 text-sm text-slate-500">
        <span>{selectedIds.length} scenario terpilih</span>
        <button type="button" className="font-semibold text-sky-700" onClick={toggleAll}>
          {allSelected ? "Unselect all" : "Select all"}
        </button>
      </div>
      <div className="table-shell bg-white">
        <table>
          <thead>
            <tr>
              <th>
                <input
                  type="checkbox"
                  className="checkbox"
                  checked={allSelected}
                  onChange={toggleAll}
                  aria-label="Select all scenarios"
                />
              </th>
              <th>Tanggal</th>
              <th>Depot</th>
              <th>Status</th>
              <th>Truck Aktif</th>
              <th>Total Cost</th>
              <th>Total Distance</th>
              <th>Total Time</th>
              <th>Detail</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.scenario_id}>
                <td>
                  <input
                    type="checkbox"
                    className="checkbox"
                    checked={selectedIds.includes(item.scenario_id)}
                    onChange={() => toggleOne(item.scenario_id)}
                    aria-label={`Select scenario ${item.scenario_id}`}
                  />
                </td>
                <td>{item.dispatch_date}</td>
                <td>{item.depot_id}</td>
                <td>
                  <span className={`rounded-full px-3 py-1 text-xs font-semibold ${statusClass(item.status)}`}>
                    {statusLabel(item.status)}
                  </span>
                </td>
                <td>{item.active_truck_count}</td>
                <td>{formatCurrency(item.total_cost)}</td>
                <td>{formatNumber(item.total_distance)} km</td>
                <td>{formatNumber(item.total_time)} min</td>
                <td>
                  {item.status === "processing" ? (
                    <span className="font-semibold text-sky-700">On Process</span>
                  ) : (
                    <Link className="font-semibold text-sea" to={`/scenarios/${item.scenario_id}`}>
                      Lihat
                    </Link>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
