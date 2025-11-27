#!/usr/bin/env python3
"""
WebSocket Proxy Client for Payment Gateway

Connects local payment gateway to cloud WebSocket server.
Forwards JSON messages bidirectionally between WS server and local HTTP gateway.
"""

import asyncio
import websockets
import aiohttp
import json
import logging
import sys
import yaml
import time
from datetime import datetime
from typing import Optional, Dict, Any
from logging.handlers import RotatingFileHandler
from aiohttp import web
from urllib.parse import urlencode


class PaymentGatewayProxy:
    """
    WebSocket proxy client that bridges cloud server and local payment gateway.

    Key improvements in v1.0.0:
    - Support for both GET and POST requests (via Header-Http-Method)
    - Request/response correlation via request_id
    - Automatic conversion of body to query params for GET requests
    """

    def __init__(
        self,
        ws_url: str,
        ws_token: str,
        routing_config_path: str = "routing_config.yaml",
        log_level: str = "INFO",
        health_port: int = 9091
    ):
        self.ws_url = ws_url
        self.ws_token = ws_token
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.running = True
        self.start_time = time.time()
        self.health_port = health_port

        # HTTP session for gateway requests (reusable, with connection pooling)
        self.http_session: Optional[aiohttp.ClientSession] = None

        # Offline queue for messages when WS is disconnected (max 10)
        self.offline_queue: asyncio.Queue = asyncio.Queue(maxsize=10)

        # Load routing configuration
        self.routing_config = self._load_routing_config(routing_config_path)

        # Cache routes for faster lookup
        self.routes = self.routing_config.get('routes', {})
        self.default_route = self.routing_config.get('default')

        # Reconnection settings (exponential backoff)
        self.reconnect_delay = 1  # Start with 1 second
        self.reconnect_max_delay = 60  # Max 60 seconds
        self.reconnect_multiplier = 2

        # Setup logging with rotation (10MB max, 3 backups)
        log_file = f"proxy_{datetime.now().strftime('%Y%m%d')}.log"

        # Rotating file handler - prevents disk overflow
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=3
        )
        file_handler.setFormatter(
            logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        )

        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(
            logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        )

        # Configure root logger
        logging.basicConfig(
            level=getattr(logging, log_level.upper()),
            handlers=[file_handler, console_handler]
        )
        self.logger = logging.getLogger(__name__)

        # Statistics
        self.stats = {
            'messages_received': 0,
            'messages_sent': 0,
            'errors': 0,
            'reconnections': 0
        }

    def _load_routing_config(self, config_path: str) -> Dict[str, Any]:
        """Load routing configuration from YAML file"""
        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
                return config
        except FileNotFoundError:
            raise Exception(f"Routing config file not found: {config_path}")
        except yaml.YAMLError as e:
            raise Exception(f"Invalid YAML in routing config: {e}")

    async def connect_to_server(self) -> bool:
        """Establish WebSocket connection to cloud server"""
        try:
            full_url = f"{self.ws_url}?token={self.ws_token}"
            self.logger.info(f"Connecting to WS server: {self.ws_url}")

            self.websocket = await asyncio.wait_for(
                websockets.connect(
                    full_url,
                    ping_interval=20,
                    ping_timeout=10
                ),
                timeout=15.0
            )

            self.logger.info("✅ Connected to cloud server")
            # Reset reconnect delay on successful connection
            self.reconnect_delay = 1
            return True

        except asyncio.TimeoutError:
            self.logger.error("❌ Connection timeout")
            return False
        except Exception as e:
            self.logger.error(f"❌ Connection failed: {type(e).__name__}: {e}")
            return False

    def _get_gateway_route(self, operation_type: str) -> Optional[Dict[str, Any]]:
        """
        Get gateway route configuration for given operation type

        Args:
            operation_type: Operation type from Header-Operation-Type

        Returns:
            Route config dict with 'url' and 'timeout' or None if not found
        """
        # Try to find exact match
        if operation_type in self.routes:
            return self.routes[operation_type]

        # Try default route
        if self.default_route:
            return self.default_route

        # No route found
        return None

    async def _ensure_http_session(self):
        """Ensure HTTP session exists with connection pooling"""
        if self.http_session is None or self.http_session.closed:
            # Create connector with connection pooling
            connector = aiohttp.TCPConnector(
                limit=10,           # Max 10 connections total
                limit_per_host=5,   # Max 5 per gateway
                ttl_dns_cache=300   # Cache DNS for 5 minutes
            )
            self.http_session = aiohttp.ClientSession(connector=connector)

    async def send_to_gateway(
        self,
        message_data: Dict[str, Any],
        headers: Dict[str, str],
        gateway_url: str,
        gateway_timeout: int
    ) -> Dict[str, Any]:
        """
        Forward message to local payment gateway via HTTP

        Args:
            message_data: JSON message body
            headers: Request headers (contains http_method info)
            gateway_url: Target gateway URL
            gateway_timeout: Request timeout in seconds

        Returns:
            Response from gateway or error object
        """
        try:
            # Extract HTTP method from headers (default to POST)
            http_method = headers.get('header-http-method', 'POST').upper()

            self.logger.info(f"➡️  {http_method} {gateway_url}")
            self.logger.debug(f"   Payload: {json.dumps(message_data, ensure_ascii=False, indent=2)}")

            # Ensure session exists
            await self._ensure_http_session()

            # Prepare request based on HTTP method
            if http_method == 'GET':
                # GET: Convert body to query parameters
                query_string = urlencode(message_data) if message_data else ""
                full_url = f"{gateway_url}?{query_string}" if query_string else gateway_url

                async with self.http_session.get(
                    full_url,
                    headers={'Content-Type': 'application/json'},
                    timeout=aiohttp.ClientTimeout(total=gateway_timeout)
                ) as response:
                    return await self._handle_gateway_response(response, http_method)

            else:
                # POST (or other methods): Send JSON in body
                async with self.http_session.request(
                    http_method,
                    gateway_url,
                    json=message_data,
                    headers={'Content-Type': 'application/json'},
                    timeout=aiohttp.ClientTimeout(total=gateway_timeout)
                ) as response:
                    return await self._handle_gateway_response(response, http_method)

        except asyncio.TimeoutError:
            self.logger.error(f"⏱️ Gateway timeout after {gateway_timeout}s")
            self.stats['errors'] += 1
            return {
                'status': 'error',
                'error': 'timeout',
                'message': f'Gateway timeout after {gateway_timeout}s'
            }
        except aiohttp.ClientConnectorError as e:
            self.logger.error(f"❌ Cannot connect to gateway: {e}")
            self.stats['errors'] += 1
            return {
                'status': 'error',
                'error': 'connection_refused',
                'message': f'Cannot connect to gateway: {str(e)}'
            }
        except Exception as e:
            self.logger.error(f"❌ Gateway error: {type(e).__name__}: {e}")
            self.stats['errors'] += 1
            return {
                'status': 'error',
                'error': 'other',
                'message': str(e)
            }

    async def _handle_gateway_response(self, response: aiohttp.ClientResponse, http_method: str) -> Dict[str, Any]:
        """Handle HTTP response from gateway"""
        if response.status == 200:
            result = await response.json()
            self.logger.info(f"✅ Gateway response: {http_method} {response.status}")
            self.logger.debug(f"   Response: {json.dumps(result, ensure_ascii=False, indent=2)}")
            return result
        else:
            error_text = await response.text()
            self.logger.error(f"❌ Gateway error: {http_method} {response.status}")
            self.logger.error(f"   Error: {error_text}")
            return {
                'status': 'error',
                'error': 'http_error',
                'message': f"HTTP {response.status}: {error_text}"
            }

    async def handle_message(self, message: str):
        """Handle incoming message from WS server"""
        try:
            # Parse JSON from WS server
            data = json.loads(message)

            # Extract request_id (CRITICAL for matching response!)
            request_id = data.get('request_id')
            if not request_id:
                self.logger.warning("⚠️  Message without request_id - cannot correlate response")

            # Extract routing headers from headers object
            headers = data.get('headers', {})
            kiosk_id = headers.get('header-kiosk-id')
            operation_type = headers.get('header-operation-type')

            # Log summary
            self.logger.info(f"📥 Received: {operation_type or 'unknown'} from kiosk {kiosk_id or 'unknown'} (request_id: {request_id})")
            self.logger.debug(f"Full message: {json.dumps(data, ensure_ascii=False, indent=2)}")

            # Count messages
            self.stats['messages_received'] += 1

            # Check if operation type is present
            if not operation_type:
                error_response = {
                    'request_id': request_id,  # Include request_id!
                    'status': 'error',
                    'error': 'missing_header',
                    'message': 'Header-Operation-Type is required'
                }
                self.logger.error("❌ Missing Header-Operation-Type")
                await self._send_or_queue(json.dumps(error_response))
                return

            # Get route for operation type
            route = self._get_gateway_route(operation_type)

            if not route:
                error_response = {
                    'request_id': request_id,  # Include request_id!
                    'status': 'error',
                    'error': 'route_not_found',
                    'message': f'No route configured for operation type: {operation_type}'
                }
                self.logger.error(f"❌ Route not found for operation type: {operation_type}")
                await self._send_or_queue(json.dumps(error_response))
                self.stats['errors'] += 1
                return

            # Extract body for gateway
            message_to_send = data.get('body', {})

            # Forward to gateway based on route
            response = await self.send_to_gateway(
                message_to_send,
                headers,  # Pass headers (contains http_method)
                route['url'],
                route['timeout']
            )

            # Add request_id to response (CRITICAL!)
            response['request_id'] = request_id

            # Send response back to WS server
            await self._send_or_queue(json.dumps(response))

            self.logger.info(f"📤 Sent response: {response.get('status', 'unknown')} (request_id: {request_id})")
            self.logger.debug(f"Full response: {json.dumps(response, ensure_ascii=False, indent=2)}")

        except json.JSONDecodeError as e:
            self.logger.error(f"❌ Invalid JSON from server: {e}")
            self.stats['errors'] += 1
            # Send error back to server
            error_response = {
                'status': 'error',
                'error': 'invalid_json',
                'message': f'Failed to parse JSON: {str(e)}'
            }
            await self._send_or_queue(json.dumps(error_response))

        except Exception as e:
            self.logger.error(f"❌ Error handling message: {type(e).__name__}: {e}")
            self.stats['errors'] += 1
            # Always send error response to server
            error_response = {
                'request_id': request_id if 'request_id' in locals() else None,
                'status': 'error',
                'error': 'processing_error',
                'message': f'Failed to process message: {str(e)}'
            }
            await self._send_or_queue(json.dumps(error_response))

    async def _send_or_queue(self, message: str):
        """Send message to WS server or queue if disconnected"""
        if self.websocket and self.websocket.state.name == "OPEN":
            try:
                await self.websocket.send(message)
                self.stats['messages_sent'] += 1
                return True
            except Exception as e:
                self.logger.error(f"❌ Failed to send: {e}")

        # WS disconnected or send failed - try to queue
        try:
            self.offline_queue.put_nowait(message)
            queue_size = self.offline_queue.qsize()
            self.logger.warning(f"📦 WS disconnected, queued message ({queue_size}/10)")
            return False
        except asyncio.QueueFull:
            self.logger.error("⚠️ Queue full (10/10), dropping message")
            self.stats['errors'] += 1
            return False

    async def _flush_queue(self):
        """Flush offline queue after reconnection"""
        if self.offline_queue.empty():
            return

        initial_size = self.offline_queue.qsize()
        self.logger.info(f"📤 Flushing {initial_size} queued messages...")

        while not self.offline_queue.empty():
            try:
                queued_msg = self.offline_queue.get_nowait()
                await self.websocket.send(queued_msg)
                self.stats['messages_sent'] += 1
                remaining = self.offline_queue.qsize()
                self.logger.info(f"✅ Sent queued message ({remaining} remaining)")
            except Exception as e:
                self.logger.error(f"❌ Failed to send queued message: {e}")
                # Put it back for retry
                try:
                    self.offline_queue.put_nowait(queued_msg)
                except asyncio.QueueFull:
                    pass
                break

    async def receive_messages(self):
        """Receive and process messages from WS server"""
        # First, flush any queued messages from previous disconnect
        await self._flush_queue()

        try:
            async for message in self.websocket:
                if not self.running:
                    break
                await self.handle_message(message)

        except websockets.exceptions.ConnectionClosed:
            self.logger.warning("⚠️  WebSocket connection closed")
        except Exception as e:
            self.logger.error(f"❌ Error receiving messages: {e}")

    def print_stats(self, periodic: bool = False):
        """Print statistics"""
        title = "⏰ Hourly Statistics" if periodic else "📊 Final Statistics"
        self.logger.info("=" * 60)
        self.logger.info(f"{title}:")
        self.logger.info(f"   Messages received: {self.stats['messages_received']}")
        self.logger.info(f"   Messages sent: {self.stats['messages_sent']}")
        self.logger.info(f"   Errors: {self.stats['errors']}")
        self.logger.info(f"   Reconnections: {self.stats['reconnections']}")
        self.logger.info("=" * 60)

    async def _periodic_stats(self):
        """Print statistics every hour"""
        while self.running:
            await asyncio.sleep(3600)  # 1 hour
            if self.running:
                self.print_stats(periodic=True)

    async def _health_handler(self, request):
        """HTTP health check endpoint handler"""
        ws_connected = bool(self.websocket and self.websocket.state.name == "OPEN")
        status = 'healthy' if ws_connected else 'disconnected'

        return web.json_response({
            'status': status,
            'ws_connected': ws_connected,
            'uptime_seconds': round(time.time() - self.start_time, 2),
            'stats': self.stats,
            'queue_size': self.offline_queue.qsize(),
            'routes_configured': len(self.routes)
        })

    async def _start_health_server(self):
        """Start HTTP health check server"""
        app = web.Application()
        app.router.add_get('/health', self._health_handler)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, 'localhost', self.health_port)
        await site.start()

        self.logger.info(f"🏥 Health check server started on http://localhost:{self.health_port}/health")
        return runner

    async def run(self):
        """Main run loop with automatic reconnection and exponential backoff"""
        self.logger.info("🚀 Payment Gateway Proxy starting...")
        self.logger.info(f"   WS Server: {self.ws_url}")
        self.logger.info(f"   Routing config loaded with {len(self.routes)} routes")

        # Start health check server
        health_runner = await self._start_health_server()

        # Start periodic statistics task
        stats_task = asyncio.create_task(self._periodic_stats())

        while self.running:
            try:
                if await self.connect_to_server():
                    # Connection successful, start receiving messages
                    await self.receive_messages()

                    # Connection lost, will reconnect
                    if self.running:
                        self.stats['reconnections'] += 1
                        self.logger.warning(
                            f"⚠️  Connection lost. Reconnecting in {self.reconnect_delay}s..."
                        )
                        await asyncio.sleep(self.reconnect_delay)

                        # Exponential backoff
                        self.reconnect_delay = min(
                            self.reconnect_delay * self.reconnect_multiplier,
                            self.reconnect_max_delay
                        )
                else:
                    # Connection failed
                    if self.running:
                        self.logger.error(
                            f"❌ Connection failed. Retrying in {self.reconnect_delay}s..."
                        )
                        await asyncio.sleep(self.reconnect_delay)

                        # Exponential backoff
                        self.reconnect_delay = min(
                            self.reconnect_delay * self.reconnect_multiplier,
                            self.reconnect_max_delay
                        )

            except KeyboardInterrupt:
                self.logger.info("⚠️  Interrupted by user")
                self.running = False
                break
            except Exception as e:
                self.logger.error(f"❌ Unexpected error: {e}")
                if self.running:
                    await asyncio.sleep(self.reconnect_delay)

        # Cancel periodic stats task
        stats_task.cancel()
        try:
            await stats_task
        except asyncio.CancelledError:
            pass

        # Stop health check server
        try:
            await health_runner.cleanup()
            self.logger.info("🏥 Health check server stopped")
        except Exception as e:
            self.logger.error(f"Error stopping health server: {e}")

        # Cleanup
        if self.websocket and self.websocket.state.name == "OPEN":
            try:
                await self.websocket.close()
            except Exception as e:
                self.logger.error(f"Error closing websocket: {e}")

        # Close HTTP session
        if self.http_session and not self.http_session.closed:
            try:
                await self.http_session.close()
            except Exception as e:
                self.logger.error(f"Error closing HTTP session: {e}")

        self.print_stats(periodic=False)
        self.logger.info("👋 Payment Gateway Proxy stopped")

    def stop(self):
        """Stop the proxy gracefully"""
        self.logger.info("🛑 Stopping proxy...")
        self.running = False
