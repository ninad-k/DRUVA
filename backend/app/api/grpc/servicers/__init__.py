"""gRPC servicers — one class per proto service definition."""

from app.api.grpc.servicers.auth import AuthServicer
from app.api.grpc.servicers.orders import OrderServicer
from app.api.grpc.servicers.portfolio import PortfolioServicer
from app.api.grpc.servicers.reports import ReportServicer
from app.api.grpc.servicers.scanner import ScannerServicer
from app.api.grpc.servicers.strategies import StrategyServicer

__all__ = [
    "AuthServicer",
    "OrderServicer",
    "PortfolioServicer",
    "ReportServicer",
    "ScannerServicer",
    "StrategyServicer",
]
