from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import structlog

from src.config import settings
from src.redis_client import redis_client
from src.auth import jwt_handler

logger = structlog.get_logger()


class TelegramBot:
    def __init__(self):
        self.app = None
        self.admin_ids = settings.admin_ids_list

    def is_admin(self, user_id: int) -> bool:
        """Check if user is admin"""
        return user_id in self.admin_ids

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        if not self.is_admin(update.effective_user.id):
            await update.message.reply_text("⛔ Access denied. You are not authorized.")
            return

        welcome_message = """
🤖 WebSocket Server Management Bot

Available commands:
/add_kiosk <kiosk_id> [name] - Add new kiosk
/list_kiosks - List all kiosks
/status - Show system status
/token_info <kiosk_id> - Show token information
/regenerate_token <kiosk_id> - Regenerate kiosk token
/enable_kiosk <kiosk_id> - Enable kiosk
/disable_kiosk <kiosk_id> - Disable kiosk
/rename_kiosk <kiosk_id> <new_name> - Rename kiosk
/remove_kiosk <kiosk_id> - Remove kiosk
"""
        await update.message.reply_text(welcome_message)

    async def add_kiosk_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /add_kiosk command"""
        if not self.is_admin(update.effective_user.id):
            await update.message.reply_text("⛔ Access denied.")
            return

        if not context.args or len(context.args) < 1:
            await update.message.reply_text("Usage: /add_kiosk <kiosk_id> [name]")
            return

        kiosk_id = context.args[0]
        name = " ".join(context.args[1:]) if len(context.args) > 1 else kiosk_id

        # Check if kiosk already exists
        if await redis_client.kiosk_exists(kiosk_id):
            await update.message.reply_text(f"❌ Kiosk '{kiosk_id}' already exists.")
            return

        # Generate JWT token
        token = jwt_handler.create_token(kiosk_id)

        # Create kiosk in Redis
        await redis_client.create_kiosk(kiosk_id, token, name)

        logger.info("kiosk_created", kiosk_id=kiosk_id, name=name, admin_id=update.effective_user.id)

        response = f"""✅ Kiosk created successfully!

Kiosk ID: {kiosk_id}
Name: {name}
Status: Offline (waiting for connection)

JWT Token:
{token}

⚠️ Save this token securely! Use it to connect the kiosk client.
"""
        await update.message.reply_text(response)

    async def list_kiosks_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /list_kiosks command"""
        if not self.is_admin(update.effective_user.id):
            await update.message.reply_text("⛔ Access denied.")
            return

        kiosks = await redis_client.get_all_kiosks()

        if not kiosks:
            await update.message.reply_text("📋 No kiosks registered yet.")
            return

        message = "📋 Registered Kiosks:\n\n"
        for kiosk in kiosks:
            status_emoji = "🟢" if kiosk['status'] == 'online' else "🔴"
            enabled_emoji = "✅" if kiosk.get('enabled') == 'true' else "❌"
            message += f"{status_emoji} {kiosk['name']} ({kiosk['id']})\n"
            message += f"   Status: {kiosk['status'].capitalize()} | Enabled: {enabled_emoji}\n\n"

        await update.message.reply_text(message)

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command"""
        if not self.is_admin(update.effective_user.id):
            await update.message.reply_text("⛔ Access denied.")
            return

        try:
            # Get statistics
            all_kiosks = await redis_client.get_all_kiosks()
            online_kiosks = await redis_client.get_online_kiosks()
            redis_connected = await redis_client.is_connected()

            online_count = len(online_kiosks)
            total_count = len(all_kiosks)
            offline_count = total_count - online_count

            message = f"""📊 System Status

🗄 Redis: {"✅ Connected" if redis_connected else "❌ Disconnected"}

📡 Kiosks:
• Total: {total_count}
• Online: 🟢 {online_count}
• Offline: 🔴 {offline_count}
"""
            await update.message.reply_text(message)

        except Exception as e:
            logger.error("status_command_failed", error=str(e))
            await update.message.reply_text(f"❌ Error: {str(e)}")

    async def regenerate_token_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /regenerate_token command"""
        if not self.is_admin(update.effective_user.id):
            await update.message.reply_text("⛔ Access denied.")
            return

        if not context.args or len(context.args) != 1:
            await update.message.reply_text("Usage: /regenerate_token <kiosk_id>")
            return

        kiosk_id = context.args[0]

        # Check if kiosk exists
        if not await redis_client.kiosk_exists(kiosk_id):
            await update.message.reply_text(f"❌ Kiosk '{kiosk_id}' not found.")
            return

        # Generate new token
        new_token = jwt_handler.create_token(kiosk_id)

        # Update token in Redis
        await redis_client.update_kiosk_token(kiosk_id, new_token)

        logger.info("token_regenerated", kiosk_id=kiosk_id, admin_id=update.effective_user.id)

        response = f"""✅ Token regenerated successfully!

Kiosk ID: {kiosk_id}

New JWT Token:
{new_token}

⚠️ Update the kiosk client with this new token. Old token is now invalid.
"""
        await update.message.reply_text(response)

    async def enable_kiosk_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /enable_kiosk command"""
        if not self.is_admin(update.effective_user.id):
            await update.message.reply_text("⛔ Access denied.")
            return

        if not context.args or len(context.args) != 1:
            await update.message.reply_text("Usage: /enable_kiosk <kiosk_id>")
            return

        kiosk_id = context.args[0]

        if not await redis_client.kiosk_exists(kiosk_id):
            await update.message.reply_text(f"❌ Kiosk '{kiosk_id}' not found.")
            return

        await redis_client.enable_kiosk(kiosk_id)

        logger.info("kiosk_enabled", kiosk_id=kiosk_id, admin_id=update.effective_user.id)

        await update.message.reply_text(f"✅ Kiosk '{kiosk_id}' enabled successfully.")

    async def disable_kiosk_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /disable_kiosk command"""
        if not self.is_admin(update.effective_user.id):
            await update.message.reply_text("⛔ Access denied.")
            return

        if not context.args or len(context.args) != 1:
            await update.message.reply_text("Usage: /disable_kiosk <kiosk_id>")
            return

        kiosk_id = context.args[0]

        if not await redis_client.kiosk_exists(kiosk_id):
            await update.message.reply_text(f"❌ Kiosk '{kiosk_id}' not found.")
            return

        await redis_client.disable_kiosk(kiosk_id)

        logger.info("kiosk_disabled", kiosk_id=kiosk_id, admin_id=update.effective_user.id)

        await update.message.reply_text(f"✅ Kiosk '{kiosk_id}' disabled successfully.")

    async def rename_kiosk_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /rename_kiosk command"""
        if not self.is_admin(update.effective_user.id):
            await update.message.reply_text("⛔ Access denied.")
            return

        if not context.args or len(context.args) < 2:
            await update.message.reply_text("Usage: /rename_kiosk <kiosk_id> <new_name>")
            return

        kiosk_id = context.args[0]
        new_name = " ".join(context.args[1:])

        if not await redis_client.kiosk_exists(kiosk_id):
            await update.message.reply_text(f"❌ Kiosk '{kiosk_id}' not found.")
            return

        await redis_client.update_kiosk_name(kiosk_id, new_name)

        logger.info("kiosk_renamed", kiosk_id=kiosk_id, new_name=new_name, admin_id=update.effective_user.id)

        await update.message.reply_text(f"✅ Kiosk '{kiosk_id}' renamed to '{new_name}' successfully.")

    async def remove_kiosk_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /remove_kiosk command"""
        if not self.is_admin(update.effective_user.id):
            await update.message.reply_text("⛔ Access denied.")
            return

        if not context.args or len(context.args) != 1:
            await update.message.reply_text("Usage: /remove_kiosk <kiosk_id>")
            return

        kiosk_id = context.args[0]

        if not await redis_client.kiosk_exists(kiosk_id):
            await update.message.reply_text(f"❌ Kiosk '{kiosk_id}' not found.")
            return

        await redis_client.delete_kiosk(kiosk_id)

        logger.info("kiosk_removed", kiosk_id=kiosk_id, admin_id=update.effective_user.id)

        await update.message.reply_text(f"✅ Kiosk '{kiosk_id}' removed successfully.")

    async def token_info_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /token_info command"""
        if not self.is_admin(update.effective_user.id):
            await update.message.reply_text("⛔ Access denied.")
            return

        if not context.args or len(context.args) != 1:
            await update.message.reply_text("Usage: /token_info <kiosk_id>")
            return

        kiosk_id = context.args[0]

        # Check if kiosk exists
        if not await redis_client.kiosk_exists(kiosk_id):
            await update.message.reply_text(f"❌ Kiosk '{kiosk_id}' not found.")
            return

        # Get kiosk info
        kiosk_info = await redis_client.get_kiosk_info(kiosk_id)
        kiosk_name = kiosk_info.get('name', kiosk_id) if kiosk_info else kiosk_id

        # Get token and decode to check expiration
        token = await redis_client.get_kiosk_token(kiosk_id)
        if not token:
            await update.message.reply_text(f"❌ Token not found for kiosk '{kiosk_id}'.")
            return

        # Decode JWT to get expiration
        try:
            from jose import jwt
            from datetime import datetime, timezone

            payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])

            issued_at = datetime.fromtimestamp(payload.get('iat', 0), tz=timezone.utc)
            expires_at = datetime.fromtimestamp(payload.get('exp', 0), tz=timezone.utc)
            now = datetime.now(timezone.utc)

            days_remaining = (expires_at - now).days

            # Get kiosk status
            status = await redis_client.get_kiosk_connection_status(kiosk_id)
            status_emoji = "🟢" if status == "online" else ("⚠️" if status == "stale" else "🔴")
            status_text = status.capitalize()

            # Build message
            msg = f"""📋 Информация о токене

Киоск: {kiosk_name} ({kiosk_id})
Статус: {status_emoji} {status_text}

Токен создан: {issued_at.strftime('%Y-%m-%d %H:%M:%S UTC')}
Истекает: {expires_at.strftime('%Y-%m-%d %H:%M:%S UTC')}
⏱️ Осталось: {days_remaining} дней
"""

            if days_remaining < 30:
                msg += f"\n⚠️ Токен скоро истечёт! Рекомендуется обновить:\n/regenerate_token {kiosk_id}"
            else:
                msg += "\n✅ Токен активен"

            await update.message.reply_text(msg)

        except Exception as e:
            logger.error("token_info_decode_failed", kiosk_id=kiosk_id, error=str(e))
            await update.message.reply_text(f"❌ Error decoding token: {str(e)}")

    async def setup(self):
        """Setup bot and register handlers"""
        self.app = Application.builder().token(settings.telegram_bot_token).build()

        # Register command handlers
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("add_kiosk", self.add_kiosk_command))
        self.app.add_handler(CommandHandler("list_kiosks", self.list_kiosks_command))
        self.app.add_handler(CommandHandler("status", self.status_command))
        self.app.add_handler(CommandHandler("token_info", self.token_info_command))
        self.app.add_handler(CommandHandler("regenerate_token", self.regenerate_token_command))
        self.app.add_handler(CommandHandler("enable_kiosk", self.enable_kiosk_command))
        self.app.add_handler(CommandHandler("disable_kiosk", self.disable_kiosk_command))
        self.app.add_handler(CommandHandler("rename_kiosk", self.rename_kiosk_command))
        self.app.add_handler(CommandHandler("remove_kiosk", self.remove_kiosk_command))

        # Initialize Telegram log handler
        from src.telegram_bot.logger import telegram_log_handler
        await telegram_log_handler.initialize(self.app.bot)

        logger.info("telegram_bot_setup_complete")

    async def start(self):
        """Start the bot"""
        await self.app.initialize()
        await self.app.start()

        # Only start polling if this is the main worker (to avoid conflicts)
        # Check if we should run the updater based on environment variable
        import os
        if os.getenv("ENABLE_TELEGRAM_POLLING", "true").lower() == "true":
            await self.app.updater.start_polling()
            logger.info("telegram_bot_started_with_polling")
        else:
            logger.info("telegram_bot_started_without_polling")

    async def stop(self):
        """Stop the bot"""
        if self.app:
            try:
                await self.app.updater.stop()
            except:
                pass  # Updater might not be running
            await self.app.stop()
            await self.app.shutdown()
            logger.info("telegram_bot_stopped")


# Global bot instance
telegram_bot = TelegramBot()
