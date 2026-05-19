"""WhatsApp notification channel via Twilio API.

Requires:
  TWILIO_ACCOUNT_SID   — Twilio account SID
  TWILIO_AUTH_TOKEN    — Twilio auth token
  TWILIO_WHATSAPP_FROM — sender number, format: "whatsapp:+14155238886"

All methods are no-ops when credentials are not configured.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from app.infrastructure.logging import get_logger

logger = get_logger(__name__)

TWILIO_MESSAGES_URL = "https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"


class WhatsAppNotifier:
    """Outbound-only WhatsApp client via Twilio.

    If any credential is missing the instance is created but all methods
    become no-ops, so callers never need to guard against ``None``.
    """

    def __init__(
        self,
        account_sid: str,
        auth_token: str,
        from_number: str,
        http: httpx.AsyncClient,
    ) -> None:
        self._sid = account_sid
        self._token = auth_token
        # Normalise: strip leading "whatsapp:" if caller already included it,
        # then re-add so the stored value is always the raw E.164 number.
        self._from = from_number.removeprefix("whatsapp:")
        self._http = http
        self._enabled = bool(account_sid and auth_token and from_number)
        if not self._enabled:
            logger.info("whatsapp.disabled", reason="missing_twilio_credentials")

    # ------------------------------------------------------------------
    # Low-level send
    # ------------------------------------------------------------------

    async def send_text(self, to: str, text: str) -> bool:
        """Send a plain-text WhatsApp message.

        Parameters
        ----------
        to:
            Recipient phone number in E.164 format (e.g. ``"+919876543210"``).
            The ``whatsapp:`` prefix is added automatically.
        text:
            Message body (plain text; max ~1 600 chars for WhatsApp).

        Returns
        -------
        bool
            ``True`` on success, ``False`` if the message was not sent.
        """
        if not self._enabled:
            return False

        to_wa = f"whatsapp:{to.removeprefix('whatsapp:')}"
        from_wa = f"whatsapp:{self._from}"
        url = TWILIO_MESSAGES_URL.format(sid=self._sid)

        try:
            resp = await self._http.post(
                url,
                data={"From": from_wa, "To": to_wa, "Body": text},
                auth=(self._sid, self._token),
                timeout=10.0,
            )
            if resp.status_code >= 400:
                logger.warning(
                    "whatsapp.send_failed",
                    to=to_wa,
                    status=resp.status_code,
                    body=resp.text[:300],
                )
                return False
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("whatsapp.send_error", to=to_wa, error=str(exc))
            return False

    # ------------------------------------------------------------------
    # High-level helpers
    # ------------------------------------------------------------------

    async def send_approval_request(
        self,
        to: str,
        order_details: dict[str, Any],
        approval_id: str,
        ttl_minutes: int = 15,
    ) -> bool:
        """Send an order approval request requiring a reply to approve/reject.

        The message instructs the recipient to reply:
          ``APPROVE <approval_id>``  or  ``REJECT <approval_id>``

        Parameters
        ----------
        to:
            Recipient phone number in E.164 format.
        order_details:
            Dict with order info, e.g. ``{"symbol": "RELIANCE", "side": "BUY",
            "quantity": 10, "price": 2850.0}``.
        approval_id:
            Unique approval request UUID string.
        ttl_minutes:
            How many minutes the approval link remains valid (informational).
        """
        symbol   = order_details.get("symbol", "N/A")
        side     = order_details.get("side", "N/A")
        quantity = order_details.get("quantity", "N/A")
        price    = order_details.get("price", "MARKET")
        exchange = order_details.get("exchange", "")

        instrument = f"{symbol} ({exchange})" if exchange else symbol

        text = (
            "DRUVA — Approval Required\n"
            "\n"
            f"Instrument : {instrument}\n"
            f"Side       : {side}\n"
            f"Quantity   : {quantity}\n"
            f"Price      : {price}\n"
            f"Approval ID: {approval_id}\n"
            f"Expires in : {ttl_minutes} minutes\n"
            "\n"
            f"Reply  APPROVE {approval_id}  to execute.\n"
            f"Reply  REJECT {approval_id}  to cancel."
        )
        return await self.send_text(to, text)

    async def send_circuit_breaker_alert(
        self,
        to: str,
        trigger: str,
        loss_pct: float,
    ) -> bool:
        """Send an urgent circuit-breaker triggered alert.

        Parameters
        ----------
        to:
            Recipient phone number in E.164 format.
        trigger:
            Human-readable description of the trigger condition.
        loss_pct:
            Portfolio drawdown percentage that caused the circuit breaker.
        """
        text = (
            "DRUVA — CIRCUIT BREAKER TRIGGERED\n"
            "\n"
            f"Trigger : {trigger}\n"
            f"Loss    : {loss_pct:.2f}%\n"
            "\n"
            "All new order generation is PAUSED. "
            "Log in to the DRUVA dashboard to review and reset."
        )
        return await self.send_text(to, text)

    async def send_regime_change(
        self,
        to: str,
        old_regime: str,
        new_regime: str,
        confidence: float,
        allocation_pct: float,
    ) -> bool:
        """Notify a user that the market-regime model has changed state.

        Parameters
        ----------
        to:
            Recipient phone number in E.164 format.
        old_regime:
            Previous regime label, e.g. ``"Bear"``.
        new_regime:
            New regime label, e.g. ``"Neutral"``.
        confidence:
            Model confidence in the new regime (0.0 – 1.0).
        allocation_pct:
            Target equity allocation percentage for the new regime.
        """
        text = (
            "DRUVA — Market Regime Change\n"
            "\n"
            f"Previous : {old_regime}\n"
            f"Current  : {new_regime}\n"
            f"Confidence: {confidence * 100:.1f}%\n"
            f"Target allocation: {allocation_pct:.0f}% equities\n"
            "\n"
            "Portfolio rebalancing will run at the next scheduled window."
        )
        return await self.send_text(to, text)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def get_whatsapp_notifier(http: httpx.AsyncClient) -> WhatsAppNotifier | None:
    """Construct a :class:`WhatsAppNotifier` from environment variables.

    Returns ``None`` if any of the three required Twilio credentials are
    absent so callers can easily skip WhatsApp setup in dev environments.
    """
    sid   = os.environ.get("TWILIO_ACCOUNT_SID", "")
    token = os.environ.get("TWILIO_AUTH_TOKEN", "")
    from_ = os.environ.get("TWILIO_WHATSAPP_FROM", "")

    if not (sid and token and from_):
        logger.info(
            "whatsapp.notifier_unavailable",
            reason="missing_env_vars",
            missing=[
                v
                for v, val in [
                    ("TWILIO_ACCOUNT_SID", sid),
                    ("TWILIO_AUTH_TOKEN", token),
                    ("TWILIO_WHATSAPP_FROM", from_),
                ]
                if not val
            ],
        )
        return None

    return WhatsAppNotifier(
        account_sid=sid,
        auth_token=token,
        from_number=from_,
        http=http,
    )
