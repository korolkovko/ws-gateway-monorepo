from fastapi import APIRouter, HTTPException, WebSocket, Query, Request
from typing import Any, Dict
import structlog
import time
import asyncio

from src.websocket import ws_manager
from src.redis_client import redis_client
from src.monitoring.metrics import metrics
from src.config import settings

logger = structlog.get_logger()

router = APIRouter()


@router.post("/send")
async def send_message(request: Request, message: Dict[str, Any]) -> Dict[str, Any]:
    """
    Send message to kiosk via WebSocket
    Expects 'Header-Kiosk-Id' header for routing
    Forwards full request (headers + body) to kiosk
    Returns kiosk response or error
    """
    start_time = time.time()

    # Extract kiosk_id from header (case-insensitive)
    kiosk_id = request.headers.get("Header-Kiosk-Id")
    if not kiosk_id:
        raise HTTPException(status_code=400, detail="Missing Header-Kiosk-Id header")

    # Extract operation type from header
    operation_type = request.headers.get("Header-Operation-Type")

    logger.info("send_request_received", kiosk_id=kiosk_id, operation_type=operation_type)

    # Check if kiosk exists
    kiosk_exists = await redis_client.kiosk_exists(kiosk_id)
    logger.info("kiosk_exists_check", kiosk_id=kiosk_id, exists=kiosk_exists)

    if not kiosk_exists:
        # Log all kiosks for debugging
        all_kiosks = await redis_client.get_all_kiosks()
        logger.warning("kiosk_not_found", kiosk_id=kiosk_id, all_kiosks=[k.get('id') for k in all_kiosks])
        return {
            "status": "error",
            "error": "kiosk_not_found",
            "kiosk_id": kiosk_id
        }

    # Check if kiosk is enabled
    if not await redis_client.is_kiosk_enabled(kiosk_id):
        logger.warning("kiosk_disabled", kiosk_id=kiosk_id)
        return {
            "status": "error",
            "error": "kiosk_disabled",
            "kiosk_id": kiosk_id
        }

    # Check if kiosk is online
    if not ws_manager.is_connected(kiosk_id):
        logger.warning("kiosk_offline", kiosk_id=kiosk_id)
        metrics.increment_errors("kiosk_offline")
        return {
            "status": "error",
            "error": "kiosk_offline",
            "kiosk_id": kiosk_id
        }

    # Prepare full request payload (headers + body)
    # Filter sensitive headers to prevent token leakage in logs
    SENSITIVE_HEADERS = {
        "authorization", "cookie", "x-api-key",
        "x-auth-token", "api-key", "secret", "token"
    }

    headers_dict = {
        k: ("***REDACTED***" if k.lower() in SENSITIVE_HEADERS else v)
        for k, v in request.headers.items()
    }

    full_request = {
        "headers": headers_dict,
        "body": message
    }

    # Log request to Telegram
    from src.telegram_bot.logger import telegram_log_handler
    http_method = request.headers.get('header-http-method', 'POST').upper()
    asyncio.create_task(telegram_log_handler.log_request(kiosk_id, message, operation_type, http_method))

    # Send full request to kiosk and wait for response
    response = await ws_manager.send_and_wait(
        kiosk_id=kiosk_id,
        message=full_request,  # Send headers + body
        timeout=settings.kiosk_response_timeout
    )

    # Calculate latency
    latency = time.time() - start_time
    metrics.observe_latency(kiosk_id, latency)

    # Track stats in Redis
    await redis_client.increment_requests()
    await redis_client.add_latency(latency)

    if response is None:
        # Timeout occurred
        logger.error("kiosk_timeout", kiosk_id=kiosk_id, latency=latency)
        await redis_client.increment_errors()
        asyncio.create_task(telegram_log_handler.log_error("timeout", kiosk_id, f"Latency: {latency:.3f}s"))
        return {
            "status": "error",
            "error": "timeout",
            "kiosk_id": kiosk_id
        }

    # Return kiosk response as-is
    logger.info("response_sent_to_backend", kiosk_id=kiosk_id, latency=latency)

    # Log response to Telegram
    asyncio.create_task(telegram_log_handler.log_response(kiosk_id, response, latency, operation_type))

    return response


@router.get("/health")
@router.head("/health")
async def health_check() -> Dict[str, Any]:
    """Health check endpoint for monitoring"""
    try:
        # Check Redis connection
        redis_connected = await redis_client.is_connected()

        # Get kiosk statistics
        online_kiosks = await redis_client.get_online_kiosks()
        all_kiosks = await redis_client.get_all_kiosks()

        # Update metrics
        metrics.set_total_kiosks(len(all_kiosks))

        return {
            "status": "healthy" if redis_connected else "degraded",
            "redis": "connected" if redis_connected else "disconnected",
            "active_kiosks": len(online_kiosks),
            "total_kiosks": len(all_kiosks)
        }
    except Exception as e:
        logger.error("health_check_failed", error=str(e))
        return {
            "status": "unhealthy",
            "error": str(e)
        }


@router.get("/metrics")
async def get_metrics():
    """Prometheus metrics endpoint"""
    from fastapi.responses import Response

    # Sync Redis stats before generating metrics
    await metrics.sync_redis_stats()

    return Response(content=metrics.get_metrics(), media_type="text/plain")


@router.get("/dashboard")
async def dashboard():
    """Web dashboard with real-time metrics"""
    from fastapi.responses import HTMLResponse

    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>WebSocket Server Dashboard</title>
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }

            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: #333;
                padding: 20px;
                min-height: 100vh;
            }

            .container {
                max-width: 1400px;
                margin: 0 auto;
            }

            header {
                background: white;
                padding: 30px;
                border-radius: 15px;
                box-shadow: 0 10px 30px rgba(0,0,0,0.2);
                margin-bottom: 30px;
            }

            h1 {
                color: #667eea;
                font-size: 2.5em;
                margin-bottom: 10px;
            }

            .subtitle {
                color: #666;
                font-size: 1.1em;
            }

            .stats-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                gap: 20px;
                margin-bottom: 30px;
            }

            .stat-card {
                background: white;
                padding: 25px;
                border-radius: 15px;
                box-shadow: 0 5px 20px rgba(0,0,0,0.1);
                transition: transform 0.3s ease;
            }

            .stat-card:hover {
                transform: translateY(-5px);
            }

            .stat-label {
                color: #666;
                font-size: 0.9em;
                text-transform: uppercase;
                letter-spacing: 1px;
                margin-bottom: 10px;
            }

            .stat-value {
                font-size: 3em;
                font-weight: bold;
                color: #667eea;
            }

            .kiosks-section {
                background: white;
                padding: 30px;
                border-radius: 15px;
                box-shadow: 0 5px 20px rgba(0,0,0,0.1);
                margin-bottom: 30px;
            }

            .kiosks-section h2 {
                color: #667eea;
                margin-bottom: 20px;
                font-size: 1.8em;
            }

            .kiosk-list {
                display: grid;
                gap: 15px;
            }

            .kiosk-item {
                display: flex;
                align-items: center;
                justify-content: space-between;
                padding: 15px 20px;
                background: #f8f9fa;
                border-radius: 10px;
                border-left: 4px solid #667eea;
            }

            .kiosk-item.offline {
                border-left-color: #e74c3c;
                opacity: 0.6;
            }

            .kiosk-info {
                display: flex;
                align-items: center;
                gap: 15px;
            }

            .status-dot {
                width: 12px;
                height: 12px;
                border-radius: 50%;
                background: #2ecc71;
                box-shadow: 0 0 10px #2ecc71;
                animation: pulse 2s infinite;
            }

            .status-dot.offline {
                background: #e74c3c;
                box-shadow: 0 0 10px #e74c3c;
                animation: none;
            }

            @keyframes pulse {
                0%, 100% { opacity: 1; }
                50% { opacity: 0.5; }
            }

            .kiosk-name {
                font-weight: 600;
                font-size: 1.1em;
            }

            .kiosk-stats {
                display: flex;
                gap: 20px;
                color: #666;
                font-size: 0.9em;
            }

            .refresh-info {
                text-align: center;
                color: white;
                margin-top: 20px;
                font-size: 0.9em;
            }

            .loading {
                text-align: center;
                padding: 40px;
                color: #666;
            }

            .error {
                background: #fee;
                border: 1px solid #fcc;
                padding: 20px;
                border-radius: 10px;
                color: #c33;
                margin: 20px 0;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <header>
                <h1>🚀 WebSocket Server Dashboard</h1>
                <p class="subtitle">Real-time monitoring for kiosk connections</p>
            </header>

            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-label">Online Kiosks</div>
                    <div class="stat-value" id="online-kiosks">-</div>
                </div>

                <div class="stat-card">
                    <div class="stat-label">Total Requests</div>
                    <div class="stat-value" id="total-requests" style="font-size: 2.5em;">-</div>
                </div>

                <div class="stat-card">
                    <div class="stat-label">Avg Latency</div>
                    <div class="stat-value" id="avg-latency">-<span class="stat-unit">ms</span></div>
                </div>

                <div class="stat-card">
                    <div class="stat-label">Errors</div>
                    <div class="stat-value" id="total-errors" style="font-size: 2.5em; color: #e74c3c;">-</div>
                </div>

                <div class="stat-card">
                    <div class="stat-label">Requests/Min</div>
                    <div class="stat-value" id="requests-per-min" style="font-size: 2.5em;">-</div>
                </div>

                <div class="stat-card">
                    <div class="stat-label">Server Status</div>
                    <div class="stat-value" id="server-status" style="font-size: 2em;">🟢</div>
                </div>
            </div>

            <div class="kiosks-section">
                <h2>📡 Kiosks Status</h2>
                <div id="kiosks-list" class="kiosk-list">
                    <div class="loading">Loading kiosks...</div>
                </div>
            </div>

            <div class="kiosks-section">
                <h2>📜 Connection History</h2>
                <div id="history-list" class="kiosk-list">
                    <div class="loading">Loading history...</div>
                </div>
            </div>

            <div class="refresh-info">
                Auto-refresh every 3 seconds • Last update: <span id="last-update">-</span>
            </div>
        </div>

        <script>
            function formatUptime(seconds) {
                const hours = Math.floor(seconds / 3600);
                const minutes = Math.floor((seconds % 3600) / 60);
                const secs = seconds % 60;
                if (hours > 0) return `${hours}h ${minutes}m`;
                if (minutes > 0) return `${minutes}m ${secs}s`;
                return `${secs}s`;
            }

            async function fetchDashboardData() {
                try {
                    const [healthRes, kiosksRes, statsRes, historyRes] = await Promise.all([
                        fetch('/health'),
                        fetch('/api/kiosks'),
                        fetch('/api/stats'),
                        fetch('/api/history')
                    ]);

                    const health = await healthRes.json();
                    const kiosks = await kiosksRes.json();
                    const stats = await statsRes.json();
                    const history = await historyRes.json();

                    // Update stats
                    document.getElementById('online-kiosks').textContent = health.active_kiosks || 0;
                    document.getElementById('total-requests').textContent = Math.floor(stats.requests_total || 0);
                    document.getElementById('avg-latency').innerHTML = Math.floor((stats.avg_latency || 0) * 1000) + '<span class="stat-unit">ms</span>';
                    document.getElementById('total-errors').textContent = Math.floor(stats.errors_total || 0);
                    document.getElementById('requests-per-min').textContent = (stats.requests_per_minute || 0).toFixed(1);
                    document.getElementById('server-status').textContent = health.status === 'healthy' ? '🟢' : '🟡';

                    // Update kiosks list
                    const kiosksList = document.getElementById('kiosks-list');
                    if (kiosks.kiosks && kiosks.kiosks.length > 0) {
                        kiosksList.innerHTML = kiosks.kiosks.map(kiosk => `
                            <div class="kiosk-item ${kiosk.online ? '' : 'offline'}">
                                <div class="kiosk-info">
                                    <div class="status-dot ${kiosk.online ? '' : 'offline'}"></div>
                                    <div class="kiosk-name">${kiosk.name || kiosk.id}</div>
                                </div>
                                <div class="kiosk-stats">
                                    <span>ID: ${kiosk.id}</span>
                                    <span>${kiosk.online ? '🟢 Online' : '🔴 Offline'}</span>
                                    ${kiosk.online && kiosk.uptime ? '<span>⏱️ ' + formatUptime(kiosk.uptime) + '</span>' : ''}
                                    ${kiosk.enabled ? '' : '<span>⚠️ Disabled</span>'}
                                </div>
                            </div>
                        `).join('');
                    } else {
                        kiosksList.innerHTML = '<div class="loading">No kiosks registered</div>';
                    }

                    // Update connection history
                    const historyList = document.getElementById('history-list');
                    if (history.history && history.history.length > 0) {
                        historyList.innerHTML = history.history.map(event => {
                            const date = new Date(event.timestamp * 1000);
                            const timeStr = date.toLocaleTimeString();
                            const icon = event.event === 'connected' ? '🟢' : '🔴';
                            const eventText = event.event === 'connected' ? 'Connected' : 'Disconnected';

                            return `
                                <div class="kiosk-item" style="border-left-color: ${event.event === 'connected' ? '#2ecc71' : '#e74c3c'};">
                                    <div class="kiosk-info">
                                        <span>${icon}</span>
                                        <div class="kiosk-name">Kiosk ${event.kiosk_id}</div>
                                    </div>
                                    <div class="kiosk-stats">
                                        <span>${eventText}</span>
                                        <span>${timeStr}</span>
                                    </div>
                                </div>
                            `;
                        }).join('');
                    } else {
                        historyList.innerHTML = '<div class="loading">No connection history yet</div>';
                    }

                    document.getElementById('last-update').textContent = new Date().toLocaleTimeString();

                } catch (error) {
                    console.error('Error fetching data:', error);
                    document.getElementById('kiosks-list').innerHTML =
                        '<div class="error">Error loading data. Please refresh the page.</div>';
                }
            }

            fetchDashboardData();
            setInterval(fetchDashboardData, 3000);
        </script>
    </body>
    </html>
    """

    return HTMLResponse(content=html_content)


@router.get("/api/kiosks")
async def get_kiosks():
    """API endpoint to get all kiosks with their status"""
    try:
        all_kiosks = await redis_client.get_all_kiosks()
        online_kiosks = await redis_client.get_online_kiosks()  # Returns list of IDs (strings)

        # Mark kiosks as online/offline and add uptime
        for kiosk in all_kiosks:
            kiosk['online'] = kiosk['id'] in online_kiosks

            # Get connection timestamp for uptime
            if kiosk['online']:
                uptime_key = f"kiosk:{kiosk['id']}:connected_at"
                connected_at = await redis_client.redis.get(uptime_key)
                if connected_at:
                    import time
                    uptime_seconds = int(time.time()) - int(float(connected_at))
                    kiosk['uptime'] = uptime_seconds
                else:
                    kiosk['uptime'] = 0
            else:
                kiosk['uptime'] = 0

        return {
            "kiosks": all_kiosks,
            "total": len(all_kiosks),
            "online": len(online_kiosks)
        }
    except Exception as e:
        logger.error("get_kiosks_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/stats")
async def get_stats():
    """API endpoint to get server statistics from Redis"""
    try:
        stats = await redis_client.get_stats()

        # Get server start time for requests/min calculation
        server_start = await redis_client.redis.get("stats:server_start_time")
        if server_start:
            import time
            uptime_minutes = (time.time() - float(server_start)) / 60
            stats["requests_per_minute"] = round(stats["requests_total"] / max(1, uptime_minutes), 1)
        else:
            stats["requests_per_minute"] = 0

        return stats
    except Exception as e:
        logger.error("get_stats_failed", error=str(e))
        return {"requests_total": 0, "errors_total": 0, "avg_latency": 0, "requests_per_minute": 0}


@router.get("/api/history")
async def get_history():
    """API endpoint to get connection history"""
    try:
        history = await redis_client.get_connection_history(limit=20)
        return {"history": history}
    except Exception as e:
        logger.error("get_history_failed", error=str(e))
        return {"history": []}


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = Query(...)):
    """WebSocket endpoint for kiosk connections"""
    await ws_manager.handle_websocket(websocket, token)
