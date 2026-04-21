"""AI Advisor REST endpoints.

All endpoints are user-scoped — a user's watchlist, LLM config, runs, and
scores are isolated by ``user_id`` from the JWT.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.advisor.allocator import Candidate, allocate
from app.core.advisor.service import AdvisorService, fallback_llm_from_settings
from app.core.auth.dependencies import get_current_user
from app.db.models.advisor import (
    AdvisorLLMConfig,
    AdvisorLLMProvider,
    AdvisorRun,
    AdvisorScore,
    AdvisorWatchlist,
    MacroRegime,
)
from app.db.models.user import User
from app.db.session import get_session
from app.infrastructure.http import get_http_client
from app.schemas.advisor import (
    AllocationOut,
    LLMConfigIn,
    LLMConfigOut,
    RunOut,
    RunTriggerIn,
    ScoreOut,
    WatchlistIn,
    WatchlistOut,
)

router = APIRouter()


def _llm_out(cfg: AdvisorLLMConfig) -> LLMConfigOut:
    return LLMConfigOut(
        id=cfg.id,
        provider=cfg.provider.value if hasattr(cfg.provider, "value") else str(cfg.provider),
        model=cfg.model,
        base_url=cfg.base_url,
        has_api_key=bool(cfg.api_key_encrypted),
        temperature=float(cfg.temperature),
        max_tokens=cfg.max_tokens,
        is_enabled=cfg.is_enabled,
        updated_at=cfg.updated_at,
    )


# ---------- LLM config ---------------------------------------------------
@router.get("/config", response_model=LLMConfigOut | None)
async def get_config(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> LLMConfigOut | None:
    cfg = (
        await session.execute(
            select(AdvisorLLMConfig).where(AdvisorLLMConfig.user_id == user.id)
        )
    ).scalar_one_or_none()
    if cfg is None:
        return None
    return _llm_out(cfg)


@router.put("/config", response_model=LLMConfigOut)
async def upsert_config(
    payload: LLMConfigIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> LLMConfigOut:
    cfg = (
        await session.execute(
            select(AdvisorLLMConfig).where(AdvisorLLMConfig.user_id == user.id)
        )
    ).scalar_one_or_none()
    if cfg is None:
        cfg = AdvisorLLMConfig(user_id=user.id, provider=AdvisorLLMProvider(payload.provider))
        session.add(cfg)
    cfg.provider = AdvisorLLMProvider(payload.provider)
    cfg.model = payload.model
    cfg.base_url = payload.base_url or cfg.base_url
    if payload.api_key is not None:
        # TODO: encrypt via app.infrastructure.encryption when plumbed.
        cfg.api_key_encrypted = payload.api_key or None
    cfg.temperature = payload.temperature  # type: ignore[assignment]
    cfg.max_tokens = payload.max_tokens
    cfg.is_enabled = payload.is_enabled
    await session.commit()
    await session.refresh(cfg)
    return _llm_out(cfg)


# ---------- Watchlist ----------------------------------------------------
@router.get("/watchlist", response_model=list[WatchlistOut])
async def list_watchlist(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[WatchlistOut]:
    rows = (
        await session.execute(
            select(AdvisorWatchlist)
            .where(AdvisorWatchlist.user_id == user.id)
            .order_by(AdvisorWatchlist.symbol.asc())
        )
    ).scalars().all()
    return [
        WatchlistOut(
            id=r.id, symbol=r.symbol, exchange=r.exchange,
            sector=r.sector, notes=r.notes, is_active=r.is_active,
        )
        for r in rows
    ]


@router.post("/watchlist", response_model=WatchlistOut, status_code=201)
async def add_watchlist(
    payload: WatchlistIn,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> WatchlistOut:
    settings = get_settings()
    http = None
    async for c in get_http_client():
        http = c
        break
    svc = AdvisorService(
        session=session, http=http,  # type: ignore[arg-type]
        fallback_llm=fallback_llm_from_settings(settings),
    )
    row = await svc.add_to_watchlist(
        user_id=user.id, symbol=payload.symbol, exchange=payload.exchange,
        sector=payload.sector, notes=payload.notes,
    )
    return WatchlistOut(
        id=row.id, symbol=row.symbol, exchange=row.exchange,
        sector=row.sector, notes=row.notes, is_active=row.is_active,
    )


@router.delete("/watchlist/{watchlist_id}", status_code=204)
async def delete_watchlist(
    watchlist_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    settings = get_settings()
    http = None
    async for c in get_http_client():
        http = c
        break
    svc = AdvisorService(
        session=session, http=http,  # type: ignore[arg-type]
        fallback_llm=fallback_llm_from_settings(settings),
    )
    await svc.remove_from_watchlist(user_id=user.id, watchlist_id=watchlist_id)


# ---------- Runs + Scores -----------------------------------------------
@router.post("/runs", status_code=201)
async def trigger_run(
    payload: RunTriggerIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    settings = get_settings()
    http = None
    async for c in get_http_client():
        http = c
        break
    if http is None:
        raise HTTPException(500, "http_client_unavailable")
    svc = AdvisorService(
        session=session, http=http,
        fallback_llm=fallback_llm_from_settings(settings),
        capital_inr=payload.capital_inr,
        max_positions=payload.max_positions,
        per_position_sl_pct=payload.stop_loss_pct,
    )
    result = await svc.run(user_id=user.id)
    return {
        "run_id": str(result.run_id),
        "regime": result.regime.value,
        "scored": result.scored,
        "top_picks": result.top_picks,
    }


@router.get("/runs", response_model=list[RunOut])
async def list_runs(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    limit: int = 20,
) -> list[RunOut]:
    rows = (
        await session.execute(
            select(AdvisorRun)
            .where(AdvisorRun.user_id == user.id)
            .order_by(desc(AdvisorRun.ran_at))
            .limit(limit)
        )
    ).scalars().all()
    return [
        RunOut(
            id=r.id, ran_at=r.ran_at, macro_regime=r.macro_regime.value,
            nifty_roc=float(r.nifty_roc) if r.nifty_roc is not None else None,
            smallcap_roc=float(r.smallcap_roc) if r.smallcap_roc is not None else None,
            llm_provider=r.llm_provider, llm_model=r.llm_model,
            symbols_scanned=r.symbols_scanned,
        )
        for r in rows
    ]


@router.get("/runs/latest/scores", response_model=list[ScoreOut])
async def latest_scores(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[ScoreOut]:
    latest_run = (
        await session.execute(
            select(AdvisorRun)
            .where(AdvisorRun.user_id == user.id)
            .order_by(desc(AdvisorRun.ran_at))
            .limit(1)
        )
    ).scalar_one_or_none()
    if latest_run is None:
        return []
    rows = (
        await session.execute(
            select(AdvisorScore)
            .where(AdvisorScore.run_id == latest_run.id)
            .order_by(desc(AdvisorScore.composite_score))
        )
    ).scalars().all()
    return [_score_to_out(r) for r in rows]


@router.get("/runs/{run_id}/scores", response_model=list[ScoreOut])
async def run_scores(
    run_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[ScoreOut]:
    rows = (
        await session.execute(
            select(AdvisorScore)
            .where(AdvisorScore.run_id == run_id, AdvisorScore.user_id == user.id)
            .order_by(desc(AdvisorScore.composite_score))
        )
    ).scalars().all()
    return [_score_to_out(r) for r in rows]


# ---------- On-demand allocation (stateless) ----------------------------
@router.post("/allocate", response_model=list[AllocationOut])
async def allocate_endpoint(
    capital_inr: float,
    max_positions: int = 8,
    stop_loss_pct: float = 10.0,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[AllocationOut]:
    latest_run = (
        await session.execute(
            select(AdvisorRun)
            .where(AdvisorRun.user_id == user.id)
            .order_by(desc(AdvisorRun.ran_at))
            .limit(1)
        )
    ).scalar_one_or_none()
    if latest_run is None:
        raise HTTPException(404, "no_advisor_run_found")
    scores = (
        await session.execute(
            select(AdvisorScore).where(AdvisorScore.run_id == latest_run.id)
        )
    ).scalars().all()
    candidates = [
        Candidate(
            symbol=s.symbol, exchange=s.exchange,
            composite_score=float(s.composite_score),
            tier=s.multibagger_tier or "C",
            last_price=float(s.last_price) if s.last_price is not None else 0.0,
        )
        for s in scores
        if s.last_price is not None
    ]
    allocs = allocate(
        candidates,
        capital_inr=capital_inr,
        regime=latest_run.macro_regime,
        max_positions=max_positions,
        stop_loss_pct=stop_loss_pct,
    )
    return [
        AllocationOut(
            symbol=a.symbol, exchange=a.exchange, tier=a.tier,
            suggested_pct=a.suggested_pct, suggested_inr=a.suggested_inr,
            qty=a.qty, stop_loss=a.stop_loss, target_price=a.target_price,
        )
        for a in allocs
    ]


def _score_to_out(r: AdvisorScore) -> ScoreOut:
    return ScoreOut(
        symbol=r.symbol, exchange=r.exchange,
        last_price=float(r.last_price) if r.last_price is not None else None,
        composite_score=float(r.composite_score),
        fundamental_score=float(r.fundamental_score),
        technical_score=float(r.technical_score),
        momentum_score=float(r.momentum_score),
        llm_score=float(r.llm_score) if r.llm_score is not None else None,
        multibagger_tier=r.multibagger_tier,
        stop_loss=float(r.stop_loss) if r.stop_loss is not None else None,
        target_price=float(r.target_price) if r.target_price is not None else None,
        suggested_allocation_pct=float(r.suggested_allocation_pct),
        rationale=r.rationale,
        features=r.features or {},
    )
