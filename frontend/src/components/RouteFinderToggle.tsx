export function RouteFinderToggle({
  register,
  watch,
  prefix = "",
}: {
  register: any;
  watch: any;
  prefix?: string;
}) {
  const fieldPath = (name: string) => (prefix ? `${prefix}.${name}` : name);
  const enabled = watch(fieldPath("use_routefinder"));

  return (
    <label className="flex items-start gap-4 rounded-[24px] border border-slate-200 bg-white p-5 shadow-sm">
      <input type="checkbox" className="checkbox mt-1" {...register(fieldPath("use_routefinder"))} />
      <div className="space-y-2">
        <span className="block text-base font-semibold text-ink">
          Use RouteFinder Clustering
        </span>
        <span className="block text-sm leading-6 text-slate-600">
          Saat aktif, RouteFinder hanya membentuk cluster SPBU dan grouping order. OR-Tools tetap menjadi solver final
          untuk assignment vehicle, multi-trip, dan route akhir.
        </span>
        <span className={`inline-flex rounded-full px-3 py-1 text-xs font-semibold ${
          enabled ? "bg-emerald-100 text-emerald-700" : "bg-slate-100 text-slate-600"
        }`}>
          {enabled ? "Enabled" : "Default OFF"}
        </span>
      </div>
    </label>
  );
}
