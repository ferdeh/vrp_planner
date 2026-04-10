import { useState } from "react";
import { formatNumber } from "../../lib/format";
import type { RouteDetailResponse } from "../../types/api";

type TimelineLeg = {
  key: string;
  kind: "origin_service" | "delivery" | "depot_reload" | "depot_wait" | "return";
  originName: string;
  originEtd: string;
  destinationName: string;
  destinationEta: string;
  destinationEtd: string;
  distanceKm: number | null;
  driveMinutes: number | null;
  startMinutes: number;
  etaMinutes: number;
  etdMinutes: number | null;
};

type TimelineRoute = {
  route: RouteDetailResponse;
  truckLabel: string;
  startLabel: string;
  finishLabel: string;
  legs: TimelineLeg[];
};

type TimelineLegWithLane = TimelineLeg & {
  labelLane: number;
};

function hhmmToMinutes(value: string | null | undefined) {
  if (!value || value === "-") {
    return null;
  }

  const [hours, minutes] = value.split(":").map(Number);
  if (Number.isNaN(hours) || Number.isNaN(minutes)) {
    return null;
  }

  return hours * 60 + minutes;
}

function minutesToHhmm(value: number) {
  const safeMinutes = ((Math.round(value) % 1440) + 1440) % 1440;
  const hours = Math.floor(safeMinutes / 60)
    .toString()
    .padStart(2, "0");
  const minutes = (safeMinutes % 60).toString().padStart(2, "0");
  return `${hours}:${minutes}`;
}

function normalizeTimelineMinutes(rawMinutes: number | null, floorMinutes: number | null) {
  if (rawMinutes === null) {
    return null;
  }

  if (floorMinutes === null) {
    return rawMinutes;
  }

  let normalized = rawMinutes;
  while (normalized < floorMinutes) {
    normalized += 1440;
  }
  return normalized;
}

function buildTimelineLegs(route: RouteDetailResponse): TimelineLeg[] {
  const legs: TimelineLeg[] = [];
  const originServiceStartMinutes = hhmmToMinutes(route.origin_service_start);
  const originEtdBaseMinutes = hhmmToMinutes(route.origin_etd);
  const originEtdMinutes = normalizeTimelineMinutes(originEtdBaseMinutes, originServiceStartMinutes);
  let lastTimelineMinutes = originEtdMinutes ?? originServiceStartMinutes;

  if (
    route.depot_service_time_minutes > 0 &&
    originServiceStartMinutes !== null &&
    originEtdMinutes !== null
  ) {
    legs.push({
      key: `origin-service-${route.truck_id}`,
      kind: "origin_service",
      originName: route.origin_name || "Depot",
      originEtd: route.origin_service_start || "-",
      destinationName: route.origin_name || "Depot",
      destinationEta: route.origin_etd || "-",
      destinationEtd: route.origin_etd || "-",
      distanceKm: null,
      driveMinutes: null,
      startMinutes: originServiceStartMinutes,
      etaMinutes: originEtdMinutes,
      etdMinutes: null,
    });
  }

  route.stops.forEach((stop, index) => {
    const previousStop = index > 0 ? route.stops[index - 1] : null;
    const isDepotWait = stop.stop_kind === "depot_wait";
    const startBaseMinutes = hhmmToMinutes(isDepotWait ? stop.eta : previousStop?.etd || route.origin_etd);
    const startMinutes = normalizeTimelineMinutes(startBaseMinutes, lastTimelineMinutes);
    const etaBaseMinutes = hhmmToMinutes(isDepotWait ? stop.etd : stop.eta);
    const etaMinutes = normalizeTimelineMinutes(etaBaseMinutes, startMinutes);
    const etdBaseMinutes = hhmmToMinutes(stop.etd);
    const etdMinutes = normalizeTimelineMinutes(etdBaseMinutes, etaMinutes);

    if (startMinutes === null || etaMinutes === null) {
      return;
    }

    legs.push({
      key: `${route.truck_id}-${stop.order_id}-${stop.sequence}`,
      kind:
        stop.stop_kind === "depot_reload"
          ? "depot_reload"
          : stop.stop_kind === "depot_wait"
            ? "depot_wait"
            : "delivery",
      originName: isDepotWait ? stop.spbu_name || route.origin_name || "-" : previousStop?.spbu_name || route.origin_name || "-",
      originEtd: isDepotWait ? stop.eta : previousStop?.etd || route.origin_etd || "-",
      destinationName: stop.spbu_name || "-",
      destinationEta: isDepotWait ? stop.etd : stop.eta,
      destinationEtd: stop.etd,
      distanceKm: isDepotWait ? null : stop.travel_distance_km ?? null,
      driveMinutes: isDepotWait ? null : stop.travel_time_minutes ?? null,
      startMinutes,
      etaMinutes,
      etdMinutes,
    });

    lastTimelineMinutes = etdMinutes ?? etaMinutes;
  });

  if (route.stops.length > 0) {
    const lastStop = route.stops[route.stops.length - 1];
    const startBaseMinutes = hhmmToMinutes(lastStop.etd);
    const startMinutes = normalizeTimelineMinutes(startBaseMinutes, lastTimelineMinutes);
    const etaMinutes =
      route.return_travel_time_minutes !== null && route.return_travel_time_minutes !== undefined
        ? (startMinutes !== null ? startMinutes + route.return_travel_time_minutes : null)
        : normalizeTimelineMinutes(hhmmToMinutes(route.return_eta), startMinutes);

    if (startMinutes !== null && etaMinutes !== null) {
      legs.push({
        key: `return-${route.truck_id}`,
        kind: "return",
        originName: lastStop.spbu_name || "-",
        originEtd: lastStop.etd,
        destinationName: route.origin_name || "Depot",
        destinationEta: route.return_eta || "-",
        destinationEtd: "-",
        distanceKm: route.return_distance_km ?? null,
        driveMinutes: route.return_travel_time_minutes ?? null,
        startMinutes,
        etaMinutes,
        etdMinutes: null,
      });

      lastTimelineMinutes = etaMinutes;
    }
  }

  return legs;
}

function buildTimelineRoutes(routes: RouteDetailResponse[]): TimelineRoute[] {
  return routes
    .map((route) => ({
      route,
      truckLabel: route.no_polisi || route.truck_id,
      startLabel: route.origin_service_start || route.origin_etd || "-",
      finishLabel: route.return_eta || route.origin_etd || "-",
      legs: buildTimelineLegs(route),
    }))
    .filter((item) => item.legs.length > 0);
}

function assignMilestoneLanes(legs: TimelineLeg[]): TimelineLegWithLane[] {
  const laneLastEtaMinutes: number[] = [];

  return legs.map((leg) => {
    let lane = 0;
    while (
      laneLastEtaMinutes[lane] !== undefined &&
      Math.abs(leg.etaMinutes - laneLastEtaMinutes[lane]) < 35
    ) {
      lane += 1;
    }
    laneLastEtaMinutes[lane] = leg.etaMinutes;
    return {
      ...leg,
      labelLane: lane,
    };
  });
}

export function RouteIllustration({ routes }: { routes: RouteDetailResponse[] }) {
  const [activeLegKey, setActiveLegKey] = useState<string | null>(null);
  const timelineRoutes = buildTimelineRoutes(routes);

  if (!timelineRoutes.length) {
    return null;
  }

  const allLegs = timelineRoutes.flatMap((item) => item.legs);
  const depotGateLimit = timelineRoutes[0]?.route.depot_gate_limit;
  const depotServiceTime = timelineRoutes[0]?.route.depot_service_time_minutes ?? 0;
  const domainStart = Math.min(...allLegs.map((leg) => leg.startMinutes));
  const domainEnd = Math.max(...allLegs.map((leg) => leg.etdMinutes ?? leg.etaMinutes));
  const chartRange = Math.max(domainEnd - domainStart, 60);
  const tickCount = 7;
  const ticks = Array.from({ length: tickCount }, (_, index) => {
    const ratio = index / (tickCount - 1);
    return {
      left: ratio * 100,
      label: minutesToHhmm(domainStart + chartRange * ratio),
    };
  });

  const positionPercent = (minutes: number) => ((minutes - domainStart) / chartRange) * 100;

  return (
    <section className="rounded-[28px] border border-sky-100 bg-gradient-to-br from-slate-50 via-white to-sky-50 p-5 shadow-sm">
      <div className="mb-4 flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <h4 className="text-base font-semibold text-ink">Route Timeline</h4>
          <p className="text-sm text-slate-500">
            Semua mobil digabung dalam satu gantt chart dengan skala waktu yang sama, termasuk loading di depot sebelum gate out.
          </p>
        </div>
        <div className="flex flex-wrap gap-2 text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">
          {depotGateLimit ? <span className="rounded-full bg-rose-100 px-3 py-1 text-rose-700">Gate Limit {depotGateLimit}</span> : null}
          {depotServiceTime > 0 ? <span className="rounded-full bg-amber-100 px-3 py-1 text-amber-700">Depot Service {depotServiceTime} Min</span> : null}
          <span className="rounded-full bg-slate-100 px-3 py-1">Travel Bar</span>
          <span className="rounded-full bg-emerald-100 px-3 py-1 text-emerald-700">Destination Milestone</span>
          <span className="rounded-full bg-orange-100 px-3 py-1 text-orange-700">Depot Loading</span>
          <span className="rounded-full bg-amber-100 px-3 py-1 text-amber-700">SPBU Service Time</span>
          <span className="rounded-full bg-white px-3 py-1">Hover Milestone For Detail</span>
        </div>
      </div>

      <div className="overflow-x-auto rounded-[24px] border border-slate-200/80 bg-white/40 p-3">
        <div className="min-w-[1200px]">
          <div className="grid grid-cols-[240px_1fr] gap-4">
            <div className="sticky left-0 z-30 rounded-[20px] border border-slate-200 bg-white/95 px-4 py-3 shadow-sm backdrop-blur">
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-400">
                Truck / Summary
              </p>
            </div>
            <div className="relative h-10">
              {ticks.map((tick) => (
                <div
                  key={tick.label}
                  className="absolute top-0 -translate-x-1/2"
                  style={{ left: `${tick.left}%` }}
                >
                  <div className="h-3 w-px bg-slate-300" />
                  <p className="mt-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-400">
                    {tick.label}
                  </p>
                </div>
              ))}
            </div>
          </div>

          <div className="space-y-4">
            {timelineRoutes.map((item) => (
              <div key={item.route.truck_id} className="grid grid-cols-[240px_1fr] gap-4">
                <div className="sticky left-0 z-20 rounded-[24px] border border-slate-200 bg-white/95 p-4 shadow-sm backdrop-blur">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-400">
                    Truck Row
                  </p>
                  <p className="mt-2 text-base font-semibold text-ink">{item.truckLabel}</p>
                  <div className="mt-3 space-y-2 text-sm text-slate-500">
                    <p>Origin {item.route.origin_name || "-"}</p>
                    <p>Service Start {item.startLabel}</p>
                    <p>Gate Out {item.route.origin_etd || "-"}</p>
                    <p>Trip Count {item.route.trip_count}</p>
                    <p>Finish {item.finishLabel}</p>
                  </div>
                </div>

                <div
                  className="relative rounded-[24px] border border-slate-200 bg-white/90 p-5 shadow-sm"
                  onMouseLeave={() => setActiveLegKey((current) => (item.legs.some((leg) => leg.key === current) ? null : current))}
                >
                  <div className="relative h-[156px]">
                    <div className="absolute left-1 right-1 top-[46px] h-px bg-slate-200" />

                    {assignMilestoneLanes(item.legs).map((leg) => {
                      const travelStart = positionPercent(leg.startMinutes);
                      const travelEnd = positionPercent(leg.etaMinutes);
                      const serviceEnd =
                        (leg.kind === "delivery" || leg.kind === "depot_reload" || leg.kind === "depot_wait") &&
                        leg.etdMinutes !== null
                          ? positionPercent(leg.etdMinutes)
                          : travelEnd;
                      const legDurationMinutes =
                        (leg.etdMinutes ?? leg.etaMinutes) - leg.startMinutes;
                      const travelWidth = Math.max(travelEnd - travelStart, 1.6);
                      const serviceWidth =
                        (leg.kind === "delivery" || leg.kind === "depot_reload" || leg.kind === "depot_wait") &&
                        leg.etdMinutes !== null
                          ? Math.max(serviceEnd - travelEnd, 1.2)
                          : 0;
                      const milestoneLeft = travelEnd;
                      const labelTop = leg.labelLane * 20;

                      const isActive = activeLegKey === leg.key;
                      const tooltipLeft = `clamp(16px, calc(${milestoneLeft}% - 120px), calc(100% - 256px))`;

                      return (
                        <div key={leg.key}>
                          <div
                            className={`absolute top-[30px] h-8 rounded-[14px] px-3 py-1 text-xs font-semibold text-white shadow-sm ${
                              leg.kind === "return"
                                ? "bg-gradient-to-r from-slate-500 to-slate-700"
                                : leg.kind === "origin_service"
                                  ? "border border-orange-300 bg-orange-200 text-orange-950"
                                  : leg.kind === "depot_reload" || leg.kind === "depot_wait"
                                    ? "border border-orange-300 bg-orange-200 text-orange-950"
                                    : "bg-gradient-to-r from-sky-600 to-cyan-500"
                            }`}
                            style={{
                              left: `calc(${travelStart}% + 4px)`,
                              width: `calc(${travelWidth}% - 2px)`,
                              minWidth: 62,
                            }}
                          >
                            <div className="flex items-center justify-between gap-3">
                              <span className="truncate">
                                {leg.kind === "return"
                                  ? "Return"
                                  : leg.kind === "origin_service"
                                    ? "Depot Service"
                                    : leg.kind === "depot_reload"
                                      ? leg.originName
                                      : leg.kind === "depot_wait"
                                        ? "Depot Wait"
                                      : leg.originName}
                              </span>
                              <span>
                                {leg.kind === "origin_service" || leg.kind === "depot_wait"
                                  ? `${formatNumber(legDurationMinutes)} min`
                                  : leg.kind === "depot_reload"
                                    ? leg.distanceKm !== null
                                      ? `${formatNumber(leg.distanceKm)} km`
                                      : "-"
                                  : leg.distanceKm !== null
                                    ? `${formatNumber(leg.distanceKm)} km`
                                    : "-"}
                              </span>
                            </div>
                          </div>

                          <div
                            className={`absolute -translate-x-1/2 text-[11px] font-semibold uppercase tracking-[0.12em] ${
                              leg.kind === "origin_service" || leg.kind === "depot_reload" || leg.kind === "depot_wait"
                                ? "text-orange-700"
                                : "text-emerald-700"
                            }`}
                            style={{ left: `calc(${milestoneLeft}% + 4px)`, top: labelTop }}
                          >
                            {leg.kind === "origin_service"
                              ? `Gate Out ${leg.destinationEta}`
                              : leg.kind === "depot_reload"
                                ? `Reload ${leg.destinationEta}`
                                : leg.kind === "depot_wait"
                                  ? `Wait ${leg.destinationEta}`
                                : `ETA ${leg.destinationEta}`}
                          </div>

                              {serviceWidth > 0 ? (
                            <div
                              className={`absolute top-[30px] h-8 rounded-[14px] px-3 py-1 text-xs font-semibold ${
                                leg.kind === "depot_reload" || leg.kind === "depot_wait"
                                  ? "border border-orange-300 bg-orange-200/90 text-orange-900"
                                  : "border border-amber-300 bg-amber-200/90 text-amber-900"
                              }`}
                              style={{
                                left: `calc(${travelEnd}% + 4px)`,
                                width: `calc(${serviceWidth}% - 2px)`,
                                minWidth: 42,
                              }}
                            >
                              {leg.kind === "depot_wait" ? "Wait" : leg.kind === "depot_reload" ? "Reload" : "Service"}
                            </div>
                          ) : null}

                          <button
                            type="button"
                            className="absolute top-[38px] z-10 h-5 w-5 -translate-x-1/2 rounded-full border-4 border-white bg-emerald-500 shadow-sm transition hover:scale-110 focus:scale-110 focus:outline-none focus:ring-4 focus:ring-emerald-100"
                            style={{
                              left: `calc(${milestoneLeft}% + 4px)`,
                            }}
                            onMouseEnter={() => setActiveLegKey(leg.key)}
                            onFocus={() => setActiveLegKey(leg.key)}
                            aria-label={`Detail route ${leg.destinationName}`}
                          />

                          {isActive ? (
                            <div
                              className="absolute top-[72px] z-20 w-60 rounded-[20px] border border-slate-200 bg-white p-4 text-sm shadow-xl"
                              style={{ left: tooltipLeft }}
                            >
                              <div className="flex items-start justify-between gap-3">
                                <div>
                                  <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-400">
                                    {leg.kind === "return"
                                      ? "Depot Return"
                                      : leg.kind === "origin_service"
                                        ? "Depot Service"
                                        : leg.kind === "depot_reload"
                                          ? "Depot Reload"
                                        : leg.kind === "depot_wait"
                                          ? "Depot Wait"
                                        : "Destination"}
                                  </p>
                                  <p className="mt-1 font-semibold text-ink">{leg.destinationName}</p>
                                </div>
                                <span className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${
                                  leg.kind === "origin_service" || leg.kind === "depot_wait" || leg.kind === "depot_reload"
                                    ? "bg-orange-100 text-orange-800"
                                    : "bg-emerald-100 text-emerald-800"
                                }`}>
                                  {leg.kind === "origin_service"
                                    ? `Gate Out ${leg.destinationEta}`
                                    : leg.kind === "depot_wait"
                                      ? `Wait Until ${leg.destinationEta}`
                                      : `ETA ${leg.destinationEta}`}
                                </span>
                              </div>

                              <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-slate-600">
                                <div className="rounded-2xl bg-slate-50 px-3 py-2">
                                  <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-400">
                                    From
                                  </p>
                                  <p className="mt-1 font-medium text-slate-700">{leg.originName}</p>
                                </div>
                                <div className="rounded-2xl bg-slate-50 px-3 py-2">
                                  <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-400">
                                    ETD Origin
                                  </p>
                                  <p className="mt-1 font-medium text-slate-700">{leg.originEtd}</p>
                                </div>
                                <div className="rounded-2xl bg-slate-50 px-3 py-2">
                                  <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-400">
                                    ETD Dest
                                  </p>
                                  <p className="mt-1 font-medium text-slate-700">{leg.destinationEtd}</p>
                                </div>
                                <div className="rounded-2xl bg-slate-50 px-3 py-2">
                                  <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-400">
                                    {leg.kind === "origin_service"
                                      ? "Service"
                                      : leg.kind === "depot_reload" || leg.kind === "depot_wait"
                                        ? "Travel"
                                        : "Drive"}
                                  </p>
                                  <p className="mt-1 font-medium text-slate-700">
                                    {leg.kind === "origin_service"
                                      ? `${formatNumber(item.route.depot_service_time_minutes)} min`
                                      : leg.kind === "depot_reload" || leg.kind === "depot_wait"
                                        ? leg.driveMinutes !== null
                                          ? `${formatNumber(leg.driveMinutes)} min`
                                          : "-"
                                      : leg.driveMinutes !== null
                                        ? `${formatNumber(leg.driveMinutes)} min`
                                        : "-"}
                                  </p>
                                </div>
                                <div className="rounded-2xl bg-slate-50 px-3 py-2">
                                  <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-400">
                                    {leg.kind === "origin_service" ? "Gate Limit" : "Distance"}
                                  </p>
                                  <p className="mt-1 font-medium text-slate-700">
                                    {leg.kind === "origin_service"
                                      ? (item.route.depot_gate_limit ?? "-")
                                      : leg.distanceKm !== null
                                        ? `${formatNumber(leg.distanceKm)} km`
                                        : "-"}
                                  </p>
                                </div>
                                <div className="rounded-2xl bg-slate-50 px-3 py-2">
                                  <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-400">
                                    Leg Type
                                  </p>
                                  <p className="mt-1 font-medium text-slate-700">
                                    {leg.kind === "return"
                                      ? "Return leg"
                                      : leg.kind === "origin_service"
                                        ? "Depot loading"
                                        : leg.kind === "depot_reload"
                                          ? "Depot reload"
                                          : leg.kind === "depot_wait"
                                            ? "Depot wait"
                                            : "Delivery leg"}
                                  </p>
                                </div>
                              </div>
                            </div>
                          ) : null}
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
