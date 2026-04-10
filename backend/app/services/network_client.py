"""Client abstraction for network matrix lookups."""

from __future__ import annotations

import heapq
import logging

import httpx

from app.core.config import get_settings
from app.models import schemas
from app.services.master_data_client import MasterDataClient
from app.utils.distance_utils import haversine_distance_km

logger = logging.getLogger(__name__)


class NetworkDataError(ValueError):
    """Raised when required SPBU network master data is unavailable or inconsistent."""


class NetworkClient:
    """Read matrices and feasible route hints from external network service."""

    DEFAULT_EDGE_SPEED_KMH = 40.0

    def __init__(self, master_data_client: MasterDataClient | None = None) -> None:
        self.settings = get_settings()
        self.master_data_client = master_data_client or MasterDataClient()
        self._graph_coordinates_cache: dict[str, tuple[float, float]] | None = None
        self._effective_edges_cache: list[dict] | None = None
        self._detailed_graph_cache: dict[str, list[dict[str, str | float]]] | None = None
        self._leg_audit_cache: dict[tuple[str, str], dict[str, str | float | None]] = {}

    def get_time_matrix(self, depot_id: str, spbu_ids: list[str]) -> schemas.MatrixResponse:
        if self.settings.use_mock_master_data:
            return self._build_mock_matrix(depot_id, spbu_ids, minutes_per_km=2)
        try:
            return schemas.MatrixResponse.model_validate(
                self._get(
                    self.settings.api_paths["time_matrix"],
                    params={"depot_id": depot_id, "spbu_ids": ",".join(spbu_ids)},
                )
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 404:
                logger.warning("Time matrix request failed, falling back to graph-derived matrix: %s", exc)
            else:
                logger.warning("Time matrix endpoint not found, falling back to graph-derived matrix.")
        except httpx.HTTPError as exc:
            logger.warning("Time matrix request failed, falling back to graph-derived matrix: %s", exc)
        try:
            return self._build_matrix_from_edges(depot_id, spbu_ids, mode="time")
        except httpx.HTTPError as exc:
            raise NetworkDataError("Failed to load SPBU network master data edges for time matrix.") from exc

    def get_distance_matrix(self, depot_id: str, spbu_ids: list[str]) -> schemas.MatrixResponse:
        if self.settings.use_mock_master_data:
            return self._build_mock_matrix(depot_id, spbu_ids, minutes_per_km=1, distance_mode=True)
        try:
            return schemas.MatrixResponse.model_validate(
                self._get(
                    self.settings.api_paths["distance_matrix"],
                    params={"depot_id": depot_id, "spbu_ids": ",".join(spbu_ids)},
                )
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 404:
                logger.warning("Distance matrix request failed, falling back to graph-derived matrix: %s", exc)
            else:
                logger.warning("Distance matrix endpoint not found, falling back to graph-derived matrix.")
        except httpx.HTTPError as exc:
            logger.warning("Distance matrix request failed, falling back to graph-derived matrix: %s", exc)
        try:
            return self._build_matrix_from_edges(depot_id, spbu_ids, mode="distance")
        except httpx.HTTPError as exc:
            raise NetworkDataError("Failed to load SPBU network master data edges for distance matrix.") from exc

    def get_leg_audit(self, origin_id: str, destination_id: str) -> dict[str, str | float | None]:
        if origin_id == destination_id:
            return {
                "travel_path": origin_id,
                "segment_max_velocity_kmh": "-",
                "travel_distance_km": 0.0,
                "travel_time_minutes": 0.0,
            }

        if self.settings.use_mock_master_data:
            coordinates = self._get_graph_coordinates()
            distance = self._fallback_pair_cost(origin_id, destination_id, coordinates, mode="distance")
            minutes = self._fallback_pair_cost(origin_id, destination_id, coordinates, mode="time")
            return {
                "travel_path": f"{origin_id} -> {destination_id}",
                "segment_max_velocity_kmh": str(int(self.DEFAULT_EDGE_SPEED_KMH)),
                "travel_distance_km": round(distance, 2),
                "travel_time_minutes": round(minutes, 2),
            }

        cache_key = (origin_id, destination_id)
        if cache_key in self._leg_audit_cache:
            return dict(self._leg_audit_cache[cache_key])

        graph = self._get_detailed_graph()
        audit = self._shortest_path_audit(origin_id, destination_id, graph)
        self._leg_audit_cache[cache_key] = audit
        return dict(audit)

    def list_effective_edges(self, node_ids: list[str] | None = None) -> list[schemas.EffectiveEdgeData]:
        if self.settings.use_mock_master_data:
            return self._build_mock_effective_edges(node_ids=node_ids)

        allowed = set(node_ids) if node_ids else None
        items: list[schemas.EffectiveEdgeData] = []
        for edge in self._get(self.settings.api_paths["effective_edges"], params={}):
            from_node_id = str(edge["from_node_id"])
            to_node_id = str(edge["to_node_id"])
            if allowed is not None and (from_node_id not in allowed or to_node_id not in allowed):
                continue
            items.append(
                schemas.EffectiveEdgeData(
                    from_node_id=from_node_id,
                    to_node_id=to_node_id,
                    distance_km=float(edge["distance_km"]) if edge.get("distance_km") not in (None, "") else None,
                    max_velocity_kmh=self._read_effective_edge_speed(edge),
                    source=str(edge["source"]) if edge.get("source") else None,
                    road_category=str(edge["road_category"]) if edge.get("road_category") else None,
                )
            )
        return items

    def _get(self, path: str, params: dict[str, str]):
        url = f"{self.settings.master_data_api_base_url.rstrip('/')}{path}"
        logger.info("Fetching network data from %s", url)
        with httpx.Client(timeout=self.settings.request_timeout_seconds) as client:
            response = client.get(url, params=params)
            response.raise_for_status()
            return response.json()

    def _build_matrix_from_edges(
        self,
        depot_id: str,
        spbu_ids: list[str],
        mode: str,
    ) -> schemas.MatrixResponse:
        requested_nodes = [depot_id, *spbu_ids]
        graph = self._build_cost_graph(self._get_effective_edges(), mode)
        matrix: list[list[int]] = []
        for origin in requested_nodes:
            distances = self._shortest_paths(origin, graph)
            row: list[int] = []
            for destination in requested_nodes:
                if origin == destination:
                    row.append(0)
                    continue
                value = distances.get(destination)
                if value is None:
                    raise NetworkDataError(
                        f"No graph path found in SPBU network master data between {origin} and {destination}."
                    )
                row.append(int(round(value)))
            matrix.append(row)
        return schemas.MatrixResponse(nodes=["DEPOT", *spbu_ids], matrix=matrix)

    def _get_graph_coordinates(self) -> dict[str, tuple[float, float]]:
        if self._graph_coordinates_cache is not None:
            return self._graph_coordinates_cache
        coordinates: dict[str, tuple[float, float]] = {}
        for depot in self.master_data_client.list_depots():
            coordinates[depot.depot_id] = (depot.lat, depot.lng)
        for spbu in self.master_data_client.list_spbu():
            coordinates[spbu.spbu_id] = (spbu.lat, spbu.lng)
        self._graph_coordinates_cache = coordinates
        return coordinates

    def _get_effective_edges(self) -> list[dict]:
        if self._effective_edges_cache is None:
            self._effective_edges_cache = self._get(self.settings.api_paths["effective_edges"], params={})
        return self._effective_edges_cache

    def _get_detailed_graph(self) -> dict[str, list[dict[str, str | float]]]:
        if self._detailed_graph_cache is None:
            self._detailed_graph_cache = self._build_detailed_graph(self._get_effective_edges())
        return self._detailed_graph_cache

    def _build_cost_graph(self, edges: list[dict], mode: str) -> dict[str, list[tuple[str, float]]]:
        graph: dict[str, list[tuple[str, float]]] = {}
        for edge in edges:
            from_node = str(edge["from_node_id"])
            to_node = str(edge["to_node_id"])
            distance = self._read_edge_distance(edge)
            if mode == "distance":
                if distance is None:
                    raise NetworkDataError(
                        f"Effective edge {from_node} -> {to_node} is missing distance_km in SPBU network master data."
                    )
                cost = distance
            else:
                travel_time = edge.get("travel_time_min")
                if travel_time is not None:
                    cost = float(travel_time)
                else:
                    if distance is None:
                        raise NetworkDataError(
                            f"Effective edge {from_node} -> {to_node} is missing both travel_time_min "
                            "and distance_km in SPBU network master data."
                        )
                    max_speed = self._read_edge_speed(edge)
                    cost = max(1.0, (distance / max_speed) * 60) if distance > 0 else 0.0
            graph.setdefault(from_node, []).append((to_node, cost))
            graph.setdefault(to_node, []).append((from_node, cost))
        return graph

    def _build_detailed_graph(self, edges: list[dict]) -> dict[str, list[dict[str, str | float]]]:
        graph: dict[str, list[dict[str, str | float]]] = {}
        for edge in edges:
            from_node = str(edge["from_node_id"])
            to_node = str(edge["to_node_id"])
            distance = self._read_edge_distance(edge)
            speed = self._read_edge_speed(edge)
            travel_time = edge.get("travel_time_min")
            if travel_time is not None:
                time_cost = float(travel_time)
            elif distance is not None:
                time_cost = max(1.0, (distance / speed) * 60) if distance > 0 else 0.0
            else:
                logger.warning(
                    "Skipping detailed graph edge %s -> %s because both distance_km and travel_time_min are missing.",
                    from_node,
                    to_node,
                )
                continue
            edge_info = {
                "to_node": to_node,
                "distance_km": distance,
                "max_velocity_kmh": speed,
                "travel_time_minutes": time_cost,
            }
            reverse_edge_info = {
                "to_node": from_node,
                "distance_km": distance,
                "max_velocity_kmh": speed,
                "travel_time_minutes": time_cost,
            }
            graph.setdefault(from_node, []).append(edge_info)
            graph.setdefault(to_node, []).append(reverse_edge_info)
        return graph

    def _read_edge_distance(self, edge: dict) -> float | None:
        raw_distance = edge.get("distance_km")
        if raw_distance in (None, ""):
            return None
        try:
            return float(raw_distance)
        except (TypeError, ValueError) as exc:
            raise NetworkDataError(
                f"Invalid distance_km value on SPBU network master data edge: {raw_distance!r}"
            ) from exc

    def _read_edge_speed(self, edge: dict) -> float:
        raw_speed = (
            edge.get("max_velocity_kmh")
            or edge.get("max_speed_kmh")
            or edge.get("max_speed")
            or edge.get("speed_kmh")
        )
        try:
            speed = float(raw_speed)
        except (TypeError, ValueError):
            speed = self.DEFAULT_EDGE_SPEED_KMH
        return speed if speed > 0 else self.DEFAULT_EDGE_SPEED_KMH

    def _read_effective_edge_speed(self, edge: dict) -> float | None:
        raw_speed = (
            edge.get("max_velocity_kmh")
            or edge.get("max_speed_kmh")
            or edge.get("max_speed")
            or edge.get("speed_kmh")
        )
        if raw_speed in (None, ""):
            return None
        try:
            speed = float(raw_speed)
        except (TypeError, ValueError):
            return None
        return speed if speed > 0 else None

    def _shortest_paths(
        self,
        origin: str,
        graph: dict[str, list[tuple[str, float]]],
    ) -> dict[str, float]:
        best: dict[str, float] = {origin: 0.0}
        queue: list[tuple[float, str]] = [(0.0, origin)]
        while queue:
            current_cost, node = heapq.heappop(queue)
            if current_cost > best.get(node, float("inf")):
                continue
            for next_node, edge_cost in graph.get(node, []):
                candidate = current_cost + edge_cost
                if candidate < best.get(next_node, float("inf")):
                    best[next_node] = candidate
                    heapq.heappush(queue, (candidate, next_node))
        return best

    def _shortest_path_audit(
        self,
        origin: str,
        destination: str,
        graph: dict[str, list[dict[str, str | float]]],
    ) -> dict[str, str | float | None]:
        best: dict[str, float] = {origin: 0.0}
        predecessor: dict[str, tuple[str, dict[str, str | float]]] = {}
        queue: list[tuple[float, str]] = [(0.0, origin)]

        while queue:
            current_cost, node = heapq.heappop(queue)
            if node == destination:
                break
            if current_cost > best.get(node, float("inf")):
                continue
            for edge in graph.get(node, []):
                next_node = str(edge["to_node"])
                edge_cost = float(edge["travel_time_minutes"])
                candidate = current_cost + edge_cost
                if candidate < best.get(next_node, float("inf")):
                    best[next_node] = candidate
                    predecessor[next_node] = (node, edge)
                    heapq.heappush(queue, (candidate, next_node))

        if destination not in predecessor:
            logger.warning(
                "No graph path found in SPBU network master data between %s and %s for leg audit.",
                origin,
                destination,
            )
            return {
                "travel_path": "",
                "segment_max_velocity_kmh": "-",
                "travel_distance_km": None,
                "travel_time_minutes": None,
            }

        path_nodes = [destination]
        speeds: list[str] = []
        total_distance = 0.0
        distance_complete = True
        total_time = 0.0
        current = destination
        while current != origin:
            previous, edge = predecessor[current]
            path_nodes.append(previous)
            speeds.append(str(int(round(float(edge["max_velocity_kmh"])))))
            edge_distance = edge.get("distance_km")
            if edge_distance is None:
                distance_complete = False
            else:
                total_distance += float(edge_distance)
            total_time += float(edge["travel_time_minutes"])
            current = previous

        path_nodes.reverse()
        speeds.reverse()
        return {
            "travel_path": " -> ".join(path_nodes),
            "segment_max_velocity_kmh": " / ".join(speeds) if speeds else "-",
            "travel_distance_km": round(total_distance, 2) if distance_complete else None,
            "travel_time_minutes": round(total_time, 2),
        }

    def _build_mock_matrix(
        self,
        depot_id: str,
        spbu_ids: list[str],
        minutes_per_km: int,
        distance_mode: bool = False,
    ) -> schemas.MatrixResponse:
        depots = {item.depot_id: item for item in self.master_data_client.list_depots()}
        spbu_map = self.master_data_client.get_spbu_many(spbu_ids)
        depot = depots[depot_id]
        nodes = ["DEPOT", *spbu_ids]
        coordinates = [(depot.lat, depot.lng)] + [(spbu_map[spbu_id].lat, spbu_map[spbu_id].lng) for spbu_id in spbu_ids]
        matrix: list[list[int]] = []
        for origin_lat, origin_lng in coordinates:
            row: list[int] = []
            for dest_lat, dest_lng in coordinates:
                if (origin_lat, origin_lng) == (dest_lat, dest_lng):
                    row.append(0)
                    continue
                km = haversine_distance_km(origin_lat, origin_lng, dest_lat, dest_lng)
                if distance_mode:
                    row.append(int(round(km)))
                else:
                    row.append(int(round(km * minutes_per_km)))
            matrix.append(row)
        return schemas.MatrixResponse(nodes=nodes, matrix=matrix)

    def _build_mock_effective_edges(self, node_ids: list[str] | None = None) -> list[schemas.EffectiveEdgeData]:
        nodes = self.master_data_client.list_network_nodes(node_ids=node_ids)
        items: list[schemas.EffectiveEdgeData] = []
        for index, origin in enumerate(nodes):
            for destination in nodes[index + 1 :]:
                items.append(
                    schemas.EffectiveEdgeData(
                        from_node_id=origin.node_id,
                        to_node_id=destination.node_id,
                        distance_km=round(
                            haversine_distance_km(origin.lat, origin.lng, destination.lat, destination.lng),
                            2,
                        ),
                        max_velocity_kmh=self.DEFAULT_EDGE_SPEED_KMH,
                        source="MOCK",
                        road_category="DIRECT",
                    )
                )
        return items
