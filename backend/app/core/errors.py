from __future__ import annotations


class DhruvaError(Exception):
    http_status = 500
    code = "internal_error"


class NotFoundError(DhruvaError):
    http_status = 404
    code = "not_found"


class ValidationError(DhruvaError):
    http_status = 422
    code = "validation_error"


class UnauthorizedError(DhruvaError):
    http_status = 401
    code = "unauthorized"


class ForbiddenError(DhruvaError):
    http_status = 403
    code = "forbidden"


class RiskRejectedError(DhruvaError):
    http_status = 422
    code = "risk_rejected"


class BrokerError(DhruvaError):
    http_status = 502
    code = "broker_error"
