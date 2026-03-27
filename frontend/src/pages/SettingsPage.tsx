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
            />
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
