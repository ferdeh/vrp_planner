"""Client abstraction for SPBU and depot master data."""

from __future__ import annotations

import logging

import httpx

from app.core.config import get_settings
from app.models import schemas

logger = logging.getLogger(__name__)

MOCK_SPBU = [
    {
        "spbu_id": "SPBU001",
        "name": "SPBU A",
        "lat": -6.2,
        "lng": 106.8,
        "time_window_start": "08:00",
        "time_window_end": "17:00",
        "truck_category": 2,
        "allowed_truck_types": ["SMALL", "MEDIUM"],
    },
    {
        "spbu_id": "SPBU002",
        "name": "SPBU B",
        "lat": -6.24,
        "lng": 106.85,
        "time_window_start": "09:00",
        "time_window_end": "16:00",
        "truck_category": 4,
        "allowed_truck_types": ["SMALL", "MEDIUM", "LARGE"],
    },
]

MOCK_DEPOTS = [
    {
        "depot_id": "DPT001",
        "name": "Depot A",
        "lat": -6.1,
        "lng": 106.7,
        "time_window_start": "00:00",
        "time_window_end": "23:59",
        "gate_limit": 2,
    }
]


class MasterDataClient:
    """Read-only access layer for external master data service."""

    def __init__(self) -> None:
        self.settings = get_settings()

    def list_spbu(self, depot_id: str | None = None) -> list[schemas.SPBUData]:
        if self.settings.use_mock_master_data:
            return [schemas.SPBUData.model_validate(item) for item in MOCK_SPBU]
        try:
            return self._list_spbu_from_nodes(depot_id=depot_id)
        except Exception as exc:
            logger.warning("Failed loading SPBU from nodes endpoint, falling back to spbu path: %s", exc)
            return [schemas.SPBUData.model_validate(item) for item in self._get(self.settings.api_paths["spbu_list"])]

    def get_spbu(self, spbu_id: str) -> schemas.SPBUData:
        if self.settings.use_mock_master_data:
            for item in MOCK_SPBU:
                if item["spbu_id"] == spbu_id:
                    return schemas.SPBUData.model_validate(item)
            raise ValueError(f"SPBU {spbu_id} not found in mock data.")
        try:
            for item in self._list_spbu_from_nodes():
                if item.spbu_id == spbu_id:
                    return item
        except Exception as exc:
            logger.warning("Failed loading SPBU detail from nodes endpoint, falling back to detail path: %s", exc)
        path = self.settings.api_paths["spbu_detail"].format(id=spbu_id)
        return schemas.SPBUData.model_validate(self._get(path))

    def get_spbu_many(self, spbu_ids: list[str], depot_id: str | None = None) -> dict[str, schemas.SPBUData]:
        available = {item.spbu_id: item for item in self.list_spbu(depot_id=depot_id)}
        return {spbu_id: available[spbu_id] for spbu_id in spbu_ids if spbu_id in available}

    def list_depots(self) -> list[schemas.DepotData]:
        if self.settings.use_mock_master_data:
            return [schemas.DepotData.model_validate(item) for item in MOCK_DEPOTS]
        try:
            return self._list_depots_from_nodes()
        except Exception as exc:
            logger.warning("Failed loading depots from nodes endpoint, falling back to depots path: %s", exc)
            return [schemas.DepotData.model_validate(item) for item in self._get(self.settings.api_paths["depots"])]

    def _list_depots_from_nodes(self) -> list[schemas.DepotData]:
        raw_nodes = self._get(self.settings.api_paths["nodes"])
        depots = []
        for item in raw_nodes:
            if str(item.get("node_type", "")).upper() != "DEPOT":
                continue
            depots.append(
                schemas.DepotData(
                    depot_id=str(item["node_id"]),
                    name=str(item.get("node_name") or item.get("node_code") or item["node_id"]),
                    lat=float(item.get("lat", 0.0)),
                    lng=float(item.get("lon", item.get("lng", 0.0))),
                    time_window_start=self._normalize_time(item.get("tw_start"), fallback="00:00"),
                    time_window_end=self._normalize_time(item.get("tw_end"), fallback="23:59"),
                    gate_limit=self._normalize_gate_limit(item),
                )
            )
        if not depots:
            raise ValueError("No depot nodes found.")
        return depots

    def get_depot(self, depot_id: str) -> schemas.DepotData:
        for depot in self.list_depots():
            if depot.depot_id == depot_id:
                return depot
        raise ValueError(f"Depot {depot_id} not found in master data.")

    def _list_spbu_from_nodes(self, depot_id: str | None = None) -> list[schemas.SPBUData]:
        raw_nodes = self._get(self.settings.api_paths["nodes"])
        spbu_list = []
        for item in raw_nodes:
            if str(item.get("node_type", "")).upper() != "SPBU":
                continue
            supply_depot_ids = [str(depot) for depot in item.get("supply_depot_ids", [])]
            if depot_id and depot_id not in supply_depot_ids:
                continue
            spbu_list.append(
                schemas.SPBUData(
                    spbu_id=str(item["node_id"]),
                    name=str(item.get("node_name") or item.get("node_code") or item["node_id"]),
                    lat=float(item.get("lat", 0.0)),
                    lng=float(item.get("lon", item.get("lng", 0.0))),
                    time_window_start=self._normalize_time(item.get("tw_start"), fallback="08:00"),
                    time_window_end=self._normalize_time(item.get("tw_end"), fallback="17:00"),
                    truck_category=self._normalize_truck_category(item),
                    allowed_truck_types=[],
                    supply_depot_ids=supply_depot_ids,
                )
            )
        return spbu_list

    def _normalize_time(self, value: str | None, fallback: str) -> str:
        if not value:
            return fallback
        return value[:5]

    def _normalize_gate_limit(self, item: dict) -> int | None:
        candidates = [
            item.get("gate_limit"),
            item.get("bay_count"),
            item.get("gate_count"),
            item.get("total_bay"),
            item.get("jumlah_bay"),
            item.get("max_concurrent_trucks"),
        ]
        for value in candidates:
            if value in (None, ""):
                continue
            try:
                parsed = int(value)
            except (TypeError, ValueError):
                continue
            if parsed > 0:
                return parsed

        bays = item.get("bays") or item.get("gate_bays") or item.get("loading_bays")
        if isinstance(bays, list) and bays:
            return len(bays)
        return None

    def _normalize_truck_category(self, item: dict) -> int | None:
        candidates = [
            item.get("truck_category"),
            item.get("truck_category_id"),
            item.get("max_truck_category"),
            item.get("vehicle_category"),
            item.get("kategori_truck"),
        ]
        for value in candidates:
            if value in (None, ""):
                continue
            try:
                parsed = int(value)
            except (TypeError, ValueError):
                continue
            if parsed > 0:
                return parsed
        return None

    def _get(self, path: str):
        url = f"{self.settings.master_data_api_base_url.rstrip('/')}{path}"
        logger.info("Fetching master data from %s", url)
        with httpx.Client(timeout=self.settings.request_timeout_seconds) as client:
            response = client.get(url)
            response.raise_for_status()
            return response.json()
