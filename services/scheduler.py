import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from aiogram import Bot

from config import SCHEDULER_HOUR, SCHEDULER_MINUTE
from services.subscription import SubscriptionService

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

    def start(self):
        """Запуск планировщика."""
        # Ежедневная проверка в заданное время
        self.scheduler.add_job(
            self.daily_check_job,
            CronTrigger(hour=SCHEDULER_HOUR, minute=SCHEDULER_MINUTE),
            id="daily_subscription_check",
            replace_existing=True
        )

        self.scheduler.start()
        logger.info(
            f"Планировщик запущен. Ежедневная проверка в {SCHEDULER_HOUR:02d}:{SCHEDULER_MINUTE:02d}"
        )

    def stop(self):
        """Остановка планировщика."""
        self.scheduler.shutdown()
        logger.info("Планировщик остановлен")

    async def run_check_now(self) -> dict:
        """Запустить проверку вручную (для админов)."""
        return await self.subscription_service.process_daily_check()
