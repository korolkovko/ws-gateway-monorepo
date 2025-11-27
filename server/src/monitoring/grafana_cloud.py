import asyncio
import time
import requests
from typing import Optional
from threading import Thread
import structlog
from prometheus_client import REGISTRY, generate_latest

from src.config import settings

logger = structlog.get_logger()


class GrafanaCloudIntegration:
    """Integration with Grafana Cloud for metrics and logs"""

    def __init__(self):
        self.prometheus_enabled = bool(
            settings.grafana_prometheus_url and
            settings.grafana_prometheus_username and
            settings.grafana_prometheus_password
        )
        self.loki_enabled = bool(
            settings.grafana_loki_url and
            settings.grafana_loki_username and
            settings.grafana_loki_password
        )
        self.push_interval = 15  # Push metrics every 15 seconds
        self._running = False
        self._push_thread: Optional[Thread] = None

    def setup_loki(self):
        """Setup Loki logging handler - DISABLED for now"""
        logger.info("grafana_loki_disabled", reason="not_implemented")

    def push_metrics_to_prometheus(self):
        """Push current metrics to Grafana Cloud Prometheus"""
        if not self.prometheus_enabled:
            return

        # TEMPORARY: Disable Prometheus push due to encoding issues
        # Metrics are still available at /metrics endpoint
        # TODO: Setup Grafana Alloy or Agent to scrape metrics
        logger.debug("prometheus_push_disabled", reason="waiting_for_alloy_setup")
        return

    def _push_loop(self):
        """Background thread loop for pushing metrics"""
        logger.info("grafana_metrics_push_started", interval=self.push_interval)

        while self._running:
            try:
                self.push_metrics_to_prometheus()
            except Exception as e:
                logger.error("push_loop_error", error=str(e))

            time.sleep(self.push_interval)

    def start(self):
        """Start Grafana Cloud integration"""
        # Setup Loki
        self.setup_loki()

        # Start Prometheus push thread
        if self.prometheus_enabled:
            self._running = True
            self._push_thread = Thread(target=self._push_loop, daemon=True)
            self._push_thread.start()
            logger.info("grafana_prometheus_enabled", url=settings.grafana_prometheus_url)
        else:
            logger.info("grafana_prometheus_disabled", reason="missing_credentials")

    def stop(self):
        """Stop Grafana Cloud integration"""
        self._running = False
        if self._push_thread:
            self._push_thread.join(timeout=5)

        # Final push
        if self.prometheus_enabled:
            self.push_metrics_to_prometheus()

        logger.info("grafana_integration_stopped")


# Global instance
grafana_cloud = GrafanaCloudIntegration()
