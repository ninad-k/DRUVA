"""gRPC AuthService servicer implementation."""

from __future__ import annotations

import grpc
from google.protobuf.timestamp_pb2 import Timestamp

from app.api.grpc._generated.dhruva.v1 import auth_pb2, auth_pb2_grpc
from app.core.auth.service import AuthService
from app.db.session import SessionLocal
from app.infrastructure.logging import get_logger

logger = get_logger(__name__)


def _ts_from_datetime(dt) -> Timestamp:
    ts = Timestamp()
    if dt is not None:
        ts.FromDatetime(dt)
    return ts


class AuthServicer(auth_pb2_grpc.AuthServiceServicer):
    """Implements dhruva.v1.AuthService over gRPC."""

    async def Login(self, request: auth_pb2.LoginRequest, context: grpc.aio.ServicerContext) -> auth_pb2.TokenPair:
        async with SessionLocal() as session:
            try:
                svc = AuthService(session=session)
                token_pair = await svc.login(email=request.email, password=request.password)
                return auth_pb2.TokenPair(
                    access_token=token_pair["access_token"],
                    refresh_token=token_pair.get("refresh_token", ""),
                    expires_in=token_pair.get("expires_in", 3600),
                    token_type="Bearer",
                )
            except Exception as exc:
                logger.warning("grpc.auth.login_failed", error=str(exc))
                await context.abort(grpc.StatusCode.UNAUTHENTICATED, str(exc))

    async def Refresh(self, request: auth_pb2.RefreshRequest, context: grpc.aio.ServicerContext) -> auth_pb2.TokenPair:
        async with SessionLocal() as session:
            try:
                svc = AuthService(session=session)
                token_pair = await svc.refresh(refresh_token=request.refresh_token)
                return auth_pb2.TokenPair(
                    access_token=token_pair["access_token"],
                    refresh_token=token_pair.get("refresh_token", ""),
                    expires_in=token_pair.get("expires_in", 3600),
                    token_type="Bearer",
                )
            except Exception as exc:
                logger.warning("grpc.auth.refresh_failed", error=str(exc))
                await context.abort(grpc.StatusCode.UNAUTHENTICATED, str(exc))

    async def Logout(self, request: auth_pb2.LogoutRequest, context: grpc.aio.ServicerContext) -> auth_pb2.Empty:
        # JWT-based: logout is client-side. Nothing to revoke server-side yet.
        return auth_pb2.Empty()

    async def Me(self, request: auth_pb2.MeRequest, context: grpc.aio.ServicerContext) -> auth_pb2.User:
        # Extract user from gRPC metadata (Authorization: Bearer <token>)
        metadata = dict(context.invocation_metadata())
        token = (metadata.get("authorization") or "").removeprefix("Bearer ").strip()
        if not token:
            await context.abort(grpc.StatusCode.UNAUTHENTICATED, "missing authorization header")

        async with SessionLocal() as session:
            try:
                svc = AuthService(session=session)
                user = await svc.get_user_from_token(token)
                return auth_pb2.User(
                    id=str(user.id),
                    email=user.email,
                    display_name=getattr(user, "display_name", user.email),
                    created_at=_ts_from_datetime(getattr(user, "created_at", None)),
                )
            except Exception as exc:
                logger.warning("grpc.auth.me_failed", error=str(exc))
                await context.abort(grpc.StatusCode.UNAUTHENTICATED, str(exc))
