import { formatCurrency, formatNumber } from "../../lib/format";

export function MetricCard({
  label,
  value,
  tone = "number",
}: {
  label: string;
  value: number;
  tone?: "currency" | "number";
}) {
  return (
    <div className="panel p-6">
      <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-500">{label}</p>
      <p className="mt-4 font-display text-4xl leading-none text-ink md:text-5xl">
        {tone === "currency" ? formatCurrency(value) : formatNumber(value)}
      </p>
      <div className="mt-5 h-1.5 w-20 rounded-full bg-gradient-to-r from-sky-500 to-cyan-400" />
    </div>
  );
}
