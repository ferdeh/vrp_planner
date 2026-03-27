import { formatNumber } from "../../lib/format";
import type { RouteDetailResponse } from "../../types/api";
import { RouteStopsTable } from "../tables/RouteStopsTable";

export function RouteCard({ route }: { route: RouteDetailResponse }) {
  const truckLabel = route.no_polisi || route.truck_id;
  const tripSummaries = Array.from({ length: route.trip_count }, (_, index) => {
    const tripSequence = index + 1;
    const tripStops = route.stops.filter((stop) => stop.trip_sequence === tripSequence);
    const reloadStop = tripStops.find((stop) => stop.stop_kind === "depot_reload");
    const deliveryStops = tripStops.filter((stop) => stop.stop_kind === "delivery");
    const tripLoad = deliveryStops.reduce((sum, stop) => sum + stop.delivered_volume, 0);
    const firstDelivery = deliveryStops[0];
    const lastDelivery = deliveryStops[deliveryStops.length - 1];

    return {
      tripSequence,
      startLabel:
        tripSequence === 1
          ? `${route.origin_service_start || "-"} -> ${route.origin_etd || "-"}`
          : `${reloadStop?.eta || "-"} -> ${reloadStop?.etd || "-"}`,
      startContext: tripSequence === 1 ? "Depot Service" : "Depot Reload",
      firstDestination: firstDelivery?.spbu_name || firstDelivery?.spbu_id || "-",
      deliveryCount: deliveryStops.length,
      tripLoad,
      finishLabel:
        tripSequence === route.trip_count
          ? `${lastDelivery?.etd || "-"} -> ${route.return_eta || "-"}`
          : lastDelivery?.etd || reloadStop?.etd || "-",
      finishContext: tripSequence === route.trip_count ? "Last Delivery / Return Depot" : "Last Delivery",
    };
  });

  return (
    <section className="panel overflow-hidden">
      <div className="panel-header flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
        <div>
          <h3 className="text-lg font-semibold text-ink">No Polisi {truckLabel}</h3>
          <div className="mt-1 space-y-1 text-sm text-slate-500">
            <p>Truck Type {route.truck_type}</p>
            <p>Truck ID {route.truck_id}</p>
          </div>
          <p className="text-sm text-slate-500">Kapasitas {route.capacity_kl} KL</p>
        </div>
        <div className="flex flex-wrap gap-3 text-sm text-slate-600">
          <span>Trip {route.trip_count}</span>
          <span>Load {formatNumber(route.total_load)} KL</span>
          <span>Util {formatNumber(route.utilization_percent)}%</span>
          <span>Jarak {formatNumber(route.route_distance)} km</span>
          <span>Waktu {formatNumber(route.route_time)} min</span>
        </div>
      </div>
      <div className="panel-body">
        {tripSummaries.length ? (
          <div className="mb-6 grid gap-4 xl:grid-cols-3">
            {tripSummaries.map((trip) => (
              <article
                key={`${route.truck_id}-trip-${trip.tripSequence}`}
                className="rounded-[24px] border border-sky-100 bg-gradient-to-br from-slate-50 via-white to-sky-50 p-4 shadow-sm"
              >
                <div className="flex items-center justify-between gap-3">
                  <h4 className="text-sm font-semibold uppercase tracking-[0.16em] text-sky-700">
                    Trip {trip.tripSequence}
                  </h4>
                  <span className="rounded-full bg-white px-3 py-1 text-xs font-semibold text-slate-500 shadow-sm">
                    {formatNumber(trip.tripLoad)} KL
                  </span>
                </div>
                <div className="mt-4 space-y-2 text-sm text-slate-600">
                  <p>
                    <span className="font-semibold text-ink">{trip.startContext}</span> {trip.startLabel}
                  </p>
                  <p>
                    <span className="font-semibold text-ink">Tujuan Pertama</span> {trip.firstDestination}
                  </p>
                  <p>
                    <span className="font-semibold text-ink">Delivery Stop</span> {trip.deliveryCount}
                  </p>
                  <p>
                    <span className="font-semibold text-ink">{trip.finishContext}</span> {trip.finishLabel}
                  </p>
                </div>
              </article>
            ))}
          </div>
        ) : null}
        <RouteStopsTable route={route} />
      </div>
    </section>
  );
}
