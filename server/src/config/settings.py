from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List
import os


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    # Server
    ws_host: str = "0.0.0.0"
    ws_port: int = 8080
    port: int = int(os.getenv("PORT", "8000"))  # Railway uses PORT env variable
    kiosk_response_timeout: int = 45  # Increased timeout for kiosk waiting on external modules
    allow_duplicate_connections: bool = False  # Allow multiple connections from same kiosk

    @property
    def api_port(self) -> int:
        """Get API port (Railway passes it via PORT env variable)"""
        return self.port

    # Redis
    redis_url: str = "redis://localhost:6379"

    # Telegram
    telegram_bot_token: str = ""
    telegram_admin_ids: str = ""
    telegram_log_chat_id: str = ""  # Chat ID for sending logs

    # JWT
    jwt_secret: str = ""
    jwt_expiration_days: int = 365
    jwt_algorithm: str = "HS256"

    # Monitoring (optional)
    grafana_cloud_api_key: str = ""
    uptimerobot_api_key: str = ""

    # Grafana Cloud - Prometheus
    grafana_prometheus_url: str = ""  # e.g., https://prometheus-prod-XX-XX.grafana.net/api/prom/push
    grafana_prometheus_username: str = ""  # Usually a number like 123456
    grafana_prometheus_password: str = ""  # API Key from Grafana Cloud

    # Grafana Cloud - Loki
    grafana_loki_url: str = ""  # e.g., https://logs-prod-XX.grafana.net/loki/api/v1/push
    grafana_loki_username: str = ""  # Usually a number like 123456
    grafana_loki_password: str = ""  # API Key from Grafana Cloud

    # Logging
    log_level: str = "INFO"

    @property
    def admin_ids_list(self) -> List[int]:
        """Parse comma-separated admin IDs into list of integers"""
        return [int(id.strip()) for id in self.telegram_admin_ids.split(',') if id.strip()]


settings = Settings()
