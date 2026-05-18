"""Shared helpers for all gRPC servicers."""

from __future__ import annotations

from datetime import datetime

import grpc
from google.protobuf.timestamp_pb2 import Timestamp

from app.core.auth.service import AuthService
from app.db.session import SessionLocal
from app.infrastructure.logging import get_logger

logger = get_logger(__name__)


def ts_from_dt(dt: datetime | None) -> Timestamp:
    ts = Timestamp()
    if dt is not None:
        ts.FromDatetime(dt)
    return ts


async def require_auth(context: grpc.aio.ServicerContext):
    """Extract and validate Bearer token from gRPC metadata.

    Returns the User object or aborts the call with UNAUTHENTICATED.
    """
    metadata = dict(context.invocation_metadata())
    token = (metadata.get("authorization") or "").removeprefix("Bearer ").strip()
    if not token:
        await context.abort(grpc.StatusCode.UNAUTHENTICATED, "missing authorization header")
        return None  # never reached — abort raises

    async with SessionLocal() as session:
        try:
            svc = AuthService(session=session)
            return await svc.get_user_from_token(token)
        except Exception as exc:
            logger.warning("grpc.auth.token_invalid", error=str(exc))
            await context.abort(grpc.StatusCode.UNAUTHENTICATED, "invalid token")
            return None
