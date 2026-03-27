"""Tests for truck master data normalization."""

from __future__ import annotations

from app.services.master_data_client import MasterDataClient
from app.services.truck_master_data_client import TruckMasterDataClient


def test_normalize_truck_reads_compartments_from_api_payload(configured_modules):
    client = TruckMasterDataClient()

    truck = client._normalize_truck(
        {
            "id": "TRK100",
            "truck_type": "FUSO",
            "depot_id": "DPT001",
            "shift_start": "06:00",
            "shift_end": "18:00",
            "compatible_product_types": ["PERTALITE"],
            "compartments": [
                {"id": "A", "capacity": 8},
                {"id": "B", "capacity_kl": 6},
            ],
        }
    )

    assert truck.capacity_kl == 14
    assert [item.compartment_id for item in truck.compartments] == ["A", "B"]
    assert [item.capacity_kl for item in truck.compartments] == [8, 6]


def test_normalize_truck_reads_real_api_compartement_fields(configured_modules):
    client = TruckMasterDataClient()

    truck = client._normalize_truck(
        {
            "id": "uuid-1",
            "truck_code": "TRK001",
            "no_polisi": "B9101FMS",
            "truck_category": 4,
            "truck_type_name": "CDE",
            "depot_id": 4,
            "compartement_count": 2,
            "capacity_per_compartement_kl": "8.00",
            "capacity_kl": "16.00",
            "status": "ACTIVE",
        }
    )

    assert truck.truck_id == "TRK001"
    assert truck.truck_type == "CDE"
    assert truck.truck_category == 4
    assert truck.capacity_kl == 16
    assert len(truck.compartments) == 2
    assert [item.capacity_kl for item in truck.compartments] == [8, 8]


def test_normalize_spbu_and_depot_node_payload_reads_category_and_gate_limit(configured_modules):
    client = MasterDataClient()
    client.settings.use_mock_master_data = False
    client._get = lambda _path: [
        {
            "node_id": "SPBU001",
            "node_type": "SPBU",
            "node_name": "SPBU A",
            "lat": -6.2,
            "lon": 106.8,
            "tw_start": "08:00:00",
            "tw_end": "17:00:00",
            "truck_category": 4,
            "supply_depot_ids": ["DPT001"],
        },
        {
            "node_id": "DPT001",
            "node_type": "DEPOT",
            "node_name": "Depot A",
            "lat": -6.1,
            "lon": 106.7,
            "tw_start": "05:00:00",
            "tw_end": "21:00:00",
            "gate_limit": 3,
        }
    ]

    spbu = client._list_spbu_from_nodes("DPT001")
    depots = client._list_depots_from_nodes()

    assert len(spbu) == 1
    assert spbu[0].truck_category == 4
    assert len(depots) == 1
    assert depots[0].gate_limit == 3
    assert depots[0].time_window_start == "05:00"
    assert depots[0].time_window_end == "21:00"
