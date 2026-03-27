import type { RouteDetailResponse } from "../../types/api";

export function RouteStopsTable({
  route,
}: {
  route: RouteDetailResponse;
}) {
  const displayRows: Array<{
    key: string;
    sequence: number;
    tripSequence: number;
    originName: string;
    originEtd: string;
    path: string;
    maxVelocity: string;
    driveMinutes: number | string;
    orderId: string;
    parentOrderId: string;
    destinationName: string;
    eta: string;
    etd: string;
    volume: number | string;
    status: string;
  }> = route.stops.map((stop, index) => {
    const previousStop = index > 0 ? route.stops[index - 1] : null;
    return {
      key: `${stop.order_id}-${stop.sequence}`,
      sequence: stop.sequence,
      tripSequence: stop.trip_sequence,
      originName: previousStop?.spbu_name || route.origin_name || "-",
      originEtd: previousStop?.etd || route.origin_etd || "-",
      path: stop.travel_path || "-",
      maxVelocity: stop.segment_max_velocity_kmh || "-",
      driveMinutes: stop.travel_time_minutes ?? "-",
      orderId: stop.stop_kind === "depot_reload" ? "DEPOT RELOAD" : stop.order_id,
      parentOrderId: stop.stop_kind === "depot_reload" ? "-" : stop.parent_order_id,
      destinationName: stop.spbu_name || "-",
      eta: stop.eta,
      etd: stop.etd,
      volume: stop.stop_kind === "depot_reload" ? "-" : stop.delivered_volume,
      status: stop.arrival_status,
    };
  });

  if (route.stops.length > 0) {
    const lastStop = route.stops[route.stops.length - 1];
    displayRows.push({
      key: `return-${route.truck_id}`,
      sequence: route.stops.length + 1,
      tripSequence: route.trip_count,
      originName: lastStop.spbu_name || "-",
      originEtd: lastStop.etd,
      path: route.return_path || "-",
      maxVelocity: route.return_segment_max_velocity_kmh || "-",
      driveMinutes: route.return_travel_time_minutes ?? "-",
      orderId: "-",
      parentOrderId: "-",
      destinationName: route.origin_name || "Depot",
      eta: route.return_eta || "-",
      etd: "-",
      volume: "-",
      status: "returned_to_depot",
    });
  }

  return (
    <div className="table-shell">
      <table>
        <thead>
          <tr>
            <th>Seq</th>
            <th>Trip</th>
            <th>Origin</th>
            <th>ETD Origin</th>
            <th>Path</th>
            <th>Max Velocity</th>
            <th>Drive Min</th>
            <th>Order</th>
            <th>Parent</th>
            <th>Destination</th>
            <th>ETA Dest</th>
            <th>ETD Dest</th>
            <th>Volume</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {displayRows.map((row) => (
            <tr key={row.key}>
              <td>{row.sequence}</td>
              <td>{row.tripSequence}</td>
              <td>{row.originName}</td>
              <td>{row.originEtd}</td>
              <td>{row.path}</td>
              <td>{row.maxVelocity}</td>
              <td>{row.driveMinutes}</td>
              <td>{row.orderId}</td>
              <td>{row.parentOrderId}</td>
              <td>{row.destinationName}</td>
              <td>{row.eta}</td>
              <td>{row.etd}</td>
              <td>{row.volume}</td>
              <td>{row.status}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
