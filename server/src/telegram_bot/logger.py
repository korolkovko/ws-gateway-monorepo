import structlog
from typing import Optional, Dict, Any
from telegram import Bot
from telegram.error import TelegramError
from telegram.constants import ParseMode
import asyncio
import json
import html as html_lib

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
                            parse_mode=ParseMode.HTML,
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

    def _format_json(self, data: Any, max_length: int = 500) -> str:
        """Format data as pretty JSON with HTML escaping"""
        try:
            json_str = json.dumps(data, ensure_ascii=False, indent=2)
            if len(json_str) > max_length:
                json_str = json_str[:max_length] + "\n  ... (truncated)"
            # Escape HTML characters
            json_str = html_lib.escape(json_str)
            return f"<pre>{json_str}</pre>"
        except:
            return f"<code>{html_lib.escape(str(data)[:max_length])}</code>"

    def _extract_key_fields(self, data: dict, operation_type: str = None) -> Dict[str, Any]:
        """Extract key fields from response data based on operation type"""
        key_fields = {}

        # Common fields
        if 'status' in data:
            key_fields['status'] = data['status']
        if 'order_id' in data:
            key_fields['order'] = f"#{data['order_id']}"

        # Fiscal-specific fields
        if operation_type == 'fiscal' and 'fiscal_receipt' in data:
            receipt = data['fiscal_receipt']
            if 'fiscal_document_number' in receipt:
                key_fields['fd'] = receipt['fiscal_document_number']
            if 'ofd_reg_number' in receipt:
                key_fields['ofd'] = receipt['ofd_reg_number']
            if 'fn_number' in receipt:
                key_fields['fn'] = receipt['fn_number']

        # Payment-specific fields
        if operation_type == 'payment':
            if 'transaction_id' in data:
                key_fields['transaction'] = data['transaction_id']
            if 'amount' in data or 'sum' in data:
                key_fields['amount'] = f"{data.get('amount', data.get('sum', 0))}₽"

        return key_fields

    async def log_request(self, kiosk_id: str, message_data: dict, operation_type: str = None, http_method: str = None):
        """Log incoming request with improved formatting"""
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

        # Format message with HTML
        lines = [
            f"<b>{header}</b>",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"Kiosk: {html_lib.escape(kiosk_id)}"
        ]

        # Add HTTP method if provided
        if http_method:
            lines.append(f"Method: {html_lib.escape(http_method)}")

        # Add formatted JSON
        lines.append("\nRequest:")
        lines.append(self._format_json(message_data))

        msg = "\n".join(lines)
        await self.log(msg)

    async def log_response(self, kiosk_id: str, response_data: dict, latency: float, operation_type: str = None):
        """Log response sent with improved formatting"""
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

        # Format message with HTML
        lines = [
            f"<b>{header}</b>",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"Kiosk: {html_lib.escape(kiosk_id)}",
            f"Latency: <b>{latency:.3f}s</b>"
        ]

        # Extract and show key fields
        key_fields = self._extract_key_fields(response_data, operation_type)
        if key_fields:
            lines.append("")
            if 'status' in key_fields:
                status = key_fields['status']
                status_lower = str(status).lower()
                # Show ✅ for success, ❌ only for actual errors
                if status_lower in ['ok', 'success', 'completed', 'succeed']:
                    status_emoji = "✅"
                elif status_lower in ['error', 'failed', 'timeout']:
                    status_emoji = "❌"
                else:
                    status_emoji = ""  # No emoji for other statuses

                if status_emoji:
                    lines.append(f"{status_emoji} Status: <b>{html_lib.escape(str(status))}</b>")
                else:
                    lines.append(f"Status: <b>{html_lib.escape(str(status))}</b>")

            # Add other key fields
            for key, value in key_fields.items():
                if key != 'status':
                    key_display = key.replace('_', ' ').title()
                    lines.append(f"  • {key_display}: <code>{html_lib.escape(str(value))}</code>")

        # Add formatted JSON
        lines.append("\nFull Response:")
        lines.append(self._format_json(response_data))

        msg = "\n".join(lines)
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
