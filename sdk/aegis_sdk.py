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
import time
import random
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional


SDK_VERSION = "2.0.0"


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


class AegisCircuitOpenError(AegisError):
    """Raised when the client-side circuit breaker is open."""
    def __init__(self, reset_at: float):
        self.reset_at = reset_at
        remaining = max(0, reset_at - time.monotonic())
        super().__init__(503, f"Circuit breaker open — retry in {remaining:.0f}s")


# ═══════════════════════════════════════════════════════
#  Client-Side Circuit Breaker
# ═══════════════════════════════════════════════════════

@dataclass
class _CircuitBreaker:
    """Tracks consecutive failures and opens the circuit to prevent cascading errors."""
    failure_threshold: int = 5
    reset_timeout_seconds: float = 30.0
    _failure_count: int = field(default=0, init=False, repr=False)
    _state: str = field(default="closed", init=False, repr=False)  # closed | open | half_open
    _opened_at: float = field(default=0.0, init=False, repr=False)

    def record_success(self):
        self._failure_count = 0
        self._state = "closed"

    def record_failure(self):
        self._failure_count += 1
        if self._failure_count >= self.failure_threshold:
            self._state = "open"
            self._opened_at = time.monotonic()

    def allow_request(self) -> bool:
        if self._state == "closed":
            return True
        if self._state == "open":
            elapsed = time.monotonic() - self._opened_at
            if elapsed >= self.reset_timeout_seconds:
                self._state = "half_open"
                return True
            return False
        # half_open: allow one probe request
        return True

    @property
    def state(self) -> str:
        # Check for auto-transition from open
        if self._state == "open":
            elapsed = time.monotonic() - self._opened_at
            if elapsed >= self.reset_timeout_seconds:
                return "half_open"
        return self._state

    @property
    def reset_at(self) -> float:
        return self._opened_at + self.reset_timeout_seconds


# ═══════════════════════════════════════════════════════
#  Retry Configuration
# ═══════════════════════════════════════════════════════

@dataclass
class RetryConfig:
    """Configuration for automatic retry with exponential backoff."""
    max_retries: int = 3
    base_delay_seconds: float = 0.5
    max_delay_seconds: float = 10.0
    jitter: bool = True
    retryable_status_codes: tuple = (429, 500, 502, 503, 504)

    def delay_for_attempt(self, attempt: int) -> float:
        delay = min(self.base_delay_seconds * (2 ** attempt), self.max_delay_seconds)
        if self.jitter:
            delay *= (0.5 + random.random())
        return delay


# ═══════════════════════════════════════════════════════
#  AEGIS Client
# ═══════════════════════════════════════════════════════

class AegisClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        agent_id: str,
        timeout: float = 60.0,
        retry: RetryConfig | None = None,
        circuit_breaker_threshold: int = 5,
        circuit_breaker_timeout: float = 30.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.agent_id = agent_id
        self.timeout = timeout
        self.retry = retry or RetryConfig()
        self._cb = _CircuitBreaker(
            failure_threshold=circuit_breaker_threshold,
            reset_timeout_seconds=circuit_breaker_timeout,
        )
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": f"aegis-sdk-python/{SDK_VERSION}",
        }
        self._sync_client: httpx.Client | None = None
        self._async_client: httpx.AsyncClient | None = None

    def _get_sync_client(self) -> httpx.Client:
        if self._sync_client is None or self._sync_client.is_closed:
            self._sync_client = httpx.Client(timeout=self.timeout)
        return self._sync_client

    def _get_async_client(self) -> httpx.AsyncClient:
        if self._async_client is None or self._async_client.is_closed:
            self._async_client = httpx.AsyncClient(timeout=self.timeout)
        return self._async_client

    def close(self):
        """Close the underlying HTTP connection pools."""
        if self._sync_client and not self._sync_client.is_closed:
            self._sync_client.close()
        if self._async_client and not self._async_client.is_closed:
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._async_client.aclose())
            except RuntimeError:
                asyncio.run(self._async_client.aclose())

    async def aclose(self):
        """Async close for the underlying HTTP connection pools."""
        if self._sync_client and not self._sync_client.is_closed:
            self._sync_client.close()
        if self._async_client and not self._async_client.is_closed:
            await self._async_client.aclose()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.aclose()

    @property
    def circuit_state(self) -> str:
        """Current circuit breaker state: closed | open | half_open."""
        return self._cb.state

    def _build_payload(
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
    ) -> dict:
        return {
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

    @staticmethod
    def _parse_response(resp: httpx.Response) -> ProxyResult:
        if resp.status_code == 401:
            raise AegisError(401, "Invalid API key or expired token")
        if resp.status_code == 404:
            raise AegisError(404, "Agent not found or not owned by this user")

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
        """Execute a proxied API call through AEGIS with retry and circuit breaker."""
        if not self._cb.allow_request():
            raise AegisCircuitOpenError(self._cb.reset_at)

        req_headers = dict(self._headers)
        if idempotency_key:
            req_headers["X-Idempotency-Key"] = idempotency_key

        payload = self._build_payload(
            service_name, action, target_url, method,
            headers, body, prompt, model, estimated_cost_usd,
        )

        last_error: Exception | None = None

        for attempt in range(self.retry.max_retries + 1):
            try:
                client = self._get_sync_client()
                resp = client.post(
                    f"{self.base_url}/api/v1/proxy/execute",
                    json=payload,
                    headers=req_headers,
                )

                # Non-retryable client errors
                if resp.status_code in (401, 403, 404, 409, 422):
                    self._cb.record_success()
                    return self._parse_response(resp)

                # Retryable errors
                if resp.status_code in self.retry.retryable_status_codes:
                    self._cb.record_failure()
                    last_error = AegisError(resp.status_code, f"HTTP {resp.status_code}")
                    if attempt < self.retry.max_retries:
                        delay = self.retry.delay_for_attempt(attempt)
                        # Respect Retry-After header if present
                        retry_after = resp.headers.get("Retry-After")
                        if retry_after:
                            try:
                                delay = max(delay, float(retry_after))
                            except ValueError:
                                pass
                        time.sleep(delay)
                        continue
                    raise last_error

                # Success
                self._cb.record_success()
                return self._parse_response(resp)

            except (httpx.ConnectError, httpx.TimeoutException, httpx.ReadTimeout) as e:
                self._cb.record_failure()
                last_error = AegisError(0, f"Connection error: {e}")
                if attempt < self.retry.max_retries:
                    time.sleep(self.retry.delay_for_attempt(attempt))
                    continue

        raise last_error or AegisError(0, "Request failed after all retries")

    async def execute_async(
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
        """Async version of execute with retry and circuit breaker."""
        import asyncio

        if not self._cb.allow_request():
            raise AegisCircuitOpenError(self._cb.reset_at)

        req_headers = dict(self._headers)
        if idempotency_key:
            req_headers["X-Idempotency-Key"] = idempotency_key

        payload = self._build_payload(
            service_name, action, target_url, method,
            headers, body, prompt, model, estimated_cost_usd,
        )

        last_error: Exception | None = None

        for attempt in range(self.retry.max_retries + 1):
            try:
                client = self._get_async_client()
                resp = await client.post(
                    f"{self.base_url}/api/v1/proxy/execute",
                    json=payload,
                    headers=req_headers,
                )

                if resp.status_code in (401, 403, 404, 409, 422):
                    self._cb.record_success()
                    return self._parse_response(resp)

                if resp.status_code in self.retry.retryable_status_codes:
                    self._cb.record_failure()
                    last_error = AegisError(resp.status_code, f"HTTP {resp.status_code}")
                    if attempt < self.retry.max_retries:
                        delay = self.retry.delay_for_attempt(attempt)
                        retry_after = resp.headers.get("Retry-After")
                        if retry_after:
                            try:
                                delay = max(delay, float(retry_after))
                            except ValueError:
                                pass
                        await asyncio.sleep(delay)
                        continue
                    raise last_error

                self._cb.record_success()
                return self._parse_response(resp)

            except (httpx.ConnectError, httpx.TimeoutException, httpx.ReadTimeout) as e:
                self._cb.record_failure()
                last_error = AegisError(0, f"Connection error: {e}")
                if attempt < self.retry.max_retries:
                    await asyncio.sleep(self.retry.delay_for_attempt(attempt))
                    continue

        raise last_error or AegisError(0, "Request failed after all retries")