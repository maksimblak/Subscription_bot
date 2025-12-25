import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest

from config import SCHEDULER_HOUR, SCHEDULER_MINUTE
from database.models import UserModelExtended, ActionLogModel
from services.subscription import SubscriptionService
from utils.messages import Messages

logger = logging.getLogger(__name__)


class SchedulerService:
    def __init__(self, bot: Bot):
        self.bot = bot
        self.scheduler = AsyncIOScheduler()
        self.subscription_service = SubscriptionService(bot)

    async def daily_check_job(self):
        """Задача ежедневной проверки подписок."""
        logger.info("Запуск ежедневной проверки подписок...")

        try:
            stats = await self.subscription_service.process_daily_check()
            logger.info(
                f"Проверка завершена: проверено {stats['checked']}, "
                f"новых доступов {stats['new_access_granted']}, "
                f"деактивировано {stats['deactivated']}, "
                f"ошибок {stats['errors']}"
            )
        except Exception as e:
            logger.error(f"Ошибка при ежедневной проверке: {e}")

    async def send_upcoming_notifications(self):
        """Отправка уведомлений о скором открытии канала."""
        logger.info("Отправка уведомлений о предстоящих каналах...")

        try:
            # Получаем пользователей, которым скоро откроется канал (за 3 дня)
            users = await UserModelExtended.get_users_approaching_milestone(days_before=3)

            sent = 0
            for user_data in users:
                user_id = user_data["user_id"]
                channel_name = user_data["channel_name"]
                days_required = user_data["days_required"]
                days_subscribed = user_data["days_subscribed"]
                emoji = user_data.get("emoji", "📺")

                days_left = days_required - days_subscribed

                # Отправляем только если осталось 1, 2 или 3 дня
                if days_left in [1, 2, 3]:
                    try:
                        await self.bot.send_message(
                            user_id,
                            Messages.channel_upcoming(channel_name, days_left, emoji),
                            parse_mode="HTML"
                        )
                        sent += 1
                    except TelegramBadRequest as e:
                        logger.warning(f"Не удалось отправить уведомление пользователю {user_id}: {e}")

            logger.info(f"Отправлено {sent} уведомлений о предстоящих каналах")

        except Exception as e:
            logger.error(f"Ошибка при отправке уведомлений: {e}")

    def start(self):
        """Запуск планировщика."""
        # Ежедневная проверка подписок
        self.scheduler.add_job(
            self.daily_check_job,
            CronTrigger(hour=SCHEDULER_HOUR, minute=SCHEDULER_MINUTE),
            id="daily_subscription_check",
            replace_existing=True
        )

        # Уведомления о предстоящих каналах (за час до основной проверки)
        notification_hour = SCHEDULER_HOUR - 1 if SCHEDULER_HOUR > 0 else 23
        self.scheduler.add_job(
            self.send_upcoming_notifications,
            CronTrigger(hour=notification_hour, minute=SCHEDULER_MINUTE),
            id="upcoming_notifications",
            replace_existing=True
        )

        self.scheduler.start()
        logger.info(
            f"Планировщик запущен. "
            f"Ежедневная проверка в {SCHEDULER_HOUR:02d}:{SCHEDULER_MINUTE:02d}, "
            f"уведомления в {notification_hour:02d}:{SCHEDULER_MINUTE:02d}"
        )

    def stop(self):
        """Остановка планировщика."""
        self.scheduler.shutdown()
        logger.info("Планировщик остановлен")

    async def run_check_now(self) -> dict:
        """Запустить проверку вручную (для админов)."""
        return await self.subscription_service.process_daily_check()

    async def run_notifications_now(self) -> int:
        """Запустить отправку уведомлений вручную."""
        await self.send_upcoming_notifications()
        return 0
