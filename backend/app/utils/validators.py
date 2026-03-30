"""Validation helpers for domain objects."""

from __future__ import annotations

from app.models import schemas
from app.utils.time_utils import hhmm_to_minutes


def validate_order(order: schemas.OrderInput) -> None:
    """Raise ValueError when an order is not internally consistent."""

    if order.demand_kl <= 0:
        raise ValueError(f"Order {order.order_id} must have positive demand.")
    if order.service_time_minutes < 0:
        raise ValueError(f"Order {order.order_id} cannot have negative service time.")
    if order.priority and not order.eta:
        raise ValueError(f"Order {order.order_id} must define ETA when marked as priority.")
    if order.eta:
        hhmm_to_minutes(order.eta)
    if hhmm_to_minutes(order.time_window_end) < hhmm_to_minutes(order.time_window_start):
        raise ValueError(f"Order {order.order_id} has invalid time window.")


def validate_truck(truck: schemas.TruckInput, scenario_depot_id: str) -> None:
    """Raise ValueError when a truck is invalid for a scenario."""

    if truck.capacity_kl <= 0:
        raise ValueError(f"Truck {truck.truck_id} must have positive capacity.")
    if not truck.compartments:
        raise ValueError(f"Truck {truck.truck_id} must define at least one compartment.")
    if any(compartment.capacity_kl <= 0 for compartment in truck.compartments):
        raise ValueError(f"Truck {truck.truck_id} has a compartment with invalid capacity.")
    if truck.start_depot_id != scenario_depot_id or truck.end_depot_id != scenario_depot_id:
        raise ValueError(
            f"Truck {truck.truck_id} must start and end at scenario depot {scenario_depot_id} for MVP."
        )
    if hhmm_to_minutes(truck.shift_end) < hhmm_to_minutes(truck.shift_start):
        raise ValueError(f"Truck {truck.truck_id} has invalid shift window.")
