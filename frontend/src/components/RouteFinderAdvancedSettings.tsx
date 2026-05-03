export function RouteFinderAdvancedSettings({
  register,
  watch,
  prefix = "",
}: {
  register: any;
  watch: any;
  prefix?: string;
}) {
  const fieldPath = (name: string) => (prefix ? `${prefix}.${name}` : name);
  if (!watch(fieldPath("use_routefinder"))) {
    return null;
  }

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <label className="field rounded-[24px] border border-slate-200 bg-white p-5 shadow-sm">
        <span className="text-sm font-semibold text-ink">Cluster Mode</span>
        <select className="input" {...register(fieldPath("cluster_mode"))}>
          <option value="soft">Soft</option>
          <option value="hard">Hard</option>
        </select>
      </label>

      <label className="field rounded-[24px] border border-slate-200 bg-white p-5 shadow-sm">
        <span className="text-sm font-semibold text-ink">Max Cluster Size</span>
        <input type="number" className="input" {...register(fieldPath("max_cluster_size"), { valueAsNumber: true })} />
      </label>
    </div>
  );
}
