"""Tests for network client caching behavior."""

from __future__ import annotations

from app.core import config as config_module
from app.models import schemas
from app.services.network_client import NetworkClient


class _DummyMasterDataClient:
    def __init__(self) -> None:
        self.depot_calls = 0
        self.spbu_calls = 0

    def list_depots(self) -> list[schemas.DepotData]:
        self.depot_calls += 1
        return [
            schemas.DepotData(
                depot_id="DPT001",
                name="Depot A",
                lat=-6.1,
                lng=106.7,
                time_window_start="00:00",
                time_window_end="23:59",
                gate_limit=2,
            )
        ]

    def list_spbu(self) -> list[schemas.SPBUData]:
        self.spbu_calls += 1
        return [
            schemas.SPBUData(
                spbu_id="SPBU001",
                name="SPBU A",
                lat=-6.2,
                lng=106.8,
                time_window_start="08:00",
                time_window_end="16:00",
                truck_category=2,
            )
        ]


def test_network_client_caches_leg_audit_dependencies(monkeypatch):
    monkeypatch.setenv("USE_MOCK_MASTER_DATA", "false")
    config_module.get_settings.cache_clear()

    master_data_client = _DummyMasterDataClient()
    network_client = NetworkClient(master_data_client=master_data_client)
    edge_fetch_calls = 0

    def fake_get(_path: str, params: dict[str, str]):
        nonlocal edge_fetch_calls
        edge_fetch_calls += 1
        assert params == {}
        return [
            {
                "from_node_id": "DPT001",
                "to_node_id": "SPBU001",
                "distance_km": 10,
                "travel_time_min": 20,
                "max_velocity_kmh": 30,
            }
        ]

    monkeypatch.setattr(network_client, "_get", fake_get)

    first = network_client.get_leg_audit("DPT001", "SPBU001")
    second = network_client.get_leg_audit("DPT001", "SPBU001")

    assert first == second
    assert master_data_client.depot_calls == 1
    assert master_data_client.spbu_calls == 1
    assert edge_fetch_calls == 1

