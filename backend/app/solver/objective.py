"""Objective-related helpers for routing solver."""

from __future__ import annotations

from app.models import schemas


def vehicle_fixed_cost(truck: schemas.TruckInput, config: schemas.OptimizationConfig) -> int:
    """Return fixed cost used by solver objective."""

    base_cost = truck.fixed_cost
    if config.minimize_truck_count:
        base_cost += config.penalties.fixed_cost_vehicle
    return int(round(base_cost))


def transit_cost(distance_km: int, travel_minutes: int, truck: schemas.TruckInput, config: schemas.OptimizationConfig) -> int:
    """Return cost coefficient for a travel arc."""

    total = 0.0
    if config.minimize_distance:
        total += distance_km * truck.variable_cost_per_km * config.penalties.distance_weight
    if config.minimize_time:
        total += travel_minutes * truck.variable_cost_per_minute * config.penalties.time_weight
    return int(round(total))
