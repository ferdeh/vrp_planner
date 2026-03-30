"""Objective-related helpers for routing solver."""

from __future__ import annotations

from app.models import schemas


def active_objective_priority(config: schemas.OptimizationConfig) -> list[str]:
    ordered = [item for item in config.objective_priority if getattr(config, item, False)]
    return ordered or ["minimize_unserved_orders"]


def objective_priority_scale(config: schemas.OptimizationConfig, objective_key: str) -> int:
    ordered = active_objective_priority(config)
    if objective_key not in ordered:
        return 1
    rank = ordered.index(objective_key)
    return 100 ** (len(ordered) - rank - 1)


def effective_unserved_penalty(config: schemas.OptimizationConfig) -> int:
    base_penalty = int(round(config.penalties.unserved_order_penalty))
    if not config.minimize_unserved_orders:
        return base_penalty
    return max(1, base_penalty * objective_priority_scale(config, "minimize_unserved_orders"))


def vehicle_fixed_cost(truck: schemas.TruckInput, config: schemas.OptimizationConfig) -> int:
    """Return fixed cost used by solver objective."""

    base_cost = 0.0
    if config.minimize_truck_count:
        base_cost += (
            config.penalties.activation_cost_vehicle
            * objective_priority_scale(config, "minimize_truck_count")
        )
    return int(round(base_cost))


def transit_cost(
    distance_km: int,
    travel_minutes: int,
    truck: schemas.TruckInput,
    config: schemas.OptimizationConfig,
) -> int:
    """Return cost coefficient for a travel arc."""

    total = 0.0
    if config.minimize_distance:
        total += (
            distance_km
            * config.penalties.distance_weight
            * objective_priority_scale(config, "minimize_distance")
        )
    if config.minimize_time:
        total += (
            travel_minutes
            * config.penalties.time_weight
            * objective_priority_scale(config, "minimize_time")
        )
    return int(round(total))
