import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { RouteFinderAdvancedSettings } from "../components/RouteFinderAdvancedSettings";
import { RouteFinderToggle } from "../components/RouteFinderToggle";
import { AppLayout } from "../components/layout/AppLayout";
import { PageHeader } from "../components/layout/PageHeader";
import { OptimizationConfigPanel } from "../components/forms/OptimizationConfigPanel";
import { SolverModeCard } from "../components/SolverModeCard";
import { SolverRunMetrics } from "../components/SolverRunMetrics";
import { defaultOptimizationConfig } from "../lib/sampleData";
import { getSettings, getSolverSettings, updateSettings, updateSolverSettings } from "../services/api";
import type { OptimizationRequest, SolverSettings, SystemSettingsPayload } from "../types/api";

const costParameterGroups = [
  {
    title: "Penalty Shipment dan Service Level",
    description: "Parameter ini mengatur seberapa mahal order drop, telat, dan overtime saat solver membandingkan solusi.",
    items: [
      {
        path: "penalties.unserved_order_penalty",
        label: "Unserved order penalty",
        helper: "Penalty per shipment yang tidak terkirim saat Allow unserved aktif.",
      },
      {
        path: "penalties.late_arrival_penalty_per_minute",
        label: "Late arrival penalty / minute",
        helper: "Penalty per menit keterlambatan terhadap TW SPBU saat Time window dipakai sebagai soft constraint.",
      },
      {
        path: "penalties.priority_eta_penalty_per_minute",
        label: "Priority ETA penalty / minute",
        helper: "Penalty per menit keterlambatan order priority saat SPBU Priority dipakai sebagai soft constraint.",
      },
      {
        path: "penalties.overtime_penalty_per_minute",
        label: "Overtime penalty / minute",
        helper: "Penalty per menit pelanggaran working time atau route duration.",
      },
      {
        path: "penalties.depot_operation_window_penalty_per_minute",
        label: "Depot operation window penalty / minute",
        helper: "Penalty per menit jika operasi depot melewati jendela operasi depot.",
      },
      {
        path: "penalties.active_truck_idle_penalty_per_minute",
        label: "Active truck idle penalty / minute",
        helper: "Penalty saat truck aktif selesai terlalu cepat. Dipakai di mode minimize truck count dan minimize depot operation.",
      },
      {
        path: "penalties.unused_opportunity_capacity_penalty_per_kl",
        label: "Unused opportunity capacity penalty / KL",
        helper: "Penalty untuk kapasitas trip/reload yang terlanjur dijalankan tetapi tidak termanfaatkan. Dipakai di mode minimize depot operation.",
      },
      {
        path: "penalties.capacity_violation_penalty",
        label: "Capacity violation penalty",
        helper: "Disimpan untuk roadmap. Saat ini kapasitas masih diperlakukan hard oleh solver.",
      },
    ],
  },
  {
    title: "Threshold Utilisasi Truck Aktif",
    description: "Threshold ini menentukan minimal proporsi jam kerja yang dianggap cukup untuk truck aktif pada masing-masing objective utama.",
    items: [
      {
        path: "penalties.active_truck_idle_threshold_percent_truck_count",
        label: "Idle threshold truck count (%)",
        helper: "Dipakai saat objective utama minimize truck count. Default 50 berarti truck aktif mulai kena penalty bila kerja di bawah 50% window efektifnya.",
      },
      {
        path: "penalties.active_truck_idle_threshold_percent_depot_operation",
        label: "Idle threshold depot (%)",
        helper: "Dipakai saat objective utama minimize depot operation. Default 75 berarti truck aktif diharapkan bekerja minimal 75% window efektifnya.",
      },
    ],
  },
  {
    title: "Objective Weight dan Cost Routing",
    description: "Parameter ini memengaruhi biaya route dan objective efisiensi setelah solver mendapatkan service level terbaik.",
    items: [
      {
        path: "penalties.activation_cost_vehicle",
        label: "Activation cost vehicle",
        helper: "Biaya aktivasi truck. Dipakai sekaligus pada objective solver dan total cost hasil.",
      },
      {
        path: "penalties.distance_weight",
        label: "Distance weight",
        helper: "Biaya per km untuk objective solver dan total cost hasil.",
      },
      {
        path: "penalties.time_weight",
        label: "Time weight",
        helper: "Biaya per menit perjalanan untuk objective solver dan total cost hasil.",
      },
      {
        path: "penalties.depot_operation_time_weight",
        label: "Depot operation time weight",
        helper: "Bobot objective agar truck gate out lebih cepat dan route span lebih rapat.",
      },
    ],
  },
];

const schema = z.object({
  default_optimization_config: z.any(),
  ui_preferences: z.record(z.string(), z.unknown()),
  solver_settings: z.object({
    use_routefinder: z.boolean(),
    cluster_mode: z.enum(["soft", "hard"]),
    max_cluster_size: z.number().int().min(3).max(6),
  }),
});

type FormValue = {
  default_optimization_config: OptimizationRequest["optimization_config"];
  ui_preferences: Record<string, unknown>;
  solver_settings: SolverSettings;
};

const defaultSolverSettings: SolverSettings = {
  use_routefinder: false,
  cluster_mode: "soft",
  max_cluster_size: 5,
};

export function SettingsPage() {
  const queryClient = useQueryClient();
  const settingsQuery = useQuery({
    queryKey: ["settings"],
    queryFn: getSettings,
  });
  const solverSettingsQuery = useQuery({
    queryKey: ["solver-settings"],
    queryFn: getSolverSettings,
  });
  const form = useForm<FormValue>({
    resolver: zodResolver(schema),
    defaultValues: {
      default_optimization_config: defaultOptimizationConfig,
      ui_preferences: {},
      solver_settings: defaultSolverSettings,
    },
  });

  useEffect(() => {
    if (settingsQuery.data || solverSettingsQuery.data) {
      form.reset({
        default_optimization_config: settingsQuery.data?.default_optimization_config ?? defaultOptimizationConfig,
        ui_preferences: settingsQuery.data?.ui_preferences ?? {},
        solver_settings: solverSettingsQuery.data
          ? {
              use_routefinder: solverSettingsQuery.data.use_routefinder,
              cluster_mode: solverSettingsQuery.data.cluster_mode,
              max_cluster_size: solverSettingsQuery.data.max_cluster_size,
            }
          : defaultSolverSettings,
      });
    }
  }, [form, settingsQuery.data, solverSettingsQuery.data]);

  const mutation = useMutation({
    mutationFn: async (values: FormValue) => {
      const settingsPayload: SystemSettingsPayload = {
        default_optimization_config: values.default_optimization_config,
        ui_preferences: values.ui_preferences,
      };
      await updateSettings(settingsPayload);
      await updateSolverSettings(values.solver_settings);
    },
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["settings"] }),
        queryClient.invalidateQueries({ queryKey: ["solver-settings"] }),
      ]);
    },
  });
  const solverSettings = form.watch("solver_settings");

  return (
    <AppLayout>
      <PageHeader
        title="Settings dan Constraints"
        description="Atur default global untuk objective, hard constraint, soft constraint, dan solver option."
      />

      <form
        className="space-y-6"
        onSubmit={form.handleSubmit((values) => mutation.mutate(values))}
      >
        <section className="panel">
          <div className="panel-body">
            <OptimizationConfigPanel
              register={(name: string, options?: Record<string, unknown>) =>
                form.register(name as never, options as never)
              }
              watch={form.watch}
              setValue={form.setValue}
              prefix="default_optimization_config"
              showCostControls={false}
            />
          </div>
        </section>

        <section className="panel">
          <div className="panel-body space-y-6">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.32em] text-sky-600">Cost Parameter</p>
              <h2 className="mt-3 text-2xl font-semibold text-ink">Default Cost dan Penalty</h2>
              <p className="mt-3 max-w-4xl text-sm leading-6 text-slate-600">
                Semua parameter cost yang dipakai solver dapat diatur di sini. Nilai ini akan menjadi default global
                untuk skenario baru, lalu masih bisa diubah lagi pada form optimisasi bila diperlukan.
              </p>
            </div>

            <div className="flex justify-end">
              <button
                type="button"
                className="btn-secondary"
                onClick={() => {
                  Object.entries(defaultOptimizationConfig.penalties).forEach(([key, value]) => {
                    form.setValue(`default_optimization_config.penalties.${key}` as never, value as never, {
                      shouldDirty: true,
                    });
                  });
                }}
              >
                Reset parameter solver ke default
              </button>
            </div>

            <div className="rounded-[24px] border border-sky-200 bg-sky-50/80 p-5 text-sm leading-6 text-sky-950">
              Cost truck default sekarang berasal dari internal app untuk komponen variable:
              <span className="font-semibold"> variable cost vehicle per km</span> dan
              <span className="font-semibold"> variable cost vehicle per minute</span>. Sementara biaya aktivasi truck
              memakai <span className="font-semibold">activation cost vehicle</span>. Nilai ini akan dipasang ke semua
              truck saat Sync Truck atau saat skenario dikirim ke solver.
            </div>

            {costParameterGroups.map((group) => (
              <section key={group.title} className="space-y-4">
                <div>
                  <h3 className="text-lg font-semibold text-ink">{group.title}</h3>
                  <p className="mt-2 text-sm leading-6 text-slate-600">{group.description}</p>
                </div>
                <div className="grid gap-4 lg:grid-cols-2">
                  {group.items.map((item) => (
                    <label key={item.path} className="rounded-[22px] border border-slate-200 bg-white p-5 shadow-sm">
                      <span className="block text-sm font-semibold text-ink">{item.label}</span>
                      <span className="mt-2 block text-sm leading-6 text-slate-600">{item.helper}</span>
                      <input
                        type="number"
                        className="input mt-4"
                        {...form.register(`default_optimization_config.${item.path}` as never, {
                          valueAsNumber: true,
                        })}
                      />
                    </label>
                  ))}
                </div>
              </section>
            ))}
          </div>
        </section>

        <SolverModeCard settings={solverSettings} />
        <SolverRunMetrics settings={solverSettings} />

        <section className="panel">
          <div className="panel-body space-y-6">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.32em] text-sky-600">RouteFinder Settings</p>
              <h2 className="mt-3 text-2xl font-semibold text-ink">Default Solver Mode</h2>
              <p className="mt-3 max-w-4xl text-sm leading-6 text-slate-600">
                Semua pengaturan hybrid RouteFinder dipindahkan ke sini. Nilai ini akan ikut tersimpan bersama settings global
                saat Anda menekan tombol simpan di bawah.
              </p>
            </div>

            <RouteFinderToggle
              register={(name: string, options?: Record<string, unknown>) =>
                form.register(name as never, options as never)
              }
              watch={form.watch}
              prefix="solver_settings"
            />
            <RouteFinderAdvancedSettings
              register={(name: string, options?: Record<string, unknown>) =>
                form.register(name as never, options as never)
              }
              watch={form.watch}
              prefix="solver_settings"
            />

            <div className="grid gap-4 lg:grid-cols-2">
              <label className="rounded-[22px] border border-slate-200 bg-white p-5 shadow-sm">
                <span className="block text-sm font-semibold text-ink">Soft cross-cluster penalty</span>
                <span className="mt-2 block text-sm leading-6 text-slate-600">
                  Penalty perpindahan shipment ke shipment antar cluster RouteFinder saat cluster mode `soft`.
                </span>
                <input
                  type="number"
                  min="0"
                  className="input mt-4"
                  {...form.register("default_optimization_config.penalties.soft_cluster_penalty" as never, {
                    valueAsNumber: true,
                  })}
                />
              </label>

              <label className="rounded-[22px] border border-slate-200 bg-white p-5 shadow-sm">
                <span className="block text-sm font-semibold text-ink">Hard cross-cluster penalty</span>
                <span className="mt-2 block text-sm leading-6 text-slate-600">
                  Penalty perpindahan shipment ke shipment antar cluster RouteFinder saat cluster mode `hard`. Nilai ini
                  tetap berupa objective penalty, bukan hard constraint absolut.
                </span>
                <input
                  type="number"
                  min="0"
                  className="input mt-4"
                  {...form.register("default_optimization_config.penalties.hard_cluster_penalty" as never, {
                    valueAsNumber: true,
                  })}
                />
              </label>
            </div>

            <div className="flex justify-end">
              <button
                type="button"
                className="btn-secondary"
                onClick={() => {
                  form.setValue(
                    "default_optimization_config.penalties.soft_cluster_penalty" as never,
                    defaultOptimizationConfig.penalties.soft_cluster_penalty as never,
                    { shouldDirty: true },
                  );
                  form.setValue(
                    "default_optimization_config.penalties.hard_cluster_penalty" as never,
                    defaultOptimizationConfig.penalties.hard_cluster_penalty as never,
                    { shouldDirty: true },
                  );
                }}
              >
                Reset cross-cluster penalty ke default
              </button>
            </div>
          </div>
        </section>

        <div className="flex items-center justify-between">
          <p className="text-sm text-slate-500">
            Default ini akan di-merge ke setiap request optimisasi baru, termasuk mode RouteFinder.
          </p>
          <button type="submit" className="btn-primary" disabled={mutation.isPending}>
            {mutation.isPending ? "Menyimpan..." : "Simpan Settings"}
          </button>
        </div>
      </form>
    </AppLayout>
  );
}
