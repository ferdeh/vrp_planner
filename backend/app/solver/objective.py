"""Objective-related helpers for routing solver."""

from __future__ import annotations

import math

from app.models import schemas


UNUSED_CAPACITY_SCALE = 100


def active_objective_priority(config: schemas.OptimizationConfig) -> list[str]:
    ordered = [item for item in config.objective_priority if getattr(config, item, False)]
    return ordered or ["minimize_distance"]


def objective_priority_scale(config: schemas.OptimizationConfig, objective_key: str) -> int:
    ordered = active_objective_priority(config)
    if objective_key not in ordered:
        return 1
    rank = ordered.index(objective_key)
    return 100 ** (len(ordered) - rank - 1)


def effective_unserved_penalty(config: schemas.OptimizationConfig) -> int:
    return max(1, int(round(config.penalties.unserved_order_penalty)))


def active_utilization_objective_key(config: schemas.OptimizationConfig) -> str | None:
    if (
        config.primary_objective == schemas.PrimaryObjective.MINIMIZE_DEPOT_OPERATION
        and config.minimize_depot_operation_time
    ):
        return "minimize_depot_operation_time"
    if (
        config.primary_objective == schemas.PrimaryObjective.MINIMIZE_TRUCK_COUNT
        and config.minimize_truck_count
    ):
        return "minimize_truck_count"
    if config.minimize_truck_count:
        return "minimize_truck_count"
    if config.minimize_depot_operation_time:
        return "minimize_depot_operation_time"
    return None


def vehicle_working_limit_minutes(
    truck: schemas.TruckInput,
    config: schemas.OptimizationConfig,
) -> int:
    shift_start = hhmm_to_minutes_safe(truck.shift_start)
    shift_end = hhmm_to_minutes_safe(truck.shift_end)
    if shift_end <= shift_start:
        return 0
    working_limit = (
        shift_end
        if not config.max_vehicle_working_time_minutes
        else min(shift_end, shift_start + config.max_vehicle_working_time_minutes)
    )
    return max(0, working_limit - shift_start)


def active_truck_idle_threshold_ratio(config: schemas.OptimizationConfig) -> float:
    objective_key = active_utilization_objective_key(config)
    if objective_key == "minimize_depot_operation_time":
        return max(0.0, float(config.penalties.active_truck_idle_threshold_percent_depot_operation) / 100.0)
    return max(0.0, float(config.penalties.active_truck_idle_threshold_percent_truck_count) / 100.0)


def active_truck_idle_target_minutes(
    truck: schemas.TruckInput,
    config: schemas.OptimizationConfig,
    *,
    min_cycle_minutes: int,
) -> int:
    available_minutes = vehicle_working_limit_minutes(truck, config)
    if available_minutes <= 0:
        return 0
    threshold = max(
        int(min_cycle_minutes),
        int(math.ceil(available_minutes * active_truck_idle_threshold_ratio(config))),
    )
    return min(available_minutes, threshold)


def active_truck_idle_penalty_enabled(config: schemas.OptimizationConfig) -> bool:
    return config.minimize_truck_count or config.minimize_depot_operation_time


def unused_opportunity_capacity_penalty_enabled(config: schemas.OptimizationConfig) -> bool:
    return config.minimize_depot_operation_time


def utilization_objective_scale(config: schemas.OptimizationConfig) -> int:
    objective_key = active_utilization_objective_key(config)
    if objective_key is not None:
        return objective_priority_scale(config, objective_key)
    return 1


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


def hhmm_to_minutes_safe(value: str) -> int:
    hours, minutes = value.split(":")
    return (int(hours) * 60) + int(minutes)
