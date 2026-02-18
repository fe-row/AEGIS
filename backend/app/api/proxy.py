"""
Proxy v4 — Fixes: async SSRF, shared httpx pool, O(1) counters,
safe permission cache, proper snapshot handling.
"""
import uuid
import time
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.models.database import get_db
from app.models.entities import (
    User, Agent, AgentPermission, AgentStatus, SecretVault, ActionType,
)
from app.schemas.schemas import ProxyRequest, ProxyResponse
from app.services.policy_engine import policy_engine
from app.services.jit_broker import jit_broker
from app.services.wallet_service import WalletService
from app.services.circuit_breaker import circuit_breaker
from app.services.hitl_gateway import HITLGateway
from app.services.audit_service import AuditService
from app.services.prompt_firewall import prompt_firewall
from app.services.anomaly_detector import anomaly_detector
from app.services.trust_engine import TrustEngine
from app.services.rollback_service import RollbackService
from app.services.identity_service import IdentityService
from app.middleware.auth_middleware import get_current_user
from app.api.websocket import ws_manager
from app.utils.metrics import PROXY_EXECUTIONS, PROXY_COST
from app.utils.ssrf_guard import validate_url_async
from app.utils.idempotency import check_idempotency, store_idempotency, lock_idempotency, unlock_idempotency
from app.utils.cache import get_cached_permission, set_cached_permission
from app.utils.counters import get_hourly_count, increment_hourly_counter
from app.utils.http_pool import get_http_client
from app.utils.errors import ErrorCode
from app.middleware.pure_asgi import get_correlation_id
from app.logging_config import get_logger

logger = get_logger("proxy")
router = APIRouter(prefix="/proxy", tags=["Proxy Execution"])


def _block(request_id: uuid.UUID, code: str, msg: str, policy=None) -> ProxyResponse:
    PROXY_EXECUTIONS.labels(status="blocked").inc()
    return ProxyResponse(
        request_id=request_id, status="blocked", message=msg,
        policy_result={"error_code": code, **(policy or {})},
    )


@router.post("/execute", response_model=ProxyResponse)
async def execute_proxy(
    data: ProxyRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    t0 = time.monotonic()
    rid = uuid.uuid4()
    ip = request.client.host if request.client else "unknown"
    idem_key = request.headers.get("x-idempotency-key", "")
    corr = get_correlation_id()
    at = ActionType.LLM_INFERENCE.value if data.model else ActionType.API_CALL.value
    ctx = {"correlation_id": corr, "request_id": str(rid)}

    # ── 0. Idempotency ──
    if idem_key:
        cached = await check_idempotency(idem_key)
        if cached:
            return ProxyResponse(**cached)
        if not await lock_idempotency(idem_key):
            raise HTTPException(status_code=409, detail="Duplicate request in progress")

    try:
        # ── 1. SSRF (async DNS) ──
        url_ok, url_reason = await validate_url_async(data.target_url)
        if not url_ok:
            await AuditService.log(
                data.agent_id, user.id, at, data.service_name, False,
                ip_address=ip, metadata={"ssrf": url_reason, **ctx},
            )
            return _block(rid, ErrorCode.SSRF_BLOCKED, f"URL blocked: {url_reason}")

        # ── 2. Identity ──
        agent = await IdentityService.get_agent_for_sponsor(db, data.agent_id, user.id)
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        if agent.status != AgentStatus.ACTIVE.value:
            await AuditService.log(
                agent.id, user.id, at, data.service_name, False,
                ip_address=ip, metadata={"reason": f"agent_{agent.status}", **ctx},
            )
            code = ErrorCode.AGENT_PANIC if agent.status == "panic" else ErrorCode.AGENT_SUSPENDED
            return _block(rid, code, f"Agent is {agent.status}")

        # ── 3. Prompt Firewall ──
        if data.prompt:
            fw = prompt_firewall.analyze(data.prompt)
            if not fw.safe:
                await TrustEngine.penalize_injection(db, agent.id)
                await AuditService.log(
                    agent.id, user.id, at, data.service_name, False,
                    prompt_snippet=data.prompt, ip_address=ip,
                    metadata={"threats": fw.threats_detected, **ctx},
                )
                return _block(rid, ErrorCode.PROMPT_INJECTION, f"Injection: {fw.threats_detected}")

        # ── 4. Anomaly Detection ──
        anomaly = await anomaly_detector.detect_anomaly(
            db, agent.id, data.service_name, data.action, data.estimated_cost_usd,
        )
        if anomaly["is_anomalous"]:
            await TrustEngine.penalize_anomaly(db, agent.id)
            await ws_manager.send_to_user(str(user.id), "anomaly", {
                "agent_id": str(agent.id), "anomalies": anomaly["anomalies"],
            })
            await AuditService.log(
                agent.id, user.id, at, data.service_name, False,
                ip_address=ip, metadata={"anomaly": anomaly, **ctx},
            )
            return _block(rid, ErrorCode.ANOMALY_DETECTED, f"Anomaly: {anomaly['anomalies']}")

        # ── 5. Permission (cached) ──
        cached_perm = await get_cached_permission(agent.id, data.service_name)

        if cached_perm is None:
            perm_q = await db.execute(
                select(AgentPermission).where(
                    AgentPermission.agent_id == agent.id,
                    AgentPermission.service_name == data.service_name,
                    AgentPermission.is_active == True,
                )
            )
            perm_obj = perm_q.scalar_one_or_none()
            if not perm_obj:
                await AuditService.log(
                    agent.id, user.id, at, data.service_name, False,
                    ip_address=ip, metadata={"reason": "no_permission", **ctx},
                )
                return _block(rid, ErrorCode.NO_PERMISSION, f"No permission: {data.service_name}")

            # FIX: store as plain dict, access as plain dict
            cached_perm = {
                "time_window_start": perm_obj.time_window_start,
                "time_window_end": perm_obj.time_window_end,
                "allowed_actions": perm_obj.allowed_actions,
                "max_requests_per_hour": perm_obj.max_requests_per_hour,
                "max_records_per_request": perm_obj.max_records_per_request,
                "requires_hitl": perm_obj.requires_hitl,
            }
            await set_cached_permission(agent.id, data.service_name, cached_perm)

        # ── 6. Wallet ──
        can_spend, spend_msg = await WalletService.can_spend(db, agent.id, data.estimated_cost_usd)
        if not can_spend:
            await AuditService.log(
                agent.id, user.id, at, data.service_name, False,
                cost_usd=data.estimated_cost_usd, ip_address=ip,
                metadata={"wallet": spend_msg, **ctx},
            )
            return _block(rid, ErrorCode.WALLET_INSUFFICIENT_FUNDS, spend_msg)

        # ── 7. Circuit Breaker ──
        tripped = await circuit_breaker.check_and_trip(db, agent.id, data.estimated_cost_usd)
        if tripped:
            await TrustEngine.penalize_circuit_break(db, agent.id)
            await ws_manager.send_to_user(str(user.id), "circuit_breaker", {
                "agent_id": str(agent.id),
            })
            await AuditService.log(
                agent.id, user.id, at, data.service_name, False,
                ip_address=ip, metadata={"reason": "circuit_breaker", **ctx},
            )
            return _block(rid, ErrorCode.CIRCUIT_BREAKER, "Agent in PANIC mode")

        # ── 8. OPA Policy ──
        # FIX: O(1) counter instead of O(n) buffer scan
        current_reqs = await get_hourly_count(agent.id, data.service_name)
        wallet = await WalletService.get_wallet(db, agent.id)

        policy_result = await policy_engine.evaluate(
            agent_id=str(agent.id),
            agent_type=agent.agent_type,
            service_name=data.service_name,
            action=data.action,
            trust_score=agent.trust_score,
            permission=cached_perm,
            wallet_balance=wallet.balance_usd if wallet else 0,
            estimated_cost=data.estimated_cost_usd,
            current_hour_requests=current_reqs,
        )

        if not policy_result["allowed"] and not policy_result.get("requires_hitl"):
            await TrustEngine.penalize_violation(db, agent.id)
            await AuditService.log(
                agent.id, user.id, at, data.service_name, False,
                policy_evaluation=policy_result, ip_address=ip, metadata=ctx,
            )
            return _block(rid, ErrorCode.POLICY_DENIED, str(policy_result["deny_reasons"]), policy_result)

        # ── 9. HITL ──
        if policy_result.get("requires_hitl"):
            hitl_req = await HITLGateway.create_request(
                db, agent.id, user.id,
                f"{data.action} → {data.service_name}",
                {"url": data.target_url, "method": data.method},
                data.estimated_cost_usd,
            )
            await ws_manager.send_to_user(str(user.id), "hitl_required", {
                "id": str(hitl_req.id), "agent_id": str(agent.id),
            })
            PROXY_EXECUTIONS.labels(status="hitl_pending").inc()
            r = ProxyResponse(request_id=rid, status="hitl_pending", message=f"HITL: {hitl_req.id}")
            if idem_key:
                await store_idempotency(idem_key, r.model_dump(mode="json"))
            return r

        # ── 10. JIT Secret ──
        vault_q = await db.execute(
            select(SecretVault).where(
                SecretVault.sponsor_id == user.id,
                SecretVault.service_name == data.service_name,
            )
        )
        vault = vault_q.scalar_one_or_none()

        headers = dict(data.headers or {})
        eph_token = None
        if vault:
            eph_token = await jit_broker.mint_ephemeral_token(
                agent.id, data.service_name, vault.encrypted_secret,
            )
            resolved = await jit_broker.resolve_token(eph_token)
            if resolved:
                headers["Authorization"] = f"Bearer {resolved['real_secret']}"

        # ── 11. Execute (shared pool) ──
        response_code = None
        response_body = None
        try:
            client = await get_http_client()
            resp = await client.request(
                method=data.method,
                url=data.target_url,
                headers=headers,
                json=data.body if data.method in ("POST", "PUT", "PATCH") else None,
            )
            response_code = resp.status_code
            try:
                response_body = resp.json()
            except Exception:
                response_body = resp.text[:5000]
        except Exception as e:
            response_code = 504 if "timeout" in str(e).lower() else 502
            response_body = {"error": type(e).__name__}

        # ── 12. Revoke JIT ──
        if eph_token:
            await jit_broker.revoke_token(eph_token)

        # ── 13. Charge wallet ──
        cost = data.estimated_cost_usd
        if cost > 0:
            tx = await WalletService.charge(db, agent.id, cost, f"{data.action}@{data.service_name}", data.service_name, at)
            if tx:
                await circuit_breaker.record_spend(agent.id, cost)
                PROXY_COST.inc(cost)

        # ── 14. Behavior ──
        await anomaly_detector.record_action(agent.id, data.service_name, data.action, cost)

        # ── 15. Trust ──
        if response_code and 200 <= response_code < 400:
            await TrustEngine.reward_success(db, agent.id)

        # ── 16. Increment hourly counter ──
        await increment_hourly_counter(agent.id, data.service_name)

        duration_ms = int((time.monotonic() - t0) * 1000)

        # ── 17. Audit (buffered) ──
        await AuditService.log(
            agent.id, user.id, at, data.service_name, True,
            cost_usd=cost, prompt_snippet=data.prompt, model_used=data.model,
            policy_evaluation=policy_result, response_code=response_code,
            ip_address=ip, duration_ms=duration_ms, metadata=ctx,
        )

        # ── 18. Snapshot ──
        if data.method in ("POST", "PUT", "PATCH", "DELETE"):
            try:
                from app.models.entities import AuditLog as AL
                latest_q = await db.execute(
                    select(func.max(AL.id)).where(AL.agent_id == agent.id)
                )
                latest_id = latest_q.scalar() or 1
                await RollbackService.save_snapshot(
                    db, agent.id, latest_id,
                    {"method": data.method, "url": data.target_url, "status": response_code},
                    {"service": data.service_name, "method": data.method, "url": data.target_url},
                )
            except Exception as e:
                logger.debug("snapshot_skip", error=str(e))

        # ── 19. Respond ──
        PROXY_EXECUTIONS.labels(status="executed").inc()

        resp = ProxyResponse(
            request_id=rid, status="executed",
            response_code=response_code, response_body=response_body,
            cost_charged_usd=cost, policy_result=policy_result,
            message="OK", duration_ms=duration_ms,
        )

        if idem_key:
            await store_idempotency(idem_key, resp.model_dump(mode="json"))

        return resp

    finally:
        if idem_key:
            await unlock_idempotency(idem_key)