import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import BOT_TOKEN, MAIN_CHANNEL_ID, CHANNELS_CONFIG
from database.db import db
from database.models import ChannelModel
from handlers.user import user_router
from handlers.admin import admin_router
from services.scheduler import SchedulerService

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def on_startup(bot: Bot):
    """Действия при запуске бота."""
    logger.info("Бот запускается...")

    # Подключаемся к БД
    await db.connect()
    logger.info("База данных подключена")

    # Инициализируем каналы в БД
    await ChannelModel.create(MAIN_CHANNEL_ID, "Материнский канал", 0, is_main=True)
    for channel in CHANNELS_CONFIG:
        if channel["id"] != 0:
            await ChannelModel.create(
                channel["id"],
                channel["name"],
                channel["days_required"],
                is_main=False
            )
    logger.info("Каналы инициализированы")

    # Проверяем, что бот админ в каналах
    try:
        me = await bot.get_me()
        logger.info(f"Бот запущен: @{me.username}")
    except Exception as e:
        logger.error(f"Ошибка получения информации о боте: {e}")


async def on_shutdown(bot: Bot, scheduler: SchedulerService):
    """Действия при остановке бота."""
    logger.info("Бот останавливается...")

    # Останавливаем планировщик
    scheduler.stop()

    # Отключаемся от БД
    await db.disconnect()
    logger.info("Бот остановлен")


async def main():
    # Проверка токена
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE" or not BOT_TOKEN:
        logger.error("Не указан BOT_TOKEN! Создайте файл .env на основе .env.example")
        return

    # Создаём бота и диспетчер
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()

    # Регистрируем роутеры
    dp.include_router(user_router)
    dp.include_router(admin_router)

    # Инициализируем планировщик
    scheduler = SchedulerService(bot)

    # Регистрируем обработчики startup/shutdown
    async def startup_handler():
        await on_startup(bot)

    async def shutdown_handler():
        await on_shutdown(bot, scheduler)

    dp.startup.register(startup_handler)
    dp.shutdown.register(shutdown_handler)

    # Запускаем планировщик
    scheduler.start()

    # Запускаем polling
    logger.info("Запуск polling...")
    try:
        await dp.start_polling(
            bot,
            allowed_updates=["message", "callback_query", "chat_member"]
        )
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
