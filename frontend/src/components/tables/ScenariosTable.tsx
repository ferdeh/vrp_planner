import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { formatCurrency, formatNumber, statusClass, statusLabel } from "../../lib/format";
import type { ScenarioListItem } from "../../types/api";

const PAGE_SIZE_OPTIONS = [10, 50, 100] as const;

export function ScenariosTable({
  items,
  selectedIds,
  onSelectionChange,
  enablePagination = false,
}: {
  items: ScenarioListItem[];
  selectedIds: string[];
  onSelectionChange: (ids: string[]) => void;
  enablePagination?: boolean;
}) {
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState<number | "all">(10);
  const totalItems = items.length;
  const totalPages = !enablePagination || pageSize === "all" ? 1 : Math.max(1, Math.ceil(totalItems / pageSize));
  const safeCurrentPage = Math.min(currentPage, totalPages);
  const pageStart = !enablePagination || pageSize === "all" ? 0 : (safeCurrentPage - 1) * pageSize;
  const pageEnd = !enablePagination || pageSize === "all" ? totalItems : pageStart + pageSize;
  const visibleItems = enablePagination ? items.slice(pageStart, pageEnd) : items;
  const visibleIds = visibleItems.map((item) => item.scenario_id);
  const allSelected = visibleItems.length > 0 && visibleItems.every((item) => selectedIds.includes(item.scenario_id));

  useEffect(() => {
    if (currentPage !== safeCurrentPage) {
      setCurrentPage(safeCurrentPage);
    }
  }, [currentPage, safeCurrentPage]);

  useEffect(() => {
    if (!enablePagination) {
      return;
    }
    setCurrentPage(1);
  }, [enablePagination, pageSize]);

  const toggleAll = () => {
    if (allSelected) {
      onSelectionChange(selectedIds.filter((item) => !visibleIds.includes(item)));
      return;
    }
    onSelectionChange(Array.from(new Set([...selectedIds, ...visibleIds])));
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
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-[24px] border border-slate-200/80 bg-slate-50/90 px-4 py-3 text-sm text-slate-500">
        <div className="flex flex-wrap items-center gap-3">
          <span>{selectedIds.length} scenario terpilih</span>
          <button type="button" className="font-semibold text-sky-700" onClick={toggleAll}>
            {allSelected ? "Batal pilih halaman" : "Pilih semua halaman"}
          </button>
        </div>
        {enablePagination ? (
          <div className="flex flex-wrap items-center gap-3">
            <span>
              Menampilkan {totalItems === 0 ? 0 : pageStart + 1}-{Math.min(pageEnd, totalItems)} dari {totalItems}
            </span>
            <label className="flex items-center gap-2">
              <span>Per page</span>
              <select
                className="input h-10 w-auto min-w-[96px] rounded-full px-4 py-0 text-sm"
                value={pageSize}
                onChange={(event) => {
                  const nextValue = event.target.value;
                  setPageSize(nextValue === "all" ? "all" : Number(nextValue));
                }}
              >
                {PAGE_SIZE_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
                <option value="all">All</option>
              </select>
            </label>
          </div>
        ) : null}
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
              <th>Scenario ID</th>
              <th>Tanggal</th>
              <th>Depot</th>
              <th>Status</th>
              <th>Total Demand</th>
              <th>Total Served</th>
              <th>Truck Aktif</th>
              <th>Total Cost</th>
              <th>Total Distance</th>
              <th>Total Time</th>
              <th>Detail</th>
            </tr>
          </thead>
          <tbody>
            {visibleItems.map((item) => (
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
                <td className="max-w-[220px] break-all font-mono text-xs leading-5">{item.scenario_id}</td>
                <td>{item.dispatch_date}</td>
                <td>{item.depot_id}</td>
                <td>
                  <div className="space-y-1">
                    <span className={`inline-flex rounded-full px-3 py-1 text-xs font-semibold ${statusClass(item.status)}`}>
                      {statusLabel(item.status)}
                    </span>
                    {item.status === "processing" && item.status_message ? (
                      <p className="max-w-[240px] text-xs leading-5 text-slate-500">{item.status_message}</p>
                    ) : null}
                  </div>
                </td>
                <td>{formatNumber(item.total_demand)} KL</td>
                <td>{formatNumber(item.total_delivered_demand)} KL</td>
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
      {enablePagination && totalPages > 1 ? (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-[24px] border border-slate-200/80 bg-white/90 px-4 py-3 text-sm text-slate-500 shadow-sm">
          <span>
            Page {safeCurrentPage} / {totalPages}
          </span>
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              className="btn-secondary px-4 py-2"
              disabled={safeCurrentPage === 1}
              onClick={() => setCurrentPage((page) => Math.max(1, page - 1))}
            >
              Prev
            </button>
            <button
              type="button"
              className="btn-secondary px-4 py-2"
              disabled={safeCurrentPage === totalPages}
              onClick={() => setCurrentPage((page) => Math.min(totalPages, page + 1))}
            >
              Next
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
