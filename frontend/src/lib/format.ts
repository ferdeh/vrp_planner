export function formatNumber(value: number) {
  return new Intl.NumberFormat("id-ID", { maximumFractionDigits: 2 }).format(value);
}

export function formatCurrency(value: number) {
  return new Intl.NumberFormat("id-ID", {
    style: "currency",
    currency: "IDR",
    maximumFractionDigits: 0,
  }).format(value);
}

export function statusClass(status: string) {
  if (status === "processing") return "bg-sky-100 text-sky-700";
  if (status === "feasible") return "bg-emerald-100 text-emerald-700";
  if (status === "partial") return "bg-amber-100 text-amber-700";
  if (status === "timeout") return "bg-orange-100 text-orange-700";
  if (status === "infeasible") return "bg-rose-100 text-rose-700";
  return "bg-slate-200 text-slate-700";
}

export function statusLabel(status: string) {
  if (status === "processing") return "On Process";
  if (status === "feasible") return "Feasible";
  if (status === "partial") return "Partial";
  if (status === "timeout") return "Timeout";
  if (status === "infeasible") return "Infeasible";
  if (status === "error") return "Error";
  return status;
}

export function analysisStatusClass(status: string) {
  if (status === "processing") return "bg-sky-100 text-sky-700";
  if (status === "completed") return "bg-emerald-100 text-emerald-700";
  if (status === "error") return "bg-rose-100 text-rose-700";
  return "bg-slate-200 text-slate-700";
}

export function analysisStatusLabel(status: string) {
  if (status === "processing") return "On Process";
  if (status === "completed") return "Completed";
  if (status === "error") return "Error";
  return status;
}

export function analysisLevelLabel(level: string) {
  if (level === "level_1") return "Level 1 · Cepat";
  if (level === "level_2") return "Level 2 · Kuat";
  return level;
}
