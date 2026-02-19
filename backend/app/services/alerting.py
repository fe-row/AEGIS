"""
Alerting Service — PagerDuty and OpsGenie integration for critical incidents.
Auto-triggered on circuit breaker trips, trust score drops, and budget exhaustion.
"""
import httpx
from typing import Optional

from app.config import get_settings
from app.logging_config import get_logger

logger = get_logger("alerting")
settings = get_settings()


class AlertSeverity:
    CRITICAL = "critical"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class AlertService:
    """Sends incident alerts to PagerDuty or OpsGenie."""

    @staticmethod
    async def send_alert(
        summary: str,
        severity: str = AlertSeverity.ERROR,
        source: str = "aegis-backend",
        details: Optional[dict] = None,
    ):
        """Route alert to configured provider(s)."""
        provider = settings.ALERT_PROVIDER.lower() if settings.ALERT_PROVIDER else ""

        if "pagerduty" in provider and settings.PAGERDUTY_ROUTING_KEY:
            await AlertService._send_pagerduty(summary, severity, source, details)

        if "opsgenie" in provider and settings.OPSGENIE_API_KEY:
            await AlertService._send_opsgenie(summary, severity, source, details)

        if not provider:
            logger.warning("alert_no_provider", summary=summary)

    @staticmethod
    async def send_critical(summary: str, source: str = "aegis-backend", details: Optional[dict] = None):
        await AlertService.send_alert(summary, AlertSeverity.CRITICAL, source, details)

    @staticmethod
    async def send_warning(summary: str, source: str = "aegis-backend", details: Optional[dict] = None):
        await AlertService.send_alert(summary, AlertSeverity.WARNING, source, details)

    # ── PagerDuty Events API v2 ──

    @staticmethod
    async def _send_pagerduty(
        summary: str,
        severity: str,
        source: str,
        details: Optional[dict] = None,
    ):
        """Send alert via PagerDuty Events API v2."""
        payload = {
            "routing_key": settings.PAGERDUTY_ROUTING_KEY,
            "event_action": "trigger",
            "payload": {
                "summary": f"[AEGIS] {summary}",
                "severity": severity,
                "source": source,
                "component": "aegis-platform",
                "custom_details": details or {},
            },
        }

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    "https://events.pagerduty.com/v2/enqueue",
                    json=payload,
                )
                if resp.status_code == 202:
                    logger.info("pagerduty_alert_sent", summary=summary)
                else:
                    logger.error(
                        "pagerduty_alert_failed",
                        status=resp.status_code,
                        body=resp.text,
                    )
        except Exception as e:
            logger.error("pagerduty_error", error=str(e))

    # ── OpsGenie Alert API ──

    @staticmethod
    async def _send_opsgenie(
        summary: str,
        severity: str,
        source: str,
        details: Optional[dict] = None,
    ):
        """Send alert via OpsGenie Alert API."""
        priority_map = {
            AlertSeverity.CRITICAL: "P1",
            AlertSeverity.ERROR: "P2",
            AlertSeverity.WARNING: "P3",
            AlertSeverity.INFO: "P5",
        }

        payload = {
            "message": f"[AEGIS] {summary}",
            "priority": priority_map.get(severity, "P3"),
            "source": source,
            "tags": ["aegis", "automated"],
            "details": details or {},
        }

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    "https://api.opsgenie.com/v2/alerts",
                    json=payload,
                    headers={
                        "Authorization": f"GenieKey {settings.OPSGENIE_API_KEY}",
                        "Content-Type": "application/json",
                    },
                )
                if resp.status_code in (200, 202):
                    logger.info("opsgenie_alert_sent", summary=summary)
                else:
                    logger.error(
                        "opsgenie_alert_failed",
                        status=resp.status_code,
                        body=resp.text,
                    )
        except Exception as e:
            logger.error("opsgenie_error", error=str(e))
