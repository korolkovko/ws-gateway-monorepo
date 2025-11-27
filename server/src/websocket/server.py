import asyncio
import json
import uuid
from typing import Dict, Optional
from fastapi import WebSocket, WebSocketDisconnect
import structlog

from src.auth import jwt_handler
from src.redis_client import redis_client
from src.monitoring.metrics import metrics
from src.config.settings import settings

logger = structlog.get_logger()


async def _log_to_telegram(func, *args, **kwargs):
    """Helper to safely log to Telegram without blocking"""
    try:
        from src.telegram_bot.logger import telegram_log_handler
        await func(*args, **kwargs)
    except Exception as e:
        logger.error("telegram_log_failed", error=str(e))


class WebSocketManager:
    def __init__(self):
        # Active WebSocket connections: {kiosk_id: WebSocket}
        self.active_connections: Dict[str, WebSocket] = {}
        # Pending responses: {request_id: asyncio.Future}
        self.pending_responses: Dict[str, asyncio.Future] = {}

    async def connect(self, websocket: WebSocket, kiosk_id: str):
        """Register a new WebSocket connection"""
        import time

        # Check if kiosk is already connected
        if kiosk_id in self.active_connections:
            old_websocket = self.active_connections[kiosk_id]

            # If duplicate connections are allowed, skip the check and replace old connection
            if settings.allow_duplicate_connections:
                logger.info("allowing_duplicate_connection", kiosk_id=kiosk_id, reason="allow_duplicate_connections_enabled")

                # Remove old connection from active_connections FIRST
                # This prevents server from routing new messages to old connection
                del self.active_connections[kiosk_id]

                # Accept NEW connection and register it BEFORE closing old
                # This minimizes the window where kiosk appears offline
                await websocket.accept()
                self.active_connections[kiosk_id] = websocket
                await redis_client.set_kiosk_online(kiosk_id)

                # Store connection timestamp for uptime tracking
                await redis_client.redis.set(f"kiosk:{kiosk_id}:connected_at", str(time.time()))

                metrics.increment_active_connections(kiosk_id)

                # NOW close old connection (it's already removed from active_connections)
                # Old connection will cleanup itself in finally block
                try:
                    await old_websocket.close(code=1000, reason="Replaced by new connection")
                except:
                    pass

                logger.info("kiosk_connected", kiosk_id=kiosk_id, replaced_old=True)

                # Log connection event to history
                await redis_client.log_connection_event(kiosk_id, "connected")

                # Log to Telegram
                from src.telegram_bot.logger import telegram_log_handler
                asyncio.create_task(telegram_log_handler.log_connection(kiosk_id, "connected"))

                return True
            else:
                # Check if old connection is still alive by checking websocket state
                # Don't send messages - just check connection state
                if not old_websocket.client_state.name == 'CLOSED':
                    # Old connection appears alive - reject new connection
                    logger.warning("duplicate_connection_attempt", kiosk_id=kiosk_id, reason="existing_connection_alive")

                    # Notify Telegram about duplicate connection
                    from src.telegram_bot.logger import telegram_log_handler
                    asyncio.create_task(telegram_log_handler.log_duplicate_connection(kiosk_id))

                    await websocket.close(code=1008, reason="Kiosk already connected")
                    return False
                else:
                    # Old connection is dead - clean it up and accept new one
                    logger.info("replacing_dead_connection", kiosk_id=kiosk_id)
                    try:
                        await old_websocket.close()
                    except:
                        pass
                    # Clean up old connection data
                    if kiosk_id in self.active_connections:
                        del self.active_connections[kiosk_id]

        await websocket.accept()
        self.active_connections[kiosk_id] = websocket
        await redis_client.set_kiosk_online(kiosk_id)

        # Store connection timestamp for uptime tracking
        await redis_client.redis.set(f"kiosk:{kiosk_id}:connected_at", str(time.time()))

        metrics.increment_active_connections(kiosk_id)

        logger.info("kiosk_connected", kiosk_id=kiosk_id)

        # Log connection event to history
        await redis_client.log_connection_event(kiosk_id, "connected")

        # Log to Telegram
        from src.telegram_bot.logger import telegram_log_handler
        asyncio.create_task(telegram_log_handler.log_connection(kiosk_id, "connected"))

        return True

    async def disconnect(self, kiosk_id: str, websocket: WebSocket = None):
        """Remove WebSocket connection"""
        # Only remove if this is the current active connection (prevent race condition)
        if kiosk_id in self.active_connections:
            if websocket is None or self.active_connections[kiosk_id] == websocket:
                del self.active_connections[kiosk_id]
                await redis_client.set_kiosk_offline(kiosk_id)
                metrics.decrement_active_connections(kiosk_id)
                logger.info("kiosk_disconnected", kiosk_id=kiosk_id)

                # Log disconnection event to history
                asyncio.create_task(redis_client.log_connection_event(kiosk_id, "disconnected"))

                # Log to Telegram
                from src.telegram_bot.logger import telegram_log_handler
                asyncio.create_task(telegram_log_handler.log_connection(kiosk_id, "disconnected"))
            else:
                logger.info("skip_disconnect", kiosk_id=kiosk_id, reason="not_current_connection")

    def is_connected(self, kiosk_id: str) -> bool:
        """Check if kiosk is connected"""
        return kiosk_id in self.active_connections

    async def send_and_wait(self, kiosk_id: str, message: dict, timeout: int) -> Optional[dict]:
        """
        Send message to kiosk and wait for response
        Returns kiosk response or None if timeout/error
        """
        if kiosk_id not in self.active_connections:
            logger.warning("kiosk_not_connected", kiosk_id=kiosk_id)
            return None

        websocket = self.active_connections[kiosk_id]

        # Generate UUID for request tracking (critical for parallel requests!)
        request_id = str(uuid.uuid4())

        # Add request_id to message before sending
        message["request_id"] = request_id

        future = asyncio.Future()
        self.pending_responses[request_id] = future

        try:
            # Send message to kiosk (now includes request_id)
            await websocket.send_json(message)
            metrics.increment_messages_sent(kiosk_id)

            logger.info("message_sent_to_kiosk", kiosk_id=kiosk_id, request_id=request_id)

            # Wait for response with timeout
            response = await asyncio.wait_for(future, timeout=timeout)
            metrics.increment_messages_received(kiosk_id)

            logger.info("response_received_from_kiosk", kiosk_id=kiosk_id, request_id=request_id)

            return response

        except asyncio.TimeoutError:
            logger.error("kiosk_response_timeout", kiosk_id=kiosk_id, request_id=request_id, timeout=timeout)
            metrics.increment_errors("timeout")
            return None

        except Exception as e:
            logger.error("error_sending_to_kiosk", kiosk_id=kiosk_id, error=str(e))
            metrics.increment_errors("send_error")
            return None

        finally:
            # Clean up pending response
            if request_id in self.pending_responses:
                del self.pending_responses[request_id]

    async def handle_kiosk_message(self, kiosk_id: str, message: dict):
        """Handle incoming message from kiosk (response to our request)"""
        # Extract request_id from response
        request_id = message.get("request_id")

        if not request_id:
            logger.warning("kiosk_response_without_request_id", kiosk_id=kiosk_id)
            return

        # Match by exact request_id (supports parallel requests!)
        if request_id in self.pending_responses:
            future = self.pending_responses[request_id]
            if not future.done():
                future.set_result(message)
        else:
            logger.warning("unknown_request_id", kiosk_id=kiosk_id, request_id=request_id)


    async def handle_websocket(self, websocket: WebSocket, token: str):
        """Handle WebSocket connection lifecycle"""
        from fastapi import WebSocketException, status

        logger.info("websocket_connection_attempt", client=websocket.client)

        # Verify JWT token BEFORE accepting connection
        kiosk_id = jwt_handler.verify_token(token)
        if not kiosk_id:
            logger.warning("invalid_token", token=token[:20], client=websocket.client)
            raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid token")

        logger.info("token_verified", kiosk_id=kiosk_id)

        # Check if kiosk exists and is enabled BEFORE accepting
        if not await redis_client.kiosk_exists(kiosk_id):
            logger.warning("kiosk_not_found", kiosk_id=kiosk_id)
            raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="Kiosk not found")

        if not await redis_client.is_kiosk_enabled(kiosk_id):
            logger.warning("kiosk_disabled", kiosk_id=kiosk_id)
            raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="Kiosk disabled")

        # Verify token matches stored token BEFORE accepting
        stored_token = await redis_client.get_kiosk_token(kiosk_id)
        if stored_token != token:
            logger.warning("token_mismatch", kiosk_id=kiosk_id)
            raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="Token mismatch")

        logger.info("attempting_connect", kiosk_id=kiosk_id)

        # Connect kiosk
        connected = await self.connect(websocket, kiosk_id)
        if not connected:
            logger.warning("connection_rejected", kiosk_id=kiosk_id)
            return

        try:
            # Keep connection alive and handle incoming messages
            while True:
                # Receive message from kiosk
                data = await websocket.receive_text()

                try:
                    message = json.loads(data)
                    # Handle regular message from kiosk
                    await self.handle_kiosk_message(kiosk_id, message)

                except json.JSONDecodeError:
                    logger.error("invalid_json_from_kiosk", kiosk_id=kiosk_id, data=data)

        except WebSocketDisconnect as e:
            logger.warning("websocket_disconnect", kiosk_id=kiosk_id, code=getattr(e, 'code', 'unknown'), reason=getattr(e, 'reason', 'unknown'))
        except Exception as e:
            logger.error("websocket_error", kiosk_id=kiosk_id, error=str(e), error_type=type(e).__name__)
        finally:
            logger.info("cleaning_up_connection", kiosk_id=kiosk_id)
            await self.disconnect(kiosk_id, websocket)


# Global WebSocket manager instance
ws_manager = WebSocketManager()
