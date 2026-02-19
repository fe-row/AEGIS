import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.entities import HITLRequest, HITLStatus
from app.config import get_settings
from app.utils.http_pool import get_http_client
from app.utils.webhook_signer import sign_payload
from app.services.alerting import AlertService

settings = get_settings()

HITL_EXPIRY_MINUTES = 30


class HITLGateway:
    """Human-in-the-Loop gateway. Pauses execution and notifies humans."""

    @staticmethod
    async def create_request(
        db: AsyncSession,
        agent_id: uuid.UUID,
        sponsor_id: uuid.UUID,
        action_description: str,
        action_payload: dict,
        estimated_cost: float,
    ) -> HITLRequest:
        req = HITLRequest(
            agent_id=agent_id,
            sponsor_id=sponsor_id,
            action_description=action_description,
            action_payload=action_payload,
            estimated_cost_usd=estimated_cost,
            status=HITLStatus.PENDING,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=HITL_EXPIRY_MINUTES),
        )
        db.add(req)
        await db.commit()
        await db.refresh(req)

        # Notify via webhooks
        await HITLGateway._notify(req)

        return req

    @staticmethod
    async def decide(
        db: AsyncSession,
        request_id: uuid.UUID,
        user_id: uuid.UUID,
        approved: bool,
        note: str = "",
    ) -> HITLRequest | None:
        result = await db.execute(
            select(HITLRequest).where(HITLRequest.id == request_id)
        )
        req = result.scalar_one_or_none()
        if not req:
            return None

        if req.status != HITLStatus.PENDING:
            return req

        if datetime.now(timezone.utc) > req.expires_at:
            req.status = HITLStatus.EXPIRED
            await db.commit()
            return req

        req.status = HITLStatus.APPROVED if approved else HITLStatus.REJECTED
        req.decided_by = user_id
        req.decision_note = note
        req.decided_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(req)
        return req

    @staticmethod
    async def list_pending(db: AsyncSession, sponsor_id: uuid.UUID) -> list[HITLRequest]:
        result = await db.execute(
            select(HITLRequest)
            .where(
                HITLRequest.sponsor_id == sponsor_id,
                HITLRequest.status == HITLStatus.PENDING,
            )
            .order_by(HITLRequest.created_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def _notify(req: HITLRequest):
        message = {
            "text": (
                f"🔔 *AEGIS HITL Approval Required*\n"
                f"Agent: `{req.agent_id}`\n"
                f"Action: {req.action_description}\n"
                f"Est. Cost: ${req.estimated_cost_usd:.4f}\n"
                f"Expires: {req.expires_at.isoformat()}\n"
                f"Request ID: `{req.id}`"
            )
        }

        try:
            client = await get_http_client()
        except Exception:
            return

        # Sign payloads with HMAC-SHA256 for authenticity verification
        sig_headers = sign_payload(message)

        if settings.SLACK_WEBHOOK_URL:
            try:
                await client.post(
                    settings.SLACK_WEBHOOK_URL, json=message, headers=sig_headers,
                )
            except Exception:
                pass

        if settings.TEAMS_WEBHOOK_URL:
            teams_msg = {
                "@type": "MessageCard",
                "summary": "AEGIS HITL Approval",
                "text": message["text"],
            }
            teams_sig = sign_payload(teams_msg)
            try:
                await client.post(
                    settings.TEAMS_WEBHOOK_URL, json=teams_msg, headers=teams_sig,
                )
            except Exception:
                pass

        # PagerDuty / OpsGenie alert for critical approvals
        if req.estimated_cost_usd > 10.0:
            try:
                await AlertService.send_warning(
                    f"HITL approval required: {req.action_description} "
                    f"(est. ${req.estimated_cost_usd:.2f})",
                    source="hitl-gateway",
                    details={
                        "agent_id": str(req.agent_id),
                        "request_id": str(req.id),
                        "estimated_cost": req.estimated_cost_usd,
                    },
                )
            except Exception:
                pass