"""Async gRPC server — runs alongside the FastAPI/Uvicorn HTTP server.

Start via ``asyncio.create_task(serve())`` inside the FastAPI lifespan so
both servers share the same event loop. The gRPC server listens on the port
configured by ``settings.grpc_port`` (default 50051).

Envoy (deploy/docker/envoy.yaml) proxies gRPC-Web requests from the React
frontend to this server, translating the browser-compatible Connect protocol
to standard gRPC.
"""

from __future__ import annotations

import asyncio
import sys

import grpc
from grpc import aio as grpc_aio
from grpc_reflection.v1alpha import reflection

from app.api.grpc._generated.dhruva.v1 import (
    auth_pb2,
    orders_pb2,
    portfolio_pb2,
    reports_pb2,
    scanner_pb2,
    strategies_pb2,
)
from app.api.grpc._generated.dhruva.v1 import (
    auth_pb2_grpc,
    orders_pb2_grpc,
    portfolio_pb2_grpc,
    reports_pb2_grpc,
    scanner_pb2_grpc,
    strategies_pb2_grpc,
)
from app.api.grpc.servicers import (
    AuthServicer,
    OrderServicer,
    PortfolioServicer,
    ReportServicer,
    ScannerServicer,
    StrategyServicer,
)
from app.config import get_settings
from app.infrastructure.logging import get_logger

logger = get_logger(__name__)


async def serve(stop_event: asyncio.Event | None = None) -> None:
    """Start the async gRPC server and wait until *stop_event* is set."""
    settings = get_settings()
    port = getattr(settings, "grpc_port", 50051)

    server = grpc_aio.server(
        options=[
            ("grpc.max_send_message_length", 50 * 1024 * 1024),   # 50 MB
            ("grpc.max_receive_message_length", 50 * 1024 * 1024),
            ("grpc.keepalive_time_ms", 30_000),
            ("grpc.keepalive_timeout_ms", 10_000),
        ]
    )

    # Register all servicers
    auth_pb2_grpc.add_AuthServiceServicer_to_server(AuthServicer(), server)
    orders_pb2_grpc.add_OrderServiceServicer_to_server(OrderServicer(), server)
    portfolio_pb2_grpc.add_PortfolioServiceServicer_to_server(PortfolioServicer(), server)
    reports_pb2_grpc.add_ReportServiceServicer_to_server(ReportServicer(), server)
    scanner_pb2_grpc.add_ScannerServiceServicer_to_server(ScannerServicer(), server)
    strategies_pb2_grpc.add_StrategyServiceServicer_to_server(StrategyServicer(), server)

    # Enable gRPC server reflection (lets grpcurl and Postman discover services)
    service_names = [
        auth_pb2.DESCRIPTOR.services_by_name["AuthService"].full_name,
        orders_pb2.DESCRIPTOR.services_by_name["OrderService"].full_name,
        portfolio_pb2.DESCRIPTOR.services_by_name["PortfolioService"].full_name,
        reports_pb2.DESCRIPTOR.services_by_name["ReportService"].full_name,
        scanner_pb2.DESCRIPTOR.services_by_name["ScannerService"].full_name,
        strategies_pb2.DESCRIPTOR.services_by_name["StrategyService"].full_name,
        reflection.SERVICE_NAME,
    ]
    reflection.enable_server_reflection(service_names, server)

    listen_addr = f"[::]:{port}"
    server.add_insecure_port(listen_addr)

    await server.start()
    logger.info("grpc.server.started", port=port)

    if stop_event is not None:
        await stop_event.wait()
    else:
        await server.wait_for_termination()

    await server.stop(grace=5)
    logger.info("grpc.server.stopped")
