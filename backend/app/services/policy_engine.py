import httpx
from datetime import datetime, timezone
from app.config import get_settings
from app.utils.http_pool import get_http_client

settings = get_settings()


class PolicyEngine:
    """OPA-based policy evaluation engine."""

    def __init__(self):
        self.opa_url = settings.OPA_URL

    async def evaluate(
        self,
        agent_id: str,
        agent_type: str,
        service_name: str,
        action: str,
        trust_score: float,
        permission: dict,
        wallet_balance: float,
        estimated_cost: float,
        current_hour_requests: int,
    ) -> dict:
        now = datetime.now(timezone.utc)
        input_data = {
            "input": {
                "agent_id": agent_id,
                "agent_type": agent_type,
                "service_name": service_name,
                "action": action,
                "trust_score": trust_score,
                "current_hour": now.hour,
                "current_minute": now.minute,
                "day_of_week": now.strftime("%A").lower(),
                "time_window_start": permission.get("time_window_start", "00:00"),
                "time_window_end": permission.get("time_window_end", "23:59"),
                "allowed_actions": permission.get("allowed_actions", []),
                "max_requests_per_hour": permission.get("max_requests_per_hour", 100),
                "current_hour_requests": current_hour_requests,
                "max_records_per_request": permission.get("max_records_per_request", 100),
                "wallet_balance": wallet_balance,
                "estimated_cost": estimated_cost,
                "requires_hitl": permission.get("requires_hitl", False),
            }
        }

        try:
            client = await get_http_client()
            resp = await client.post(
                f"{self.opa_url}/v1/data/aegis/main",
                json=input_data,
                timeout=5.0,
            )
            resp.raise_for_status()
            result = resp.json().get("result", {})
            return {
                "allowed": result.get("allow", False),
                "requires_hitl": result.get("requires_hitl", False),
                "deny_reasons": result.get("deny_reasons", []),
                "raw": result,
            }
        except Exception as e:
            # Fail closed: deny on OPA errors
            return {
                "allowed": False,
                "requires_hitl": False,
                "deny_reasons": [f"Policy engine error: {str(e)}"],
                "raw": {},
            }

    async def close(self):
        """No-op: lifecycle managed by shared HTTP pool."""
        pass


policy_engine = PolicyEngine()
