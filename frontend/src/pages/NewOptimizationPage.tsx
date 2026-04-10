import { z } from "zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm, type FieldErrors } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useNavigate, useLocation } from "react-router-dom";
import { useEffect, useRef, useState } from "react";
import { AppLayout } from "../components/layout/AppLayout";
import { PageHeader } from "../components/layout/PageHeader";
import { OrderTableField } from "../components/forms/OrderTableField";
import { TruckTableField } from "../components/forms/TruckTableField";
import { OptimizationConfigPanel } from "../components/forms/OptimizationConfigPanel";
import { useDepotOptions, useSpbuOptions } from "../hooks/useMasterData";
import { defaultOptimizationConfig } from "../lib/sampleData";
import { getSettings, listAvailableTrucks, optimize } from "../services/api";
import type { DepotData, OptimizationRequest, SpbuData, TruckMasterData } from "../types/api";

const SAMPLE_ORDER_VOLUME_KL = 8;

const sampleProductTypes = [
  "PERTALITE",
  "PERTAMAX",
  "PERTAMAX_TURBO",
  "PERTAMAX_GREEN",
  "BIO_SOLAR",
  "DEXLITE",
  "PERTAMINA_DEX",
] as const;

function pickRandom<T>(items: readonly T[]): T {
  return items[Math.floor(Math.random() * items.length)];
}

function shuffleItems<T>(items: T[]): T[] {
  const cloned = [...items];
  for (let index = cloned.length - 1; index > 0; index -= 1) {
    const swapIndex = Math.floor(Math.random() * (index + 1));
    [cloned[index], cloned[swapIndex]] = [cloned[swapIndex], cloned[index]];
  }
  return cloned;
}

function hhmmToMinutes(value: string): number {
  const [hours = "0", minutes = "0"] = value.split(":");
  return Number(hours) * 60 + Number(minutes);
}

function minutesToHhmm(value: number): string {
  const normalized = Math.max(0, Math.min((24 * 60) - 1, value));
  const hours = String(Math.floor(normalized / 60)).padStart(2, "0");
  const minutes = String(normalized % 60).padStart(2, "0");
  return `${hours}:${minutes}`;
}

function buildEtaOptions(timeWindowStart: string, timeWindowEnd: string): string[] {
  const startMinutes = hhmmToMinutes(timeWindowStart);
  const endMinutes = hhmmToMinutes(timeWindowEnd);
  if (Number.isNaN(startMinutes) || Number.isNaN(endMinutes) || endMinutes <= startMinutes) {
    return [timeWindowStart || "08:00"];
  }

  const options: string[] = [];
  for (let cursor = startMinutes; cursor <= endMinutes; cursor += 60) {
    options.push(minutesToHhmm(cursor));
  }

  if (!options.includes(timeWindowStart)) {
    options.unshift(timeWindowStart);
  }

  return options;
}

const hardConstraintLabels: Record<string, string> = {
  capacity_limit: "Capacity limit",
  time_window: "Time window SPBU",
  priority_eta: "SPBU Priority",
  truck_category: "Truck category",
  no_split_order: "No split order",
  depot_operation_window: "Depot operation window",
  max_route_duration: "Max route duration",
  max_vehicle_working_time: "Max working time",
  max_total_distance_per_vehicle: "Max distance per vehicle",
};

const softConstraintLabels: Record<string, string> = {
  allow_unserved_orders: "Allow unserved",
  capacity_limit: "Capacity limit",
  time_window: "Time window SPBU",
  priority_eta: "SPBU Priority",
  truck_category: "Truck category",
  depot_operation_window: "Depot operation window",
  max_route_duration: "Max route duration",
  max_vehicle_working_time: "Max working time",
  max_total_distance_per_vehicle: "Max distance per vehicle",
};

type InlineMessage = {
  text: string;
  tone: "info" | "error";
};

type RerunLocationState = {
  rerunSourceScenarioId?: string;
  rerunPayload?: OptimizationRequest;
} | null;

const schema = z.object({
  dispatch_date: z.string().min(1),
  depot_id: z.string().min(1),
  depot_service_time_minutes: z.number().min(0),
  orders: z.array(
    z.object({
      order_id: z.string().min(1),
      spbu_id: z.string().min(1),
      product_type: z.string().min(1),
      demand_kl: z.number().positive(),
      priority: z.boolean(),
      eta: z.string().nullable().optional(),
      service_time_minutes: z.number().min(0),
      time_window_start: z.string().min(1),
      time_window_end: z.string().min(1),
    }).superRefine((value, ctx) => {
      if (value.priority && !value.eta?.trim()) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["eta"],
          message: "ETA wajib diisi untuk order priority.",
        });
      }
    }),
  ).min(1),
  available_trucks: z.array(
    z.object({
      truck_id: z.string().min(1),
      no_polisi: z.string().nullable().optional(),
      truck_type: z.string().min(1),
      truck_category: z.number().int().positive().nullable().optional(),
      capacity_kl: z.number().positive(),
      start_depot_id: z.string().min(1),
      end_depot_id: z.string().min(1),
      shift_start: z.string().min(1),
      shift_end: z.string().min(1),
      compatible_product_types: z.array(z.string()).min(1),
      compartments: z.array(
        z.object({
          compartment_id: z.string().min(1),
          capacity_kl: z.number().positive(),
        }),
      ).min(1),
      status: z.string().nullable().optional(),
      not_available_from: z.string().nullable().optional(),
      not_available_to: z.string().nullable().optional(),
    }),
  ).min(1),
  optimization_config: z.any(),
});

const initialForm: OptimizationRequest = {
  dispatch_date: new Date().toISOString().slice(0, 10),
  depot_id: "",
  depot_service_time_minutes: 30,
  orders: [
    {
      order_id: "",
      spbu_id: "",
      product_type: "PERTALITE",
      demand_kl: 8,
      priority: false,
      eta: "",
      service_time_minutes: 30,
      time_window_start: "08:00",
      time_window_end: "17:00",
    },
  ],
  available_trucks: [],
  optimization_config: defaultOptimizationConfig,
};

export function NewOptimizationPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();
  const headerSectionRef = useRef<HTMLElement | null>(null);
  const ordersSectionRef = useRef<HTMLElement | null>(null);
  const trucksSectionRef = useRef<HTMLElement | null>(null);
  const appliedRerunRef = useRef<string | null>(null);
  const [truckSyncMessage, setTruckSyncMessage] = useState<InlineMessage | null>(null);
  const [orderSampleMessage, setOrderSampleMessage] = useState<InlineMessage | null>(null);
  const [rerunMessage, setRerunMessage] = useState<string | null>(null);
  const [isSampleModalOpen, setIsSampleModalOpen] = useState(false);
  const [sampleDotInput, setSampleDotInput] = useState("");
  const [sampleDotError, setSampleDotError] = useState<string | null>(null);
  const [previewRequest, setPreviewRequest] = useState<OptimizationRequest | null>(null);
  const settingsQuery = useQuery({
    queryKey: ["settings"],
    queryFn: getSettings,
  });
  const depotQuery = useDepotOptions();

  const form = useForm<OptimizationRequest>({
    resolver: zodResolver(schema),
    defaultValues: initialForm,
  });
  const { register, handleSubmit, control, reset, watch, formState, clearErrors, setError } = form;
  const rerunState = location.state as RerunLocationState;

  const depotId = watch("depot_id");
  const spbuQuery = useSpbuOptions(depotId || undefined);
  const spbuItems = (spbuQuery.data as SpbuData[] | undefined) ?? [];
  const selectedDepot = (depotQuery.data as DepotData[] | undefined)?.find(
    (item) => String(item.depot_id) === depotId,
  );

  useEffect(() => {
    if (depotId) {
      clearErrors("depot_id");
    }
  }, [clearErrors, depotId]);

  useEffect(() => {
    const rerunPayload = rerunState?.rerunPayload;
    const rerunSourceScenarioId = rerunState?.rerunSourceScenarioId;
    if (!rerunPayload || !rerunSourceScenarioId) {
      return;
    }
    if (appliedRerunRef.current === rerunSourceScenarioId) {
      return;
    }

    reset({
      ...rerunPayload,
      orders: rerunPayload.orders.map((order) => ({
        ...order,
        eta: order.eta ?? "",
      })),
      available_trucks: rerunPayload.available_trucks.map((truck) => ({
        ...truck,
        no_polisi: truck.no_polisi ?? null,
        truck_category: truck.truck_category ?? null,
        status: truck.status ?? null,
        not_available_from: truck.not_available_from ?? null,
        not_available_to: truck.not_available_to ?? null,
      })),
    });
    setPreviewRequest(null);
    setTruckSyncMessage(null);
    setOrderSampleMessage(null);
    setRerunMessage(`Input disalin dari scenario ${rerunSourceScenarioId}. Semua field tetap bisa Anda ubah sebelum optimisasi dijalankan ulang.`);
    appliedRerunRef.current = rerunSourceScenarioId;
  }, [rerunState, reset]);

  const optimizeMutation = useMutation({
    mutationFn: optimize,
    onSuccess: async (result) => {
      setPreviewRequest(null);
      await queryClient.invalidateQueries({ queryKey: ["scenarios"] });
      navigate("/", {
        state: {
          queuedScenarioId: result.scenario_id,
        },
      });
    },
  });

  const truckSyncMutation = useMutation({
    mutationFn: listAvailableTrucks,
    onSuccess: (items, variables) => {
      const normalized = items
        .map((item: TruckMasterData) => ({
          truck_id: item.truck_id,
          no_polisi: item.no_polisi ?? null,
          truck_type: item.truck_type,
          truck_category: item.truck_category ?? null,
          capacity_kl: item.capacity_kl,
          start_depot_id: variables.depotId,
          end_depot_id: variables.depotId,
          shift_start: item.shift_start,
          shift_end: item.shift_end,
          compatible_product_types: item.compatible_product_types,
          compartments: item.compartments,
          status: item.status ?? null,
          not_available_from: item.not_available_from ?? null,
          not_available_to: item.not_available_to ?? null,
        }));

      if (!normalized.length) {
        form.setValue("available_trucks", []);
        setTruckSyncMessage({ text: "Tidak ada truck baru yang available untuk depot ini.", tone: "error" });
        return;
      }

      form.setValue("available_trucks", normalized);
      clearErrors("available_trucks");
      setTruckSyncMessage({
        text: `${normalized.length} truck tersinkron dari master data untuk tanggal dispatch ini.`,
        tone: "info",
      });
    },
    onError: () => {
      setTruckSyncMessage({ text: "Sync truck gagal. Periksa koneksi ke master data truck.", tone: "error" });
    },
  });

  const applySettingsDefaults = () => {
    if (!settingsQuery.data) return;
    reset({
      ...form.getValues(),
      optimization_config: settingsQuery.data.default_optimization_config,
    });
  };

  const openSampleModal = () => {
    if (!depotId) {
      setError("depot_id", {
        type: "manual",
        message: "Pilih depot terlebih dahulu sebelum generate sample order.",
      });
      setOrderSampleMessage({
        text: "Pilih depot terlebih dahulu sebelum generate sample order.",
        tone: "error",
      });
      return;
    }

    if (!spbuItems.length) {
      setOrderSampleMessage({
        text: "Belum ada data SPBU untuk depot ini. Tunggu master data selesai dimuat.",
        tone: "error",
      });
      return;
    }

    setSampleDotInput("");
    setSampleDotError(null);
    setOrderSampleMessage(null);
    setIsSampleModalOpen(true);
  };

  const loadSample = () => {
    const dotValue = Number(sampleDotInput);
    if (!Number.isFinite(dotValue) || dotValue <= 0) {
      setSampleDotError("DOT harus diisi dengan angka lebih dari 0 KL.");
      return;
    }

    if (!spbuItems.length) {
      setSampleDotError("Data SPBU untuk depot ini belum tersedia.");
      return;
    }

    const orderCount = Math.max(1, Math.round(dotValue / SAMPLE_ORDER_VOLUME_KL));
    const dispatchDate = form.getValues("dispatch_date") || new Date().toISOString().slice(0, 10);
    const dateCode = dispatchDate.replaceAll("-", "");
    let currentPool = shuffleItems(spbuItems);
    const pickedSpbu = Array.from({ length: orderCount }, () => {
      if (!currentPool.length) {
        currentPool = shuffleItems(spbuItems);
      }
      return currentPool.pop() as SpbuData;
    });
    const generatedOrders = pickedSpbu.map((item, index) => {
      const timeWindowStart = String(item.time_window_start ?? "08:00");
      const timeWindowEnd = String(item.time_window_end ?? "17:00");
      const priority = Math.random() >= 0.5;
      const etaOptions = buildEtaOptions(timeWindowStart, timeWindowEnd);
      return {
        order_id: `ORD-${dateCode}-${String(index + 1).padStart(3, "0")}-${Math.floor(Math.random() * 90 + 10)}`,
        spbu_id: String(item.spbu_id ?? ""),
        product_type: pickRandom(sampleProductTypes),
        demand_kl: SAMPLE_ORDER_VOLUME_KL,
        priority,
        eta: priority ? pickRandom(etaOptions) : "",
        service_time_minutes: 30,
        time_window_start: timeWindowStart,
        time_window_end: timeWindowEnd,
      };
    });

    form.setValue("orders", generatedOrders, { shouldDirty: true });
    clearErrors("orders");
    setOrderSampleMessage({
      text: `DOT ${dotValue} KL dibulatkan menjadi ${generatedOrders.length} order sample acak @${SAMPLE_ORDER_VOLUME_KL} KL (total ${generatedOrders.length * SAMPLE_ORDER_VOLUME_KL} KL).`,
      tone: "info",
    });
    setTruckSyncMessage(null);
    setSampleDotError(null);
    setIsSampleModalOpen(false);
  };

  const submitOptimization = (values: OptimizationRequest) => {
    const nextTrucks = values.available_trucks.map((truck) => ({
      ...truck,
      start_depot_id: truck.start_depot_id || values.depot_id,
      end_depot_id: truck.end_depot_id || values.depot_id,
    }));
    optimizeMutation.mutate({
      ...values,
      available_trucks: nextTrucks,
    });
  };

  const scrollToTruckSection = () => {
    trucksSectionRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
  };

  const focusValidationFeedback = (errors: FieldErrors<OptimizationRequest>) => {
    const targetSection = errors.dispatch_date || errors.depot_id || errors.depot_service_time_minutes
      ? headerSectionRef.current
      : errors.orders
        ? ordersSectionRef.current
        : errors.available_trucks
          ? trucksSectionRef.current
          : null;

    if (targetSection) {
      targetSection.scrollIntoView({ behavior: "smooth", block: "center" });
      return;
    }

    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const openOptimizationPreview = handleSubmit(
    (values) => {
      if (!values.available_trucks.length) {
        const truckErrorMessage = "Belum ada truck tersedia. Klik Sync Truck dulu sebelum menjalankan optimisasi.";
        setTruckSyncMessage({ text: truckErrorMessage, tone: "error" });
        setError("available_trucks", {
          type: "manual",
          message: truckErrorMessage,
        });
        setError("root", {
          type: "manual",
          message: truckErrorMessage,
        });
        scrollToTruckSection();
        return;
      }

      clearErrors("root");
      const nextTrucks = values.available_trucks.map((truck) => ({
        ...truck,
        start_depot_id: truck.start_depot_id || values.depot_id,
        end_depot_id: truck.end_depot_id || values.depot_id,
      }));
      setPreviewRequest({
        ...values,
        available_trucks: nextTrucks,
      });
    },
    (errors) => {
      setError("root", {
        type: "manual",
        message: "Summary optimisasi belum bisa dibuka. Lengkapi depot, order, dan truck yang wajib dulu.",
      });
      focusValidationFeedback(errors);
    },
  );

  const handleSyncTrucks = () => {
    if (!depotId) {
      setError("depot_id", {
        type: "manual",
        message: "Pilih depot terlebih dahulu sebelum sync truck.",
      });
      setTruckSyncMessage({ text: "Pilih depot terlebih dahulu sebelum sync truck.", tone: "error" });
      return;
    }
    const dispatchDate = form.getValues("dispatch_date");
    if (!dispatchDate) {
      setError("dispatch_date", {
        type: "manual",
        message: "Isi dispatch date terlebih dahulu sebelum sync truck.",
      });
      setTruckSyncMessage({ text: "Isi dispatch date terlebih dahulu sebelum sync truck.", tone: "error" });
      return;
    }
    clearErrors(["depot_id", "dispatch_date"]);
    setTruckSyncMessage(null);
    setOrderSampleMessage(null);
    truckSyncMutation.mutate({ depotId, dispatchDate });
  };

  const activeObjectives = previewRequest
      ? (previewRequest.optimization_config.objective_priority ?? [])
          .map((key) => {
            if (!previewRequest.optimization_config[key as keyof typeof previewRequest.optimization_config]) {
              return null;
            }
            switch (key) {
              case "minimize_truck_count":
                return "Minimize truck count";
              case "minimize_distance":
                return "Minimize distance";
              case "minimize_time":
                return "Minimize truck time";
              case "minimize_depot_operation_time":
                return "Minimize depot operation time";
              default:
                return null;
            }
          })
          .filter(Boolean)
    : [];

  const activeHardConstraints = previewRequest
    ? Object.entries(previewRequest.optimization_config.hard_constraints)
        .filter(([, enabled]) => enabled)
        .map(([key]) => ({
          label: hardConstraintLabels[key] ?? key,
          value:
            key === "max_route_duration"
              ? previewRequest.optimization_config.max_route_duration_minutes ?? "-"
              : key === "max_vehicle_working_time"
                ? previewRequest.optimization_config.max_vehicle_working_time_minutes ?? "-"
                : key === "max_total_distance_per_vehicle"
                  ? previewRequest.optimization_config.max_total_distance_per_vehicle_km ?? "-"
                  : "-",
        }))
    : [];

  const activeSoftConstraints = previewRequest
    ? Object.entries(previewRequest.optimization_config.soft_constraints)
        .filter(([, enabled]) => enabled)
        .map(([key]) => ({
          label: softConstraintLabels[key] ?? key,
          penalty:
            key === "allow_unserved_orders"
              ? previewRequest.optimization_config.penalties.unserved_order_penalty
              : key === "time_window"
                ? previewRequest.optimization_config.penalties.late_arrival_penalty_per_minute
                : key === "priority_eta"
                  ? previewRequest.optimization_config.penalties.priority_eta_penalty_per_minute
                : key === "depot_operation_window"
                  ? previewRequest.optimization_config.penalties.depot_operation_window_penalty_per_minute
                : key === "capacity_limit"
                  ? previewRequest.optimization_config.penalties.capacity_violation_penalty
                  : key === "max_route_duration" || key === "max_vehicle_working_time"
                    ? previewRequest.optimization_config.penalties.overtime_penalty_per_minute
                    : key === "max_total_distance_per_vehicle"
                      ? previewRequest.optimization_config.penalties.distance_weight
                      : "-",
          value:
            key === "max_route_duration"
                ? previewRequest.optimization_config.max_route_duration_minutes ?? "-"
                : key === "max_vehicle_working_time"
                  ? previewRequest.optimization_config.max_vehicle_working_time_minutes ?? "-"
                  : key === "max_total_distance_per_vehicle"
                    ? previewRequest.optimization_config.max_total_distance_per_vehicle_km ?? "-"
                    : "-",
        }))
    : [];

  const getInputClass = (hasError: boolean) => (hasError ? "input input-error" : "input");
  const getSectionClass = (hasError: boolean) => (hasError ? "panel border-rose-300 ring-2 ring-rose-100" : "panel");
  const headerHasError = Boolean(
    formState.errors.dispatch_date
    || formState.errors.depot_id
    || formState.errors.depot_service_time_minutes,
  );
  const ordersHasError = Boolean(formState.errors.orders);
  const trucksHasError = Boolean(formState.errors.available_trucks);
  const headerErrorMessage = headerHasError
    ? "Lengkapi Header Dispatch dulu sebelum membuka summary optimisasi."
    : null;
  const ordersErrorMessage = ordersHasError
    ? "Periksa kembali data order. Masih ada field order yang belum valid."
    : null;
  const trucksErrorMessage = trucksHasError
    ? "Armada belum siap dipakai. Sync truck atau lengkapi data truck yang wajib."
    : null;

  return (
    <AppLayout>
      <PageHeader
        title="Optimisasi Baru"
        description="Input loading order harian, armada tersedia, dan kebijakan constraint untuk menghitung kebutuhan truck minimum."
        action={
          <button type="button" className="btn-secondary" onClick={applySettingsDefaults}>
            Pakai Default Settings
          </button>
        }
      />

      <form className="space-y-6" onSubmit={openOptimizationPreview}>
        {rerunMessage ? (
          <div className="rounded-3xl border border-sky-200 bg-sky-50 px-5 py-4 text-sm text-sky-700">
            {rerunMessage}
          </div>
        ) : null}

        <section ref={headerSectionRef} className={getSectionClass(headerHasError)}>
          <div className="panel-header">
            <h2 className="text-xl font-semibold text-ink">Header Dispatch</h2>
            {headerErrorMessage ? (
              <p className="mt-2 text-sm font-medium text-rose-600">{headerErrorMessage}</p>
            ) : null}
          </div>
          <div className="panel-body grid gap-4 md:grid-cols-4">
            <label className="field">
              <span>Dispatch date</span>
              <input
                type="date"
                className={getInputClass(Boolean(formState.errors.dispatch_date))}
                {...register("dispatch_date", {
                  onChange: () => clearErrors("dispatch_date"),
                })}
              />
              {formState.errors.dispatch_date?.message ? (
                <p className="error-text">{formState.errors.dispatch_date.message}</p>
              ) : null}
            </label>
            <label className="field">
              <span>Depot</span>
              <select
                className={getInputClass(Boolean(formState.errors.depot_id))}
                {...register("depot_id", {
                  onChange: () => clearErrors("depot_id"),
                })}
              >
                <option value="">Pilih depot</option>
                {(depotQuery.data ?? []).map((item) => (
                  <option key={String(item.depot_id)} value={String(item.depot_id)}>
                    {String(item.name)}
                  </option>
                ))}
              </select>
              {formState.errors.depot_id?.message ? (
                <p className="error-text">{formState.errors.depot_id.message}</p>
              ) : null}
            </label>
            <label className="field">
              <span>Service time per truck</span>
              <input
                type="number"
                min={0}
                className={getInputClass(Boolean(formState.errors.depot_service_time_minutes))}
                placeholder="Menit service di depot"
                disabled={!depotId}
                {...register("depot_service_time_minutes", {
                  valueAsNumber: true,
                  onChange: () => clearErrors("depot_service_time_minutes"),
                })}
              />
              {formState.errors.depot_service_time_minutes?.message ? (
                <p className="error-text">{formState.errors.depot_service_time_minutes.message}</p>
              ) : null}
            </label>
            <div className="rounded-3xl border border-dashed border-slate-300 bg-slate-50 p-4 text-sm text-slate-500">
              {depotQuery.isError
                ? "Proxy master data belum tersedia. Anda tetap bisa input manual."
                : depotId
                  ? `Gate limit depot ${
                      selectedDepot?.gate_limit ? `${selectedDepot.gate_limit} truck aktif bersamaan.` : "belum tersedia di master data."
                    } Service time per truck dipakai sebagai waktu service/loading di depot sebelum truck berangkat ke stop pertama.`
                  : "Daftar depot diambil dari node kategori DEPOT pada service master data."}
            </div>
          </div>
        </section>

        <section ref={ordersSectionRef} className={getSectionClass(ordersHasError)}>
          <div className="panel-body">
            {ordersErrorMessage ? (
              <div className="mb-4 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-medium text-rose-700">
                {ordersErrorMessage}
              </div>
            ) : null}
            <OrderTableField
              control={control}
              register={register}
              setValue={form.setValue}
              spbuOptions={spbuItems}
              depotSelected={Boolean(depotId)}
              onLoadSample={openSampleModal}
              sampleMessage={orderSampleMessage?.text ?? null}
              sampleMessageTone={orderSampleMessage?.tone}
              errors={formState.errors.orders}
            />
          </div>
        </section>

        <section ref={trucksSectionRef} className={getSectionClass(trucksHasError)}>
          <div className="panel-body">
            {trucksErrorMessage ? (
              <div className="mb-4 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-medium text-rose-700">
                {trucksErrorMessage}
              </div>
            ) : null}
            <TruckTableField
              control={control}
              register={register}
              onSyncTrucks={handleSyncTrucks}
              syncDisabled={!depotId}
              syncLoading={truckSyncMutation.isPending}
              syncMessage={truckSyncMessage?.text ?? null}
              syncMessageTone={truckSyncMessage?.tone}
              errorMessage={formState.errors.available_trucks?.message}
            />
          </div>
        </section>

        <section className="panel">
          <div className="panel-header">
            <h2 className="text-xl font-semibold text-ink">Constraint dan Objective</h2>
          </div>
          <div className="panel-body">
            <OptimizationConfigPanel register={register} watch={watch} setValue={form.setValue} />
          </div>
        </section>

        {(formState.errors.root?.message || optimizeMutation.error) && (
          <div className="rounded-3xl border border-rose-200 bg-rose-50 px-5 py-4 text-sm text-rose-700">
            {formState.errors.root?.message ?? "Optimisasi gagal. Periksa input dan koneksi backend."}
          </div>
        )}

        <div className="flex items-center justify-between">
          <p className="text-sm text-slate-500">
            Depot aktif: <span className="font-semibold text-ink">{depotId || "-"}</span>
          </p>
          <button type="submit" className="btn-primary" disabled={optimizeMutation.isPending}>
            {optimizeMutation.isPending ? "Menjalankan Solver..." : "Jalankan Optimisasi"}
          </button>
        </div>
      </form>

      {isSampleModalOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/45 px-4 py-6 backdrop-blur-sm">
          <div className="panel w-full max-w-md">
            <div className="panel-header">
              <h2 className="text-xl font-semibold text-ink">Generate Sample Order</h2>
              <p className="mt-1 text-sm text-slate-500">
                Masukkan Daily Objective Throughput (DOT) dalam KL. Sistem akan membulatkan ke order acak @8 KL pada SPBU depot terpilih.
              </p>
            </div>
            <form
              className="panel-body space-y-4"
              onSubmit={(event) => {
                event.preventDefault();
                loadSample();
              }}
            >
              <label className="field">
                <span>DOT (KL)</span>
                <input
                  type="number"
                  min="0.1"
                  step="0.1"
                  className="input"
                  placeholder="Contoh: 50"
                  value={sampleDotInput}
                  onChange={(event) => {
                    setSampleDotInput(event.target.value);
                    if (sampleDotError) {
                      setSampleDotError(null);
                    }
                  }}
                  autoFocus
                />
              </label>
              {sampleDotError ? (
                <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
                  {sampleDotError}
                </div>
              ) : null}
              <div className="flex items-center justify-end gap-3">
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={() => {
                    setIsSampleModalOpen(false);
                    setSampleDotError(null);
                  }}
                >
                  Batal
                </button>
                <button type="submit" className="btn-primary">
                  Generate
                </button>
              </div>
            </form>
          </div>
        </div>
      ) : null}

      {previewRequest ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/45 px-4 py-6 backdrop-blur-sm">
          <div className="panel flex max-h-[88vh] w-full max-w-5xl flex-col overflow-hidden">
            <div className="panel-header flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
              <div>
                <h2 className="text-xl font-semibold text-ink">Summary Sistem Optimasi</h2>
                <p className="text-sm text-slate-500">
                  Ringkasan objective, parameter solver, dan constraint sebelum optimisasi dijalankan.
                </p>
              </div>
              <div className="rounded-full bg-sky-50 px-4 py-2 text-sm font-semibold text-sky-700">
                {previewRequest.dispatch_date} · Depot {previewRequest.depot_id} · Service {previewRequest.depot_service_time_minutes} menit/truck
              </div>
            </div>
            <div className="panel-body min-h-0 flex-1 space-y-6 overflow-y-auto">
              <section className="grid gap-4 md:grid-cols-4">
                <div className="rounded-3xl border border-slate-200 bg-slate-50 p-5">
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Orders</p>
                  <p className="mt-2 text-3xl font-semibold text-ink">{previewRequest.orders.length}</p>
                </div>
                <div className="rounded-3xl border border-slate-200 bg-slate-50 p-5">
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Trucks</p>
                  <p className="mt-2 text-3xl font-semibold text-ink">{previewRequest.available_trucks.length}</p>
                </div>
                <div className="rounded-3xl border border-slate-200 bg-slate-50 p-5">
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Demand</p>
                  <p className="mt-2 text-3xl font-semibold text-ink">
                    {previewRequest.orders.reduce((total, order) => total + order.demand_kl, 0)} KL
                  </p>
                </div>
                <div className="rounded-3xl border border-slate-200 bg-slate-50 p-5">
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Solver Timeout</p>
                  <p className="mt-2 text-3xl font-semibold text-ink">
                    {previewRequest.optimization_config.solver_options.max_solver_seconds}s
                  </p>
                </div>
              </section>

              <section className="grid gap-6 lg:grid-cols-2">
                <div className="rounded-3xl border border-slate-200 bg-slate-50 p-5">
                  <h3 className="text-base font-semibold text-ink">Objective Aktif</h3>
                  <div className="mt-4 flex flex-wrap gap-2">
                    {activeObjectives.length ? (
                      activeObjectives.map((item) => (
                        <span key={item} className="rounded-full bg-sky-100 px-3 py-1.5 text-sm font-medium text-sky-700">
                          {item}
                        </span>
                      ))
                    ) : (
                      <span className="text-sm text-slate-500">Tidak ada objective aktif.</span>
                    )}
                  </div>
                </div>

                <div className="rounded-3xl border border-slate-200 bg-slate-50 p-5">
                  <h3 className="text-base font-semibold text-ink">Parameter Solver</h3>
                  <div className="mt-4 grid gap-3 text-sm text-slate-600">
                    <div className="flex items-center justify-between rounded-2xl bg-white px-4 py-3">
                      <span>First solution strategy</span>
                      <span className="font-semibold text-ink">{previewRequest.optimization_config.solver_options.first_solution_strategy}</span>
                    </div>
                    <div className="flex items-center justify-between rounded-2xl bg-white px-4 py-3">
                      <span>Local search</span>
                      <span className="font-semibold text-ink">{previewRequest.optimization_config.solver_options.local_search_metaheuristic}</span>
                    </div>
                    <div className="flex items-center justify-between rounded-2xl bg-white px-4 py-3">
                      <span>Vehicle activation weight</span>
                      <span className="font-semibold text-ink">{previewRequest.optimization_config.penalties.activation_cost_vehicle}</span>
                    </div>
                    <div className="flex items-center justify-between rounded-2xl bg-white px-4 py-3">
                      <span>Distance weight</span>
                      <span className="font-semibold text-ink">{previewRequest.optimization_config.penalties.distance_weight}</span>
                    </div>
                    <div className="flex items-center justify-between rounded-2xl bg-white px-4 py-3">
                      <span>Time weight</span>
                      <span className="font-semibold text-ink">{previewRequest.optimization_config.penalties.time_weight}</span>
                    </div>
                    <div className="flex items-center justify-between rounded-2xl bg-white px-4 py-3">
                      <span>Depot operation time weight</span>
                      <span className="font-semibold text-ink">{previewRequest.optimization_config.penalties.depot_operation_time_weight}</span>
                    </div>
                  </div>
                </div>
              </section>

              <section className="grid gap-6 xl:grid-cols-2">
                <div className="table-shell">
                  <table>
                    <thead>
                      <tr>
                        <th>Hard Constraint</th>
                        <th>Value</th>
                      </tr>
                    </thead>
                    <tbody>
                      {activeHardConstraints.length ? (
                        activeHardConstraints.map((item) => (
                          <tr key={item.label}>
                            <td className="font-semibold text-ink">{item.label}</td>
                            <td>{item.value}</td>
                          </tr>
                        ))
                      ) : (
                        <tr>
                          <td colSpan={2} className="text-center text-sm text-slate-500">
                            Tidak ada hard constraint aktif.
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>

                <div className="table-shell">
                  <table>
                    <thead>
                      <tr>
                        <th>Soft Constraint</th>
                        <th>Penalty</th>
                        <th>Value</th>
                      </tr>
                    </thead>
                    <tbody>
                      {activeSoftConstraints.length ? (
                        activeSoftConstraints.map((item) => (
                          <tr key={item.label}>
                            <td className="font-semibold text-ink">{item.label}</td>
                            <td>{item.penalty}</td>
                            <td>{item.value}</td>
                          </tr>
                        ))
                      ) : (
                        <tr>
                          <td colSpan={3} className="text-center text-sm text-slate-500">
                            Tidak ada soft constraint aktif.
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </section>
            </div>
            <div className="flex-none border-t border-slate-200/80 bg-white/95 px-6 py-5 backdrop-blur">
              <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                <p className="text-sm text-slate-500">
                  Review ringkasan ini dulu sebelum solver dijalankan ke backend.
                </p>
                <div className="flex gap-3">
                  <button
                    type="button"
                    className="btn-secondary"
                    onClick={() => setPreviewRequest(null)}
                    disabled={optimizeMutation.isPending}
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    className="btn-primary"
                    onClick={() => submitOptimization(previewRequest)}
                    disabled={optimizeMutation.isPending}
                  >
                    {optimizeMutation.isPending ? "Mengirim ke Worker..." : "Proceed"}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </AppLayout>
  );
}
