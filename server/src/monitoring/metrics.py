from prometheus_client import Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST
import structlog

logger = structlog.get_logger()


class Metrics:
    def __init__(self):
        # Active WebSocket connections
        self.active_connections = Gauge(
            'ws_active_connections',
            'Number of active WebSocket connections',
            ['kiosk_id']
        )

        # Messages sent to kiosks
        self.messages_sent = Counter(
            'ws_messages_sent_total',
            'Total messages sent to kiosks',
            ['kiosk_id']
        )

        # Messages received from kiosks
        self.messages_received = Counter(
            'ws_messages_received_total',
            'Total messages received from kiosks',
            ['kiosk_id']
        )

        # Message latency (from send to receive response)
        self.message_latency = Histogram(
            'ws_message_latency_seconds',
            'Message round-trip latency in seconds',
            ['kiosk_id'],
            buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0]
        )

        # Errors
        self.errors = Counter(
            'ws_errors_total',
            'Total errors by type',
            ['error_type']
        )

        # Total kiosks (online/offline)
        self.kiosks_online = Gauge(
            'kiosks_online',
            'Number of kiosks currently online'
        )

        self.kiosks_total = Gauge(
            'kiosks_total',
            'Total number of registered kiosks'
        )

        # Stale connections
        self.stale_connections = Gauge(
            'ws_stale_connections',
            'Number of stale connections (not responding to ping)',
            ['kiosk_id']
        )

        # Server uptime
        self.server_uptime = Gauge(
            'server_uptime_seconds',
            'Server uptime in seconds'
        )

        # Total requests from Redis
        self.redis_requests_total = Gauge(
            'redis_requests_total',
            'Total requests processed (from Redis)'
        )

        # Total errors from Redis
        self.redis_errors_total = Gauge(
            'redis_errors_total',
            'Total errors occurred (from Redis)'
        )

        # Average latency from Redis
        self.redis_avg_latency = Gauge(
            'redis_avg_latency_seconds',
            'Average request latency (from Redis)'
        )

    def increment_active_connections(self, kiosk_id: str):
        """Increment active connections for a kiosk"""
        self.active_connections.labels(kiosk_id=kiosk_id).inc()
        self.update_online_kiosks_count()

    def decrement_active_connections(self, kiosk_id: str):
        """Decrement active connections for a kiosk"""
        self.active_connections.labels(kiosk_id=kiosk_id).dec()
        self.update_online_kiosks_count()

    def increment_messages_sent(self, kiosk_id: str):
        """Increment messages sent counter"""
        self.messages_sent.labels(kiosk_id=kiosk_id).inc()

    def increment_messages_received(self, kiosk_id: str):
        """Increment messages received counter"""
        self.messages_received.labels(kiosk_id=kiosk_id).inc()

    def observe_latency(self, kiosk_id: str, latency: float):
        """Record message latency"""
        self.message_latency.labels(kiosk_id=kiosk_id).observe(latency)

    def increment_errors(self, error_type: str):
        """Increment error counter"""
        self.errors.labels(error_type=error_type).inc()

    def update_online_kiosks_count(self):
        """Update the count of online kiosks (called from connection changes)"""
        # Count online kiosks from active_connections metric
        from src.websocket import ws_manager
        online_count = len(ws_manager.active_connections)
        self.kiosks_online.set(online_count)

    def set_total_kiosks(self, count: int):
        """Set total number of kiosks"""
        self.kiosks_total.set(count)

    def mark_connection_stale(self, kiosk_id: str):
        """Mark connection as stale"""
        self.stale_connections.labels(kiosk_id=kiosk_id).set(1)

    def mark_connection_healthy(self, kiosk_id: str):
        """Mark connection as healthy (clear stale flag)"""
        self.stale_connections.labels(kiosk_id=kiosk_id).set(0)

    async def sync_redis_stats(self):
        """Sync statistics from Redis to Prometheus metrics"""
        try:
            from src.redis_client import redis_client
            import time

            # Get stats from Redis
            stats = await redis_client.get_stats()

            # Update metrics
            self.redis_requests_total.set(stats.get('requests_total', 0))
            self.redis_errors_total.set(stats.get('errors_total', 0))
            self.redis_avg_latency.set(stats.get('avg_latency', 0))

            # Calculate uptime
            server_start = await redis_client.redis.get("stats:server_start_time")
            if server_start:
                uptime = time.time() - float(server_start)
                self.server_uptime.set(uptime)

        except Exception as e:
            logger.error("sync_redis_stats_failed", error=str(e))

    def get_metrics(self) -> bytes:
        """Get Prometheus metrics in text format"""
        return generate_latest()


# Global metrics instance
metrics = Metrics()
