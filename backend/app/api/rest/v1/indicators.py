"""Indicator REST endpoints — Phase K.

GET  /api/v1/indicators            → list all registered indicators
GET  /api/v1/indicators/{name}     → meta for a single indicator
POST /api/v1/indicators/{name}/compute → compute an indicator on provided OHLCV data
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.auth.dependencies import get_current_user
from app.core.indicators import registry
from app.core.indicators.base import IndicatorMeta

router = APIRouter()


class IndicatorMetaDTO(BaseModel):
    name: str
    display_name: str
    category: str
    params: dict[str, Any] = {}
    outputs: list[str] = []
    description: str = ""


class ComputeRequest(BaseModel):
    close: list[float] | None = None
    high: list[float] | None = None
    low: list[float] | None = None
    volume: list[float] | None = None
    open: list[float] | None = None
    params: dict[str, Any] = Field(default_factory=dict)


class ComputeResponse(BaseModel):
    name: str
    outputs: dict[str, list[float | None]]


def _meta_to_dto(m: IndicatorMeta) -> IndicatorMetaDTO:
    return IndicatorMetaDTO(
        name=m.name,
        display_name=m.display_name,
        category=m.category,
        params=m.params,
        outputs=list(m.outputs),
        description=m.description,
    )


@router.get("", summary="List all registered indicators")
async def list_indicators(
    category: str | None = None,
    _user=Depends(get_current_user),
) -> list[IndicatorMetaDTO]:
    return [_meta_to_dto(m) for m in registry.list_indicators(category=category)]


@router.get("/categories", summary="List indicator categories")
async def categories(_user=Depends(get_current_user)) -> list[str]:
    return registry.categories()


@router.get("/{name}", summary="Get indicator metadata")
async def get_indicator(
    name: str,
    _user=Depends(get_current_user),
) -> IndicatorMetaDTO:
    if name not in registry:
        raise HTTPException(status_code=404, detail=f"Indicator '{name}' not found")
    meta = registry.list_indicators()
    for m in meta:
        if m.name == name:
            return _meta_to_dto(m)
    raise HTTPException(status_code=404, detail=f"Indicator '{name}' not found")


@router.post("/{name}/compute", summary="Compute an indicator on provided OHLCV data")
async def compute(
    name: str,
    body: ComputeRequest,
    _user=Depends(get_current_user),
) -> ComputeResponse:
    kwargs: dict[str, Any] = {}
    if body.close is not None:
        kwargs["close"] = body.close
    if body.high is not None:
        kwargs["high"] = body.high
    if body.low is not None:
        kwargs["low"] = body.low
    if body.volume is not None:
        kwargs["volume"] = body.volume
    if body.open is not None:
        kwargs["open"] = body.open
    kwargs.update(body.params)

    try:
        result = registry.compute(name, **kwargs)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Indicator '{name}' not found")
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    return ComputeResponse(name=name, outputs=result.to_dict())
