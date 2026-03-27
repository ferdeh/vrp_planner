"""Client abstraction for truck master data."""

from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime
from typing import Any

import httpx

from app.core.config import get_settings
from app.models import schemas
from app.services.master_data_client import MasterDataClient

logger = logging.getLogger(__name__)

MOCK_TRUCKS = [
    {
        "truck_id": "TRK001",
        "truck_type": "SMALL",
        "truck_category": 2,
        "capacity_kl": 8,
        "compartments": [
            {"compartment_id": "C1", "capacity_kl": 8},
        ],
        "fixed_cost": 1000,
        "variable_cost_per_km": 10,
        "variable_cost_per_minute": 2,
        "depot_id": "65",
        "shift_start": "06:00",
        "shift_end": "18:00",
        "compatible_product_types": ["PERTALITE", "PERTAMAX"],
        "is_available": True,
    },
    {
        "truck_id": "TRK002",
        "truck_type": "MEDIUM",
        "truck_category": 3,
        "capacity_kl": 16,
        "compartments": [
            {"compartment_id": "C1", "capacity_kl": 8},
            {"compartment_id": "C2", "capacity_kl": 8},
        ],
        "fixed_cost": 1800,
        "variable_cost_per_km": 12,
        "variable_cost_per_minute": 2,
        "depot_id": "65",
        "shift_start": "06:00",
        "shift_end": "18:00",
        "compatible_product_types": ["PERTALITE"],
        "is_available": True,
    },
]


class TruckMasterDataClient:
    """Read-only client for external truck master data service."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.master_data_client = MasterDataClient()

    def list_available_trucks(
        self,
        depot_id: str,
        dispatch_date: date | None = None,
    ) -> list[schemas.TruckMasterData]:
        if self.settings.use_mock_master_data:
            return [
                schemas.TruckMasterData.model_validate(item)
                for item in MOCK_TRUCKS
                if item["depot_id"] == depot_id and item["is_available"]
            ]

        depot_lookup = {item.depot_id: item for item in self.master_data_client.list_depots()}
        selected_depot = depot_lookup.get(depot_id)

        direct_payload = self._fetch_truck_payload(path="/v1/trucks", params={"depot_id": depot_id})
        direct_normalized = [self._normalize_truck(item) for item in direct_payload]
        direct_matches = [item for item in direct_normalized if item.is_available]
        if direct_matches:
            return self._attach_availability_windows(direct_matches, dispatch_date=dispatch_date)

        all_payload = self._fetch_truck_payload(path="/v1/trucks", params=None)
        all_normalized = [self._normalize_truck(item) for item in all_payload]
        if selected_depot is None:
            return self._attach_availability_windows(
                [item for item in all_normalized if item.is_available],
                dispatch_date=dispatch_date,
            )

        target_name = self._normalize_token(selected_depot.name)
        target_code = self._normalize_token(getattr(selected_depot, "depot_code", None) or selected_depot.name)
        filtered = [
            item
            for item in all_normalized
            if item.is_available
            and (
                self._normalize_token(item.depot_name) == target_name
                or self._normalize_token(item.depot_code) == target_code
                or target_name in self._normalize_token(item.depot_name)
                or self._normalize_token(item.depot_name) in target_name
            )
        ]
        return self._attach_availability_windows(filtered, dispatch_date=dispatch_date)

    def _fetch_truck_payload(self, path: str, params: dict[str, str] | None) -> list[dict[str, Any]]:
        url = f"{self.settings.truck_master_data_api_base_url.rstrip('/')}{path}"
        logger.info("Fetching truck master data from %s", url)
        with httpx.Client(timeout=self.settings.request_timeout_seconds) as client:
            response = client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            if isinstance(data, dict):
                if isinstance(data.get("items"), list):
                    return data["items"]
                if isinstance(data.get("data"), list):
                    return data["data"]
            if isinstance(data, list):
                return data
        return []

    def _normalize_truck(self, item: dict[str, Any]) -> schemas.TruckMasterData:
        compatible_product_types = item.get("compatible_product_types") or item.get("products") or ["PERTALITE"]
        if isinstance(compatible_product_types, str):
            compatible_product_types = [
                chunk.strip() for chunk in compatible_product_types.split(",") if chunk.strip()
            ]
        compartments = self._normalize_compartments(item)
        total_capacity = round(sum(compartment.capacity_kl for compartment in compartments), 6) if compartments else None

        depot_id = self._pick_first(item, ["depot_id", "home_depot_id", "current_depot_id", "depot"])
        available = item.get("is_available")
        if available is None:
            status = str(item.get("status", "")).lower()
            available = status in {"", "available", "ready", "active"}

        return schemas.TruckMasterData(
            truck_id=str(
                self._pick_first(item, ["truck_id", "vehicle_id", "truck_code", "id", "plate_number"])
            ),
            no_polisi=self._pick_first(item, ["no_polisi", "plate_number"], default=None),
            truck_type=str(
                self._pick_first(
                    item,
                    ["truck_type", "truck_type_name", "type", "truck_category", "category"],
                    default="UNKNOWN",
                )
            ),
            truck_category=self._normalize_truck_category(item),
            capacity_kl=float(
                total_capacity
                if total_capacity is not None
                else self._pick_first(item, ["capacity_kl", "capacity", "capacity_kl_total"], default=8)
            ),
            fixed_cost=float(self._pick_first(item, ["fixed_cost", "vehicle_fixed_cost"], default=1000)),
            variable_cost_per_km=float(
                self._pick_first(item, ["variable_cost_per_km", "cost_per_km"], default=10)
            ),
            variable_cost_per_minute=float(
                self._pick_first(item, ["variable_cost_per_minute", "cost_per_minute"], default=2)
            ),
            depot_id=str(depot_id),
            shift_start=self._normalize_time(
                self._pick_first(item, ["shift_start", "start_shift", "start_time"], default="06:00")
            ),
            shift_end=self._normalize_time(
                self._pick_first(item, ["shift_end", "end_shift", "end_time"], default="18:00")
            ),
            compatible_product_types=compatible_product_types,
            compartments=compartments,
            is_available=bool(available),
            depot_code=self._pick_first(item, ["depot_code"], default=None),
            depot_name=self._pick_first(item, ["depot_name"], default=None),
            status=self._pick_first(item, ["status"], default=None),
        )

    def _pick_first(self, item: dict[str, Any], keys: list[str], default: Any | None = None) -> Any:
        for key in keys:
            value = item.get(key)
            if value not in (None, ""):
                return value
        return default

    def _normalize_time(self, value: Any) -> str:
        if value is None:
            return "06:00"
        text = str(value)
        return text[:5] if len(text) >= 5 else text

    def _normalize_token(self, value: Any) -> str:
        if value is None:
            return ""
        return re.sub(r"[^a-z0-9]+", "", str(value).lower())

    def _normalize_truck_category(self, item: dict[str, Any]) -> int | None:
        for key in [
            "truck_category",
            "truck_category_id",
            "vehicle_category",
            "category",
            "kategori_truck",
        ]:
            value = item.get(key)
            if value in (None, ""):
                continue
            try:
                parsed = int(value)
            except (TypeError, ValueError):
                continue
            if parsed > 0:
                return parsed
        return None

    def _normalize_compartments(self, item: dict[str, Any]) -> list[schemas.TruckCompartment]:
        raw = self._pick_first(
            item,
            [
                "compartments",
                "compartment",
                "compartement",
                "kompartemen",
                "truck_compartments",
                "tank_compartments",
                "partitions",
                "chambers",
            ],
        )
        if raw is None:
            count = self._coerce_int(
                self._pick_first(
                    item,
                    [
                        "compartment_count",
                        "compartement_count",
                        "jumlah_kompartemen",
                        "number_of_compartments",
                    ],
                )
            )
            capacity_per_compartment = self._coerce_float(
                self._pick_first(
                    item,
                    [
                        "capacity_per_compartment_kl",
                        "capacity_per_compartement_kl",
                        "compartment_capacity_kl",
                    ],
                )
            )
            capacity = self._coerce_float(
                self._pick_first(item, ["capacity_kl", "capacity", "capacity_kl_total"], default=8)
            )
            if count and count > 0:
                per_compartment = (
                    round(capacity_per_compartment, 6)
                    if capacity_per_compartment > 0
                    else round(capacity / count, 6)
                )
                return [
                    schemas.TruckCompartment(compartment_id=str(index), capacity_kl=per_compartment)
                    for index in range(1, count + 1)
                ]
            return [schemas.TruckCompartment(compartment_id="1", capacity_kl=capacity)]

        values: Any = raw
        if isinstance(raw, str):
            try:
                values = json.loads(raw)
            except json.JSONDecodeError:
                values = [chunk.strip() for chunk in raw.split(",") if chunk.strip()]
        if isinstance(values, dict):
            nested = self._pick_first(values, ["items", "data", "compartments"], default=None)
            values = nested if isinstance(nested, list) else [values]

        if isinstance(values, (int, float)):
            values = [values]

        if not isinstance(values, list):
            return []

        compartments: list[schemas.TruckCompartment] = []
        for index, value in enumerate(values, start=1):
            if isinstance(value, dict):
                capacity = self._coerce_float(
                    self._pick_first(
                        value,
                        [
                            "capacity_kl",
                            "capacity",
                            "volume",
                            "size",
                            "max_capacity_kl",
                            "capacityKl",
                            "kapasitas",
                        ],
                    )
                )
                if capacity <= 0:
                    continue
                compartment_id = self._pick_first(
                    value,
                    ["compartment_id", "id", "code", "name", "sequence", "number"],
                    default=str(index),
                )
            else:
                capacity = self._coerce_float(value)
                if capacity <= 0:
                    continue
                compartment_id = str(index)
            compartments.append(
                schemas.TruckCompartment(
                    compartment_id=str(compartment_id),
                    capacity_kl=capacity,
                )
            )
        return compartments

    def _coerce_float(self, value: Any, default: float = 0.0) -> float:
        if value in (None, ""):
            return default
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _coerce_int(self, value: Any, default: int = 0) -> int:
        if value in (None, ""):
            return default
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _attach_availability_windows(
        self,
        trucks: list[schemas.TruckMasterData],
        dispatch_date: date | None = None,
    ) -> list[schemas.TruckMasterData]:
        enriched: list[schemas.TruckMasterData] = []
        for truck in trucks:
            not_available_from = None
            not_available_to = None
            status = truck.status
            try:
                windows = self._fetch_truck_payload(
                    path=f"/v1/trucks/{truck.truck_id}/availability-windows",
                    params=None,
                )
                if windows:
                    matching = self._find_dispatch_window(windows, dispatch_date)
                    if matching is not None:
                        not_available_from = self._normalize_datetime(matching.get("available_from"))
                        not_available_to = self._normalize_datetime(matching.get("available_until"))
                        status = "NOT_AVAILABLE"
            except Exception as exc:
                logger.warning("Failed to load availability windows for truck %s: %s", truck.truck_id, exc)
            enriched.append(
                truck.model_copy(
                    update={
                        "not_available_from": not_available_from,
                        "not_available_to": not_available_to,
                        "status": status,
                    }
                )
            )
        return enriched

    def _find_dispatch_window(
        self,
        windows: list[dict[str, Any]],
        dispatch_date: date | None,
    ) -> dict[str, Any] | None:
        if dispatch_date is None:
            return None

        matching: list[tuple[datetime, dict[str, Any]]] = []
        for item in windows:
            window_status = str(item.get("status", "")).strip().upper()
            if window_status != "CONFIRMED":
                continue
            start = self._parse_datetime(item.get("available_from"))
            end = self._parse_datetime(item.get("available_until"))
            if start is None or end is None:
                continue
            if start.date() <= dispatch_date <= end.date():
                matching.append((start, item))

        if not matching:
            return None

        matching.sort(key=lambda row: row[0])
        return matching[0][1]

    def _parse_datetime(self, value: Any) -> datetime | None:
        if not value:
            return None
        text = str(value)
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None

    def _normalize_datetime(self, value: Any) -> str | None:
        dt = self._parse_datetime(value)
        if dt is not None:
            return dt.strftime("%Y-%m-%d %H:%M")
        return str(value) if value else None
