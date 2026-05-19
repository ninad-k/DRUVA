"""Async email notification service using aiosmtplib + Jinja2 templates."""

from __future__ import annotations

import os
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiosmtplib

from app.infrastructure.logging import get_logger

logger = get_logger(__name__)

# ── DRUVA amber/zinc dark theme palette ──────────────────────────────────────
_BG = "#18181b"          # zinc-900
_SURFACE = "#27272a"     # zinc-800
_BORDER = "#3f3f46"      # zinc-700
_AMBER = "#f59e0b"       # amber-400
_AMBER_DARK = "#b45309"  # amber-700
_TEXT = "#e4e4e7"        # zinc-200
_MUTED = "#a1a1aa"       # zinc-400
_RED = "#ef4444"         # red-500
_GREEN = "#22c55e"       # green-500


def _html_wrapper(title: str, body: str) -> str:
    """Wrap body content in DRUVA's dark-amber HTML shell."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{title}</title>
</head>
<body style="margin:0;padding:0;background:{_BG};font-family:ui-monospace,'Courier New',monospace;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:{_BG};padding:32px 0;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0"
             style="background:{_SURFACE};border:1px solid {_BORDER};border-radius:8px;overflow:hidden;">
        <!-- Header -->
        <tr>
          <td style="background:{_AMBER_DARK};padding:20px 32px;">
            <span style="font-size:20px;font-weight:700;color:#fff;letter-spacing:2px;">DRUVA</span>
            <span style="font-size:13px;color:#fef3c7;margin-left:12px;">{title}</span>
          </td>
        </tr>
        <!-- Body -->
        <tr>
          <td style="padding:32px;color:{_TEXT};font-size:14px;line-height:1.7;">
            {body}
          </td>
        </tr>
        <!-- Footer -->
        <tr>
          <td style="padding:16px 32px;border-top:1px solid {_BORDER};">
            <span style="font-size:12px;color:{_MUTED};">
              Automated alert from DRUVA Algo-Trading Platform. Do not reply.
            </span>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def _kv_row(label: str, value: str) -> str:
    return (
        f'<tr>'
        f'<td style="padding:6px 0;color:{_MUTED};width:180px;">{label}</td>'
        f'<td style="padding:6px 0;color:{_TEXT};font-weight:600;">{value}</td>'
        f'</tr>'
    )


def _action_button(label: str, url: str, color: str) -> str:
    return (
        f'<a href="{url}" style="display:inline-block;padding:12px 28px;'
        f'background:{color};color:#fff;text-decoration:none;border-radius:6px;'
        f'font-weight:700;font-size:14px;margin:4px;">{label}</a>'
    )


# ── Config ───────────────────────────────────────────────────────────────────

@dataclass
class EmailConfig:
    """SMTP connection parameters."""

    smtp_host: str
    smtp_port: int
    username: str
    password: str
    from_address: str
    use_tls: bool = True


# ── Notifier ─────────────────────────────────────────────────────────────────

class EmailNotifier:
    """Async email sender for DRUVA trading events.

    All methods are no-ops if construction used an empty host.
    """

    def __init__(self, config: EmailConfig) -> None:
        self._config = config
        self._enabled = bool(config.smtp_host)
        if not self._enabled:
            logger.info("email.disabled", reason="no_smtp_host")

    async def send(
        self,
        to: list[str],
        subject: str,
        body_html: str,
    ) -> None:
        """Send a raw HTML email to one or more recipients."""
        if not self._enabled:
            return

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self._config.from_address
        msg["To"] = ", ".join(to)
        msg.attach(MIMEText(body_html, "html", "utf-8"))

        try:
            await aiosmtplib.send(
                msg,
                hostname=self._config.smtp_host,
                port=self._config.smtp_port,
                username=self._config.username,
                password=self._config.password,
                use_tls=self._config.use_tls,
            )
            logger.info("email.sent", to=to, subject=subject)
        except Exception as exc:  # noqa: BLE001
            logger.error("email.send_failed", error=str(exc), to=to, subject=subject)

    async def send_order_fill(
        self,
        to: list[str],
        order_details: dict,
    ) -> None:
        """Send a formatted order-fill confirmation email."""
        side = order_details.get("side", "")
        side_color = _GREEN if side == "BUY" else _RED
        rows = "".join([
            _kv_row("Order ID", str(order_details.get("id", "—"))),
            _kv_row("Symbol", str(order_details.get("symbol", "—"))),
            _kv_row("Exchange", str(order_details.get("exchange", "—"))),
            _kv_row("Side", f'<span style="color:{side_color}">{side}</span>'),
            _kv_row("Quantity", str(order_details.get("quantity", "—"))),
            _kv_row("Price", str(order_details.get("price", "MKT"))),
            _kv_row("Status", str(order_details.get("status", "—"))),
        ])
        body = (
            f'<p style="color:{_AMBER};font-weight:700;margin-top:0;">Order Filled</p>'
            f'<table cellpadding="0" cellspacing="0" style="width:100%;">{rows}</table>'
        )
        html = _html_wrapper("Order Fill", body)
        await self.send(to, f"[DRUVA] Order Filled — {order_details.get('symbol')}", html)

    async def send_approval_request(
        self,
        to: list[str],
        signal: dict,
        approve_url: str,
        reject_url: str,
    ) -> None:
        """Send an action email with Approve/Reject buttons."""
        rows = "".join([
            _kv_row("Symbol", str(signal.get("symbol", "—"))),
            _kv_row("Side", str(signal.get("side", "—"))),
            _kv_row("Quantity", str(signal.get("quantity", "—"))),
            _kv_row("Strategy", str(signal.get("strategy_id", "—"))),
            _kv_row("Expires", str(signal.get("expires_at", "—"))),
        ])
        approve_btn = _action_button("✅ Approve", approve_url, _GREEN)
        reject_btn = _action_button("❌ Reject", reject_url, _RED)
        body = (
            f'<p style="color:{_AMBER};font-weight:700;margin-top:0;">Approval Required</p>'
            f'<p style="color:{_MUTED};">A strategy has requested order placement. '
            f'Please review and act within the expiry window.</p>'
            f'<table cellpadding="0" cellspacing="0" style="width:100%;margin-bottom:24px;">'
            f'{rows}</table>'
            f'<div style="text-align:center;padding:8px 0;">{approve_btn}{reject_btn}</div>'
        )
        html = _html_wrapper("Approval Required", body)
        await self.send(
            to,
            f"[DRUVA] Action Required — Approve {signal.get('symbol')} {signal.get('side')}",
            html,
        )

    async def send_circuit_breaker_alert(
        self,
        to: list[str],
        trigger: str,
        portfolio_value: float,
        loss_pct: float,
    ) -> None:
        """Send an urgent red-alert circuit breaker notification."""
        rows = "".join([
            _kv_row("Trigger", trigger),
            _kv_row("Portfolio Value", f"₹{portfolio_value:,.2f}"),
            _kv_row("Loss %", f'<span style="color:{_RED};">{loss_pct:.2f}%</span>'),
        ])
        body = (
            f'<div style="background:{_RED};padding:12px 16px;border-radius:6px;'
            f'margin-bottom:20px;font-weight:700;font-size:16px;color:#fff;">'
            f'⚠ CIRCUIT BREAKER TRIGGERED</div>'
            f'<p style="color:{_TEXT};">All trading has been halted automatically '
            f'due to drawdown limits being breached.</p>'
            f'<table cellpadding="0" cellspacing="0" style="width:100%;">{rows}</table>'
            f'<p style="color:{_MUTED};margin-top:20px;font-size:12px;">'
            f'Manual intervention required. Check the DRUVA lock file before resuming.</p>'
        )
        html = _html_wrapper("Circuit Breaker Alert", body)
        await self.send(to, "[DRUVA] 🚨 CIRCUIT BREAKER TRIGGERED", html)

    async def send_regime_change(
        self,
        to: list[str],
        old_regime: str,
        new_regime: str,
        confidence: float,
        allocation_pct: float,
    ) -> None:
        """Notify on regime change with new allocation details."""
        rows = "".join([
            _kv_row("Previous Regime", old_regime),
            _kv_row("New Regime", f'<span style="color:{_AMBER};">{new_regime}</span>'),
            _kv_row("Confidence", f"{confidence:.1%}"),
            _kv_row("Target Allocation", f"{allocation_pct:.1f}%"),
        ])
        body = (
            f'<p style="color:{_AMBER};font-weight:700;margin-top:0;">Market Regime Changed</p>'
            f'<p style="color:{_TEXT};">The HMM regime detector has identified a regime '
            f'transition. Portfolio allocation will be adjusted accordingly.</p>'
            f'<table cellpadding="0" cellspacing="0" style="width:100%;">{rows}</table>'
        )
        html = _html_wrapper("Regime Change", body)
        await self.send(
            to,
            f"[DRUVA] Regime Change: {old_regime} → {new_regime} ({confidence:.0%} conf.)",
            html,
        )


# ── Factory ──────────────────────────────────────────────────────────────────

def get_email_notifier() -> EmailNotifier | None:
    """Build an EmailNotifier from environment variables.

    Reads: DRUVA_SMTP_HOST, DRUVA_SMTP_PORT, DRUVA_SMTP_USER,
           DRUVA_SMTP_PASS, DRUVA_ALERT_EMAIL.

    Returns None if SMTP is not configured (graceful degradation).
    """
    host = os.environ.get("DRUVA_SMTP_HOST", "")
    if not host:
        logger.info("email.notifier_disabled", reason="DRUVA_SMTP_HOST not set")
        return None

    config = EmailConfig(
        smtp_host=host,
        smtp_port=int(os.environ.get("DRUVA_SMTP_PORT", "587")),
        username=os.environ.get("DRUVA_SMTP_USER", ""),
        password=os.environ.get("DRUVA_SMTP_PASS", ""),
        from_address=os.environ.get("DRUVA_SMTP_FROM", "noreply@druva.local"),
        use_tls=os.environ.get("DRUVA_SMTP_USE_TLS", "true").lower() != "false",
    )
    return EmailNotifier(config)
