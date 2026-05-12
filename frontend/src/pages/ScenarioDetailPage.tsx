import axios from "axios";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { lazy, Suspense, useEffect, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { SummaryCard } from "../components/cards/SummaryCard";
import { ScenarioFleetCharts } from "../components/cards/ScenarioFleetCharts";
import { AppLayout } from "../components/layout/AppLayout";
import { PageHeader } from "../components/layout/PageHeader";
import { RouteCard } from "../components/routes/RouteCard";
import { RouteIllustration } from "../components/routes/RouteIllustration";
import {
  analysisLevelLabel,
  analysisStatusClass,
  analysisStatusLabel,
  formatCurrency,
  formatNumber,
  statusClass,
  statusLabel,
} from "../lib/format";
import {
  createScenarioAnalysis,
  getScenario,
  getScenarioRoutes,
  getScenarioAnalysis,
  listScenarioAnalyses,
} from "../services/api";
import type {
  AnalysisLevel,
  ScenarioAnalysisDetailResponse,
  ScenarioAnalysisProblematicOrder,
  ScenarioDetailResponse,
} from "../types/api";

const RouteMap = lazy(() =>
  import("../components/routes/RouteMap").then((module) => ({ default: module.RouteMap })),
);
const ClusterMetricsDashboard = lazy(() =>
  import("../components/ClusterMetricsDashboard").then((module) => ({ default: module.ClusterMetricsDashboard })),
);

type DetailTab = "summary" | "order-detail" | "analysis" | "route-graph" | "route-map" | "route-detail" | "others";
type DetailOrderSortKey =
  | "order_id"
  | "spbu"
  | "product"
  | "demand"
  | "priority"
  | "eta_spbu"
  | "nopol_truck"
  | "time_window"
  | "status";
type DetailOrderSortDirection = "asc" | "desc";

function formatDateTime(value: string) {
  return new Intl.DateTimeFormat("id-ID", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function hhmmToMinutes(value: string | null | undefined) {
  if (!value || !value.includes(":")) {
    return Number.POSITIVE_INFINITY;
  }
  const [hours, minutes] = value.split(":").map(Number);
  if (Number.isNaN(hours) || Number.isNaN(minutes)) {
    return Number.POSITIVE_INFINITY;
  }
  return hours * 60 + minutes;
}

function orderMeta(detail: ScenarioDetailResponse | undefined, orderId: string) {
  return detail?.input_orders.find((item) => item.order_id === orderId);
}

function withSpbuNames(detail: ScenarioDetailResponse, text: string) {
  const labelsBySpbuId = new Map<string, string>();
  for (const order of detail.input_orders) {
    if (order.spbu_name) {
      labelsBySpbuId.set(order.spbu_id, order.spbu_name);
    }
  }

  let result = text;
  for (const [spbuId, spbuName] of labelsBySpbuId) {
    result = result.replaceAll(`SPBU ${spbuId}`, spbuName);
  }
  return result;
}

function normalizeAnalysisTexts(detail: ScenarioDetailResponse, texts: string[]) {
  return texts.map((item) => withSpbuNames(detail, item));
}

function orderServiceMeta(routes: ScenarioDetailResponse["route_details"] | undefined) {
  const serviceMeta = new Map<string, { eta: string; noPolisi: string | null }>();
  if (!routes?.length) {
    return serviceMeta;
  }

  for (const route of routes) {
    for (const stop of route.stops) {
      if (stop.stop_kind !== "delivery") {
        continue;
      }
      serviceMeta.set(stop.parent_order_id, {
        eta: stop.eta,
        noPolisi: route.no_polisi ?? null,
      });
    }
  }

  return serviceMeta;
}

function sortDetailOrders(
  orders: ScenarioDetailResponse["input_orders"],
  serviceMeta: Map<string, { eta: string; noPolisi: string | null }>,
  unservedParentOrderIds: Set<string>,
  sortKey: DetailOrderSortKey,
  sortDirection: DetailOrderSortDirection,
) {
  const direction = sortDirection === "asc" ? 1 : -1;

  return [...orders].sort((left, right) => {
    const leftService = serviceMeta.get(left.order_id);
    const rightService = serviceMeta.get(right.order_id);
    const leftIsUnserved = unservedParentOrderIds.has(left.order_id);
    const rightIsUnserved = unservedParentOrderIds.has(right.order_id);

    let comparison = 0;
    switch (sortKey) {
      case "order_id":
        comparison = left.order_id.localeCompare(right.order_id);
        break;
      case "spbu":
        comparison = (left.spbu_name || left.spbu_id).localeCompare(right.spbu_name || right.spbu_id);
        break;
      case "product":
        comparison = left.product_type.localeCompare(right.product_type);
        break;
      case "demand":
        comparison = left.demand_kl - right.demand_kl;
        break;
      case "priority":
        comparison = Number(right.priority) - Number(left.priority);
        if (comparison === 0) {
          comparison = hhmmToMinutes(left.eta) - hhmmToMinutes(right.eta);
        }
        break;
      case "eta_spbu":
        comparison = hhmmToMinutes(leftService?.eta) - hhmmToMinutes(rightService?.eta);
        break;
      case "nopol_truck":
        comparison = (leftService?.noPolisi || "").localeCompare(rightService?.noPolisi || "");
        break;
      case "time_window":
        comparison = hhmmToMinutes(left.time_window_start) - hhmmToMinutes(right.time_window_start);
        if (comparison === 0) {
          comparison = hhmmToMinutes(left.time_window_end) - hhmmToMinutes(right.time_window_end);
        }
        break;
      case "status":
        comparison = Number(leftIsUnserved) - Number(rightIsUnserved);
        break;
      default:
        comparison = 0;
    }

    if (comparison === 0) {
      comparison = left.order_id.localeCompare(right.order_id);
    }
    return comparison * direction;
  });
}

function downloadJson(filename: string, payload: unknown) {
  const blob = new Blob([JSON.stringify(payload, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function AnalysisResultView({
  detail,
  analysis,
}: {
  detail: ScenarioDetailResponse;
  analysis: ScenarioAnalysisDetailResponse;
}) {
  const report = analysis.report;
  if (analysis.status === "processing") {
    return (
      <section className="panel">
        <div className="panel-body space-y-3">
          <span className={`inline-flex w-fit rounded-full px-4 py-2 text-sm font-semibold ${analysisStatusClass(analysis.status)}`}>
            {analysisStatusLabel(analysis.status)}
          </span>
          <p className="text-sm text-slate-600">
            Analysis worker sedang berjalan di background. Halaman ini akan refresh otomatis saat hasil selesai.
          </p>
        </div>
      </section>
    );
  }

  if (analysis.status === "error" || !report) {
    return (
      <section className="panel">
        <div className="panel-body space-y-3">
          <span className={`inline-flex w-fit rounded-full px-4 py-2 text-sm font-semibold ${analysisStatusClass(analysis.status)}`}>
            {analysisStatusLabel(analysis.status)}
          </span>
          <p className="text-sm text-rose-600">{analysis.message || "Analysis gagal diproses."}</p>
        </div>
      </section>
    );
  }

  return (
    <div className="space-y-6">
      <section className="grid gap-6 lg:grid-cols-2">
        <div className="panel">
          <div className="panel-header">
            <h2 className="text-xl font-semibold text-ink">Root Cause Summary</h2>
          </div>
          <div className="panel-body">
            <p className="text-sm leading-7 text-slate-600">{withSpbuNames(detail, report.root_cause_summary)}</p>
          </div>
        </div>

        <div className="panel">
          <div className="panel-header">
            <h2 className="text-xl font-semibold text-ink">Solver Status Explained</h2>
          </div>
          <div className="panel-body">
            <p className="text-sm leading-7 text-slate-600">{withSpbuNames(detail, report.solver_status_explained)}</p>
          </div>
        </div>
      </section>

      <section className="grid gap-6 lg:grid-cols-2">
        <div className="panel">
          <div className="panel-header">
            <h2 className="text-xl font-semibold text-ink">Key Findings</h2>
          </div>
          <div className="panel-body">
            {report.key_findings.length ? (
              <ul className="space-y-3 text-sm text-slate-600">
                {normalizeAnalysisTexts(detail, report.key_findings).map((item) => (
                  <li key={item} className="flex gap-2">
                    <span aria-hidden="true" className="text-sky-600">•</span>
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-slate-500">Belum ada temuan khusus.</p>
            )}
          </div>
        </div>

        <div className="panel">
          <div className="panel-header">
            <h2 className="text-xl font-semibold text-ink">Recommended Actions</h2>
          </div>
          <div className="panel-body">
            {report.recommended_actions.length ? (
              <ul className="space-y-3 text-sm text-slate-600">
                {normalizeAnalysisTexts(detail, report.recommended_actions).map((item) => (
                  <li key={item} className="flex gap-2">
                    <span aria-hidden="true" className="text-emerald-600">•</span>
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-slate-500">Belum ada rekomendasi tambahan.</p>
            )}
          </div>
        </div>
      </section>

      <section className="panel">
        <div className="panel-header">
          <h2 className="text-xl font-semibold text-ink">Ranking Order Paling Problematik</h2>
          <p className="mt-2 text-sm text-slate-500">
            Ranking ini menggabungkan heuristik existing scenario dan hasil eksperimen diagnosis.
          </p>
        </div>
        <div className="panel-body">
          {report.problematic_orders.length ? (
            <div className="space-y-4">
              {report.problematic_orders.map((item, index) => (
                <ProblematicOrderCard
                  key={item.order_id}
                  rank={index + 1}
                  detail={detail}
                  item={item}
                />
              ))}
            </div>
          ) : (
            <p className="text-sm text-slate-500">Belum ada ranking order problematik.</p>
          )}
        </div>
      </section>

      {report.experiment_results.length ? (
        <section className="panel">
          <div className="panel-header">
            <h2 className="text-xl font-semibold text-ink">Eksperimen Diagnosis</h2>
            <p className="mt-2 text-sm text-slate-500">
              Rerun diagnosis otomatis untuk melihat perubahan status saat constraint atau parameter tertentu diubah.
            </p>
          </div>
          <div className="panel-body grid gap-4 xl:grid-cols-2">
            {report.experiment_results.map((experiment) => (
              <div key={experiment.experiment_id} className="rounded-[28px] border border-slate-200 bg-slate-50 p-5">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <p className="text-lg font-semibold text-ink">{experiment.title}</p>
                    <p className="mt-1 text-sm text-slate-500">{withSpbuNames(detail, experiment.summary)}</p>
                  </div>
                  <span className={`rounded-full px-3 py-1 text-xs font-semibold ${statusClass(experiment.scenario_status)}`}>
                    {statusLabel(experiment.scenario_status)}
                  </span>
                </div>

                <div className="mt-4 grid gap-3 md:grid-cols-4">
                  <SummaryCard title="Runtime" value={`${formatNumber(experiment.solver_runtime_seconds)}s`} />
                  <SummaryCard title="Unserved" value={String(experiment.total_unserved_orders)} />
                  <SummaryCard title="Assignment" value={experiment.assignment_found ? "Ada" : "Tidak"} />
                  <SummaryCard title="Cost" value={formatCurrency(experiment.total_cost)} />
                </div>

                <div className="mt-4 space-y-2 text-sm text-slate-600">
                  <p>
                    <span className="font-semibold text-ink">Solver status:</span> {experiment.solver_status}
                  </p>
                  {experiment.changed_assumptions.length ? (
                    <div className="space-y-1">
                      <p className="font-semibold text-ink">Assumption yang diubah:</p>
                      <ul className="space-y-1">
                        {normalizeAnalysisTexts(detail, experiment.changed_assumptions).map((item) => (
                          <li key={item} className="flex gap-2">
                            <span aria-hidden="true">•</span>
                            <span>{item}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                </div>
              </div>
            ))}
          </div>
        </section>
      ) : null}
    </div>
  );
}

function ProblematicOrderCard({
  detail,
  item,
  rank,
}: {
  detail: ScenarioDetailResponse;
  item: ScenarioAnalysisProblematicOrder;
  rank: number;
}) {
  const meta = orderMeta(detail, item.order_id);
  const spbuLabel = meta?.spbu_name || item.spbu_id;

  return (
    <div className="rounded-[28px] border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-3">
            <span className="inline-flex h-9 w-9 items-center justify-center rounded-full bg-sky-100 text-sm font-bold text-sky-700">
              {rank}
            </span>
            <div>
              <p className="text-lg font-semibold text-ink">{item.order_id}</p>
              <p className="text-sm text-slate-500">
                {spbuLabel} · {meta?.product_type ?? "-"} · {meta ? `${formatNumber(meta.demand_kl)} KL` : ""}
              </p>
            </div>
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            {item.priority ? (
              <span className="rounded-full bg-amber-100 px-3 py-1 text-xs font-semibold text-amber-700">
                Priority{item.eta ? ` · ETA ${item.eta}` : ""}
              </span>
            ) : (
              <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-600">Normal</span>
            )}
            <span className="rounded-full bg-sky-100 px-3 py-1 text-xs font-semibold text-sky-700">
              Total Score {formatNumber(item.total_score)}
            </span>
            <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-600">
              Heuristik {formatNumber(item.heuristic_score)}
            </span>
            <span className="rounded-full bg-emerald-100 px-3 py-1 text-xs font-semibold text-emerald-700">
              Eksperimen {formatNumber(item.experimental_score)}
            </span>
          </div>
        </div>
      </div>

      {item.reasons.length ? (
        <div className="mt-4 rounded-[24px] border border-slate-200 bg-slate-50 p-4">
          <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-500">Kenapa Order Ini Berat</p>
          <ul className="mt-3 space-y-2 text-sm text-slate-600">
            {normalizeAnalysisTexts(detail, item.reasons).map((reason) => (
              <li key={reason} className="flex gap-2">
                <span aria-hidden="true" className="text-sky-600">•</span>
                <span>{reason}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

export function ScenarioDetailPage() {
  const params = useParams();
  const scenarioId = params.scenarioId ?? "";
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const initialTab = searchParams.get("tab");
  const [activeTab, setActiveTab] = useState<DetailTab>(
    initialTab === "analysis" ||
      initialTab === "order-detail" ||
      initialTab === "route-graph" ||
      initialTab === "route-map" ||
      initialTab === "route-detail" ||
      initialTab === "others"
      ? initialTab
      : "summary",
  );
  const [analysisLevel, setAnalysisLevel] = useState<AnalysisLevel>("level_1");
  const [selectedAnalysisId, setSelectedAnalysisId] = useState(searchParams.get("analysisId") ?? "");
  const [orderSortKey, setOrderSortKey] = useState<DetailOrderSortKey>("order_id");
  const [orderSortDirection, setOrderSortDirection] = useState<DetailOrderSortDirection>("asc");

  const detailQuery = useQuery({
    queryKey: ["scenario", scenarioId],
    queryFn: () => getScenario(scenarioId),
    enabled: Boolean(scenarioId),
    retry: false,
    refetchInterval: (query) => {
      const error = query.state.error;
      return axios.isAxiosError(error) && error.response?.status === 409 ? 2000 : false;
    },
  });

  const isAnalysisTab = activeTab === "analysis";
  const isRouteTab = activeTab === "route-graph" || activeTab === "route-map" || activeTab === "route-detail";

  const analysisJobsQuery = useQuery({
    queryKey: ["scenario-analyses", scenarioId],
    queryFn: () => listScenarioAnalyses(scenarioId),
    enabled: Boolean(scenarioId) && isAnalysisTab,
    refetchInterval: (query) => {
      const data = query.state.data;
      return data?.items.some((item) => item.status === "processing") ? 2000 : false;
    },
  });

  const analysisDetailQuery = useQuery({
    queryKey: ["scenario-analysis", scenarioId, selectedAnalysisId],
    queryFn: () => getScenarioAnalysis(scenarioId, selectedAnalysisId),
    enabled: Boolean(scenarioId && selectedAnalysisId) && isAnalysisTab,
    refetchInterval: (query) => {
      const data = query.state.data;
      return data?.status === "processing" ? 2000 : false;
    },
  });

  const routeDetailsQuery = useQuery({
    queryKey: ["scenario-routes", scenarioId],
    queryFn: () => getScenarioRoutes(scenarioId),
    enabled: Boolean(scenarioId) && detailQuery.isSuccess,
    retry: false,
  });

  const createAnalysisMutation = useMutation({
    mutationFn: (level: AnalysisLevel) => createScenarioAnalysis(scenarioId, level),
    onSuccess: async (job) => {
      setSelectedAnalysisId(job.analysis_id);
      setActiveTab("analysis");
      const next = new URLSearchParams(searchParams);
      next.set("tab", "analysis");
      next.set("analysisId", job.analysis_id);
      setSearchParams(next, { replace: true });
      await queryClient.invalidateQueries({ queryKey: ["scenario-analyses", scenarioId] });
      await queryClient.invalidateQueries({ queryKey: ["scenario-analysis", scenarioId, job.analysis_id] });
    },
  });

  useEffect(() => {
    if (!isAnalysisTab) {
      return;
    }
    const items = analysisJobsQuery.data?.items ?? [];
    if (!items.length) {
      if (selectedAnalysisId) {
        setSelectedAnalysisId("");
      }
      return;
    }
    if (!selectedAnalysisId || !items.some((item) => item.analysis_id === selectedAnalysisId)) {
      setSelectedAnalysisId(items[0].analysis_id);
    }
  }, [analysisJobsQuery.data, isAnalysisTab, selectedAnalysisId]);

  useEffect(() => {
    const queryTab = searchParams.get("tab");
    const nextTab: DetailTab =
      queryTab === "analysis" ||
        queryTab === "order-detail" ||
        queryTab === "route-graph" ||
        queryTab === "route-map" ||
        queryTab === "route-detail" ||
        queryTab === "others"
        ? queryTab
        : "summary";
    if (nextTab !== activeTab) {
      setActiveTab(nextTab);
    }

    const queryAnalysisId = searchParams.get("analysisId") ?? "";
    if (queryAnalysisId && queryAnalysisId !== selectedAnalysisId) {
      setSelectedAnalysisId(queryAnalysisId);
    }
  }, [activeTab, searchParams, selectedAnalysisId]);

  const syncSearchParams = (tab: DetailTab, analysisId?: string) => {
    const next = new URLSearchParams(searchParams);
    if (tab === "summary") {
      next.delete("tab");
    } else {
      next.set("tab", tab);
    }
    if (tab === "analysis" && analysisId) {
      next.set("analysisId", analysisId);
    } else {
      next.delete("analysisId");
    }
    setSearchParams(next, { replace: true });
  };

  const handleTabChange = (tab: DetailTab) => {
    setActiveTab(tab);
    syncSearchParams(tab, tab === "analysis" ? selectedAnalysisId : undefined);
  };

  const handleSelectAnalysis = (analysisId: string) => {
    setSelectedAnalysisId(analysisId);
    setActiveTab("analysis");
    syncSearchParams("analysis", analysisId);
  };

  const detail = detailQuery.data;
  const routeDetails = routeDetailsQuery.data ?? [];
  const routeSummaryDetails = detail?.route_details ?? [];
  const detailErrorMessage = axios.isAxiosError(detailQuery.error)
    ? ((detailQuery.error.response?.data as { detail?: string } | undefined)?.detail ?? "Gagal memuat detail scenario.")
    : "Gagal memuat detail scenario.";
  const totalUnservedDemand = detail
    ? detail.unserved_orders.reduce((sum, item) => sum + item.demand_kl, 0)
    : 0;
  const unservedParentOrderIds = new Set(detail?.unserved_orders.map((item) => item.parent_order_id) ?? []);
  const servedOrderMeta = orderServiceMeta(routeDetails);
  const sortedOrders = detail
    ? sortDetailOrders(detail.input_orders, servedOrderMeta, unservedParentOrderIds, orderSortKey, orderSortDirection)
    : [];
  const analysisJobs = analysisJobsQuery.data?.items ?? [];
  const selectedAnalysis = analysisJobs.find((item) => item.analysis_id === selectedAnalysisId);
  const handleOrderSort = (sortKey: DetailOrderSortKey) => {
    if (sortKey === orderSortKey) {
      setOrderSortDirection((current) => (current === "asc" ? "desc" : "asc"));
      return;
    }
    setOrderSortKey(sortKey);
    setOrderSortDirection("asc");
  };
  const handleRerun = () => {
    if (!detail) {
      return;
    }
    navigate("/new-optimization", {
      state: {
        rerunSourceScenarioId: detail.scenario_id,
        rerunPayload: {
          dispatch_date: detail.dispatch_date,
          depot_id: detail.depot_id,
          depot_service_time_minutes: detail.depot_service_time_minutes,
          orders: detail.input_orders.map((order) => ({
            ...order,
            eta: order.eta ?? "",
          })),
          available_trucks: detail.input_trucks.map((truck) => ({
            ...truck,
            no_polisi: truck.no_polisi ?? null,
            truck_category: truck.truck_category ?? null,
            status: truck.status ?? null,
            not_available_from: truck.not_available_from ?? null,
            not_available_to: truck.not_available_to ?? null,
          })),
          optimization_config: detail.objective_config,
        },
      },
    });
  };

  const handleDownloadOrders = () => {
    if (!detail) {
      return;
    }

    const exportPayload = {
      type: "vrp-planner-order-import",
      version: 1,
      scenario_id: detail.scenario_id,
      dispatch_date: detail.dispatch_date,
      depot_id: detail.depot_id,
      exported_at: new Date().toISOString(),
      orders: detail.input_orders.map((order) => ({
        order_id: order.order_id,
        spbu_id: order.spbu_id,
        spbu_name: order.spbu_name ?? null,
        product_type: order.product_type,
        demand_kl: order.demand_kl,
        priority: order.priority,
        eta: order.eta ?? "",
        service_time_minutes: order.service_time_minutes,
        time_window_start: order.time_window_start,
        time_window_end: order.time_window_end,
      })),
    };

    downloadJson(`orders-${detail.dispatch_date}-${detail.scenario_id.slice(0, 8)}.json`, exportPayload);
  };

  return (
    <AppLayout>
      <PageHeader
        title="Scenario Detail"
        description="Ringkasan hasil solver, komposisi truck, stop order, parameter, dan diagnosis scenario."
      />

      {detailQuery.isLoading ? (
        <section className="panel p-6 text-sm text-slate-500">Memuat detail scenario...</section>
      ) : detailQuery.isError ? (
        <section className="panel p-6 text-sm text-slate-500">
          {detailErrorMessage === "Scenario is still processing."
            ? "Scenario masih diproses worker. Halaman ini akan refresh otomatis saat hasil sudah tersedia."
            : detailErrorMessage}
        </section>
      ) : !detail ? (
        <section className="panel p-6 text-sm text-slate-500">Detail scenario belum tersedia.</section>
      ) : (
        <>
          <section className="panel">
            <div className="panel-body space-y-6">
              <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                <div>
                  <p className="text-sm text-slate-500">Scenario ID</p>
                  <p className="font-mono text-sm text-ink">{detail.scenario_id}</p>
                </div>
                <span className={`rounded-full px-4 py-2 text-sm font-semibold ${statusClass(detail.status)}`}>
                  {statusLabel(detail.status)}
                </span>
              </div>

                <div className="flex flex-wrap gap-3">
                  {[
                    { key: "summary", label: "Scenario Summary" },
                    { key: "order-detail", label: "Order Detail" },
                    { key: "analysis", label: "Scenario Analysis" },
                    { key: "route-graph", label: "Route Grafik" },
                    { key: "route-map", label: "Route Map" },
                    { key: "route-detail", label: "Route per MT" },
                    { key: "others", label: "Lainnya" },
                  ].map((tab) => (
                  <button
                    key={tab.key}
                    type="button"
                    onClick={() => handleTabChange(tab.key as DetailTab)}
                    className={
                      activeTab === tab.key
                        ? "inline-flex items-center justify-center rounded-full border border-sky-500 bg-gradient-to-r from-sky-600 to-cyan-500 px-5 py-2.5 text-sm font-semibold text-white shadow-lg shadow-sky-200"
                        : "inline-flex items-center justify-center rounded-full border border-slate-200 bg-white px-5 py-2.5 text-sm font-semibold text-slate-600 shadow-sm transition hover:border-sky-300 hover:text-sky-700"
                    }
                  >
                    {tab.label}
                  </button>
                ))}
                <button
                  type="button"
                  onClick={handleRerun}
                  className="inline-flex items-center justify-center rounded-full border border-slate-200 bg-white px-5 py-2.5 text-sm font-semibold text-slate-600 shadow-sm transition hover:border-sky-300 hover:text-sky-700"
                >
                  Rerun
                </button>
              </div>
            </div>
          </section>

          {activeTab === "summary" ? (
            <>
              <section className="panel">
                <div className="panel-body space-y-6">
                  <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-7">
                    <SummaryCard title="Active Truck" value={String(detail.active_truck_count)} />
                    <SummaryCard title="Demand Delivered" value={`${formatNumber(detail.total_delivered_demand)} KL`} />
                    <SummaryCard
                      title="Unserved Orders"
                      value={String(detail.total_unserved_orders)}
                      subtitle={`${formatNumber(totalUnservedDemand)} KL`}
                    />
                    <SummaryCard title="Penalty" value={formatCurrency(detail.total_penalty)} />
                    <SummaryCard title="Total Cost" value={formatCurrency(detail.total_cost)} />
                    <SummaryCard
                      title="Depot Operation"
                      value={`${formatNumber(detail.total_depot_operation_time_minutes)} min`}
                      subtitle={
                        detail.depot_operation_start && detail.depot_operation_end
                          ? `${detail.depot_operation_start} - ${detail.depot_operation_end}`
                          : "Tidak ada operasi depot"
                      }
                    />
                    <SummaryCard title="Runtime" value={`${detail.solver_runtime_seconds}s`} />
                  </div>

                  <div className="grid gap-4 md:grid-cols-3">
                    {detail.active_truck_type_summary.map((item) => (
                      <SummaryCard
                        key={item.truck_type}
                        title={item.truck_type}
                        value={`${item.active_count} truck`}
                        subtitle={`Capacity aktif ${formatNumber(item.total_capacity_kl)} KL`}
                      />
                    ))}
                  </div>

                  <div className="grid gap-6 lg:grid-cols-2">
                    <div className="rounded-3xl border border-slate-200 bg-slate-50 p-5">
                      <h3 className="text-base font-semibold text-ink">Cost Breakdown</h3>
                      <div className="mt-4 grid gap-3 text-sm text-slate-600">
                        <div className="flex items-center justify-between rounded-2xl bg-white px-4 py-3">
                          <span>Activation cost</span>
                          <span className="font-semibold text-ink">{formatCurrency(detail.cost_breakdown.activation_cost_total)}</span>
                        </div>
                        <div className="flex items-center justify-between rounded-2xl bg-white px-4 py-3">
                          <span>Distance cost</span>
                          <span className="font-semibold text-ink">{formatCurrency(detail.cost_breakdown.distance_cost_total)}</span>
                        </div>
                        <div className="flex items-center justify-between rounded-2xl bg-white px-4 py-3">
                          <span>Time cost</span>
                          <span className="font-semibold text-ink">{formatCurrency(detail.cost_breakdown.time_cost_total)}</span>
                        </div>
                        <div className="flex items-center justify-between rounded-2xl bg-white px-4 py-3">
                          <span>Depot operation cost</span>
                          <span className="font-semibold text-ink">{formatCurrency(detail.cost_breakdown.depot_operation_cost_total)}</span>
                        </div>
                      </div>
                    </div>

                    <div className="rounded-3xl border border-slate-200 bg-slate-50 p-5">
                      <h3 className="text-base font-semibold text-ink">Penalty Breakdown</h3>
                      <div className="mt-4 grid gap-3 text-sm text-slate-600">
                        <div className="flex items-center justify-between rounded-2xl bg-white px-4 py-3">
                          <span>Late arrival penalty</span>
                          <span className="font-semibold text-ink">{formatCurrency(detail.cost_breakdown.late_arrival_penalty_total)}</span>
                        </div>
                        <div className="flex items-center justify-between rounded-2xl bg-white px-4 py-3">
                          <span>Active truck idle penalty</span>
                          <span className="font-semibold text-ink">{formatCurrency(detail.cost_breakdown.active_truck_idle_penalty_total)}</span>
                        </div>
                        <div className="flex items-center justify-between rounded-2xl bg-white px-4 py-3">
                          <span>Unused opportunity capacity penalty</span>
                          <span className="font-semibold text-ink">{formatCurrency(detail.cost_breakdown.unused_opportunity_capacity_penalty_total)}</span>
                        </div>
                        <div className="flex items-center justify-between rounded-2xl bg-white px-4 py-3">
                          <span>Priority ETA penalty</span>
                          <span className="font-semibold text-ink">{formatCurrency(detail.cost_breakdown.priority_eta_penalty_total)}</span>
                        </div>
                        <div className="flex items-center justify-between rounded-2xl bg-white px-4 py-3">
                          <span>Overtime penalty</span>
                          <span className="font-semibold text-ink">{formatCurrency(detail.cost_breakdown.overtime_penalty_total)}</span>
                        </div>
                        <div className="flex items-center justify-between rounded-2xl bg-white px-4 py-3">
                          <span>Max distance penalty</span>
                          <span className="font-semibold text-ink">{formatCurrency(detail.cost_breakdown.max_total_distance_penalty_total)}</span>
                        </div>
                        <div className="flex items-center justify-between rounded-2xl bg-white px-4 py-3">
                          <span>Unserved penalty</span>
                          <span className="font-semibold text-ink">{formatCurrency(detail.cost_breakdown.unserved_penalty_total)}</span>
                        </div>
                        <div className="flex items-center justify-between rounded-2xl bg-white px-4 py-3">
                          <span>Depot operation window penalty</span>
                          <span className="font-semibold text-ink">{formatCurrency(detail.cost_breakdown.depot_operation_window_penalty_total)}</span>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </section>

              <ScenarioFleetCharts routes={routeSummaryDetails} />

              <section className="space-y-6">
                <section className="panel">
                  <div className="panel-header">
                    <h2 className="text-xl font-semibold text-ink">Cluster Metrics</h2>
                    <p className="mt-2 text-sm text-slate-500">
                      Ringkasan performa cluster RouteFinder untuk scenario ini ditampilkan langsung di summary.
                    </p>
                  </div>
                </section>
                <Suspense fallback={<section className="panel p-6 text-sm text-slate-500">Menyiapkan cluster metrics...</section>}>
                  <ClusterMetricsDashboard scenarioId={scenarioId} />
                </Suspense>
              </section>
            </>
          ) : null}

          {activeTab === "order-detail" ? (
            <section className="panel">
              <div className="panel-header flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
                <div>
                  <h2 className="text-xl font-semibold text-ink">List Order</h2>
                  <p className="mt-2 text-sm text-slate-500">
                    Daftar seluruh order pada scenario ini beserta status pelayanannya.
                  </p>
                </div>
                <button type="button" className="btn-secondary" onClick={handleDownloadOrders}>
                  Download Order
                </button>
              </div>
              <div className="panel-body">
                <div className="table-shell">
                  <table>
                    <thead>
                      <tr>
                        {[
                          ["order_id", "Order ID"],
                          ["spbu", "SPBU"],
                          ["product", "Produk"],
                          ["demand", "Demand"],
                          ["priority", "Priority"],
                          ["eta_spbu", "ETA SPBU"],
                          ["nopol_truck", "Nopol Truck"],
                          ["time_window", "Time Window"],
                          ["status", "Status"],
                        ].map(([sortKey, label]) => {
                          const isActive = orderSortKey === sortKey;
                          return (
                            <th key={sortKey}>
                              <button
                                type="button"
                                onClick={() => handleOrderSort(sortKey as DetailOrderSortKey)}
                                className={`inline-flex items-center gap-2 transition ${
                                  isActive ? "text-ink" : "text-slate-500 hover:text-ink"
                                }`}
                              >
                                <span>{label}</span>
                                <span className="text-[11px]">{isActive ? (orderSortDirection === "asc" ? "▲" : "▼") : "↕"}</span>
                              </button>
                            </th>
                          );
                        })}
                      </tr>
                    </thead>
                    <tbody>
                      {sortedOrders.map((order) => {
                        const isUnserved = unservedParentOrderIds.has(order.order_id);
                        const serviceMeta = servedOrderMeta.get(order.order_id);
                        return (
                          <tr key={order.order_id}>
                            <td className="font-semibold text-ink">{order.order_id}</td>
                            <td>{order.spbu_name || order.spbu_id}</td>
                            <td>{order.product_type}</td>
                            <td>{formatNumber(order.demand_kl)} KL</td>
                            <td>
                              {order.priority ? (
                                <span className="rounded-full bg-amber-100 px-3 py-1 text-xs font-semibold text-amber-700">
                                  Priority{order.eta ? ` · ETA ${order.eta}` : ""}
                                </span>
                              ) : (
                                <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-500">
                                  Normal
                                </span>
                              )}
                            </td>
                            <td>{serviceMeta?.eta ?? "-"}</td>
                            <td>{serviceMeta?.noPolisi ?? "-"}</td>
                            <td>
                              {order.time_window_start} - {order.time_window_end}
                            </td>
                            <td>
                              <span
                                className={`rounded-full px-3 py-1 text-xs font-semibold ${
                                  isUnserved
                                    ? "bg-rose-100 text-rose-700"
                                    : "bg-emerald-100 text-emerald-700"
                                }`}
                              >
                                {isUnserved ? "Unserved" : "Served"}
                              </span>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            </section>
          ) : null}

          {activeTab === "analysis" ? (
            <div className="space-y-6">
              <section className="panel">
                <div className="panel-header">
                  <h2 className="text-xl font-semibold text-ink">Buat Scenario Analysis</h2>
                  <p className="mt-2 text-sm text-slate-500">
                    Pilih level analysis. Level 1 memakai heuristik dari hasil existing scenario, sedangkan Level 2 menjalankan eksperimen diagnosis di worker terpisah.
                  </p>
                </div>
                <div className="panel-body space-y-5">
                  <div className="grid gap-4 lg:grid-cols-2">
                    {[
                      {
                        level: "level_1" as AnalysisLevel,
                        title: "Level 1 · Cepat",
                        description: "Analisis heuristik dari hasil existing scenario. Respons ringan dan cocok untuk triage cepat.",
                      },
                      {
                        level: "level_2" as AnalysisLevel,
                        title: "Level 2 · Kuat",
                        description: "Worker diagnosis menjalankan beberapa rerun otomatis setelah skenario selesai untuk menguji akar masalah secara lebih akurat.",
                      },
                    ].map((option) => (
                      <button
                        key={option.level}
                        type="button"
                        onClick={() => setAnalysisLevel(option.level)}
                        className={
                          analysisLevel === option.level
                            ? "rounded-[28px] border border-sky-400 bg-sky-50 p-5 text-left shadow-sm"
                            : "rounded-[28px] border border-slate-200 bg-white p-5 text-left shadow-sm transition hover:border-sky-200"
                        }
                      >
                        <p className="text-lg font-semibold text-ink">{option.title}</p>
                        <p className="mt-2 text-sm leading-7 text-slate-600">{option.description}</p>
                      </button>
                    ))}
                  </div>

                  <div className="flex flex-wrap items-center justify-between gap-4 rounded-[28px] border border-slate-200 bg-slate-50 px-5 py-4">
                    <div>
                      <p className="text-sm font-semibold text-ink">Level terpilih: {analysisLevelLabel(analysisLevel)}</p>
                      <p className="mt-1 text-sm text-slate-500">
                        Job analysis akan berjalan di background dan hasilnya muncul di daftar di bawah.
                      </p>
                    </div>
                    <button
                      type="button"
                      className="btn-primary"
                      disabled={createAnalysisMutation.isPending}
                      onClick={() => createAnalysisMutation.mutate(analysisLevel)}
                    >
                      {createAnalysisMutation.isPending ? "Memproses..." : "Jalankan Analysis"}
                    </button>
                  </div>

                  {createAnalysisMutation.isError ? (
                    <div className="rounded-[24px] border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-600">
                      {axios.isAxiosError(createAnalysisMutation.error)
                        ? ((createAnalysisMutation.error.response?.data as { detail?: string } | undefined)?.detail ??
                          "Gagal membuat scenario analysis.")
                        : "Gagal membuat scenario analysis."}
                    </div>
                  ) : null}
                </div>
              </section>

              <section className="panel">
                <div className="panel-header">
                  <h2 className="text-xl font-semibold text-ink">List Scenario Analysis</h2>
                  <p className="mt-2 text-sm text-slate-500">
                    Riwayat job analysis untuk skenario ini. Status akan berubah otomatis saat worker selesai.
                  </p>
                </div>
                <div className="panel-body">
                  {analysisJobsQuery.isLoading ? (
                    <p className="text-sm text-slate-500">Memuat list analysis...</p>
                  ) : analysisJobs.length ? (
                    <div className="table-shell bg-white">
                      <table>
                        <thead>
                          <tr>
                            <th>Dibuat</th>
                            <th>Level</th>
                            <th>Status</th>
                            <th>Catatan</th>
                            <th>Detail</th>
                          </tr>
                        </thead>
                        <tbody>
                          {analysisJobs.map((item) => (
                            <tr
                              key={item.analysis_id}
                              className={selectedAnalysisId === item.analysis_id ? "bg-sky-50/70" : undefined}
                            >
                              <td>{formatDateTime(item.created_at)}</td>
                              <td>{analysisLevelLabel(item.level)}</td>
                              <td>
                                <span className={`rounded-full px-3 py-1 text-xs font-semibold ${analysisStatusClass(item.status)}`}>
                                  {analysisStatusLabel(item.status)}
                                </span>
                              </td>
                              <td>{item.message}</td>
                              <td>
                                {item.status === "processing" ? (
                                  <span className="font-semibold text-sky-700">On Process</span>
                                ) : (
                                  <button
                                    type="button"
                                    className="font-semibold text-sea"
                                    onClick={() => handleSelectAnalysis(item.analysis_id)}
                                  >
                                    Lihat
                                  </button>
                                )}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <p className="text-sm text-slate-500">
                      Belum ada scenario analysis. Jalankan Level 1 atau Level 2 dari panel di atas.
                    </p>
                  )}
                </div>
              </section>

              {selectedAnalysis ? (
                <section className="space-y-6">
                  <div className="panel">
                    <div className="panel-body flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
                      <div>
                        <p className="text-sm text-slate-500">Analysis ID</p>
                        <p className="font-mono text-sm text-ink">{selectedAnalysis.analysis_id}</p>
                        <p className="mt-2 text-sm text-slate-500">
                          {analysisLevelLabel(selectedAnalysis.level)} · dibuat {formatDateTime(selectedAnalysis.created_at)}
                        </p>
                      </div>
                      <span className={`rounded-full px-4 py-2 text-sm font-semibold ${analysisStatusClass(selectedAnalysis.status)}`}>
                        {analysisStatusLabel(selectedAnalysis.status)}
                      </span>
                    </div>
                  </div>

                  {analysisDetailQuery.isLoading ? (
                    <section className="panel">
                      <div className="panel-body text-sm text-slate-500">Memuat hasil analysis...</div>
                    </section>
                  ) : analysisDetailQuery.isError ? (
                    <section className="panel">
                      <div className="panel-body text-sm text-rose-600">
                        {axios.isAxiosError(analysisDetailQuery.error)
                          ? ((analysisDetailQuery.error.response?.data as { detail?: string } | undefined)?.detail ??
                            "Gagal memuat hasil analysis.")
                          : "Gagal memuat hasil analysis."}
                      </div>
                    </section>
                  ) : analysisDetailQuery.data ? (
                    <AnalysisResultView detail={detail} analysis={analysisDetailQuery.data} />
                  ) : null}
                </section>
              ) : null}
            </div>
          ) : null}

          {activeTab === "route-graph" ? (
            <section className="panel">
              <div className="panel-header">
                <h2 className="text-xl font-semibold text-ink">Route Grafik</h2>
                <p className="mt-2 text-sm text-slate-500">
                  Visual timeline route yang mempertahankan tampilan grafik sebelumnya. Data route baru dimuat saat tab ini dibuka.
                </p>
              </div>
              <div className="panel-body">
                {routeDetailsQuery.isLoading ? (
                  <p className="text-sm text-slate-500">Memuat route grafik...</p>
                ) : routeDetails.length ? (
                  <RouteIllustration routes={routeDetails} />
                ) : (
                  <p className="text-sm text-slate-500">Tidak ada route aktif.</p>
                )}
              </div>
            </section>
          ) : null}

          {activeTab === "route-map" ? (
            <section className="panel">
              <div className="panel-header">
                <h2 className="text-xl font-semibold text-ink">Route Map</h2>
                <p className="mt-2 text-sm text-slate-500">
                  Graph pergerakan truck dari depot ke seluruh node route. Data route baru dimuat saat tab ini dibuka.
                </p>
              </div>
              <div className="panel-body">
                {routeDetailsQuery.isLoading ? (
                  <p className="text-sm text-slate-500">Memuat route map...</p>
                ) : routeDetails.length ? (
                  <Suspense
                    fallback={<p className="text-sm text-slate-500">Menyiapkan visual route map...</p>}
                  >
                    <RouteMap
                      routes={routeDetails}
                      depotId={detail.depot_id}
                      orderSpbuIds={detail.input_orders.map((item) => item.spbu_id)}
                    />
                  </Suspense>
                ) : (
                  <p className="text-sm text-slate-500">Tidak ada route aktif.</p>
                )}
              </div>
            </section>
          ) : null}

          {activeTab === "route-detail" ? (
            <section className="panel">
              <div className="panel-header">
                <h2 className="text-xl font-semibold text-ink">Route per MT</h2>
              </div>
              <div className="panel-body space-y-4">
                {routeDetailsQuery.isLoading ? (
                  <p className="text-sm text-slate-500">Memuat route per MT...</p>
                ) : routeDetails.length ? (
                  routeDetails.map((route) => <RouteCard key={route.truck_id} route={route} />)
                ) : (
                  <p className="text-sm text-slate-500">Tidak ada route aktif.</p>
                )}
              </div>
            </section>
          ) : null}

          {activeTab === "others" ? (
            <>
              <section className="grid gap-6 lg:grid-cols-2">
                <div className="panel">
                  <div className="panel-header">
                    <h2 className="text-xl font-semibold text-ink">Unserved Orders</h2>
                  </div>
                  <div className="panel-body">
                    {detail.unserved_orders.length ? (
                      <div className="space-y-3">
                        {detail.unserved_orders.map((item) => (
                          <div key={item.order_id} className="rounded-3xl border border-rose-200 bg-rose-50 p-4">
                            <p className="font-semibold text-rose-700">
                              {item.order_id} · {item.spbu_id}
                            </p>
                            <p className="mt-1 text-sm text-rose-600">
                              {formatNumber(item.demand_kl)} KL · {item.reason}
                            </p>
                            {item.constraint_details.length ? (
                              <div className="mt-3 space-y-2 rounded-2xl border border-rose-200/80 bg-white/70 p-3">
                                <p className="text-xs font-semibold uppercase tracking-[0.24em] text-rose-500">
                                  Constraint Yang Memblokir
                                </p>
                                <ul className="space-y-1.5 text-sm text-rose-700">
                                  {item.constraint_details.map((detailItem) => (
                                    <li key={detailItem} className="flex gap-2">
                                      <span aria-hidden="true">•</span>
                                      <span>{detailItem}</span>
                                    </li>
                                  ))}
                                </ul>
                              </div>
                            ) : null}
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-sm text-slate-500">Semua order terlayani.</p>
                    )}
                  </div>
                </div>

                <div className="panel">
                  <div className="panel-header">
                    <h2 className="text-xl font-semibold text-ink">Preprocessing Notes</h2>
                  </div>
                  <div className="panel-body">
                    {detail.preprocessing_notes.length ? (
                      <div className="space-y-3">
                        {detail.preprocessing_notes.map((note) => (
                          <div key={note.code + note.message} className="rounded-3xl border border-amber-200 bg-amber-50 p-4">
                            <p className="font-semibold text-amber-700">{note.code}</p>
                            <p className="mt-1 text-sm text-amber-600">{note.message}</p>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-sm text-slate-500">Tidak ada catatan preprocessing.</p>
                    )}
                  </div>
                </div>
              </section>

              <section className="grid gap-6 lg:grid-cols-2">
                <div className="panel">
                  <div className="panel-header">
                    <h2 className="text-xl font-semibold text-ink">Input Orders</h2>
                  </div>
                  <div className="panel-body space-y-3">
                    {detail.input_orders.map((order) => (
                      <div key={order.order_id} className="rounded-3xl border border-slate-200 bg-slate-50 p-4">
                        <p className="font-semibold text-ink">
                          {order.order_id} · {order.spbu_name || order.spbu_id}
                        </p>
                        <p className="mt-1 text-sm text-slate-500">
                          {order.product_type} · {formatNumber(order.demand_kl)} KL · {order.time_window_start} - {order.time_window_end}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="panel">
                  <div className="panel-header">
                    <h2 className="text-xl font-semibold text-ink">Config Snapshot</h2>
                  </div>
                  <div className="panel-body">
                    <pre className="overflow-x-auto rounded-3xl bg-ink p-4 text-xs text-white">
                      {JSON.stringify(detail.objective_config, null, 2)}
                    </pre>
                  </div>
                </div>
              </section>
            </>
          ) : null}
        </>
      )}
    </AppLayout>
  );
}
