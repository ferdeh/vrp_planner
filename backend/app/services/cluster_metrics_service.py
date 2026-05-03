"""Build cluster metrics for the scenario dashboard."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Iterable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import db_models
from app.repositories.scenario_repository import ScenarioRepository
from app.schemas.cluster_metric_schema import (
    ClusterMetricsCluster,
    ClusterMetricsEdge,
    ClusterMetricsHistoryItem,
    ClusterMetricsResponse,
    ClusterMetricsSummary,
    ClusterTruckMetric,
)
from app.services.result_service import ResultService


@dataclass
class _ScenarioHistorySnapshot:
    total_trips: int
    cluster_adherence: float | None
    cross_cluster_moves: int


@dataclass
class _ClusterAggregate:
    inbound_transitions: int = 0
    outbound_transitions: int = 0
    outbound_cross_cluster: int = 0
    internal_transitions: int = 0
    distance_total: float = 0
    distance_count: int = 0


class ClusterMetricsService:
    """Aggregate RouteFinder clustering metrics for a scenario."""

    HISTORY_LIMIT = 8

    def __init__(
        self,
        db: Session,
        *,
        result_service: ResultService | None = None,
    ) -> None:
        self.db = db
        self.result_service = result_service or ResultService()
        self.scenario_repository = ScenarioRepository(db)

    def get_cluster_metrics(self, scenario_id: UUID | str) -> ClusterMetricsResponse:
        scenario = self.scenario_repository.get_scenario(scenario_id)
        if scenario is None:
            raise ValueError("Scenario not found.")
        if scenario.result is None:
            raise ValueError("Scenario result is not available.")

        related_scenarios = self.scenario_repository.list_related_scenarios(
            dispatch_date=scenario.dispatch_date,
            depot_id=scenario.depot_id,
            limit=self.HISTORY_LIMIT,
        )
        scenario_ids = [item.id for item in related_scenarios]
        clusters_by_scenario = self._load_clusters(scenario_ids)
        runs_by_scenario = self._load_latest_solver_runs(scenario_ids)

        current_detail = self.result_service.build_detail_response(scenario, include_route_stops=True)
        current_clusters = clusters_by_scenario.get(scenario.id, [])
        current_run = runs_by_scenario.get(scenario.id)

        current_summary, cluster_rows, edge_rows, truck_rows = self._build_current_snapshot(
            detail=current_detail,
            cluster_rows=current_clusters,
        )

        history = []
        for item in sorted(related_scenarios, key=lambda row: row.created_at):
            if item.result is None:
                continue
            history_snapshot = self._build_history_snapshot(
                item,
                clusters_by_scenario.get(item.id, []),
            )
            history.append(
                ClusterMetricsHistoryItem(
                    scenario_id=UUID(item.id),
                    run_id=None if runs_by_scenario.get(item.id) is None else UUID(runs_by_scenario[item.id].id),
                    created_at=item.created_at,
                    solver_mode=self._solver_mode_label(runs_by_scenario.get(item.id), bool(clusters_by_scenario.get(item.id))),
                    total_distance=round(item.result.total_distance, 2),
                    total_demand=round(item.result.total_demand, 2),
                    total_trips=history_snapshot.total_trips,
                    cluster_adherence=history_snapshot.cluster_adherence,
                    cross_cluster_moves=history_snapshot.cross_cluster_moves,
                )
            )

        return ClusterMetricsResponse(
            scenario_id=UUID(scenario.id),
            has_cluster_data=bool(current_clusters),
            summary=current_summary,
            clusters=cluster_rows,
            edges=edge_rows,
            truck_metrics=truck_rows,
            history=history,
        )

    def _load_clusters(self, scenario_ids: Iterable[str]) -> dict[str, list[db_models.VRPCluster]]:
        ids = list(scenario_ids)
        if not ids:
            return {}
        stmt = (
            select(db_models.VRPCluster)
            .where(db_models.VRPCluster.scenario_id.in_(ids))
            .order_by(db_models.VRPCluster.scenario_id, db_models.VRPCluster.cluster_id)
        )
        rows = self.db.execute(stmt).scalars().all()
        grouped: dict[str, list[db_models.VRPCluster]] = defaultdict(list)
        for row in rows:
            grouped[row.scenario_id].append(row)
        return grouped

    def _load_latest_solver_runs(self, scenario_ids: Iterable[str]) -> dict[str, db_models.VRPSolverRun]:
        ids = list(scenario_ids)
        if not ids:
            return {}
        stmt = (
            select(db_models.VRPSolverRun)
            .where(db_models.VRPSolverRun.scenario_id.in_(ids))
            .order_by(db_models.VRPSolverRun.scenario_id, db_models.VRPSolverRun.created_at.desc())
        )
        rows = self.db.execute(stmt).scalars().all()
        latest: dict[str, db_models.VRPSolverRun] = {}
        for row in rows:
            latest.setdefault(row.scenario_id, row)
        return latest

    @staticmethod
    def _stop_kind(order_id: str) -> str:
        if order_id.startswith("DEPOT_WAIT#"):
            return "depot_wait"
        if order_id.startswith("DEPOT_RELOAD#"):
            return "depot_reload"
        return "delivery"

    def _build_history_snapshot(
        self,
        scenario: db_models.Scenario,
        cluster_rows: list[db_models.VRPCluster],
    ) -> _ScenarioHistorySnapshot:
        cluster_by_spbu = self._cluster_by_spbu(cluster_rows)
        total_transitions = 0
        same_cluster_transitions = 0
        cross_cluster_moves = 0
        total_trips = 0

        if not cluster_by_spbu:
            for route in scenario.result.routes:
                total_trips += self._route_trip_count_raw(route)
            return _ScenarioHistorySnapshot(
                total_trips=total_trips,
                cluster_adherence=None,
                cross_cluster_moves=0,
            )

        for route in scenario.result.routes:
            total_trips += self._route_trip_count_raw(route)
            delivery_stops = [
                stop
                for stop in sorted(route.stops, key=lambda item: item.sequence)
                if self._stop_kind(stop.order_id) == "delivery"
            ]
            for previous_stop, current_stop in zip(delivery_stops, delivery_stops[1:]):
                from_cluster = cluster_by_spbu.get(previous_stop.spbu_id)
                to_cluster = cluster_by_spbu.get(current_stop.spbu_id)
                if not from_cluster or not to_cluster:
                    continue
                total_transitions += 1
                if from_cluster == to_cluster:
                    same_cluster_transitions += 1
                else:
                    cross_cluster_moves += 1

        adherence = None
        if cluster_by_spbu:
            adherence = 1.0 if total_transitions == 0 else same_cluster_transitions / total_transitions

        return _ScenarioHistorySnapshot(
            total_trips=total_trips,
            cluster_adherence=None if adherence is None else round(adherence, 4),
            cross_cluster_moves=cross_cluster_moves,
        )

    def _build_current_snapshot(
        self,
        *,
        detail,
        cluster_rows: list[db_models.VRPCluster],
    ) -> tuple[
        ClusterMetricsSummary,
        list[ClusterMetricsCluster],
        list[ClusterMetricsEdge],
        list[ClusterTruckMetric],
    ]:
        cluster_by_spbu = self._cluster_by_spbu(cluster_rows)
        aggregates: dict[str, _ClusterAggregate] = defaultdict(_ClusterAggregate)
        edges: list[ClusterMetricsEdge] = []
        truck_metrics: list[ClusterTruckMetric] = []
        total_trips = 0
        total_transitions = 0
        same_cluster_transitions = 0
        cross_cluster_moves = 0

        for route in detail.route_details:
            total_trips += int(route.trip_count)
            delivery_stops = [stop for stop in route.stops if stop.stop_kind == "delivery"]
            cluster_counts = Counter(
                cluster_id
                for cluster_id in (cluster_by_spbu.get(stop.spbu_id) for stop in delivery_stops)
                if cluster_id
            )
            dominant_cluster = None
            dominant_cluster_nodes = 0
            if cluster_counts:
                dominant_cluster, dominant_cluster_nodes = max(
                    cluster_counts.items(),
                    key=lambda item: (item[1], item[0]),
                )
            total_nodes = len(delivery_stops)
            purity_ratio = (
                0.0 if total_nodes == 0 or dominant_cluster is None else dominant_cluster_nodes / total_nodes
            )
            truck_metrics.append(
                ClusterTruckMetric(
                    truck_id=route.truck_id,
                    no_polisi=route.no_polisi,
                    dominant_cluster=dominant_cluster,
                    purity_ratio=round(purity_ratio, 4),
                    cluster_count=len(cluster_counts),
                    total_nodes=total_nodes,
                    dominant_cluster_nodes=dominant_cluster_nodes,
                    utilization_percent=round(route.utilization_percent, 2),
                    total_distance=round(route.route_distance, 2),
                    trip_count=int(route.trip_count),
                )
            )

            for previous_stop, current_stop in zip(delivery_stops, delivery_stops[1:]):
                from_cluster = cluster_by_spbu.get(previous_stop.spbu_id)
                to_cluster = cluster_by_spbu.get(current_stop.spbu_id)
                distance_km = float(current_stop.travel_distance_km or 0)
                is_cross_cluster = bool(from_cluster and to_cluster and from_cluster != to_cluster)
                edges.append(
                    ClusterMetricsEdge(
                        truck_id=route.truck_id,
                        no_polisi=route.no_polisi,
                        from_spbu_id=previous_stop.spbu_id,
                        to_spbu_id=current_stop.spbu_id,
                        from_cluster=from_cluster,
                        to_cluster=to_cluster,
                        distance_km=round(distance_km, 2),
                        trip_sequence=int(current_stop.trip_sequence),
                        is_cross_cluster=is_cross_cluster,
                    )
                )
                if not from_cluster or not to_cluster:
                    continue

                total_transitions += 1
                from_aggregate = aggregates[from_cluster]
                to_aggregate = aggregates[to_cluster]
                from_aggregate.outbound_transitions += 1
                to_aggregate.inbound_transitions += 1
                from_aggregate.distance_total += distance_km
                from_aggregate.distance_count += 1
                to_aggregate.distance_total += distance_km
                to_aggregate.distance_count += 1

                if from_cluster == to_cluster:
                    same_cluster_transitions += 1
                    from_aggregate.internal_transitions += 1
                else:
                    cross_cluster_moves += 1
                    from_aggregate.outbound_cross_cluster += 1

        adherence = None
        if cluster_by_spbu:
            adherence = 1.0 if total_transitions == 0 else same_cluster_transitions / total_transitions

        cluster_metrics = []
        for row in cluster_rows:
            aggregate = aggregates[row.cluster_id]
            cluster_metrics.append(
                ClusterMetricsCluster(
                    cluster_id=row.cluster_id,
                    spbu_ids=list(row.spbu_ids or []),
                    spbu_count=len(row.spbu_ids or []),
                    total_demand_kl=round(row.total_demand_kl, 2),
                    avg_distance=round(
                        0
                        if aggregate.distance_count == 0
                        else aggregate.distance_total / aggregate.distance_count,
                        2,
                    ),
                    cluster_leakage=round(
                        0
                        if aggregate.outbound_transitions == 0
                        else aggregate.outbound_cross_cluster / aggregate.outbound_transitions,
                        4,
                    ),
                    inbound_transitions=aggregate.inbound_transitions,
                    outbound_transitions=aggregate.outbound_transitions,
                    internal_transitions=aggregate.internal_transitions,
                )
            )

        active_routes = [route for route in detail.route_details if route.total_load > 0]
        avg_utilization = (
            None
            if not active_routes
            else round(
                sum(float(route.utilization_percent) for route in active_routes) / len(active_routes),
                2,
            )
        )

        summary = ClusterMetricsSummary(
            total_distance=round(detail.total_distance, 2),
            total_trips=total_trips,
            cluster_adherence=None if adherence is None else round(adherence, 4),
            cross_cluster_moves=cross_cluster_moves,
            shortage_kl=round(sum(item.demand_kl for item in detail.unserved_orders), 2),
            truck_utilization=avg_utilization,
            total_clusters=len(cluster_rows),
            total_spbu=sum(len(row.spbu_ids or []) for row in cluster_rows),
        )
        truck_metrics.sort(key=lambda item: (-item.purity_ratio, item.truck_id))
        edges.sort(key=lambda item: (item.trip_sequence, item.truck_id, item.from_spbu_id, item.to_spbu_id))
        cluster_metrics.sort(key=lambda item: item.cluster_id)
        return summary, cluster_metrics, edges, truck_metrics

    @staticmethod
    def _cluster_by_spbu(cluster_rows: Iterable[db_models.VRPCluster]) -> dict[str, str]:
        mapping: dict[str, str] = {}
        for row in cluster_rows:
            for spbu_id in row.spbu_ids or []:
                mapping[spbu_id] = row.cluster_id
        return mapping

    @staticmethod
    def _route_trip_count_raw(route: db_models.OptimizationRoute) -> int:
        ordered_stops = sorted(route.stops, key=lambda item: item.sequence)
        if not ordered_stops:
            return 0
        reload_count = sum(1 for stop in ordered_stops if stop.order_id.startswith("DEPOT_RELOAD#"))
        return reload_count + 1

    @staticmethod
    def _solver_mode_label(
        solver_run: db_models.VRPSolverRun | None,
        has_clusters: bool,
    ) -> str:
        if solver_run is not None:
            return "RouteFinder ON" if solver_run.routefinder_enabled else "RouteFinder OFF"
        return "RouteFinder ON" if has_clusters else "RouteFinder OFF"
