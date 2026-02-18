"""
AEGIS Python SDK — for integrating AI agents with the AEGIS proxy.

Usage:
    from aegis_sdk import AegisClient

    aegis = AegisClient(
        base_url="https://aegis.yourcompany.com",
        api_key="aegis_abc123...",
        agent_id="uuid-of-your-agent",
    )

    # Proxied API call — agent never touches the real API key
    result = aegis.execute(
        service_name="openai",
        action="read",
        target_url="https://api.openai.com/v1/chat/completions",
        method="POST",
        body={"model": "gpt-4", "messages": [...]},
        estimated_cost_usd=0.03,
        prompt="What is 2+2?",
        model="gpt-4",
    )

    if result.status == "executed":
        print(result.response_body)
    elif result.status == "blocked":
        print(f"Blocked: {result.message}")
    elif result.status == "hitl_pending":
        print(f"Awaiting human approval: {result.message}")
"""
import httpx
import uuid
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class ProxyResult:
    request_id: str
    status: str  # executed | blocked | hitl_pending
    response_code: Optional[int]
    response_body: Any
    cost_charged_usd: float
    message: str
    duration_ms: Optional[int]
    policy_result: Optional[dict]


class AegisError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"AEGIS Error {status_code}: {detail}")


class AegisClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        agent_id: str,
        timeout: float = 60.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.agent_id = agent_id
        self.timeout = timeout
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "aegis-sdk-python/1.0.0",
        }

    def execute(
        self,
        service_name: str,
        action: str,
        target_url: str,
        method: str = "GET",
        headers: dict | None = None,
        body: Any = None,
        prompt: str | None = None,
        model: str | None = None,
        estimated_cost_usd: float = 0.0,
        idempotency_key: str | None = None,
    ) -> ProxyResult:
        """Execute a proxied API call through AEGIS."""
        req_headers = dict(self._headers)
        if idempotency_key:
            req_headers["X-Idempotency-Key"] = idempotency_key

        payload = {
            "agent_id": self.agent_id,
            "service_name": service_name,
            "action": action,
            "target_url": target_url,
            "method": method.upper(),
            "headers": headers or {},
            "body": body,
            "prompt": prompt,
            "model": model,
            "estimated_cost_usd": estimated_cost_usd,
        }

        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(
                f"{self.base_url}/api/v1/proxy/execute",
                json=payload,
                headers=req_headers,
            )

        if resp.status_code == 401:
            raise AegisError(401, "Invalid API key or expired token")
        if resp.status_code == 404:
            raise AegisError(404, "Agent not found or not owned by this user")
        if resp.status_code == 429:
            raise AegisError(429, "Rate limit exceeded")
        if resp.status_code >= 500:
            raise AegisError(resp.status_code, "AEGIS server error")

        data = resp.json()
        return ProxyResult(
            request_id=data.get("request_id", ""),
            status=data.get("status", "unknown"),
            response_code=data.get("response_code"),
            response_body=data.get("response_body"),
            cost_charged_usd=data.get("cost_charged_usd", 0),
            message=data.get("message", ""),
            duration_ms=data.get("duration_ms"),
            policy_result=data.get("policy_result"),
        )

    async def execute_async(self, **kwargs) -> ProxyResult:
        """Async version of execute."""
        req_headers = dict(self._headers)
        idem_key = kwargs.pop("idempotency_key", None)
        if idem_key:
            req_headers["X-Idempotency-Key"] = idem_key

        payload = {
            "agent_id": self.agent_id,
            "service_name": kwargs["service_name"],
            "action": kwargs["action"],
            "target_url": kwargs["target_url"],
            "method": kwargs.get("method", "GET").upper(),
            "headers": kwargs.get("headers", {}),
            "body": kwargs.get("body"),
            "prompt": kwargs.get("prompt"),
            "model": kwargs.get("model"),
            "estimated_cost_usd": kwargs.get("estimated_cost_usd", 0),
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/api/v1/proxy/execute",
                json=payload,
                headers=req_headers,
            )

        if resp.status_code >= 400:
            detail = resp.json().get("detail", f"HTTP {resp.status_code}")
            raise AegisError(resp.status_code, detail)

        data = resp.json()
        return ProxyResult(
            request_id=data.get("request_id", ""),
            status=data.get("status", "unknown"),
            response_code=data.get("response_code"),
            response_body=data.get("response_body"),
            cost_charged_usd=data.get("cost_charged_usd", 0),
            message=data.get("message", ""),
            duration_ms=data.get("duration_ms"),
            policy_result=data.get("policy_result"),
        )