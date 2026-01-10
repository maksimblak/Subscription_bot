import logging
from aiogram import Router, Bot, F
from aiogram.types import Message, ChatMemberUpdated, CallbackQuery
from aiogram.filters import Command, ChatMemberUpdatedFilter, IS_NOT_MEMBER, IS_MEMBER
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import MAIN_CHANNEL_ID, CHANNELS_CONFIG
from database.models import UserModel, UserChannelModel, ActionLogModel, UserModelExtended
from services.subscription import SubscriptionService
from utils.messages import Messages, ProgressBar, Keyboards

logger = logging.getLogger(__name__)

user_router = Router()


def get_main_keyboard() -> InlineKeyboardBuilder:
    """Главная клавиатура пользователя."""
    builder = InlineKeyboardBuilder()
    for text, callback in Keyboards.MAIN_MENU:
        builder.button(text=text, callback_data=callback)
    builder.adjust(2)
    return builder


def get_settings_keyboard(notifications_on: bool) -> InlineKeyboardBuilder:
    """Клавиатура настроек."""
    builder = InlineKeyboardBuilder()
    notif_text = "🔔 Уведомления: ВКЛ" if notifications_on else "🔕 Уведомления: ВЫКЛ"
    builder.button(text=notif_text, callback_data="settings:toggle_notifications")
    builder.button(text="◀️ Назад", callback_data="user:back")
    builder.adjust(1)
    return builder


@user_router.message(Command("start"))
async def cmd_start(message: Message, bot: Bot):
    """Обработчик команды /start."""
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name or "Пользователь"

    # Проверяем, не забанен ли пользователь
    if await UserModelExtended.is_banned(user_id):
        user = await UserModel.get(user_id)
        reason = user.get("ban_reason") if user else None
        await message.answer(
            f"🚫 <b>Ваш доступ заблокирован</b>\n\n"
            f"Причина: {reason or 'не указана'}\n\n"
            f"Для разблокировки обратитесь к администратору.",
            parse_mode="HTML"
        )
        return

    subscription_service = SubscriptionService(bot)

    # Проверяем подписку на материнский канал
    is_subscribed = await subscription_service.check_main_subscription(user_id)

    if not is_subscribed:
        await message.answer(Messages.not_subscribed(), parse_mode="HTML")
        return

    # Регистрируем/обновляем пользователя
    result = await subscription_service.register_user(user_id, username, first_name)
    status = result["status"]

    if status == "new":
        await message.answer(
            Messages.welcome_new(first_name),
            reply_markup=get_main_keyboard().as_markup(),
            parse_mode="HTML"
        )

        # Логируем
        await ActionLogModel.log(
            ActionLogModel.USER_REGISTERED,
            user_id,
            f"username: @{username}"
        )

    elif status == "reactivated":
        await message.answer(
            Messages.welcome_back(first_name),
            reply_markup=get_main_keyboard().as_markup(),
            parse_mode="HTML"
        )

        await ActionLogModel.log(
            ActionLogModel.USER_REACTIVATED,
            user_id,
            f"username: @{username}"
        )
    else:
        await message.answer(
            Messages.welcome_existing(first_name),
            reply_markup=get_main_keyboard().as_markup(),
            parse_mode="HTML"
        )


@user_router.message(Command("status"))
async def cmd_status(message: Message, bot: Bot):
    """Показать статус пользователя."""
    await show_user_status(message, bot)


@user_router.callback_query(F.data == "user:status")
async def callback_status(callback: CallbackQuery, bot: Bot):
    """Показать статус через callback."""
    await show_user_status(callback.message, bot, callback.from_user.id)
    await callback.answer()


async def show_user_status(message: Message, bot: Bot, user_id: int = None):
    """Общая функция показа статуса."""
    if user_id is None:
        user_id = message.from_user.id

    subscription_service = SubscriptionService(bot)
    status = await subscription_service.get_user_status(user_id)

    if not status["exists"]:
        await message.answer("❌ Вы не зарегистрированы. Нажмите /start", parse_mode="HTML")
        return

    user = status["user"]
    days = status["days_subscribed"]
    channels = status["channels"]

    # Находим следующий канал
    next_channel = None
    for ch in CHANNELS_CONFIG:
        if ch["days_required"] > days and ch["id"] != 0:
            next_channel = ch
            break

    text = Messages.user_status(
        first_name=user["first_name"] or "Пользователь",
        days=days,
        is_active=user["is_active"],
        channels=channels,
        next_channel=next_channel
    )

    builder = InlineKeyboardBuilder()
    builder.button(text="📺 Получить доступ", callback_data="user:channels")
    builder.button(text="⚙️ Настройки", callback_data="user:settings")
    builder.adjust(2)

    await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")


@user_router.message(Command("channels"))
async def cmd_channels(message: Message, bot: Bot):
    """Показать все доступные каналы пользователю."""
    await show_channels(message, bot)


@user_router.callback_query(F.data == "user:channels")
async def callback_channels(callback: CallbackQuery, bot: Bot):
    """Показать каналы через callback."""
    await show_channels(callback.message, bot, callback.from_user.id)
    await callback.answer()


async def show_channels(message: Message, bot: Bot, user_id: int = None):
    """Общая функция показа каналов."""
    if user_id is None:
        user_id = message.from_user.id

    subscription_service = SubscriptionService(bot)
    available = await subscription_service.get_available_channels(user_id)

    if not available:
        status = await subscription_service.get_user_status(user_id)
        if not status["exists"]:
            await message.answer("❌ Сначала зарегистрируйтесь: /start", parse_mode="HTML")
        else:
            await message.answer(
                "✅ Все доступные каналы уже открыты!\n\n"
                "Ожидайте новых по мере подписки.",
                parse_mode="HTML"
            )
        return

    # Выдаём доступ к каналам
    for channel in available:
        invite_link = await subscription_service.grant_channel_access(user_id, channel["id"])
        if invite_link:
            msg = await message.answer(
                Messages.channel_access_granted(
                    channel["name"],
                    invite_link,
                    channel.get("emoji", "🎁")
                ),
                parse_mode="HTML"
            )
            await UserChannelModel.update_message_id(user_id, channel["id"], msg.message_id)

            await ActionLogModel.log(
                ActionLogModel.CHANNEL_ACCESS_GRANTED,
                user_id,
                f"channel: {channel['name']}"
            )


@user_router.message(Command("settings"))
async def cmd_settings(message: Message):
    """Показать настройки."""
    await show_settings(message)


@user_router.callback_query(F.data == "user:settings")
async def callback_settings(callback: CallbackQuery):
    """Показать настройки через callback."""
    await show_settings(callback.message, callback.from_user.id)
    await callback.answer()


async def show_settings(message: Message, user_id: int = None):
    """Общая функция показа настроек."""
    if user_id is None:
        user_id = message.from_user.id

    user = await UserModel.get(user_id)
    if not user:
        await message.answer("❌ Вы не зарегистрированы. Нажмите /start")
        return

    notifications_on = user.get("notifications_enabled", True)

    await message.answer(
        "⚙️ <b>Настройки</b>\n\n"
        "Управляйте уведомлениями о новых каналах:",
        reply_markup=get_settings_keyboard(notifications_on).as_markup(),
        parse_mode="HTML"
    )


@user_router.callback_query(F.data == "settings:toggle_notifications")
async def toggle_notifications(callback: CallbackQuery):
    """Переключить уведомления."""
    user_id = callback.from_user.id
    user = await UserModel.get(user_id)

    if not user:
        await callback.answer("Ошибка!", show_alert=True)
        return

    current = user.get("notifications_enabled", True)
    await UserModelExtended.toggle_notifications(user_id, not current)

    await callback.message.edit_reply_markup(
        reply_markup=get_settings_keyboard(not current).as_markup()
    )
    await callback.answer(
        "🔔 Уведомления включены" if not current else "🔕 Уведомления выключены"
    )


@user_router.callback_query(F.data == "user:back")
async def callback_back(callback: CallbackQuery):
    """Вернуться в главное меню."""
    await callback.message.edit_text(
        "🏠 <b>Главное меню</b>\n\nВыберите действие:",
        reply_markup=get_main_keyboard().as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()


# ═══════════════════════════════════════
# ОБРАБОТКА СОБЫТИЙ КАНАЛА
# ═══════════════════════════════════════

@user_router.chat_member(ChatMemberUpdatedFilter(IS_MEMBER >> IS_NOT_MEMBER))
async def on_user_left(event: ChatMemberUpdated, bot: Bot):
    """Обработка отписки пользователя от материнского канала."""
    if event.chat.id != MAIN_CHANNEL_ID:
        return

    # Используем new_chat_member.user.id - это ID пользователя, чей статус изменился
    # event.from_user.id может быть ID админа, который кикнул пользователя
    user_id = event.new_chat_member.user.id
    logger.info(f"Пользователь {user_id} отписался от материнского канала")

    subscription_service = SubscriptionService(bot)

    # Отзываем все доступы
    message_ids = await subscription_service.revoke_user_access(user_id)

    # Логируем
    await ActionLogModel.log(
        ActionLogModel.USER_LEFT,
        user_id,
        f"channels_revoked: {len(message_ids)}"
    )

    # Удаляем сообщения с invite-ссылками
    for msg_id in message_ids:
        try:
            await bot.delete_message(user_id, msg_id)
        except Exception as e:
            logger.warning(f"Не удалось удалить сообщение {msg_id}: {e}")

    # Уведомляем пользователя
    try:
        await bot.send_message(user_id, Messages.user_left(), parse_mode="HTML")
    except Exception as e:
        logger.warning(f"Не удалось отправить уведомление: {e}")


@user_router.chat_member(ChatMemberUpdatedFilter(IS_NOT_MEMBER >> IS_MEMBER))
async def on_user_joined(event: ChatMemberUpdated, bot: Bot):
    """Обработка подписки на материнский канал."""
    if event.chat.id != MAIN_CHANNEL_ID:
        return

    # Используем new_chat_member.user.id - это ID пользователя, чей статус изменился
    user_id = event.new_chat_member.user.id
    logger.info(f"Пользователь {user_id} подписался на материнский канал")

    try:
        await bot.send_message(
            user_id,
            "👋 <b>Добро пожаловать в канал!</b>\n\n"
            "Чтобы получить доступ к дополнительным каналам и бонусам, "
            "нажмите /start",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.warning(f"Не удалось отправить приветствие: {e}")
