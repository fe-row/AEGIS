"""
WebSocket endpoint and connection manager for real-time events.
Supports HITL notifications, anomaly alerts, and circuit breaker events.
"""
import orjson
import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
import jwt as pyjwt
from app.config import get_settings
from app.logging_config import get_logger
from app.utils.jwt_blacklist import is_token_blacklisted

logger = get_logger("websocket")
settings = get_settings()

router = APIRouter()

MAX_CONNECTIONS_PER_USER = 10


class WebSocketManager:
    """Manages WebSocket connections per user for real-time events."""

    def __init__(self):
        self._connections: dict[str, list[WebSocket]] = {}

    async def connect(self, user_id: str, websocket: WebSocket):
        await websocket.accept()
        if user_id not in self._connections:
            self._connections[user_id] = []

        # SECURITY: Cap connections per user to prevent DoS
        while len(self._connections[user_id]) >= MAX_CONNECTIONS_PER_USER:
            oldest = self._connections[user_id].pop(0)
            try:
                await oldest.close(code=4008, reason="Connection limit reached")
            except Exception:
                pass
            logger.warning("ws_evicted_oldest", user_id=user_id)

        self._connections[user_id].append(websocket)
        logger.info("ws_connected", user_id=user_id, count=len(self._connections[user_id]))

    def disconnect(self, user_id: str, websocket: WebSocket):
        if user_id in self._connections:
            self._connections[user_id] = [
                ws for ws in self._connections[user_id] if ws != websocket
            ]
            if not self._connections[user_id]:
                del self._connections[user_id]
        logger.info("ws_disconnected", user_id=user_id)

    async def send_to_user(self, user_id: str, event: str, data: dict):
        """Send event to all connections for a user."""
        if user_id not in self._connections:
            return
        message = orjson.dumps({"event": event, "data": data}).decode()
        disconnected = []
        for ws in self._connections[user_id]:
            try:
                await ws.send_text(message)
            except Exception:
                disconnected.append(ws)
        # Clean up stale connections
        for ws in disconnected:
            self.disconnect(user_id, ws)

    async def broadcast(self, event: str, data: dict):
        """Broadcast event to all connected users."""
        message = orjson.dumps({"event": event, "data": data}).decode()
        for user_id in list(self._connections.keys()):
            for ws in self._connections.get(user_id, []):
                try:
                    await ws.send_text(message)
                except Exception:
                    pass


ws_manager = WebSocketManager()


async def _extract_user_id(token: str) -> str | None:
    """Extract user_id from JWT token — validates type and blacklist."""
    try:
        payload = pyjwt.decode(
            token, settings.jwt_verification_key,
            algorithms=[settings.JWT_ALGORITHM],
        )
        # SECURITY: Only accept access tokens for WebSocket connections
        if payload.get("type") != "access":
            logger.warning("ws_rejected_non_access_token", token_type=payload.get("type"))
            return None

        # SECURITY: Reject blacklisted/revoked tokens
        jti = payload.get("jti", "")
        if jti and await is_token_blacklisted(jti):
            logger.warning("ws_rejected_blacklisted_token", jti=jti)
            return None

        return payload.get("sub")
    except pyjwt.exceptions.PyJWTError:
        return None


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(default=""),
):
    # Prefer token via first message (secure), fall back to query param (legacy)
    user_id = None
    if token:
        logger.warning("ws_token_in_query", hint="Token in URL is logged by proxies. Use message-based auth.")
        user_id = await _extract_user_id(token)

    if not user_id:
        # Accept and wait for auth message
        await websocket.accept()
        try:
            first_msg = await asyncio.wait_for(websocket.receive_text(), timeout=5.0)
            auth_data = orjson.loads(first_msg)
            if auth_data.get("type") == "auth" and auth_data.get("token"):
                user_id = await _extract_user_id(auth_data["token"])
        except (asyncio.TimeoutError, ValueError, Exception):
            pass

        if not user_id:
            await websocket.close(code=4001, reason="Invalid token")
            return

        # Connection already accepted, register directly (with limit check)
        if user_id not in ws_manager._connections:
            ws_manager._connections[user_id] = []

        while len(ws_manager._connections[user_id]) >= MAX_CONNECTIONS_PER_USER:
            oldest = ws_manager._connections[user_id].pop(0)
            try:
                await oldest.close(code=4008, reason="Connection limit reached")
            except Exception:
                pass

        ws_manager._connections[user_id].append(websocket)
        logger.info("ws_connected", user_id=user_id, count=len(ws_manager._connections[user_id]))
    else:
        await ws_manager.connect(user_id, websocket)

    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text(
                    orjson.dumps({"event": "pong", "data": {}}).decode()
                )
    except WebSocketDisconnect:
        ws_manager.disconnect(user_id, websocket)
    except Exception:
        ws_manager.disconnect(user_id, websocket)

