"""RouteFinder-compatible SPBU clustering service."""

from __future__ import annotations

from collections import defaultdict

from app.schemas.canonical_vrp_schema import CanonicalOrder, CanonicalVRPModel
from app.schemas.routefinder_cluster_schema import Cluster, ClusterResult
from app.services.preprocessing_service import PreprocessedProblem


class RouteFinderClusterService:
    """Generate SPBU clusters and inject cluster metadata."""

    def generate(
        self,
        model: CanonicalVRPModel,
        *,
        max_cluster_size: int | None = None,
    ) -> ClusterResult:
        return self.generate_spbu_clusters(
            model,
            max_cluster_size=max_cluster_size or model.settings.max_cluster_size,
        )

    def generate_spbu_clusters(
        self,
        model: CanonicalVRPModel,
        max_cluster_size: int = 5,
    ) -> ClusterResult:
        orders_by_spbu = self.group_orders_by_spbu(model.orders)
        spbu_ids = [
            node.node_id
            for node in model.nodes
            if node.node_type.lower() == "spbu"
        ]
        if not spbu_ids:
            return ClusterResult(clusters=[])

        cluster_size = min(max(1, int(max_cluster_size)), 6)
        distance_matrix = model.matrices.distance_matrix
        matrix_index_by_node_id = {
            node_id: index
            for index, node_id in enumerate(model.matrices.node_ids)
        }
        total_demand_by_spbu = {
            spbu_id: round(sum(order.quantity_kl for order in orders_by_spbu.get(spbu_id, [])), 6)
            for spbu_id in spbu_ids
        }
        unassigned = set(spbu_ids)
        clusters: list[Cluster] = []

        while unassigned:
            seed = max(
                unassigned,
                key=lambda spbu_id: (total_demand_by_spbu.get(spbu_id, 0.0), spbu_id),
            )
            cluster_spbu_ids = [seed]
            unassigned.remove(seed)
            current = seed

            while unassigned and len(cluster_spbu_ids) < cluster_size:
                nearest = min(
                    unassigned,
                    key=lambda candidate: (
                        self._distance_between(
                            current,
                            candidate,
                            matrix_index_by_node_id,
                            distance_matrix,
                        ),
                        -total_demand_by_spbu.get(candidate, 0.0),
                        candidate,
                    ),
                )
                cluster_spbu_ids.append(nearest)
                unassigned.remove(nearest)
                current = nearest

            clusters.append(
                Cluster(
                    cluster_id=f"CL-{len(clusters) + 1:03d}",
                    spbu_ids=cluster_spbu_ids,
                    total_demand_kl=round(
                        sum(total_demand_by_spbu.get(spbu_id, 0.0) for spbu_id in cluster_spbu_ids),
                        2,
                    ),
                )
            )

        return ClusterResult(clusters=clusters)

    def group_orders_by_spbu(
        self,
        orders: list[CanonicalOrder],
    ) -> dict[str, list[CanonicalOrder]]:
        grouped: dict[str, list[CanonicalOrder]] = defaultdict(list)
        for order in orders:
            grouped[order.node_id].append(order)
        return dict(grouped)

    def map_orders_to_clusters(
        self,
        clusters: list[Cluster],
        orders: list[CanonicalOrder],
    ) -> dict[str, dict[str, object]]:
        orders_by_spbu = self.group_orders_by_spbu(orders)
        mapped: dict[str, dict[str, object]] = {}
        for cluster in clusters:
            cluster_orders: list[CanonicalOrder] = []
            for spbu_id in cluster.spbu_ids:
                cluster_orders.extend(orders_by_spbu.get(spbu_id, []))
            mapped[cluster.cluster_id] = {
                "spbu_ids": list(cluster.spbu_ids),
                "orders": cluster_orders,
                "total_demand_kl": round(sum(order.quantity_kl for order in cluster_orders), 2),
            }
        return mapped

    def inject_cluster_metadata(
        self,
        model: CanonicalVRPModel,
        cluster_result: ClusterResult,
    ) -> CanonicalVRPModel:
        cluster_by_spbu = {
            spbu_id: cluster.cluster_id
            for cluster in cluster_result.clusters
            for spbu_id in cluster.spbu_ids
        }
        enriched = model.model_copy(deep=True)
        enriched.clusters = [cluster.model_copy(deep=True) for cluster in cluster_result.clusters]
        for node in enriched.nodes:
            node.cluster_id = cluster_by_spbu.get(node.node_id)
        return enriched

    def apply_clusters_to_problem(
        self,
        problem: PreprocessedProblem,
        cluster_result: ClusterResult,
        *,
        cluster_mode: str,
    ) -> PreprocessedProblem:
        cluster_by_spbu = {
            spbu_id: cluster.cluster_id
            for cluster in cluster_result.clusters
            for spbu_id in cluster.spbu_ids
        }
        problem.clusters = [cluster.model_copy(deep=True) for cluster in cluster_result.clusters]
        problem.cluster_mode = cluster_mode
        problem.use_routefinder = bool(cluster_result.clusters)
        for node in problem.route_nodes:
            if node.node_kind != "shipment":
                node.cluster_id = None
                continue
            node.cluster_id = cluster_by_spbu.get(node.spbu_id)
        return problem

    @staticmethod
    def _distance_between(
        from_node_id: str,
        to_node_id: str,
        matrix_index_by_node_id: dict[str, int],
        distance_matrix: list[list[int]],
    ) -> int:
        from_index = matrix_index_by_node_id.get(from_node_id)
        to_index = matrix_index_by_node_id.get(to_node_id)
        if from_index is None or to_index is None:
            return 10**9
        return int(distance_matrix[from_index][to_index])
