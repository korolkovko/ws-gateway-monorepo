import asyncio
import time
from datetime import datetime, timezone, timedelta
import structlog

from src.redis_client import redis_client
from src.config import settings

logger = structlog.get_logger()

# UTC+5 timezone
UTC_PLUS_5 = timezone(timedelta(hours=5))

# Reminder interval: 30 days in seconds
REMINDER_INTERVAL = 30 * 24 * 60 * 60


async def send_security_reminder():
    """Send security reminder to all admins and log chat"""
    try:
        # Get all kiosks
        all_kiosks = await redis_client.get_all_kiosks()

        if not all_kiosks:
            logger.info("security_reminder_skipped", reason="no_kiosks")
            return

        # Decode tokens to check expiration
        from jose import jwt

        kiosk_info_list = []
        for kiosk in all_kiosks:
            kiosk_id = kiosk['id']
            kiosk_name = kiosk.get('name', kiosk_id)

            # Get token
            token = await redis_client.get_kiosk_token(kiosk_id)
            if not token:
                continue

            try:
                # Decode to get expiration
                payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
                expires_at = datetime.fromtimestamp(payload.get('exp', 0), tz=timezone.utc)
                now = datetime.now(timezone.utc)
                days_remaining = (expires_at - now).days

                kiosk_info_list.append({
                    'id': kiosk_id,
                    'name': kiosk_name,
                    'days_remaining': days_remaining
                })
            except Exception as e:
                logger.error("token_decode_failed", kiosk_id=kiosk_id, error=str(e))

        if not kiosk_info_list:
            logger.info("security_reminder_skipped", reason="no_valid_tokens")
            return

        # Build reminder message
        msg = "🔐 Напоминание о безопасности токенов\n\n📋 Статус всех киосков:\n\n"

        for kiosk_info in kiosk_info_list:
            days = kiosk_info['days_remaining']
            if days < 30:
                msg += f"⚠️ {kiosk_info['name']} ({kiosk_info['id']})\n"
                msg += f"   Токен действителен ещё {days} дней\n"
                msg += "   Рекомендуется обновить!\n\n"
            else:
                msg += f"✅ {kiosk_info['name']} ({kiosk_info['id']})\n"
                msg += f"   Токен действителен ещё {days} дней\n\n"

        msg += "💡 Команды:\n"
        msg += "/token_info <kiosk_id> - проверить токен\n"
        msg += "/regenerate_token <kiosk_id> - обновить токен"

        # Send to admins and log chat
        from src.telegram_bot import telegram_bot

        if telegram_bot.app and telegram_bot.app.bot:
            # Send to all admins
            for admin_id in settings.admin_ids_list:
                try:
                    await telegram_bot.app.bot.send_message(
                        chat_id=admin_id,
                        text=msg
                    )
                    logger.info("security_reminder_sent_to_admin", admin_id=admin_id)
                except Exception as e:
                    logger.error("security_reminder_send_failed", admin_id=admin_id, error=str(e))

            # Send to log chat if configured
            if settings.telegram_log_chat_id:
                try:
                    await telegram_bot.app.bot.send_message(
                        chat_id=settings.telegram_log_chat_id,
                        text=msg
                    )
                    logger.info("security_reminder_sent_to_chat", chat_id=settings.telegram_log_chat_id)
                except Exception as e:
                    logger.error("security_reminder_send_to_chat_failed", error=str(e))

        logger.info("security_reminder_completed", kiosks_count=len(kiosk_info_list))

    except Exception as e:
        logger.error("security_reminder_failed", error=str(e))


async def security_reminder_task():
    """Background task that checks every 24 hours if reminder is needed"""
    logger.info("security_reminder_task_started")

    while True:
        try:
            # Wait 24 hours
            await asyncio.sleep(24 * 60 * 60)

            # Check current time in UTC+5
            now_utc5 = datetime.now(UTC_PLUS_5)

            # Only send reminder at 12:00 (noon)
            if now_utc5.hour != 12:
                logger.debug("security_reminder_check_skipped", hour=now_utc5.hour)
                continue

            # Check if 30 days passed since last reminder
            last_reminder = await redis_client.redis.get("last_security_reminder")
            current_time = time.time()

            if not last_reminder or (current_time - float(last_reminder)) >= REMINDER_INTERVAL:
                logger.info("security_reminder_triggered", days_since_last=
                           (current_time - float(last_reminder)) / (24 * 60 * 60) if last_reminder else None)

                # Send reminder
                await send_security_reminder()

                # Update last reminder timestamp
                await redis_client.redis.set("last_security_reminder", str(current_time))
            else:
                days_remaining = (REMINDER_INTERVAL - (current_time - float(last_reminder))) / (24 * 60 * 60)
                logger.info("security_reminder_not_needed", days_until_next=int(days_remaining))

        except asyncio.CancelledError:
            logger.info("security_reminder_task_cancelled")
            break
        except Exception as e:
            logger.error("security_reminder_task_error", error=str(e))
