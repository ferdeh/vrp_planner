import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { AppLayout } from "../components/layout/AppLayout";
import { PageHeader } from "../components/layout/PageHeader";
import { RouteFinderAdvancedSettings } from "../components/RouteFinderAdvancedSettings";
import { RouteFinderToggle } from "../components/RouteFinderToggle";
import { SolverModeCard } from "../components/SolverModeCard";
import { SolverRunMetrics } from "../components/SolverRunMetrics";
import { defaultOptimizationConfig } from "../lib/sampleData";
import { getSettings, getSolverSettings, updateSettings, updateSolverSettings } from "../services/api";
import type { SolverSettings, SystemSettingsPayload } from "../types/api";

const schema = z.object({
  use_routefinder: z.boolean(),
  cluster_mode: z.enum(["soft", "hard"]),
  max_cluster_size: z.number().int().min(3).max(6),
});

const defaultValues: SolverSettings = {
  use_routefinder: false,
  cluster_mode: "soft",
  max_cluster_size: 5,
};

const penaltySchema = z.object({
  soft_cluster_penalty: z.number().min(0),
  hard_cluster_penalty: z.number().min(0),
});

type CrossClusterPenaltyForm = z.infer<typeof penaltySchema>;

const defaultPenaltyValues: CrossClusterPenaltyForm = {
  soft_cluster_penalty: defaultOptimizationConfig.penalties.soft_cluster_penalty,
  hard_cluster_penalty: defaultOptimizationConfig.penalties.hard_cluster_penalty,
};

export function SolverSettingsPage() {
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ["solver-settings"],
    queryFn: getSolverSettings,
  });
  const settingsQuery = useQuery({
    queryKey: ["settings"],
    queryFn: getSettings,
  });
  const form = useForm<SolverSettings>({
    resolver: zodResolver(schema),
    defaultValues,
  });
  const penaltyForm = useForm<CrossClusterPenaltyForm>({
    resolver: zodResolver(penaltySchema),
    defaultValues: defaultPenaltyValues,
  });

  useEffect(() => {
    if (query.data) {
      form.reset({
        use_routefinder: query.data.use_routefinder,
        cluster_mode: query.data.cluster_mode,
        max_cluster_size: query.data.max_cluster_size,
      });
    }
  }, [form, query.data]);

  useEffect(() => {
    if (settingsQuery.data) {
      penaltyForm.reset({
        soft_cluster_penalty: settingsQuery.data.default_optimization_config.penalties.soft_cluster_penalty,
        hard_cluster_penalty: settingsQuery.data.default_optimization_config.penalties.hard_cluster_penalty,
      });
    }
  }, [penaltyForm, settingsQuery.data]);

  const mutation = useMutation({
    mutationFn: updateSolverSettings,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["solver-settings"] });
    },
  });
  const penaltyMutation = useMutation({
    mutationFn: updateSettings,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["settings"] });
    },
  });

  const values = form.watch();
  const saveCrossClusterPenalties = (penaltyValues: CrossClusterPenaltyForm) => {
    const currentSettings = settingsQuery.data;
    const payload: SystemSettingsPayload = currentSettings
      ? {
          default_optimization_config: {
            ...currentSettings.default_optimization_config,
            penalties: {
              ...currentSettings.default_optimization_config.penalties,
              ...penaltyValues,
            },
          },
          ui_preferences: currentSettings.ui_preferences,
        }
      : {
          default_optimization_config: {
            ...defaultOptimizationConfig,
            penalties: {
              ...defaultOptimizationConfig.penalties,
              ...penaltyValues,
            },
          },
          ui_preferences: {},
        };
    penaltyMutation.mutate(payload);
  };

  return (
    <AppLayout>
      <PageHeader
        title="Solver Settings"
        description="Atur apakah RouteFinder dipakai untuk clustering SPBU sebelum OR-Tools menjalankan final optimization."
      />

      <SolverModeCard settings={values} />
      <SolverRunMetrics settings={values} />

      <form className="space-y-6" onSubmit={form.handleSubmit((nextValues) => mutation.mutate(nextValues))}>
        <section className="panel">
          <div className="panel-body space-y-5">
            <RouteFinderToggle register={form.register} watch={form.watch} />
            <RouteFinderAdvancedSettings register={form.register} watch={form.watch} />
          </div>
        </section>

        <section className="panel">
          <div className="panel-body space-y-5">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.32em] text-sky-600">Cross-Cluster Penalty</p>
              <h2 className="mt-3 text-2xl font-semibold text-ink">Penalty RouteFinder</h2>
              <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-600">
                Nilai ini mengatur penalty perpindahan antar cluster RouteFinder pada arc shipment ke shipment. Disimpan
                sebagai default global optimization config.
              </p>
            </div>

            <div className="grid gap-4 lg:grid-cols-2">
              <label className="field rounded-[24px] border border-slate-200 bg-white p-5 shadow-sm">
                <span className="text-sm font-semibold text-ink">Soft cross-cluster penalty</span>
                <input
                  type="number"
                  min="0"
                  className="input"
                  {...penaltyForm.register("soft_cluster_penalty", { valueAsNumber: true })}
                />
              </label>

              <label className="field rounded-[24px] border border-slate-200 bg-white p-5 shadow-sm">
                <span className="text-sm font-semibold text-ink">Hard cross-cluster penalty</span>
                <input
                  type="number"
                  min="0"
                  className="input"
                  {...penaltyForm.register("hard_cluster_penalty", { valueAsNumber: true })}
                />
              </label>
            </div>

            <div className="rounded-[24px] border border-amber-200 bg-amber-50/80 p-4 text-sm leading-6 text-amber-900">
              Mode hard tetap berupa objective penalty besar, bukan hard constraint absolut.
            </div>

            <div className="flex items-center justify-between gap-4">
              <button
                type="button"
                className="btn-secondary"
                onClick={() => penaltyForm.reset(defaultPenaltyValues)}
              >
                Reset ke default
              </button>
              <button
                type="button"
                className="btn-primary"
                disabled={penaltyMutation.isPending}
                onClick={penaltyForm.handleSubmit(saveCrossClusterPenalties)}
              >
                {penaltyMutation.isPending ? "Menyimpan..." : "Simpan Cross-Cluster Penalty"}
              </button>
            </div>
          </div>
        </section>

        <div className="flex items-center justify-between gap-4">
          <p className="text-sm leading-6 text-slate-500">
            Default backend tetap OFF sampai toggle ini diaktifkan dan disimpan.
          </p>
          <button type="submit" className="btn-primary" disabled={mutation.isPending}>
            {mutation.isPending ? "Menyimpan..." : "Simpan Solver Settings"}
          </button>
        </div>
      </form>
    </AppLayout>
  );
}
