"""
WebSocket endpoint and connection manager for real-time events.
Supports HITL notifications, anomaly alerts, and circuit breaker events.
"""
import json
import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from jose import JWTError, jwt
from app.config import get_settings
from app.logging_config import get_logger

logger = get_logger("websocket")
settings = get_settings()

router = APIRouter()


class WebSocketManager:
    """Manages WebSocket connections per user for real-time events."""

    def __init__(self):
        self._connections: dict[str, list[WebSocket]] = {}

    async def connect(self, user_id: str, websocket: WebSocket):
        await websocket.accept()
        if user_id not in self._connections:
            self._connections[user_id] = []
        self._connections[user_id].append(websocket)
        logger.info("ws_connected", user_id=user_id)

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
        message = json.dumps({"event": event, "data": data}, default=str)
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
        message = json.dumps({"event": event, "data": data}, default=str)
        for user_id in list(self._connections.keys()):
            for ws in self._connections.get(user_id, []):
                try:
                    await ws.send_text(message)
                except Exception:
                    pass


ws_manager = WebSocketManager()


def _extract_user_id(token: str) -> str | None:
    """Extract user_id from JWT token."""
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
        )
        return payload.get("sub")
    except JWTError:
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
        user_id = _extract_user_id(token)

    if not user_id:
        # Accept and wait for auth message
        await websocket.accept()
        try:
            first_msg = await asyncio.wait_for(websocket.receive_text(), timeout=5.0)
            auth_data = json.loads(first_msg)
            if auth_data.get("type") == "auth" and auth_data.get("token"):
                user_id = _extract_user_id(auth_data["token"])
        except (asyncio.TimeoutError, json.JSONDecodeError, Exception):
            pass

        if not user_id:
            await websocket.close(code=4001, reason="Invalid token")
            return

        # Connection already accepted, register directly
        if user_id not in ws_manager._connections:
            ws_manager._connections[user_id] = []
        ws_manager._connections[user_id].append(websocket)
        logger.info("ws_connected", user_id=user_id)
    else:
        await ws_manager.connect(user_id, websocket)

    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text(
                    json.dumps({"event": "pong", "data": {}})
                )
    except WebSocketDisconnect:
        ws_manager.disconnect(user_id, websocket)
    except Exception:
        ws_manager.disconnect(user_id, websocket)
