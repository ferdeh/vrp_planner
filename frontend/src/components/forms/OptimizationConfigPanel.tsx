import { useEffect, useRef, useState, type DragEvent } from "react";

const objectiveItems = [
  {
    key: "minimize_unserved_orders",
    label: "Minimize unserved orders",
    description: "Utamakan order terlayani sebanyak mungkin sebelum mengejar objective lain.",
  },
  {
    key: "minimize_truck_count",
    label: "Minimize truck count",
    description: "Prioritaskan jumlah truck aktif minimum.",
  },
  {
    key: "minimize_distance",
    label: "Minimize distance",
    description: "Gunakan biaya jarak pada objective.",
  },
  {
    key: "minimize_time",
    label: "Minimize truck time",
    description: "Gunakan biaya waktu pada objective.",
  },
  {
    key: "minimize_depot_operation_time",
    label: "Minimize depot operation time",
    description: "Dorong truck gate out lebih pagi dan menyelesaikan rute lebih cepat.",
  },
] as const;

type ObjectiveKey = (typeof objectiveItems)[number]["key"];

function normalizeObjectivePriority(priority: string[] | undefined): ObjectiveKey[] {
  const normalized: ObjectiveKey[] = [];
  for (const item of priority ?? []) {
    if (objectiveItems.some((objective) => objective.key === item) && !normalized.includes(item as ObjectiveKey)) {
      normalized.push(item as ObjectiveKey);
    }
  }
  for (const item of objectiveItems) {
    if (!normalized.includes(item.key)) {
      normalized.push(item.key);
    }
  }
  return normalized;
}

const hardItems = [
  { path: "capacity_limit", label: "Capacity limit", description: "Kapasitas truck wajib dipenuhi." },
  { path: "time_window", label: "Time window SPBU", description: "Jendela penerimaan SPBU dipaksa keras." },
  {
    path: "priority_eta",
    label: "SPBU Priority",
    description: "Order SPBU priority wajib tiba sebelum ETA yang diminta.",
  },
  {
    path: "truck_category",
    label: "Truck category",
    description: "Truck hanya boleh masuk node bila kategori truck sama atau lebih kecil dari kategori node.",
  },
  {
    path: "no_split_order",
    label: "No split order",
    description: "Aktif bila setiap order tidak boleh dipecah menjadi beberapa pengiriman.",
  },
  {
    path: "depot_operation_window",
    label: "Depot operation window",
    description: "Paksa operasi loading depot berada di dalam TW depot master data.",
  },
  { path: "max_route_duration", label: "Max route duration", description: "Aktifkan bila ingin batas durasi rute menjadi hard." },
  { path: "max_vehicle_working_time", label: "Max working time", description: "Batasi jam kerja maksimum kendaraan." },
  { path: "max_total_distance_per_vehicle", label: "Max distance per vehicle", description: "Batasi total km per kendaraan." },
] as const;

const softItems = [
  { path: "allow_unserved_orders", label: "Allow unserved", description: "Order boleh tidak terlayani dengan penalty." },
] as const;

const hardConstraintValueFieldMap: Record<string, { path: string; placeholder: string }> = {
  max_route_duration: {
    path: "max_route_duration_minutes",
    placeholder: "Input menit",
  },
  max_vehicle_working_time: {
    path: "max_vehicle_working_time_minutes",
    placeholder: "Input menit",
  },
  max_total_distance_per_vehicle: {
    path: "max_total_distance_per_vehicle_km",
    placeholder: "Input km",
  },
};

const softConstraintPenaltyFieldMap: Record<string, { path: string; placeholder: string }> = {
  allow_unserved_orders: {
    path: "penalties.unserved_order_penalty",
    placeholder: "Penalty",
  },
  capacity_limit: {
    path: "penalties.capacity_violation_penalty",
    placeholder: "Penalty",
  },
  time_window: {
    path: "penalties.late_arrival_penalty_per_minute",
    placeholder: "Penalty / min",
  },
  priority_eta: {
    path: "penalties.priority_eta_penalty_per_minute",
    placeholder: "Penalty / min",
  },
  depot_operation_window: {
    path: "penalties.depot_operation_window_penalty_per_minute",
    placeholder: "Penalty / min",
  },
  max_route_duration: {
    path: "penalties.overtime_penalty_per_minute",
    placeholder: "Penalty / min",
  },
  max_vehicle_working_time: {
    path: "penalties.overtime_penalty_per_minute",
    placeholder: "Penalty / min",
  },
  max_total_distance_per_vehicle: {
    path: "penalties.distance_weight",
    placeholder: "Penalty",
  },
};

const softConstraintValueFieldMap: Record<string, { path: string; placeholder: string }> = {
  max_route_duration: {
    path: "max_route_duration_minutes",
    placeholder: "Input menit",
  },
  max_vehicle_working_time: {
    path: "max_vehicle_working_time_minutes",
    placeholder: "Input menit",
  },
  max_total_distance_per_vehicle: {
    path: "max_total_distance_per_vehicle_km",
    placeholder: "Input km",
  },
};

const firstSolutionStrategies = [
  {
    value: "AUTOMATIC",
    label: "Automatic",
    description: "Biarkan OR-Tools memilih strategi solusi awal secara otomatis.",
  },
  {
    value: "PATH_CHEAPEST_ARC",
    label: "Path Cheapest Arc",
    description: "Membangun rute awal secara greedy dengan memilih arc termurah lebih dulu. Cepat dan cocok untuk baseline MVP.",
  },
  {
    value: "PARALLEL_CHEAPEST_INSERTION",
    label: "Parallel Cheapest Insertion",
    description: "Menyusun beberapa rute sekaligus dan memasukkan order ke posisi termurah. Biasanya memberi solusi awal lebih rapi.",
  },
  {
    value: "LOCAL_CHEAPEST_INSERTION",
    label: "Local Cheapest Insertion",
    description: "Menambahkan order satu per satu ke posisi lokal termurah pada rute. Cocok untuk solusi awal yang lebih terstruktur.",
  },
] as const;

const localSearchStrategies = [
  {
    value: "GUIDED_LOCAL_SEARCH",
    label: "Guided Local Search",
    description: "Memperbaiki solusi dengan memberi penalti pada pola rute yang buruk agar solver keluar dari solusi lokal yang kurang baik. Umumnya paling stabil untuk VRP harian.",
  },
  {
    value: "TABU_SEARCH",
    label: "Tabu Search",
    description: "Mengingat langkah yang baru dicoba agar solver tidak berputar pada pola yang sama. Cocok saat ingin eksplorasi solusi lebih agresif.",
  },
  {
    value: "SIMULATED_ANNEALING",
    label: "Simulated Annealing",
    description: "Sesekali menerima solusi yang lebih buruk untuk membuka peluang menemukan solusi global yang lebih baik. Berguna untuk kasus yang mudah terjebak lokal optimum.",
  },
] as const;

export function OptimizationConfigPanel({
  register,
  watch,
  setValue,
  prefix = "optimization_config",
  showCostControls = true,
}: {
  register: any;
  watch: any;
  setValue: any;
  prefix?: string;
  showCostControls?: boolean;
}) {
  const nullableNumber = {
    setValueAs: (value: string) => (value === "" ? null : Number(value)),
  };
  const hardConstraints = watch(`${prefix}.hard_constraints`) ?? {};
  const softConstraints = watch(`${prefix}.soft_constraints`) ?? {};
  const watchedObjectivePriority = watch(`${prefix}.objective_priority`) as string[] | undefined;
  const objectivePriority = normalizeObjectivePriority(watchedObjectivePriority);
  const selectedFirstSolutionStrategy =
    watch(`${prefix}.solver_options.first_solution_strategy`) ?? "PATH_CHEAPEST_ARC";
  const selectedLocalSearchStrategy =
    watch(`${prefix}.solver_options.local_search_metaheuristic`) ?? "GUIDED_LOCAL_SEARCH";
  const derivedSoftItems = [
    ...softItems,
    ...hardItems.filter((item) => item.path !== "no_split_order" && !hardConstraints[item.path]).map((item) => ({
      path: item.path,
      label: item.label,
      description: `${item.description} Diperlakukan sebagai soft constraint bila dipilih di sini.`,
    })),
  ];
  const activeHardItems = hardItems.filter((item) => Boolean(hardConstraints[item.path]));
  const availableHardItems = hardItems.filter((item) => !hardConstraints[item.path]);
  const activeSoftItems = derivedSoftItems.filter((item) => Boolean(softConstraints[item.path]));
  const availableSoftItems = derivedSoftItems.filter((item) => !softConstraints[item.path]);
  const [selectedHardConstraint, setSelectedHardConstraint] = useState<string>(availableHardItems[0]?.path ?? "");
  const [selectedSoftConstraint, setSelectedSoftConstraint] = useState<string>(availableSoftItems[0]?.path ?? "");
  const [isStrategyMenuOpen, setIsStrategyMenuOpen] = useState(false);
  const [previewedStrategy, setPreviewedStrategy] = useState<string | null>(null);
  const [isLocalSearchMenuOpen, setIsLocalSearchMenuOpen] = useState(false);
  const [previewedLocalSearch, setPreviewedLocalSearch] = useState<string | null>(null);
  const [draggedObjectiveKey, setDraggedObjectiveKey] = useState<ObjectiveKey | null>(null);
  const strategyMenuRef = useRef<HTMLDivElement | null>(null);
  const localSearchMenuRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (JSON.stringify(watchedObjectivePriority ?? []) !== JSON.stringify(objectivePriority)) {
      setValue(`${prefix}.objective_priority`, objectivePriority, { shouldDirty: false });
    }
  }, [objectivePriority, prefix, setValue, watchedObjectivePriority]);

  useEffect(() => {
    if (!availableHardItems.length) {
      setSelectedHardConstraint("");
      return;
    }
    if (!availableHardItems.some((item) => item.path === selectedHardConstraint)) {
      setSelectedHardConstraint(availableHardItems[0].path);
    }
  }, [availableHardItems, selectedHardConstraint]);

  useEffect(() => {
    if (!availableSoftItems.length) {
      setSelectedSoftConstraint("");
      return;
    }
    if (!availableSoftItems.some((item) => item.path === selectedSoftConstraint)) {
      setSelectedSoftConstraint(availableSoftItems[0].path);
    }
  }, [availableSoftItems, selectedSoftConstraint]);

  useEffect(() => {
    hardItems.forEach((item) => {
      if (hardConstraints[item.path] && softConstraints[item.path]) {
        setValue(`${prefix}.soft_constraints.${item.path}`, false, { shouldDirty: true });
      }
    });
  }, [hardConstraints, softConstraints, prefix, setValue]);

  useEffect(() => {
    if (!isStrategyMenuOpen) {
      return;
    }

    const handleOutsideClick = (event: MouseEvent) => {
      if (strategyMenuRef.current && !strategyMenuRef.current.contains(event.target as Node)) {
        setIsStrategyMenuOpen(false);
      }
    };

    window.addEventListener("mousedown", handleOutsideClick);
    return () => window.removeEventListener("mousedown", handleOutsideClick);
  }, [isStrategyMenuOpen]);

  useEffect(() => {
    if (!isLocalSearchMenuOpen) {
      return;
    }

    const handleOutsideClick = (event: MouseEvent) => {
      if (localSearchMenuRef.current && !localSearchMenuRef.current.contains(event.target as Node)) {
        setIsLocalSearchMenuOpen(false);
      }
    };

    window.addEventListener("mousedown", handleOutsideClick);
    return () => window.removeEventListener("mousedown", handleOutsideClick);
  }, [isLocalSearchMenuOpen]);

  const addHardConstraint = () => {
    if (!selectedHardConstraint) {
      return;
    }
    setValue(`${prefix}.hard_constraints.${selectedHardConstraint}`, true, { shouldDirty: true });
    if (selectedHardConstraint in softConstraints) {
      setValue(`${prefix}.soft_constraints.${selectedHardConstraint}`, false, { shouldDirty: true });
    }
  };

  const removeHardConstraint = (path: string) => {
    setValue(`${prefix}.hard_constraints.${path}`, false, { shouldDirty: true });
  };

  const addSoftConstraint = () => {
    if (!selectedSoftConstraint) {
      return;
    }
    setValue(`${prefix}.soft_constraints.${selectedSoftConstraint}`, true, { shouldDirty: true });
  };

  const removeSoftConstraint = (path: string) => {
    setValue(`${prefix}.soft_constraints.${path}`, false, { shouldDirty: true });
  };

  const renderHardConstraintValue = (path: string) => {
    const config = hardConstraintValueFieldMap[path];
    if (!config) {
      return <span className="text-sm text-slate-400">-</span>;
    }

    return (
      <input
        type="number"
        min="0"
        className="input max-w-40"
        placeholder={config.placeholder}
        {...register(`${prefix}.${config.path}`, nullableNumber)}
      />
    );
  };

  const renderSoftConstraintPenalty = (path: string) => {
    const config = softConstraintPenaltyFieldMap[path];
    if (!config) {
      return <span className="text-sm text-slate-400">-</span>;
    }

    return (
      <input
        type="number"
        min="0"
        className="input max-w-40"
        placeholder={config.placeholder}
        {...register(`${prefix}.${config.path}`, { valueAsNumber: true })}
      />
    );
  };

  const renderSoftConstraintValue = (path: string) => {
    const config = softConstraintValueFieldMap[path];
    if (!config) {
      return <span className="text-sm text-slate-400">-</span>;
    }

    return (
      <input
        type="number"
        min="0"
        className="input max-w-40"
        placeholder={config.placeholder}
        {...register(
          `${prefix}.${config.path}`,
          nullableNumber,
        )}
      />
    );
  };

  const selectedStrategyMeta =
    firstSolutionStrategies.find((item) => item.value === selectedFirstSolutionStrategy) ??
    firstSolutionStrategies[1];
  const selectedLocalSearchMeta =
    localSearchStrategies.find((item) => item.value === selectedLocalSearchStrategy) ??
    localSearchStrategies[0];
  const orderedObjectiveItems = objectivePriority
    .map((key) => objectiveItems.find((item) => item.key === key))
    .filter((item): item is (typeof objectiveItems)[number] => Boolean(item));

  const moveObjective = (sourceKey: ObjectiveKey, targetKey: ObjectiveKey) => {
    if (sourceKey === targetKey) {
      return;
    }
    const next = [...objectivePriority];
    const sourceIndex = next.indexOf(sourceKey);
    const targetIndex = next.indexOf(targetKey);
    if (sourceIndex < 0 || targetIndex < 0) {
      return;
    }
    next.splice(sourceIndex, 1);
    next.splice(targetIndex, 0, sourceKey);
    setValue(`${prefix}.objective_priority`, next, { shouldDirty: true });
  };

  const handleObjectiveDragStart = (objectiveKey: ObjectiveKey) => {
    setDraggedObjectiveKey(objectiveKey);
  };

  const handleObjectiveDrop = (event: DragEvent<HTMLDivElement>, targetKey: ObjectiveKey) => {
    event.preventDefault();
    if (!draggedObjectiveKey) {
      return;
    }
    moveObjective(draggedObjectiveKey, targetKey);
    setDraggedObjectiveKey(null);
  };

  return (
    <div className="space-y-8">
      <div className="space-y-4">
        <div>
          <h3 className="text-lg font-semibold text-ink">Objective</h3>
          <p className="text-sm text-slate-500">
            Drag kartu objective untuk mengatur prioritas solver. Urutan paling atas akan diprioritaskan lebih dulu.
          </p>
        </div>
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {orderedObjectiveItems.map((item, index) => {
            const isEnabled = Boolean(watch(`${prefix}.${item.key}`));
            return (
              <div
                key={item.key}
                draggable
                onDragStart={() => handleObjectiveDragStart(item.key)}
                onDragOver={(event) => event.preventDefault()}
                onDrop={(event) => handleObjectiveDrop(event, item.key)}
                onDragEnd={() => setDraggedObjectiveKey(null)}
                className={`rounded-3xl border p-4 transition ${
                  isEnabled
                    ? "border-sky-200 bg-sky-50/70"
                    : "border-slate-200 bg-slate-50"
                } ${draggedObjectiveKey === item.key ? "opacity-60" : ""}`}
              >
                <div className="mb-3 flex items-center justify-between gap-3">
                  <span className="rounded-full bg-white px-3 py-1 text-xs font-semibold text-slate-500 shadow-sm">
                    Priority #{index + 1}
                  </span>
                  <span className="cursor-grab text-slate-400" aria-hidden="true">
                    ⋮⋮
                  </span>
                </div>
                <div className="flex gap-3">
                  <input type="checkbox" className="checkbox mt-1" {...register(`${prefix}.${item.key}`)} />
                  <div>
                    <p className="font-semibold text-ink">{item.label}</p>
                    <p className="text-sm text-slate-500">{item.description}</p>
                    <p className="mt-2 text-xs text-slate-400">
                      Geser kartu ini untuk menaikkan atau menurunkan prioritas objective.
                    </p>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <div className="space-y-4">
        <div>
          <h3 className="text-lg font-semibold text-ink">Hard Constraints</h3>
          <p className="text-sm text-slate-500">Constraint yang benar-benar memblokir solusi.</p>
        </div>
        <div className="flex flex-col gap-3 rounded-3xl border border-slate-200 bg-slate-50 p-4 md:flex-row md:items-end">
          <label className="field flex-1">
            <span>Pilih hard constraint</span>
            <select
              className="input"
              value={selectedHardConstraint}
              onChange={(event) => setSelectedHardConstraint(event.target.value)}
              disabled={!availableHardItems.length}
            >
              {availableHardItems.length ? null : <option value="">Semua hard constraint sudah aktif</option>}
              {availableHardItems.map((item) => (
                <option key={item.path} value={item.path}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            className="btn-secondary"
            onClick={addHardConstraint}
            disabled={!selectedHardConstraint}
          >
            Add Constraint
          </button>
        </div>

        <div className="table-shell">
          <table>
            <thead>
              <tr>
                <th>Constraint</th>
                <th>Description</th>
                <th>Value</th>
                <th>Status</th>
                <th>Aksi</th>
              </tr>
            </thead>
            <tbody>
              {activeHardItems.length ? (
                activeHardItems.map((item) => (
                  <tr key={item.path}>
                    <td className="font-semibold text-ink">{item.label}</td>
                    <td>{item.description}</td>
                    <td>{renderHardConstraintValue(item.path)}</td>
                    <td>
                      <span className="rounded-full bg-emerald-100 px-3 py-1 text-xs font-semibold text-emerald-700">
                        Active
                      </span>
                    </td>
                    <td>
                      <button
                        type="button"
                        className="text-sm font-semibold text-rose-600"
                        onClick={() => removeHardConstraint(item.path)}
                      >
                        Hapus
                      </button>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={5} className="text-center text-sm text-slate-500">
                    Belum ada hard constraint aktif.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="space-y-4">
        <div>
          <h3 className="text-lg font-semibold text-ink">Soft Constraints</h3>
          <p className="text-sm text-slate-500">Constraint yang boleh dilanggar dengan penalty.</p>
        </div>
        <div className="flex flex-col gap-3 rounded-3xl border border-slate-200 bg-slate-50 p-4 md:flex-row md:items-end">
          <label className="field flex-1">
            <span>Pilih soft constraint</span>
            <select
              className="input"
              value={selectedSoftConstraint}
              onChange={(event) => setSelectedSoftConstraint(event.target.value)}
              disabled={!availableSoftItems.length}
            >
              {availableSoftItems.length ? null : <option value="">Semua soft constraint sudah aktif</option>}
              {availableSoftItems.map((item) => (
                <option key={item.path} value={item.path}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            className="btn-secondary"
            onClick={addSoftConstraint}
            disabled={!selectedSoftConstraint}
          >
            Add Constraint
          </button>
        </div>

        <div className="table-shell">
          <table>
            <thead>
              <tr>
                <th>Constraint</th>
                <th>Description</th>
                <th>Penalty</th>
                <th>Value</th>
                <th>Status</th>
                <th>Aksi</th>
              </tr>
            </thead>
            <tbody>
              {activeSoftItems.length ? (
                activeSoftItems.map((item) => (
                  <tr key={item.path}>
                    <td className="font-semibold text-ink">{item.label}</td>
                    <td>{item.description}</td>
                    <td>{renderSoftConstraintPenalty(item.path)}</td>
                    <td>{renderSoftConstraintValue(item.path)}</td>
                    <td>
                      <span className="rounded-full bg-amber-100 px-3 py-1 text-xs font-semibold text-amber-700">
                        Active
                      </span>
                    </td>
                    <td>
                      <button
                        type="button"
                        className="text-sm font-semibold text-rose-600"
                        onClick={() => removeSoftConstraint(item.path)}
                      >
                        Hapus
                      </button>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={6} className="text-center text-sm text-slate-500">
                    Belum ada soft constraint aktif.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className={`grid gap-4 md:grid-cols-2 ${showCostControls ? "lg:grid-cols-5" : "lg:grid-cols-3"}`}>
        {showCostControls ? (
          <>
            <label className="field">
              <span>Vehicle activation weight</span>
              <input type="number" className="input" {...register(`${prefix}.penalties.activation_cost_vehicle`, { valueAsNumber: true })} />
            </label>
            <label className="field">
              <span>Distance weight</span>
              <input type="number" className="input" {...register(`${prefix}.penalties.distance_weight`, { valueAsNumber: true })} />
            </label>
            <label className="field">
              <span>Time weight</span>
              <input type="number" className="input" {...register(`${prefix}.penalties.time_weight`, { valueAsNumber: true })} />
            </label>
            <label className="field">
              <span>Depot operation time weight</span>
              <input
                type="number"
                className="input"
                {...register(`${prefix}.penalties.depot_operation_time_weight`, { valueAsNumber: true })}
              />
            </label>
          </>
        ) : null}
        <label className="field">
          <span>Solver timeout (sec)</span>
          <input type="number" className="input" {...register(`${prefix}.solver_options.max_solver_seconds`, { valueAsNumber: true })} />
        </label>
        <label className="field">
          <span>First solution strategy</span>
          <input type="hidden" {...register(`${prefix}.solver_options.first_solution_strategy`)} />
          <div className="relative" ref={strategyMenuRef}>
            <button
              type="button"
              className="input flex items-center justify-between text-left"
              onClick={() => {
                setPreviewedStrategy(selectedFirstSolutionStrategy);
                setIsStrategyMenuOpen((current) => !current);
              }}
            >
              <span>{selectedStrategyMeta.label}</span>
              <span className="text-slate-400">{isStrategyMenuOpen ? "▴" : "▾"}</span>
            </button>
            {isStrategyMenuOpen ? (
              <div className="absolute z-30 mt-2 w-full rounded-[24px] border border-slate-200 bg-white p-3 shadow-2xl shadow-slate-200">
                <div className="space-y-2">
                  {firstSolutionStrategies.map((item) => (
                    <div
                      key={item.value}
                      className="group relative"
                      onMouseEnter={() => setPreviewedStrategy(item.value)}
                      onFocus={() => setPreviewedStrategy(item.value)}
                      onMouseLeave={() => setPreviewedStrategy(null)}
                      onBlur={() => setPreviewedStrategy(null)}
                    >
                      <button
                        type="button"
                        className={`w-full rounded-2xl border px-4 py-3 text-left transition ${
                          item.value === selectedFirstSolutionStrategy
                            ? "border-sky-200 bg-sky-50 text-sky-700"
                            : "border-transparent bg-slate-50 text-slate-700 hover:border-slate-200 hover:bg-slate-100"
                        }`}
                        onClick={() => {
                          setValue(`${prefix}.solver_options.first_solution_strategy`, item.value, { shouldDirty: true });
                          setPreviewedStrategy(item.value);
                          setIsStrategyMenuOpen(false);
                        }}
                      >
                        <div className="flex items-start justify-between gap-4">
                          <p className="text-sm font-semibold">{item.label}</p>
                          {item.value === selectedFirstSolutionStrategy ? (
                            <span className="mt-0.5 rounded-full bg-white px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-sky-600 shadow-sm">
                              Selected
                            </span>
                          ) : null}
                        </div>
                      </button>
                      {previewedStrategy === item.value ? (
                        <div className="pointer-events-none absolute left-[calc(100%+12px)] top-1/2 z-40 hidden w-72 -translate-y-1/2 rounded-[20px] border border-sky-100 bg-white p-4 shadow-2xl shadow-slate-200 xl:block">
                          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-sky-600">Algorithm Info</p>
                          <p className="mt-3 text-sm font-semibold text-ink">{item.label}</p>
                          <p className="mt-2 text-sm leading-6 text-slate-600">{item.description}</p>
                        </div>
                      ) : null}
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        </label>
        <label className="field">
          <span>Local search</span>
          <input type="hidden" {...register(`${prefix}.solver_options.local_search_metaheuristic`)} />
          <div className="relative" ref={localSearchMenuRef}>
            <button
              type="button"
              className="input flex items-center justify-between text-left"
              onClick={() => {
                setPreviewedLocalSearch(selectedLocalSearchStrategy);
                setIsLocalSearchMenuOpen((current) => !current);
              }}
            >
              <span>{selectedLocalSearchMeta.label}</span>
              <span className="text-slate-400">{isLocalSearchMenuOpen ? "▴" : "▾"}</span>
            </button>
            {isLocalSearchMenuOpen ? (
              <div className="absolute z-30 mt-2 w-full rounded-[24px] border border-slate-200 bg-white p-3 shadow-2xl shadow-slate-200">
                <div className="space-y-2">
                  {localSearchStrategies.map((item) => (
                    <div
                      key={item.value}
                      className="group relative"
                      onMouseEnter={() => setPreviewedLocalSearch(item.value)}
                      onFocus={() => setPreviewedLocalSearch(item.value)}
                      onMouseLeave={() => setPreviewedLocalSearch(null)}
                      onBlur={() => setPreviewedLocalSearch(null)}
                    >
                      <button
                        type="button"
                        className={`w-full rounded-2xl border px-4 py-3 text-left transition ${
                          item.value === selectedLocalSearchStrategy
                            ? "border-sky-200 bg-sky-50 text-sky-700"
                            : "border-transparent bg-slate-50 text-slate-700 hover:border-slate-200 hover:bg-slate-100"
                        }`}
                        onClick={() => {
                          setValue(`${prefix}.solver_options.local_search_metaheuristic`, item.value, {
                            shouldDirty: true,
                          });
                          setPreviewedLocalSearch(item.value);
                          setIsLocalSearchMenuOpen(false);
                        }}
                      >
                        <div className="flex items-start justify-between gap-4">
                          <p className="text-sm font-semibold">{item.label}</p>
                          {item.value === selectedLocalSearchStrategy ? (
                            <span className="mt-0.5 rounded-full bg-white px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-sky-600 shadow-sm">
                              Selected
                            </span>
                          ) : null}
                        </div>
                      </button>
                      {previewedLocalSearch === item.value ? (
                        <div className="pointer-events-none absolute left-[calc(100%+12px)] top-1/2 z-40 hidden w-72 -translate-y-1/2 rounded-[20px] border border-sky-100 bg-white p-4 shadow-2xl shadow-slate-200 xl:block">
                          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-sky-600">Algorithm Info</p>
                          <p className="mt-3 text-sm font-semibold text-ink">{item.label}</p>
                          <p className="mt-2 text-sm leading-6 text-slate-600">{item.description}</p>
                        </div>
                      ) : null}
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        </label>
      </div>
    </div>
  );
}
