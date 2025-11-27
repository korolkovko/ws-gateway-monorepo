import structlog
from typing import Optional
from telegram import Bot
from telegram.error import TelegramError
import asyncio

from src.config import settings

logger = structlog.get_logger()


class TelegramLogHandler:
    """Handler for sending logs to Telegram chat"""

    def __init__(self):
        self.bot: Optional[Bot] = None
        self.chat_id: Optional[str] = None
        self.enabled = False
        self._queue = asyncio.Queue()
        self._task: Optional[asyncio.Task] = None

    async def initialize(self, bot: Bot):
        """Initialize the handler with bot instance"""
        if not settings.telegram_log_chat_id:
            logger.info("telegram_log_handler_disabled", reason="no_chat_id_configured")
            return

        self.bot = bot
        self.chat_id = settings.telegram_log_chat_id
        self.enabled = True

        # Start background task to process logs
        self._task = asyncio.create_task(self._process_queue())

        logger.info("telegram_log_handler_initialized", chat_id=self.chat_id)

        # Send test message
        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text="✅ Telegram logging initialized successfully!"
            )
        except Exception as e:
            logger.error("telegram_log_test_message_failed", error=str(e))
            self.enabled = False

    async def _process_queue(self):
        """Background task to process log queue"""
        while True:
            try:
                message = await self._queue.get()
                if self.bot and self.chat_id:
                    try:
                        await self.bot.send_message(
                            chat_id=self.chat_id,
                            text=message,
                            disable_notification=True
                        )
                    except TelegramError as e:
                        logger.error("telegram_log_send_failed", error=str(e))
            except Exception as e:
                logger.error("telegram_log_queue_error", error=str(e))

            await asyncio.sleep(0.1)  # Small delay to avoid rate limits

    async def log(self, message: str):
        """Queue a message to be sent to Telegram"""
        if not self.enabled:
            return

        # Truncate long messages
        if len(message) > 4000:
            message = message[:3997] + "..."

        await self._queue.put(message)

    async def log_event(self, event_type: str, **data):
        """Log an event with structured data"""
        if not self.enabled:
            return

        # Format event data
        lines = [f"🔔 {event_type.replace('_', ' ').title()}"]
        for key, value in data.items():
            lines.append(f"  • {key}: {value}")

        message = "\n".join(lines)
        await self.log(message)

    async def log_request(self, kiosk_id: str, message_data: dict, operation_type: str = None):
        """Log incoming request"""
        # Map operation types to emojis
        operation_emojis = {
            'payment': '💳',
            'fiscal': '🧾',
            'kds': '🧑‍🍳',
            'print': '🖨️'
        }

        # Build header with arrow and optional operation emoji
        header = "⬇️"
        if operation_type and operation_type in operation_emojis:
            header += f" {operation_emojis[operation_type]}"
        header += " Request Received"

        msg = f"""{header}
  • Kiosk: {kiosk_id}
  • Data: {str(message_data)[:200]}"""
        await self.log(msg)

    async def log_response(self, kiosk_id: str, response_data: dict, latency: float, operation_type: str = None):
        """Log response sent"""
        # Map operation types to emojis
        operation_emojis = {
            'payment': '💳',
            'fiscal': '🧾',
            'kds': '🧑‍🍳',
            'print': '🖨️'
        }

        # Build header with arrow and optional operation emoji
        header = "⬆️"
        if operation_type and operation_type in operation_emojis:
            header += f" {operation_emojis[operation_type]}"
        header += " Response Sent"

        msg = f"""{header}
  • Kiosk: {kiosk_id}
  • Latency: {latency:.3f}s
  • Data: {str(response_data)[:200]}"""
        await self.log(msg)

    async def log_connection(self, kiosk_id: str, status: str):
        """Log connection event"""
        emoji = "🟢" if status == "connected" else "🔴"
        msg = f"""{emoji} Connection {status.title()}
  • Kiosk: {kiosk_id}"""
        await self.log(msg)

    async def log_error(self, error_type: str, kiosk_id: Optional[str] = None, details: str = ""):
        """Log error event"""
        msg = f"""❌ Error: {error_type}"""
        if kiosk_id:
            msg += f"\n  • Kiosk: {kiosk_id}"
        if details:
            msg += f"\n  • Details: {details[:200]}"
        await self.log(msg)

    async def log_stale_connection(self, kiosk_id: str):
        """Log stale connection detected"""
        from src.redis_client import redis_client
        kiosk_info = await redis_client.get_kiosk_info(kiosk_id)
        kiosk_name = kiosk_info.get('name', kiosk_id) if kiosk_info else kiosk_id

        msg = f"""⚠️ Потеряна связь с киоском
  • Киоск: {kiosk_name} ({kiosk_id})
  • Статус: Stale (не отвечает на ping)"""
        await self.log(msg)

    async def log_duplicate_connection(self, kiosk_id: str):
        """Log duplicate connection attempt"""
        from src.redis_client import redis_client
        kiosk_info = await redis_client.get_kiosk_info(kiosk_id)
        kiosk_name = kiosk_info.get('name', kiosk_id) if kiosk_info else kiosk_id

        msg = f"""⚠️ Попытка дублирующего подключения
  • Киоск: {kiosk_name} ({kiosk_id})
  • Текущий статус: Online
  • Действие: Заблокировано"""
        await self.log(msg)

    async def shutdown(self):
        """Shutdown the handler"""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass


# Global instance
telegram_log_handler = TelegramLogHandler()
