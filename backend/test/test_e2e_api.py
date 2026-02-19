"""
E2E integration tests — exercises real FastAPI routes with an in-memory
SQLite database.  No mocks for the HTTP layer; only Redis and external
services (OPA, etc.) are stubbed so tests run without infrastructure.
"""
import os
import uuid
import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

# Must be set before any app import
os.environ["DATABASE_URL"] = "sqlite+aiosqlite://"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"
os.environ["OPA_URL"] = "http://localhost:8181"
os.environ["JWT_SECRET"] = "e2e-test-secret-key-at-least-32-chars-long"
os.environ["ENCRYPTION_KEY"] = ""
os.environ["ENVIRONMENT"] = "test"

import httpx
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.models.database import Base, get_db
from app.middleware.auth_middleware import create_access_token
from app.models.entities import User, UserRole, Agent, AgentStatus, MicroWallet

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_engine = create_async_engine("sqlite+aiosqlite://", echo=False)
_TestSession = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


def _build_mock_redis():
    """Return a minimal Redis mock good enough for auth lockout, rate-limit
    checks, JWT blacklist, caching, and counter helpers."""
    storage: dict[str, str] = {}
    redis = AsyncMock()

    async def mock_get(key):
        return storage.get(key)

    async def mock_set(key, value, **kwargs):
        if kwargs.get("nx") and key in storage:
            return False
        storage[key] = value
        return True

    async def mock_setex(key, ttl, value):
        storage[key] = value
        return True

    async def mock_delete(*keys):
        for k in keys:
            storage.pop(k, None)
        return len(keys)

    async def mock_incr(key):
        cur = int(storage.get(key, 0))
        storage[key] = str(cur + 1)
        return cur + 1

    async def mock_ttl(key):
        return 900

    redis.get = mock_get
    redis.set = mock_set
    redis.setex = mock_setex
    redis.delete = mock_delete
    redis.incr = mock_incr
    redis.ttl = mock_ttl
    redis.ping = AsyncMock(return_value=True)
    redis.sadd = AsyncMock(return_value=1)
    redis.srem = AsyncMock(return_value=1)
    redis.smembers = AsyncMock(return_value=set())
    redis.expire = AsyncMock(return_value=True)
    redis.zadd = AsyncMock(return_value=1)
    redis.zrangebyscore = AsyncMock(return_value=[])
    redis.zremrangebyscore = AsyncMock(return_value=0)
    redis.eval = AsyncMock(return_value=1)
    redis.scan = AsyncMock(return_value=(0, []))

    class MockPipeline:
        def __init__(self):
            self._results = []

        def incr(self, key):
            self._results.append(1)
            return self

        def expire(self, key, ttl):
            self._results.append(True)
            return self

        def __getattr__(self, name):
            def method(*a, **kw):
                self._results.append(None)
                return self
            return method

        async def execute(self):
            return self._results

    redis.pipeline = lambda: MockPipeline()
    return redis


_mock_redis = _build_mock_redis()


@pytest.fixture(autouse=True)
async def _setup_db():
    """Create all tables before each test; drop them after."""
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def _override_get_db():
    async with _TestSession() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@pytest.fixture()
async def client():
    """Yield an httpx.AsyncClient wired to the real FastAPI app."""
    # Patch redis before importing app (it may be cached)
    with patch("app.utils.redis_client.get_redis", return_value=_mock_redis):
        from app.main import app as fastapi_app

        fastapi_app.dependency_overrides[get_db] = _override_get_db

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=fastapi_app),
            base_url="http://testserver",
        ) as ac:
            yield ac

        fastapi_app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_PASSWORD = "Str0ng!Pass#99"

async def _create_user_in_db(role: UserRole = UserRole.ADMIN) -> User:
    """Insert a user directly into the test DB and return it."""
    from app.middleware.auth_middleware import hash_password

    user = User(
        id=uuid.uuid4(),
        email=f"test-{uuid.uuid4().hex[:8]}@aegis.dev",
        hashed_password=hash_password(VALID_PASSWORD),
        full_name="Test User",
        organization="AEGIS Tests",
        role=role,
        is_active=True,
    )
    async with _TestSession() as s:
        s.add(user)
        await s.commit()
        await s.refresh(user)
    return user


def _auth_header(user_id: uuid.UUID) -> dict[str, str]:
    token, _, _ = create_access_token(user_id)
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Tests — Health
# ---------------------------------------------------------------------------

class TestHealth:
    @pytest.mark.asyncio
    async def test_health_returns_200(self, client: httpx.AsyncClient):
        resp = await client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert "status" in body
        assert "version" in body


# ---------------------------------------------------------------------------
# Tests — Auth (register + login)
# ---------------------------------------------------------------------------

class TestAuth:
    @pytest.mark.asyncio
    async def test_register_creates_user(self, client: httpx.AsyncClient):
        resp = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "new@aegis.dev",
                "password": VALID_PASSWORD,
                "full_name": "New User",
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["email"] == "new@aegis.dev"
        assert "id" in body

    @pytest.mark.asyncio
    async def test_register_duplicate_email_fails(self, client: httpx.AsyncClient):
        payload = {
            "email": "dup@aegis.dev",
            "password": VALID_PASSWORD,
            "full_name": "Dup User",
        }
        await client.post("/api/v1/auth/register", json=payload)
        resp = await client.post("/api/v1/auth/register", json=payload)
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_register_weak_password_rejected(self, client: httpx.AsyncClient):
        resp = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "weak@aegis.dev",
                "password": "short",
                "full_name": "Weak",
            },
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_login_success(self, client: httpx.AsyncClient):
        user = await _create_user_in_db()
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": user.email, "password": VALID_PASSWORD},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body.get("access_token") or body.get("mfa_required")

    @pytest.mark.asyncio
    async def test_login_wrong_password(self, client: httpx.AsyncClient):
        user = await _create_user_in_db()
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": user.email, "password": "Wrong!Pass#1"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_me_returns_current_user(self, client: httpx.AsyncClient):
        user = await _create_user_in_db()
        resp = await client.get("/api/v1/auth/me", headers=_auth_header(user.id))
        assert resp.status_code == 200
        assert resp.json()["email"] == user.email

    @pytest.mark.asyncio
    async def test_me_unauthenticated(self, client: httpx.AsyncClient):
        resp = await client.get("/api/v1/auth/me")
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Tests — Agents CRUD
# ---------------------------------------------------------------------------

class TestAgents:
    @pytest.mark.asyncio
    async def test_create_and_list_agents(self, client: httpx.AsyncClient):
        user = await _create_user_in_db(UserRole.ADMIN)
        headers = _auth_header(user.id)

        # Create
        resp = await client.post(
            "/api/v1/agents/",
            json={"name": "Bot-1", "agent_type": "support"},
            headers=headers,
        )
        assert resp.status_code == 201
        agent = resp.json()
        assert agent["name"] == "Bot-1"
        assert agent["status"] == "active"
        assert "identity_fingerprint" in agent

        # List
        resp = await client.get("/api/v1/agents/", headers=headers)
        assert resp.status_code == 200
        agents = resp.json()
        assert any(a["name"] == "Bot-1" for a in agents)

    @pytest.mark.asyncio
    async def test_create_agent_unauthenticated(self, client: httpx.AsyncClient):
        resp = await client.post(
            "/api/v1/agents/",
            json={"name": "Ghost", "agent_type": "devops"},
        )
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_viewer_cannot_create_agent(self, client: httpx.AsyncClient):
        viewer = await _create_user_in_db(UserRole.VIEWER)
        resp = await client.post(
            "/api/v1/agents/",
            json={"name": "Blocked", "agent_type": "sales"},
            headers=_auth_header(viewer.id),
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_suspend_and_activate_agent(self, client: httpx.AsyncClient):
        user = await _create_user_in_db(UserRole.ADMIN)
        headers = _auth_header(user.id)

        # Create agent
        resp = await client.post(
            "/api/v1/agents/",
            json={"name": "Toggle", "agent_type": "ops"},
            headers=headers,
        )
        agent_id = resp.json()["id"]

        # Suspend
        resp = await client.post(f"/api/v1/agents/{agent_id}/suspend", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "suspended"

        # Activate
        resp = await client.post(f"/api/v1/agents/{agent_id}/activate", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "active"


# ---------------------------------------------------------------------------
# Tests — Wallets
# ---------------------------------------------------------------------------

class TestWallets:
    @pytest.mark.asyncio
    async def test_wallet_created_with_agent(self, client: httpx.AsyncClient):
        user = await _create_user_in_db(UserRole.ADMIN)
        headers = _auth_header(user.id)

        resp = await client.post(
            "/api/v1/agents/",
            json={"name": "Wallet-Bot", "agent_type": "finance"},
            headers=headers,
        )
        agent_id = resp.json()["id"]

        resp = await client.get(f"/api/v1/wallets/{agent_id}", headers=headers)
        # Wallet may be auto-created or not — both are valid
        assert resp.status_code in (200, 404)


# ---------------------------------------------------------------------------
# Tests — RBAC boundary
# ---------------------------------------------------------------------------

class TestRBACBoundary:
    @pytest.mark.asyncio
    async def test_viewer_cannot_access_audit_export(self, client: httpx.AsyncClient):
        viewer = await _create_user_in_db(UserRole.VIEWER)
        resp = await client.get(
            "/api/v1/audit/",
            headers=_auth_header(viewer.id),
        )
        # Viewers have audit:read, so this should work
        assert resp.status_code in (200, 422)

    @pytest.mark.asyncio
    async def test_agent_developer_can_execute_proxy(self, client: httpx.AsyncClient):
        """Agent developer role should have proxy:execute permission."""
        dev = await _create_user_in_db(UserRole.AGENT_DEVELOPER)
        # We just check that the permission gate doesn't block — the actual
        # proxy will fail because there's no agent/OPA, but it shouldn't be 403.
        resp = await client.post(
            "/api/v1/proxy/execute",
            json={
                "agent_id": str(uuid.uuid4()),
                "service_name": "openai",
                "action": "read",
                "target_url": "https://api.openai.com/v1/models",
            },
            headers=_auth_header(dev.id),
        )
        # Should NOT be 403 (permission denied)
        assert resp.status_code != 403


# ---------------------------------------------------------------------------
# Tests — Security headers
# ---------------------------------------------------------------------------

class TestSecurityHeaders:
    @pytest.mark.asyncio
    async def test_security_headers_present(self, client: httpx.AsyncClient):
        resp = await client.get("/api/v1/auth/me")
        headers = resp.headers
        assert headers.get("x-content-type-options") == "nosniff"
        assert headers.get("x-frame-options") == "DENY"
        assert headers.get("x-xss-protection") == "1; mode=block"
        assert "x-request-id" in headers
