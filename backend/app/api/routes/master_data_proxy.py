"""Proxy routes for external master data."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Query

from app.models import schemas
from app.services.master_data_client import MasterDataClient
from app.services.truck_master_data_client import TruckMasterDataClient

router = APIRouter(prefix="/api/v1/master-data", tags=["master-data"])


@router.get("/spbu", response_model=schemas.MasterDataListResponse)
def list_spbu_proxy(depot_id: str | None = Query(default=None)) -> schemas.MasterDataListResponse:
    """Return SPBU master data."""

    client = MasterDataClient()
    try:
        items = [item.model_dump() for item in client.list_spbu(depot_id=depot_id)]
        return schemas.MasterDataListResponse(items=items)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/depots", response_model=schemas.MasterDataListResponse)
def list_depots_proxy() -> schemas.MasterDataListResponse:
    """Return depot master data."""

    client = MasterDataClient()
    try:
        items = [item.model_dump() for item in client.list_depots()]
        return schemas.MasterDataListResponse(items=items)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/trucks", response_model=schemas.MasterDataListResponse)
def list_trucks_proxy(
    depot_id: str = Query(...),
    dispatch_date: date | None = Query(default=None),
) -> schemas.MasterDataListResponse:
    """Return available trucks for a selected depot."""

    client = TruckMasterDataClient()
    try:
        items = [item.model_dump() for item in client.list_available_trucks(depot_id, dispatch_date=dispatch_date)]
        return schemas.MasterDataListResponse(items=items)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
