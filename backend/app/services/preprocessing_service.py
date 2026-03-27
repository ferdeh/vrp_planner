"""Preprocessing and validation for optimization scenarios."""

from __future__ import annotations

from datetime import datetime
import logging
import math
from dataclasses import dataclass
from typing import Literal

from app.models import schemas
from app.services.master_data_client import MasterDataClient
from app.services.network_client import NetworkClient
from app.utils.time_utils import clamp_window, hhmm_to_minutes
from app.utils.validators import validate_order, validate_truck

logger = logging.getLogger(__name__)


@dataclass
class RouteNode:
    node_index: int
    node_kind: Literal["shipment", "reload"]
    order_id: str
    parent_order_id: str
    spbu_id: str
    product_type: str
    demand_kl: float
    service_time_minutes: int
    time_window_start: int
    time_window_end: int
    allowed_vehicle_indices: list[int]
    matrix_node_name: str
    priority: bool = False
    priority_eta_minutes: int | None = None


@dataclass
class PreprocessedProblem:
    depot_id: str
    depot_name: str
    depot_gate_limit: int
    depot_operation_window_start: int
    depot_operation_window_end: int
    dispatch_date: str
    depot_service_time_minutes: int
    config: schemas.OptimizationConfig
    notes: list[schemas.PreprocessingNote]
    route_nodes: list[RouteNode]
    preassigned_unserved: list[schemas.UnservedOrderDetail]
    orders: list[schemas.OrderInput]
    trucks: list[schemas.TruckInput]
    spbu_map: dict[str, schemas.SPBUData]
    time_matrix: list[list[int]]
    distance_matrix: list[list[int]]
    matrix_positions: dict[str, int]

    @property
    def total_demand(self) -> float:
        return round(sum(order.demand_kl for order in self.orders), 2)

    @property
    def shipments(self) -> list[RouteNode]:
        return [node for node in self.route_nodes if node.node_kind == "shipment"]

    @property
    def reload_nodes(self) -> list[RouteNode]:
        return [node for node in self.route_nodes if node.node_kind == "reload"]

    def get_node(self, manager_node: int) -> RouteNode | None:
        if manager_node <= 0:
            return None
        return self.route_nodes[manager_node - 1]


class PreprocessingService:
    """Prepare validated solver-ready problem objects."""

    def __init__(
        self,
        master_data_client: MasterDataClient | None = None,
        network_client: NetworkClient | None = None,
    ) -> None:
        self.master_data_client = master_data_client or MasterDataClient()
        self.network_client = network_client or NetworkClient(self.master_data_client)

    def preprocess(
        self,
        payload: schemas.OptimizationRequest,
        config: schemas.OptimizationConfig,
    ) -> PreprocessedProblem:
        notes: list[schemas.PreprocessingNote] = []
        shipments: list[RouteNode] = []
        preassigned_unserved: list[schemas.UnservedOrderDetail] = []

        available_trucks = self._filter_dispatch_available_trucks(
            payload.available_trucks,
            dispatch_date=payload.dispatch_date,
            notes=notes,
        )

        for order in payload.orders:
            validate_order(order)
        for truck in available_trucks:
            validate_truck(truck, payload.depot_id)

        spbu_ids = sorted({order.spbu_id for order in payload.orders})
        spbu_map = self.master_data_client.get_spbu_many(spbu_ids, depot_id=payload.depot_id)
        try:
            depot = self.master_data_client.get_depot(payload.depot_id)
            depot_name = depot.name
            depot_gate_limit = depot.gate_limit or max(1, len(available_trucks))
            depot_operation_window_start = hhmm_to_minutes(depot.time_window_start)
            depot_operation_window_end = hhmm_to_minutes(depot.time_window_end)
        except Exception:
            depot_name = payload.depot_id
            depot_gate_limit = max(1, len(available_trucks))
            depot_operation_window_start = 0
            depot_operation_window_end = (24 * 60) - 1
        missing_spbu = [spbu_id for spbu_id in spbu_ids if spbu_id not in spbu_map]
        if missing_spbu:
            raise ValueError(
                f"SPBU not found in master data for depot {payload.depot_id}: {', '.join(missing_spbu)}"
            )

        time_matrix_response = self.network_client.get_time_matrix(payload.depot_id, spbu_ids)
        distance_matrix_response = self.network_client.get_distance_matrix(payload.depot_id, spbu_ids)
        matrix_positions = {name: index for index, name in enumerate(time_matrix_response.nodes)}

        if config.soft_constraints.capacity_limit or not config.hard_constraints.capacity_limit:
            notes.append(
                schemas.PreprocessingNote(
                    code="CAPACITY_VIOLATION_NOT_SUPPORTED",
                    message="Capacity violation remains hard in MVP solver; penalty is stored for roadmap only.",
                )
            )
        if config.soft_constraints.truck_category or not config.hard_constraints.truck_category:
            notes.append(
                schemas.PreprocessingNote(
                    code="TRUCK_CATEGORY_SOFT_NOT_SUPPORTED",
                    message="Truck category remains hard in MVP solver for SPBU access policy.",
                )
            )

        for order in payload.orders:
            spbu = spbu_map[order.spbu_id]
            start = hhmm_to_minutes(spbu.time_window_start)
            end = hhmm_to_minutes(spbu.time_window_end)
            start, end = clamp_window(start, end)
            compatible_vehicle_indices = [
                index
                for index, truck in enumerate(available_trucks)
                if (
                    not config.hard_constraints.truck_category
                    or spbu.truck_category is None
                    or (
                        truck.truck_category is not None
                        and truck.truck_category <= spbu.truck_category
                    )
                )
            ]

            if not compatible_vehicle_indices:
                reason = "No truck matches SPBU truck category policy."
                if config.soft_constraints.allow_unserved_orders:
                    preassigned_unserved.append(
                        schemas.UnservedOrderDetail(
                            order_id=order.order_id,
                            parent_order_id=order.order_id,
                            spbu_id=order.spbu_id,
                            demand_kl=order.demand_kl,
                            reason=reason,
                        )
                    )
                    notes.append(
                        schemas.PreprocessingNote(
                            code="ORDER_INFEASIBLE_COMPATIBILITY",
                            message=f"Order {order.order_id} marked unserved before solver.",
                            metadata={"order_id": order.order_id},
                        )
                    )
                    continue
                raise ValueError(f"Order {order.order_id} infeasible before solver: {reason}")

            compatible_max_compartment_capacity = max(
                self._max_compartment_capacity(available_trucks[index]) for index in compatible_vehicle_indices
            )
            selected_shipment_capacity = self._select_shipment_capacity(
                order.demand_kl,
                [self._max_compartment_capacity(available_trucks[index]) for index in compatible_vehicle_indices],
            )
            if config.hard_constraints.no_split_order and order.demand_kl > compatible_max_compartment_capacity:
                reason = (
                    f"Order demand {order.demand_kl} KL exceeds max feasible compartment capacity "
                    f"{compatible_max_compartment_capacity} KL while no split order is active."
                )
                if config.soft_constraints.allow_unserved_orders:
                    preassigned_unserved.append(
                        schemas.UnservedOrderDetail(
                            order_id=order.order_id,
                            parent_order_id=order.order_id,
                            spbu_id=order.spbu_id,
                            demand_kl=order.demand_kl,
                            reason=reason,
                        )
                    )
                    notes.append(
                        schemas.PreprocessingNote(
                            code="ORDER_INFEASIBLE_NO_SPLIT",
                            message=f"Order {order.order_id} marked unserved because split is disabled.",
                            metadata={
                                "order_id": order.order_id,
                                "demand_kl": order.demand_kl,
                                "max_compartment_capacity_kl": compatible_max_compartment_capacity,
                            },
                        )
                    )
                    continue
                raise ValueError(f"Order {order.order_id} infeasible before solver: {reason}")

            shipment_count = max(1, math.ceil(order.demand_kl / selected_shipment_capacity))
            remaining = order.demand_kl
            for shipment_number in range(1, shipment_count + 1):
                shipment_demand = min(remaining, selected_shipment_capacity)
                remaining = round(remaining - shipment_demand, 6)
                shipment_order_id = order.order_id if shipment_count == 1 else f"{order.order_id}#{shipment_number}"
                shipment_vehicle_indices = [
                    index
                    for index in compatible_vehicle_indices
                    if self._max_compartment_capacity(available_trucks[index]) >= shipment_demand
                ]
                if not shipment_vehicle_indices:
                    reason = (
                        f"No compatible truck compartment can carry shipment {shipment_order_id} "
                        f"with demand {shipment_demand} KL."
                    )
                    if config.soft_constraints.allow_unserved_orders:
                        preassigned_unserved.append(
                            schemas.UnservedOrderDetail(
                                order_id=shipment_order_id,
                                parent_order_id=order.order_id,
                                spbu_id=order.spbu_id,
                                demand_kl=shipment_demand,
                                reason=reason,
                            )
                        )
                        notes.append(
                            schemas.PreprocessingNote(
                                code="SHIPMENT_INFEASIBLE_COMPARTMENT",
                                message=f"Shipment {shipment_order_id} marked unserved before solver.",
                                metadata={
                                    "order_id": order.order_id,
                                    "shipment_order_id": shipment_order_id,
                                    "shipment_demand_kl": shipment_demand,
                                },
                            )
                        )
                        continue
                    raise ValueError(f"Order {order.order_id} infeasible before solver: {reason}")
                shipments.append(
                    RouteNode(
                        node_index=len(shipments) + 1,
                        node_kind="shipment",
                        order_id=shipment_order_id,
                        parent_order_id=order.order_id,
                        spbu_id=order.spbu_id,
                        product_type=order.product_type,
                        demand_kl=shipment_demand,
                        service_time_minutes=order.service_time_minutes,
                        time_window_start=start,
                        time_window_end=end,
                        allowed_vehicle_indices=shipment_vehicle_indices,
                        matrix_node_name=order.spbu_id,
                        priority=order.priority,
                        priority_eta_minutes=hhmm_to_minutes(order.eta) if order.priority and order.eta else None,
                    )
                )
            if shipment_count > 1:
                notes.append(
                    schemas.PreprocessingNote(
                        code="ORDER_SPLIT",
                        message=f"Order {order.order_id} split into {shipment_count} feasible compartment-sized shipments.",
                        metadata={
                            "order_id": order.order_id,
                            "shipments": shipment_count,
                            "max_compartment_capacity_kl": compatible_max_compartment_capacity,
                            "selected_shipment_capacity_kl": selected_shipment_capacity,
                        },
                    )
                )

        if not shipments and preassigned_unserved:
            notes.append(
                schemas.PreprocessingNote(
                    code="NO_FEASIBLE_SHIPMENTS",
                    message="No shipment remained for solver after preprocessing.",
                )
            )

        route_nodes = list(shipments)
        if shipments:
            for reload_number in range(1, len(shipments)):
                route_nodes.append(
                    RouteNode(
                        node_index=len(route_nodes) + 1,
                        node_kind="reload",
                        order_id=f"DEPOT_RELOAD#{reload_number}",
                        parent_order_id="-",
                        spbu_id=payload.depot_id,
                        product_type="DEPOT_RELOAD",
                        demand_kl=0.0,
                        service_time_minutes=payload.depot_service_time_minutes,
                        time_window_start=0,
                        time_window_end=24 * 60 * 2,
                        allowed_vehicle_indices=list(range(len(available_trucks))),
                        matrix_node_name="DEPOT",
                    )
                )

        logger.info(
            "Preprocessed scenario with %s shipments, %s reload nodes, %s trucks, %s preassigned unserved orders",
            len(shipments),
            len(route_nodes) - len(shipments),
            len(available_trucks),
            len(preassigned_unserved),
        )

        return PreprocessedProblem(
            depot_id=payload.depot_id,
            depot_name=depot_name,
            depot_gate_limit=depot_gate_limit,
            depot_operation_window_start=depot_operation_window_start,
            depot_operation_window_end=depot_operation_window_end,
            dispatch_date=str(payload.dispatch_date),
            depot_service_time_minutes=payload.depot_service_time_minutes,
            config=config,
            notes=notes,
            route_nodes=route_nodes,
            preassigned_unserved=preassigned_unserved,
            orders=payload.orders,
            trucks=available_trucks,
            spbu_map=spbu_map,
            time_matrix=time_matrix_response.matrix,
            distance_matrix=distance_matrix_response.matrix,
            matrix_positions=matrix_positions,
        )

    def _filter_dispatch_available_trucks(
        self,
        trucks: list[schemas.TruckInput],
        dispatch_date,
        notes: list[schemas.PreprocessingNote],
    ) -> list[schemas.TruckInput]:
        filtered: list[schemas.TruckInput] = []
        for truck in trucks:
            unavailable = self._overlaps_dispatch_date(
                truck.not_available_from,
                truck.not_available_to,
                str(dispatch_date),
            )
            if unavailable:
                notes.append(
                    schemas.PreprocessingNote(
                        code="TRUCK_NOT_AVAILABLE_ON_DISPATCH_DATE",
                        message=f"Truck {truck.truck_id} excluded because it is not available on dispatch date.",
                        metadata={
                            "truck_id": truck.truck_id,
                            "dispatch_date": str(dispatch_date),
                            "not_available_from": truck.not_available_from,
                            "not_available_to": truck.not_available_to,
                        },
                    )
                )
                continue
            filtered.append(truck)
        return filtered

    def _overlaps_dispatch_date(
        self,
        not_available_from: str | None,
        not_available_to: str | None,
        dispatch_date: str,
    ) -> bool:
        if not not_available_from or not not_available_to:
            return False
        try:
            start = datetime.fromisoformat(not_available_from.replace("Z", "+00:00"))
            end = datetime.fromisoformat(not_available_to.replace("Z", "+00:00"))
        except ValueError:
            return False
        return start.date().isoformat() <= dispatch_date <= end.date().isoformat()

    def _max_compartment_capacity(self, truck: schemas.TruckInput) -> float:
        if truck.compartments:
            return max(compartment.capacity_kl for compartment in truck.compartments)
        return truck.capacity_kl

    def _select_shipment_capacity(self, demand_kl: float, compartment_capacities: list[float]) -> float:
        positive_capacities = sorted(capacity for capacity in compartment_capacities if capacity > 0)
        if not positive_capacities:
            return demand_kl

        minimum_shipment_count = min(math.ceil(demand_kl / capacity) for capacity in positive_capacities)
        for capacity in positive_capacities:
            if math.ceil(demand_kl / capacity) == minimum_shipment_count:
                return capacity
        return positive_capacities[-1]
