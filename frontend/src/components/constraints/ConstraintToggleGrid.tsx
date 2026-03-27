interface Item {
  path: string;
  label: string;
  description: string;
}

export function ConstraintToggleGrid({
  register,
  mode,
  prefix,
  items,
}: {
  register: any;
  mode: "hard" | "soft";
  prefix: string;
  items: Item[];
}) {
  return (
    <div className="grid gap-3 md:grid-cols-2">
      {items.map((item) => {
        const path =
          mode === "hard"
            ? `${prefix}.hard_constraints.${item.path}`
            : `${prefix}.soft_constraints.${item.path}`;

        return (
          <label key={item.path} className="rounded-3xl border border-slate-200 bg-slate-50 p-4">
            <div className="flex items-start gap-3">
              <input type="checkbox" className="checkbox mt-1" {...register(path)} />
              <div>
                <p className="font-semibold text-ink">{item.label}</p>
                <p className="mt-1 text-sm text-slate-500">{item.description}</p>
              </div>
            </div>
          </label>
        );
      })}
    </div>
  );
}
