"""Disruption state endpoint. Returns current passage disruptions.

The dim_disruptions table does not exist yet (Phase 6). Until then, this returns an empty list.
"""

from fastapi import APIRouter

from shockt_api.schemas import DisruptionInfo

router = APIRouter()


@router.get("/disruptions")
def get_disruptions() -> list[DisruptionInfo]:
    return []
