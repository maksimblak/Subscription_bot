import logging
from aiogram import Router, Bot, F
from aiogram.types import Message, ChatMemberUpdated
from aiogram.filters import Command, ChatMemberUpdatedFilter, IS_NOT_MEMBER, IS_MEMBER

from config import MAIN_CHANNEL_ID, CHANNELS_CONFIG
from database.models import UserModel, UserChannelModel
from services.subscription import SubscriptionService
from utils.helpers import format_date

logger = logging.getLogger(__name__)

user_router = Router()


@user_router.message(Command("start"))
async def cmd_start(message: Message, bot: Bot):
    """Обработчик команды /start."""
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name

    subscription_service = SubscriptionService(bot)

    # Проверяем подписку на материнский канал
    is_subscribed = await subscription_service.check_main_subscription(user_id)

    if not is_subscribed:
        await message.answer(
            "❌ Для использования бота необходимо подписаться на основной канал.\n\n"
            "После подписки нажмите /start ещё раз."
        )
        return

    # Регистрируем/обновляем пользователя
    result = await subscription_service.register_user(user_id, username, first_name)
    status = result["status"]

    if status == "new":
        await message.answer(
            f"👋 Добро пожаловать, {first_name}!\n\n"
            f"Вы успешно зарегистрированы. Теперь вам будут открываться "
            f"дополнительные каналы по мере вашей подписки.\n\n"
            f"📊 Используйте /status для просмотра вашего прогресса."
        )

        # Выдаём доступ к первому каналу (0 дней)
        for channel in CHANNELS_CONFIG:
            if channel["days_required"] == 0 and channel["id"] != 0:
                invite_link = await subscription_service.grant_channel_access(user_id, channel["id"])
                if invite_link:
                    msg = await message.answer(
                        f"🎁 Вам доступен канал <b>{channel['name']}</b>!\n\n"
                        f"Ссылка: {invite_link}\n\n"
                        f"⚠️ Ссылка одноразовая.",
                        parse_mode="HTML"
                    )
                    await UserChannelModel.update_message_id(user_id, channel["id"], msg.message_id)

    elif status == "reactivated":
        await message.answer(
            f"👋 С возвращением, {first_name}!\n\n"
            f"Ваш аккаунт был реактивирован. Обратите внимание, что отсчёт "
            f"времени подписки начинается заново.\n\n"
            f"📊 Используйте /status для просмотра вашего прогресса."
        )
    else:
        await message.answer(
            f"👋 Привет, {first_name}!\n\n"
            f"Вы уже зарегистрированы в системе.\n\n"
            f"📊 Используйте /status для просмотра вашего прогресса."
        )


@user_router.message(Command("status"))
async def cmd_status(message: Message, bot: Bot):
    """Показать статус пользователя."""
    user_id = message.from_user.id
    subscription_service = SubscriptionService(bot)

    status = await subscription_service.get_user_status(user_id)

    if not status["exists"]:
        await message.answer(
            "❌ Вы не зарегистрированы. Нажмите /start для регистрации."
        )
        return

    user = status["user"]
    days = status["days_subscribed"]
    channels = status["channels"]

    # Формируем список доступных каналов
    channels_text = "\n".join([f"  • {ch['name']}" for ch in channels]) if channels else "  Пока нет доступных каналов"

    # Следующий доступный канал
    next_channel = None
    for ch in CHANNELS_CONFIG:
        if ch["days_required"] > days and ch["id"] != 0:
            next_channel = ch
            break

    next_text = ""
    if next_channel:
        days_left = next_channel["days_required"] - days
        next_text = f"\n\n⏳ Следующий канал: <b>{next_channel['name']}</b> через {days_left} дн."

    await message.answer(
        f"📊 <b>Ваш статус</b>\n\n"
        f"👤 Пользователь: {user['first_name'] or 'Не указано'}\n"
        f"📅 Дней подписки: {days}\n"
        f"✅ Статус: {'Активен' if user['is_active'] else 'Неактивен'}\n\n"
        f"📺 <b>Доступные каналы:</b>\n{channels_text}"
        f"{next_text}",
        parse_mode="HTML"
    )


@user_router.message(Command("channels"))
async def cmd_channels(message: Message, bot: Bot):
    """Показать все доступные каналы пользователю."""
    user_id = message.from_user.id
    subscription_service = SubscriptionService(bot)

    # Проверяем доступные каналы
    available = await subscription_service.get_available_channels(user_id)

    if not available:
        status = await subscription_service.get_user_status(user_id)
        if not status["exists"]:
            await message.answer("❌ Сначала зарегистрируйтесь: /start")
        else:
            await message.answer(
                "✅ Все доступные каналы уже открыты или ожидайте новых по мере подписки."
            )
        return

    # Выдаём доступ к каналам
    for channel in available:
        invite_link = await subscription_service.grant_channel_access(user_id, channel["id"])
        if invite_link:
            msg = await message.answer(
                f"🎁 Канал <b>{channel['name']}</b>\n\n"
                f"Ссылка: {invite_link}\n\n"
                f"⚠️ Ссылка одноразовая.",
                parse_mode="HTML"
            )
            await UserChannelModel.update_message_id(user_id, channel["id"], msg.message_id)


# Обработчик отписки от материнского канала
@user_router.chat_member(ChatMemberUpdatedFilter(IS_MEMBER >> IS_NOT_MEMBER))
async def on_user_left(event: ChatMemberUpdated, bot: Bot):
    """Обработка отписки пользователя от материнского канала."""
    if event.chat.id != MAIN_CHANNEL_ID:
        return

    user_id = event.from_user.id
    logger.info(f"Пользователь {user_id} отписался от материнского канала")

    subscription_service = SubscriptionService(bot)

    # Отзываем все доступы
    message_ids = await subscription_service.revoke_user_access(user_id)

    # Удаляем сообщения с invite-ссылками
    for msg_id in message_ids:
        try:
            await bot.delete_message(user_id, msg_id)
        except Exception as e:
            logger.warning(f"Не удалось удалить сообщение {msg_id} у пользователя {user_id}: {e}")

    # Уведомляем пользователя
    try:
        await bot.send_message(
            user_id,
            "😔 Вы отписались от основного канала.\n\n"
            "Ваш доступ ко всем дополнительным каналам был отозван.\n"
            "Если хотите вернуться - подпишитесь снова и нажмите /start"
        )
    except Exception as e:
        logger.warning(f"Не удалось отправить уведомление пользователю {user_id}: {e}")


# Обработчик подписки на материнский канал (для автоматической регистрации)
@user_router.chat_member(ChatMemberUpdatedFilter(IS_NOT_MEMBER >> IS_MEMBER))
async def on_user_joined(event: ChatMemberUpdated, bot: Bot):
    """Обработка подписки на материнский канал."""
    if event.chat.id != MAIN_CHANNEL_ID:
        return

    user_id = event.from_user.id
    logger.info(f"Пользователь {user_id} подписался на материнский канал")

    # Отправляем приветственное сообщение с предложением зарегистрироваться
    try:
        await bot.send_message(
            user_id,
            "👋 Добро пожаловать в канал!\n\n"
            "Чтобы получить доступ к дополнительным каналам и бонусам, "
            "нажмите /start"
        )
    except Exception as e:
        logger.warning(f"Не удалось отправить приветствие пользователю {user_id}: {e}")
