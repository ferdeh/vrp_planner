import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { AppLayout } from "../components/layout/AppLayout";
import { PageHeader } from "../components/layout/PageHeader";
import { OptimizationConfigPanel } from "../components/forms/OptimizationConfigPanel";
import { defaultOptimizationConfig } from "../lib/sampleData";
import { getSettings, updateSettings } from "../services/api";
import type { OptimizationRequest, SystemSettingsPayload } from "../types/api";

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
        path: "penalties.capacity_violation_penalty",
        label: "Capacity violation penalty",
        helper: "Disimpan untuk roadmap. Saat ini kapasitas masih diperlakukan hard oleh solver.",
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
});

type FormValue = {
  default_optimization_config: OptimizationRequest["optimization_config"];
  ui_preferences: Record<string, unknown>;
};

export function SettingsPage() {
  const queryClient = useQueryClient();
  const settingsQuery = useQuery({
    queryKey: ["settings"],
    queryFn: getSettings,
  });
  const form = useForm<FormValue>({
    resolver: zodResolver(schema),
    defaultValues: {
      default_optimization_config: defaultOptimizationConfig,
      ui_preferences: {},
    },
  });

  useEffect(() => {
    if (settingsQuery.data) {
      form.reset({
        default_optimization_config: settingsQuery.data.default_optimization_config,
        ui_preferences: settingsQuery.data.ui_preferences,
      });
    }
  }, [form, settingsQuery.data]);

  const mutation = useMutation({
    mutationFn: (payload: SystemSettingsPayload) => updateSettings(payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["settings"] });
    },
  });

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

        <div className="flex items-center justify-between">
          <p className="text-sm text-slate-500">
            Default ini akan di-merge ke setiap request optimisasi baru.
          </p>
          <button type="submit" className="btn-primary" disabled={mutation.isPending}>
            {mutation.isPending ? "Menyimpan..." : "Simpan Settings"}
          </button>
        </div>
      </form>
    </AppLayout>
  );
}
