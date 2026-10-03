from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from urllib.parse import urlencode
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import build_whatsapp_notifier, get_approval_service
from app.api.rest.v1 import webhooks_whatsapp
from app.core.errors import ValidationError
from app.core.execution.approval_service import ApprovalService
from app.core.notifications.whatsapp import WhatsAppNotifier
from app.db.session import get_session

URL = "http://testserver/api/v1/webhooks/whatsapp"
TOKEN = "twilio-test-token"
SENDER = "+911234567890"


def _settings(**kw: str) -> SimpleNamespace:
    base = {
        "twilio_account_sid": "ACtest",
        "twilio_auth_token": TOKEN,
        "twilio_whatsapp_from": "whatsapp:+14155238886",
        "approval_ttl_minutes": 15,
    }
    base.update(kw)
    return SimpleNamespace(**base)


def _scalars(rows: list[object]) -> MagicMock:
    result = MagicMock()
    result.scalars.return_value.first.return_value = rows[0] if rows else None
    result.scalars.return_value.all.return_value = rows
    return result


@pytest.fixture
def approval_service() -> AsyncMock:
    return AsyncMock(spec=ApprovalService)


@pytest.fixture
def session() -> AsyncMock:
    s = AsyncMock()
    s.execute.return_value = _scalars([SimpleNamespace(user_id=uuid4())])
    return s


@pytest.fixture
def client(monkeypatch, approval_service, session) -> TestClient:
    monkeypatch.setattr(webhooks_whatsapp, "get_settings", lambda: _settings())
    app = FastAPI()
    app.include_router(webhooks_whatsapp.router, prefix="/api/v1/webhooks/whatsapp")
    app.dependency_overrides[get_approval_service] = lambda: approval_service
    app.dependency_overrides[get_session] = lambda: session
    return TestClient(app)


def _post(client: TestClient, params: dict[str, str], *, sign: bool = True, token: str = TOKEN):
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    if sign:
        headers["X-Twilio-Signature"] = webhooks_whatsapp.compute_twilio_signature(
            URL, list(params.items()), token
        )
    return client.post("/api/v1/webhooks/whatsapp", content=urlencode(params), headers=headers)


def test_signature_matches_twilio_reference_algorithm() -> None:
    import base64
    import hashlib
    import hmac

    params = [("To", "whatsapp:+1"), ("Body", "hi"), ("From", "whatsapp:+2")]
    data = URL + "Body" + "hi" + "From" + "whatsapp:+2" + "To" + "whatsapp:+1"
    expected = base64.b64encode(hmac.new(b"k", data.encode(), hashlib.sha1).digest()).decode()
    assert webhooks_whatsapp.compute_twilio_signature(URL, params, "k") == expected


def test_approve_calls_service(client, approval_service, session) -> None:
    aid = uuid4()
    resp = _post(client, {"From": f"whatsapp:{SENDER}", "Body": f"APPROVE {aid}"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/xml")
    assert "<Response><Message>Approved" in resp.text
    approval_service.approve.assert_awaited_once()
    assert approval_service.approve.await_args.args[1] == aid
    approval_service.reject.assert_not_awaited()


def test_reject_calls_service(client, approval_service) -> None:
    aid = uuid4()
    resp = _post(client, {"From": f"whatsapp:{SENDER}", "Body": f"reject {aid}"})
    assert resp.status_code == 200
    assert "Rejected" in resp.text
    approval_service.reject.assert_awaited_once()
    assert approval_service.reject.await_args.args[1] == aid
    approval_service.approve.assert_not_awaited()


def test_bad_signature_rejected(client, approval_service) -> None:
    params = {"From": f"whatsapp:{SENDER}", "Body": f"APPROVE {uuid4()}"}
    assert _post(client, params, token="wrong-token").status_code == 403
    assert _post(client, params, sign=False).status_code == 403
    approval_service.approve.assert_not_awaited()


def test_unset_credentials_rejected(monkeypatch, client, approval_service) -> None:
    monkeypatch.setattr(
        webhooks_whatsapp, "get_settings", lambda: _settings(twilio_auth_token="")
    )
    params = {"From": f"whatsapp:{SENDER}", "Body": f"APPROVE {uuid4()}"}
    assert _post(client, params, token="").status_code == 403
    approval_service.approve.assert_not_awaited()


def test_unknown_sender_rejected(client, approval_service, session) -> None:
    session.execute.return_value = _scalars([])
    resp = _post(client, {"From": "whatsapp:+10000000000", "Body": f"APPROVE {uuid4()}"})
    assert resp.status_code == 403
    approval_service.approve.assert_not_awaited()


@pytest.mark.parametrize("body", ["", "hello", "APPROVE", "APPROVE not-a-uuid", f"CANCEL {uuid4()}"])
def test_malformed_body_gets_help(client, approval_service, body) -> None:
    resp = _post(client, {"From": f"whatsapp:{SENDER}", "Body": body})
    assert resp.status_code == 200
    assert "Reply APPROVE" in resp.text
    approval_service.approve.assert_not_awaited()
    approval_service.reject.assert_not_awaited()


def test_service_error_reported_in_twiml(client, approval_service) -> None:
    approval_service.approve.side_effect = ValidationError("approval_expired")
    resp = _post(client, {"From": f"whatsapp:{SENDER}", "Body": f"APPROVE {uuid4()}"})
    assert resp.status_code == 200
    assert "Failed: validation_error" in resp.text


# ----------------------------------------------------------------------------
# Notifier wiring
# ----------------------------------------------------------------------------


def test_build_notifier_requires_all_credentials() -> None:
    http = MagicMock()
    assert isinstance(build_whatsapp_notifier(_settings(), http), WhatsAppNotifier)
    for missing in ("twilio_account_sid", "twilio_auth_token", "twilio_whatsapp_from"):
        assert build_whatsapp_notifier(_settings(**{missing: ""}), http) is None


def _approval_service(notifier, session) -> ApprovalService:
    return ApprovalService(session=session, execution_service=MagicMock(), whatsapp_notifier=notifier)


async def test_create_sends_whatsapp_to_linked_numbers(monkeypatch) -> None:
    from app.core.execution import approval_service as mod

    monkeypatch.setattr(mod, "get_settings", lambda: _settings())
    notifier = AsyncMock(spec=WhatsAppNotifier)
    session = AsyncMock()
    session.add = MagicMock()
    session.scalar.return_value = uuid4()
    session.execute.return_value = _scalars([SimpleNamespace(destination=SENDER)])
    svc = _approval_service(notifier, session)

    approval = await svc.create(
        uuid4(), None, {"symbol": "RELIANCE", "exchange": "NSE", "side": "BUY", "quantity": "10"}
    )

    notifier.send_approval_request.assert_awaited_once()
    args = notifier.send_approval_request.await_args
    assert args.args[0] == SENDER
    assert args.args[1]["symbol"] == "RELIANCE"
    assert args.args[2] == str(approval.id)


async def test_create_without_notifier_skips_whatsapp(monkeypatch) -> None:
    from app.core.execution import approval_service as mod

    monkeypatch.setattr(mod, "get_settings", lambda: _settings())
    session = AsyncMock()
    session.add = MagicMock()
    svc = _approval_service(None, session)
    await svc.create(uuid4(), None, {"symbol": "X"})
    session.scalar.assert_not_awaited()


async def test_whatsapp_failure_does_not_break_create(monkeypatch) -> None:
    from app.core.execution import approval_service as mod

    monkeypatch.setattr(mod, "get_settings", lambda: _settings())
    notifier = AsyncMock(spec=WhatsAppNotifier)
    notifier.send_approval_request.side_effect = RuntimeError("twilio down")
    session = AsyncMock()
    session.add = MagicMock()
    session.scalar.return_value = uuid4()
    session.execute.return_value = _scalars([SimpleNamespace(destination=SENDER)])
    svc = _approval_service(notifier, session)
    approval = await svc.create(uuid4(), None, {"symbol": "X"})
    assert approval.status == "pending"
