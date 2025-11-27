import asyncio
import structlog
from fastapi import FastAPI
from contextlib import asynccontextmanager
import uvicorn

from src.config import settings
from src.redis_client import redis_client
from src.telegram_bot import telegram_bot
from src.api import router
from src.monitoring import grafana_cloud

# Configure structured logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_log_level,
        structlog.processors.JSONRenderer()
    ]
)

logger = structlog.get_logger()


def validate_config():
    """Validate required configuration before starting"""
    errors = []

    if not settings.telegram_bot_token:
        errors.append("TELEGRAM_BOT_TOKEN is not set")

    if not settings.telegram_admin_ids:
        errors.append("TELEGRAM_ADMIN_IDS is not set")

    if not settings.jwt_secret:
        errors.append("JWT_SECRET is not set")

    if errors:
        logger.error("configuration_error", errors=errors)
        raise ValueError(f"Missing required configuration: {', '.join(errors)}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    logger.info("application_starting")

    # Validate configuration
    validate_config()
    logger.info("configuration_validated")

    # Connect to Redis
    await redis_client.connect()
    logger.info("redis_connected")

    # Set server start time for stats
    import time
    await redis_client.redis.set("stats:server_start_time", str(time.time()))

    # Setup and start Telegram bot
    await telegram_bot.setup()
    await telegram_bot.start()
    logger.info("telegram_bot_started")

    # Start Grafana Cloud integration
    grafana_cloud.start()
    logger.info("grafana_cloud_started")

    # Start security reminder task
    from src.scheduler import security_reminder_task
    reminder_task = asyncio.create_task(security_reminder_task())
    logger.info("security_reminder_task_started")

    logger.info("application_ready")

    yield

    # Shutdown
    logger.info("application_shutting_down")

    # Stop security reminder task
    reminder_task.cancel()
    try:
        await reminder_task
    except asyncio.CancelledError:
        pass

    # Stop Grafana Cloud integration
    grafana_cloud.stop()

    # Stop Telegram bot
    await telegram_bot.stop()

    # Disconnect Redis
    await redis_client.disconnect()

    logger.info("application_stopped")


# Create FastAPI app
app = FastAPI(
    title="WebSocket Payment Gateway Server",
    description="WebSocket server for kiosk communication via Railway",
    version="1.0.0",
    lifespan=lifespan
)

# Include API routes
app.include_router(router)


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "WebSocket Payment Gateway Server",
        "version": "1.0.0",
        "status": "running"
    }


if __name__ == "__main__":
    logger.info("starting_server", host=settings.ws_host, port=settings.api_port)

    uvicorn.run(
        "main:app",
        host=settings.ws_host,
        port=settings.api_port,
        log_level=settings.log_level.lower(),
        access_log=True,
        ws_max_size=1024 * 1024,  # Limit WebSocket messages to 1MB
        ws_ping_interval=20.0,    # Send WebSocket ping every 20 seconds
        ws_ping_timeout=10.0      # Close connection if pong not received in 10 seconds
    )
