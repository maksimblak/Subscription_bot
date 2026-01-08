import logging
import asyncio
from aiogram import Router, Bot, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import ADMIN_IDS, CHANNELS_CONFIG, MAIN_CHANNEL_ID
from datetime import datetime, timezone
from database.models import (
    UserModel, ChannelModel, UserChannelModel,
    ActionLogModel, UserModelExtended, ChannelModelExtended,
    ScheduledBroadcastModel
)
from services.subscription import SubscriptionService
from services.scheduler import SchedulerService
from utils.helpers import is_admin, parse_date
from utils.messages import Messages, Keyboards

logger = logging.getLogger(__name__)

admin_router = Router()


# ═══════════════════════════════════════
# FSM STATES
# ═══════════════════════════════════════

class AdminStates(StatesGroup):
    waiting_channel_days = State()
    waiting_broadcast_text = State()
    waiting_mass_grant_days = State()
    waiting_mass_revoke_days = State()
    waiting_user_id_for_grant = State()  # Для ручной выдачи доступа
    waiting_user_id_for_bonus = State()  # Для начисления бонусных дней
    waiting_bonus_days = State()  # Ввод количества бонусных дней
    waiting_user_id_for_ban = State()  # Для бана пользователя
    waiting_ban_reason = State()  # Причина бана
    waiting_scheduled_text = State()  # Текст отложенной рассылки
    waiting_scheduled_datetime = State()  # Дата и время рассылки


# ═══════════════════════════════════════
# KEYBOARDS
# ═══════════════════════════════════════

def get_admin_keyboard() -> InlineKeyboardBuilder:
    """Главная клавиатура админа."""
    builder = InlineKeyboardBuilder()
    for text, callback in Keyboards.ADMIN_MENU:
        builder.button(text=text, callback_data=callback)
    builder.adjust(2)
    return builder


def get_analytics_keyboard() -> InlineKeyboardBuilder:
    """Клавиатура аналитики."""
    builder = InlineKeyboardBuilder()
    for text, callback in Keyboards.ADMIN_ANALYTICS:
        builder.button(text=text, callback_data=callback)
    builder.adjust(2)
    return builder


def get_channels_keyboard(channels: list) -> InlineKeyboardBuilder:
    """Клавиатура каналов."""
    builder = InlineKeyboardBuilder()
    for ch in channels:
        if not ch.get("is_main"):
            builder.button(
                text=f"{ch.get('emoji', '📺')} {ch['name']} ({ch['days_required']}д)",
                callback_data=f"channel:edit:{ch['channel_id']}"
            )
    builder.button(text="◀️ Назад", callback_data="admin:back")
    builder.adjust(1)
    return builder


def get_users_keyboard() -> InlineKeyboardBuilder:
    """Клавиатура управления пользователями."""
    builder = InlineKeyboardBuilder()
    for text, callback in Keyboards.ADMIN_USERS:
        builder.button(text=text, callback_data=callback)
    builder.adjust(2)
    return builder


# ═══════════════════════════════════════
# MAIN ADMIN COMMANDS
# ═══════════════════════════════════════

@admin_router.message(Command("admin"))
async def cmd_admin(message: Message):
    """Главное меню админ-панели."""
    if not is_admin(message.from_user.id):
        await message.answer("❌ У вас нет доступа к админ-панели.")
        return

    await message.answer(
        "🔧 <b>Админ-панель</b>\n\nВыберите действие:",
        reply_markup=get_admin_keyboard().as_markup(),
        parse_mode="HTML"
    )


@admin_router.callback_query(F.data == "admin:back")
async def admin_back(callback: CallbackQuery, state: FSMContext):
    """Вернуться в главное меню админа."""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    await state.clear()
    await callback.message.edit_text(
        "🔧 <b>Админ-панель</b>\n\nВыберите действие:",
        reply_markup=get_admin_keyboard().as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()


# ═══════════════════════════════════════
# STATISTICS
# ═══════════════════════════════════════

@admin_router.callback_query(F.data == "admin:stats")
async def admin_stats(callback: CallbackQuery):
    """Показать статистику."""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    retention = await UserModelExtended.get_retention_stats()

    text = Messages.admin_stats(
        total=retention["total"],
        active=retention["active"],
        inactive=retention["inactive"],
        retention_rate=retention["retention_rate"],
        periods=retention["by_period"]
    )

    builder = InlineKeyboardBuilder()
    builder.button(text="📈 Подробная аналитика", callback_data="admin:analytics")
    builder.button(text="◀️ Назад", callback_data="admin:back")
    builder.adjust(1)

    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await callback.answer()


@admin_router.message(Command("stats"))
async def cmd_stats(message: Message):
    """Быстрая команда для статистики."""
    if not is_admin(message.from_user.id):
        return

    retention = await UserModelExtended.get_retention_stats()

    text = Messages.admin_stats(
        total=retention["total"],
        active=retention["active"],
        inactive=retention["inactive"],
        retention_rate=retention["retention_rate"],
        periods=retention["by_period"]
    )

    await message.answer(text, parse_mode="HTML")


# ═══════════════════════════════════════
# ANALYTICS
# ═══════════════════════════════════════

@admin_router.callback_query(F.data == "admin:analytics")
async def admin_analytics(callback: CallbackQuery):
    """Меню аналитики."""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    await callback.message.edit_text(
        "📈 <b>Аналитика</b>\n\nВыберите тип отчёта:",
        reply_markup=get_analytics_keyboard().as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()


@admin_router.callback_query(F.data == "analytics:daily")
async def analytics_daily(callback: CallbackQuery):
    """Статистика по дням."""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    stats = await ActionLogModel.get_daily_stats(30)
    text = Messages.admin_daily_stats(stats)

    builder = InlineKeyboardBuilder()
    builder.button(text="◀️ Назад", callback_data="admin:analytics")
    builder.adjust(1)

    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await callback.answer()


@admin_router.callback_query(F.data == "analytics:retention")
async def analytics_retention(callback: CallbackQuery):
    """Статистика удержания."""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    retention = await UserModelExtended.get_retention_stats()
    action_stats = await ActionLogModel.get_stats_by_period(30)

    registrations = action_stats.get("user_registered", 0)
    left = action_stats.get("user_left", 0)
    churn_rate = round(left / retention["total"] * 100, 1) if retention["total"] > 0 else 0

    text = f"""
📊 <b>Retention & Churn</b>

📈 <b>За последние 30 дней:</b>
   • Новых регистраций: <b>{registrations}</b>
   • Отписались: <b>{left}</b>
   • Churn rate: <b>{churn_rate}%</b>

📊 <b>Общий Retention:</b>
   • Всего было: <b>{retention['total']}</b>
   • Осталось: <b>{retention['active']}</b>
   • Retention: <b>{retention['retention_rate']}%</b>
"""

    builder = InlineKeyboardBuilder()
    builder.button(text="◀️ Назад", callback_data="admin:analytics")
    builder.adjust(1)

    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await callback.answer()


# ═══════════════════════════════════════
# LOGS
# ═══════════════════════════════════════

@admin_router.callback_query(F.data == "admin:logs")
async def admin_logs(callback: CallbackQuery):
    """Показать логи действий."""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    logs = await ActionLogModel.get_recent(20)
    text = Messages.admin_logs(logs)

    builder = InlineKeyboardBuilder()
    builder.button(text="🔄 Обновить", callback_data="admin:logs")
    builder.button(text="◀️ Назад", callback_data="admin:back")
    builder.adjust(2)

    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await callback.answer()


# ═══════════════════════════════════════
# CHANNELS MANAGEMENT
# ═══════════════════════════════════════

@admin_router.callback_query(F.data == "admin:channels")
async def admin_channels(callback: CallbackQuery):
    """Управление каналами."""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    channels = await ChannelModel.get_all()

    text = f"""
📺 <b>Управление каналами</b>

🏠 <b>Материнский канал:</b> <code>{MAIN_CHANNEL_ID}</code>

Нажмите на канал для изменения количества дней:
"""

    await callback.message.edit_text(
        text,
        reply_markup=get_channels_keyboard(channels).as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()


@admin_router.callback_query(F.data.startswith("channel:edit:"))
async def edit_channel(callback: CallbackQuery, state: FSMContext):
    """Редактирование канала."""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    channel_id = int(callback.data.split(":")[2])
    channel = await ChannelModel.get(channel_id)

    if not channel:
        await callback.answer("Канал не найден", show_alert=True)
        return

    await state.update_data(editing_channel_id=channel_id)
    await state.set_state(AdminStates.waiting_channel_days)

    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отмена", callback_data="admin:channels")

    await callback.message.edit_text(
        f"✏️ <b>Редактирование канала</b>\n\n"
        f"📺 {channel['name']}\n"
        f"Текущее требование: <b>{channel['days_required']}</b> дней\n\n"
        f"Введите новое количество дней:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()


@admin_router.message(AdminStates.waiting_channel_days)
async def process_channel_days(message: Message, state: FSMContext):
    """Обработка нового количества дней."""
    if not is_admin(message.from_user.id):
        return

    try:
        new_days = int(message.text)
        if new_days < 0:
            raise ValueError()
    except ValueError:
        await message.answer("❌ Введите корректное число дней (0 или больше)")
        return

    data = await state.get_data()
    channel_id = data.get("editing_channel_id")

    await ChannelModelExtended.update_days(channel_id, new_days)
    channel = await ChannelModel.get(channel_id)

    await ActionLogModel.log(
        ActionLogModel.CHANNEL_SETTINGS_CHANGED,
        message.from_user.id,
        f"channel: {channel['name']}, new_days: {new_days}"
    )

    await state.clear()
    await message.answer(
        f"✅ Канал <b>{channel['name']}</b> обновлён!\n"
        f"Новое требование: <b>{new_days}</b> дней",
        parse_mode="HTML"
    )


# ═══════════════════════════════════════
# USERS MANAGEMENT
# ═══════════════════════════════════════

@admin_router.callback_query(F.data == "admin:users")
async def admin_users(callback: CallbackQuery):
    """Управление пользователями."""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    total = await UserModel.count_total()
    active = await UserModel.count_active()

    text = f"""
👥 <b>Управление пользователями</b>

📊 Всего: <b>{total}</b>
✅ Активных: <b>{active}</b>
❌ Неактивных: <b>{total - active}</b>

Выберите действие:
"""

    await callback.message.edit_text(
        text,
        reply_markup=get_users_keyboard().as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()


@admin_router.callback_query(F.data == "users:list")
async def users_list(callback: CallbackQuery):
    """Список пользователей."""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    users = await UserModel.get_all_users()

    if not users:
        await callback.message.edit_text("👥 Пользователей пока нет.")
        await callback.answer()
        return

    users_list = users[:20]
    text_lines = []

    for user in users_list:
        status = "✅" if user["is_active"] else "❌"
        username = f"@{user['username']}" if user["username"] else "—"
        text_lines.append(f"{status} <code>{user['user_id']}</code> | {username}")

    text = "\n".join(text_lines)
    total_text = f"\n\n📊 Показано {len(users_list)} из {len(users)}" if len(users) > 20 else ""

    builder = InlineKeyboardBuilder()
    builder.button(text="◀️ Назад", callback_data="admin:users")

    await callback.message.edit_text(
        f"👥 <b>Список пользователей</b>\n\n{text}{total_text}",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()


# ═══════════════════════════════════════
# MASS OPERATIONS
# ═══════════════════════════════════════

@admin_router.callback_query(F.data == "users:mass_grant")
async def mass_grant_start(callback: CallbackQuery, state: FSMContext):
    """Начать массовую выдачу доступа."""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    await state.set_state(AdminStates.waiting_mass_grant_days)

    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отмена", callback_data="admin:users")

    await callback.message.edit_text(
        "✅ <b>Массовая выдача доступа</b>\n\n"
        "Введите диапазон дней подписки (например: 30-60).\n"
        "Всем пользователям в этом диапазоне будет выдан доступ к следующему каналу.",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()


@admin_router.message(AdminStates.waiting_mass_grant_days)
async def process_mass_grant(message: Message, state: FSMContext, bot: Bot):
    """Обработка массовой выдачи."""
    if not is_admin(message.from_user.id):
        return

    try:
        parts = message.text.split("-")
        min_days = int(parts[0].strip())
        max_days = int(parts[1].strip())
    except (ValueError, IndexError):
        await message.answer("❌ Введите диапазон в формате: MIN-MAX (например: 30-60)")
        return

    await state.clear()

    users = await UserModelExtended.get_users_by_days_range(min_days, max_days)

    if not users:
        await message.answer(f"👥 Нет пользователей с {min_days}-{max_days} днями подписки")
        return

    subscription_service = SubscriptionService(bot)
    granted = 0

    for user in users:
        available = await subscription_service.get_available_channels(user["user_id"])
        if available:
            channel = available[0]  # Берём первый доступный
            invite_link = await subscription_service.grant_channel_access(user["user_id"], channel["id"])
            if invite_link:
                try:
                    msg = await bot.send_message(
                        user["user_id"],
                        f"🎁 <b>Вам открыт доступ к каналу {channel['name']}!</b>\n\n"
                        f"Ссылка: {invite_link}",
                        parse_mode="HTML"
                    )
                    await UserChannelModel.update_message_id(user["user_id"], channel["id"], msg.message_id)
                    granted += 1
                except Exception:
                    pass

    await ActionLogModel.log(
        ActionLogModel.ADMIN_MASS_GRANT,
        message.from_user.id,
        f"range: {min_days}-{max_days}, granted: {granted}"
    )

    await message.answer(
        f"✅ <b>Массовая выдача завершена</b>\n\n"
        f"Пользователей в диапазоне: {len(users)}\n"
        f"Выдано доступов: {granted}",
        parse_mode="HTML"
    )


@admin_router.callback_query(F.data == "users:mass_revoke")
async def mass_revoke_start(callback: CallbackQuery, state: FSMContext):
    """Начать массовый отзыв доступа."""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    channels = await ChannelModel.get_additional()

    builder = InlineKeyboardBuilder()
    for ch in channels:
        builder.button(
            text=f"❌ {ch['name']}",
            callback_data=f"mass_revoke:{ch['channel_id']}"
        )
    builder.button(text="◀️ Назад", callback_data="admin:users")
    builder.adjust(1)

    await callback.message.edit_text(
        "❌ <b>Массовый отзыв доступа</b>\n\n"
        "Выберите канал, доступ к которому нужно отозвать у всех пользователей:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()


@admin_router.callback_query(F.data.startswith("mass_revoke:"))
async def process_mass_revoke(callback: CallbackQuery, bot: Bot):
    """Обработка массового отзыва."""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    channel_id = int(callback.data.split(":")[1])
    channel = await ChannelModel.get(channel_id)

    if not channel:
        await callback.answer("Канал не найден", show_alert=True)
        return

    # Подтверждение
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Да, отозвать", callback_data=f"confirm_revoke:{channel_id}")
    builder.button(text="❌ Отмена", callback_data="admin:users")
    builder.adjust(2)

    await callback.message.edit_text(
        f"⚠️ <b>Подтверждение</b>\n\n"
        f"Вы уверены, что хотите отозвать доступ к каналу "
        f"<b>{channel['name']}</b> у ВСЕХ пользователей?",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()


@admin_router.callback_query(F.data.startswith("confirm_revoke:"))
async def confirm_mass_revoke(callback: CallbackQuery, bot: Bot):
    """Подтверждение массового отзыва."""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    channel_id = int(callback.data.split(":")[1])
    channel = await ChannelModel.get(channel_id)

    await callback.message.edit_text("⏳ Выполняется отзыв доступа...")

    # Получаем всех пользователей с доступом к этому каналу
    users_with_access = await UserChannelModel.get_users_with_channel_access(channel_id)
    revoked = 0

    for user_data in users_with_access:
        user_id = user_data["user_id"]
        try:
            # Удаляем из канала
            await bot.ban_chat_member(channel_id, user_id)
            await bot.unban_chat_member(channel_id, user_id, only_if_banned=True)
            # Удаляем запись из БД
            await UserChannelModel.revoke_access(user_id, channel_id)
            revoked += 1
        except Exception:
            # Даже при ошибке Telegram удаляем из БД
            await UserChannelModel.revoke_access(user_id, channel_id)

    await ActionLogModel.log(
        ActionLogModel.ADMIN_MASS_REVOKE,
        callback.from_user.id,
        f"channel: {channel['name']}, revoked: {revoked}"
    )

    await callback.message.edit_text(
        f"✅ <b>Массовый отзыв завершён</b>\n\n"
        f"Канал: {channel['name']}\n"
        f"Отозвано доступов: {revoked}",
        parse_mode="HTML"
    )
    await callback.answer()


# ═══════════════════════════════════════
# MANUAL GRANT (Платное ускорение)
# ═══════════════════════════════════════

@admin_router.callback_query(F.data == "users:manual_grant")
async def manual_grant_start(callback: CallbackQuery, state: FSMContext):
    """Начать ручную выдачу доступа."""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    await state.set_state(AdminStates.waiting_user_id_for_grant)

    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отмена", callback_data="admin:users")

    await callback.message.edit_text(
        "💎 <b>Ручная выдача доступа</b>\n\n"
        "Введите ID пользователя или @username:\n\n"
        "<i>Это позволяет выдать доступ к каналу раньше срока "
        "(например, за оплату)</i>",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()


@admin_router.message(AdminStates.waiting_user_id_for_grant)
async def process_user_for_grant(message: Message, state: FSMContext, bot: Bot):
    """Обработка введённого user_id для выдачи доступа."""
    if not is_admin(message.from_user.id):
        return

    user_input = message.text.strip()

    # Пробуем найти пользователя
    user = None

    if user_input.startswith("@"):
        # Поиск по username (эффективный запрос с индексом)
        username = user_input[1:]
        user = await UserModel.get_by_username(username)
    else:
        # Поиск по ID
        try:
            user_id = int(user_input)
            user = await UserModel.get(user_id)
        except ValueError:
            await message.answer("❌ Введите корректный ID (число) или @username")
            return

    if not user:
        await message.answer(
            "❌ Пользователь не найден в базе.\n"
            "Убедитесь, что он зарегистрирован через /start"
        )
        return

    # Очищаем состояние FSM (user_id передаётся через callback_data)
    await state.clear()

    # Получаем каналы, к которым у пользователя ещё нет доступа
    channels = await ChannelModel.get_additional()
    user_channels = await UserChannelModel.get_user_channels(user["user_id"])
    user_channel_ids = {ch["channel_id"] for ch in user_channels}

    available_channels = [ch for ch in channels if ch["channel_id"] not in user_channel_ids]

    if not available_channels:
        await message.answer(
            f"✅ У пользователя <code>{user['user_id']}</code> уже есть доступ ко всем каналам!",
            parse_mode="HTML"
        )
        return

    builder = InlineKeyboardBuilder()
    for ch in available_channels:
        builder.button(
            text=f"{ch.get('emoji', '📺')} {ch['name']} ({ch['days_required']}д)",
            callback_data=f"grant_to:{user['user_id']}:{ch['channel_id']}"
        )
    builder.button(text="❌ Отмена", callback_data="admin:users")
    builder.adjust(1)

    username_text = f"@{user['username']}" if user.get("username") else "—"

    await message.answer(
        f"💎 <b>Выдача доступа</b>\n\n"
        f"👤 Пользователь: <code>{user['user_id']}</code>\n"
        f"📝 Username: {username_text}\n"
        f"👋 Имя: {user.get('first_name', '—')}\n\n"
        f"Выберите канал для выдачи доступа:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )


@admin_router.callback_query(F.data.startswith("grant_to:"))
async def process_manual_grant(callback: CallbackQuery, bot: Bot):
    """Выдать доступ к выбранному каналу."""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    parts = callback.data.split(":")
    user_id = int(parts[1])
    channel_id = int(parts[2])

    user = await UserModel.get(user_id)
    channel = await ChannelModel.get(channel_id)

    if not user or not channel:
        await callback.answer("Ошибка: пользователь или канал не найден", show_alert=True)
        return

    # Проверяем, нет ли уже доступа
    if await UserChannelModel.has_access(user_id, channel_id):
        await callback.answer("У пользователя уже есть доступ к этому каналу", show_alert=True)
        return

    await callback.message.edit_text("⏳ Выдаю доступ...")

    subscription_service = SubscriptionService(bot)
    invite_link = await subscription_service.grant_channel_access(user_id, channel_id)

    if invite_link:
        # Отправляем пользователю ссылку
        try:
            msg = await bot.send_message(
                user_id,
                f"🎁 <b>Вам открыт доступ к каналу!</b>\n\n"
                f"📺 <b>{channel['name']}</b>\n\n"
                f"🔗 Ссылка для вступления:\n{invite_link}\n\n"
                f"⚠️ Ссылка одноразовая — используйте её сейчас!",
                parse_mode="HTML"
            )
            await UserChannelModel.update_message_id(user_id, channel_id, msg.message_id)
        except Exception as e:
            logger.warning(f"Не удалось отправить ссылку пользователю {user_id}: {e}")

        # Логируем
        await ActionLogModel.log(
            ActionLogModel.ADMIN_MANUAL_GRANT,
            user_id,
            f"channel: {channel['name']}, by_admin: {callback.from_user.id}"
        )

        builder = InlineKeyboardBuilder()
        builder.button(text="💎 Выдать ещё", callback_data="users:manual_grant")
        builder.button(text="◀️ Назад", callback_data="admin:users")
        builder.adjust(2)

        await callback.message.edit_text(
            f"✅ <b>Доступ выдан!</b>\n\n"
            f"👤 Пользователь: <code>{user_id}</code>\n"
            f"📺 Канал: <b>{channel['name']}</b>\n\n"
            f"Ссылка отправлена пользователю.",
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
    else:
        await callback.message.edit_text(
            "❌ Ошибка при создании ссылки.\n"
            "Убедитесь, что бот является админом канала.",
            parse_mode="HTML"
        )

    await callback.answer()


@admin_router.callback_query(F.data == "users:search")
async def users_search(callback: CallbackQuery, state: FSMContext):
    """Поиск пользователя."""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    await state.set_state(AdminStates.waiting_user_id_for_grant)

    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отмена", callback_data="admin:users")

    await callback.message.edit_text(
        "🔍 <b>Поиск пользователя</b>\n\n"
        "Введите ID пользователя или @username:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()


# ═══════════════════════════════════════
# RUN CHECK
# ═══════════════════════════════════════

@admin_router.callback_query(F.data == "admin:run_check")
async def admin_run_check(callback: CallbackQuery, bot: Bot):
    """Запустить проверку подписок вручную."""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    await callback.message.edit_text("⏳ Запускаю проверку подписок...")
    await callback.answer()

    scheduler_service = SchedulerService(bot)
    stats = await scheduler_service.run_check_now()

    builder = InlineKeyboardBuilder()
    builder.button(text="◀️ Назад", callback_data="admin:back")

    await callback.message.edit_text(
        f"✅ <b>Проверка завершена</b>\n\n"
        f"📊 Результаты:\n"
        f"   • Проверено: <b>{stats['checked']}</b>\n"
        f"   • Новых доступов: <b>{stats['new_access_granted']}</b>\n"
        f"   • Деактивировано: <b>{stats['deactivated']}</b>\n"
        f"   • Ошибок: <b>{stats['errors']}</b>",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )


# ═══════════════════════════════════════
# BROADCAST
# ═══════════════════════════════════════

@admin_router.message(Command("broadcast"))
async def cmd_broadcast(message: Message, state: FSMContext, bot: Bot):
    """Рассылка сообщения всем активным пользователям."""
    if not is_admin(message.from_user.id):
        return

    text = message.text.replace("/broadcast", "").strip()

    if not text:
        await state.set_state(AdminStates.waiting_broadcast_text)
        await message.answer(
            "📢 <b>Рассылка</b>\n\n"
            "Введите текст сообщения для рассылки всем активным пользователям.\n"
            "Поддерживается HTML-форматирование.",
            parse_mode="HTML"
        )
        return

    await do_broadcast(message, bot, text)


@admin_router.message(AdminStates.waiting_broadcast_text)
async def process_broadcast(message: Message, state: FSMContext, bot: Bot):
    """Обработка текста рассылки."""
    if not is_admin(message.from_user.id):
        return

    await state.clear()
    await do_broadcast(message, bot, message.text)


async def do_broadcast(message: Message, bot: Bot, text: str):
    """Выполнить рассылку."""
    users = await UserModel.get_active_users()
    sent = 0
    failed = 0

    status_msg = await message.answer(f"⏳ Рассылка: 0/{len(users)}...")

    for i, user in enumerate(users):
        try:
            await bot.send_message(user["user_id"], text, parse_mode="HTML")
            sent += 1
        except Exception:
            failed += 1

        # Rate limiting: задержка между сообщениями для предотвращения флуда
        await asyncio.sleep(0.05)

        if (i + 1) % 10 == 0:
            try:
                await status_msg.edit_text(f"⏳ Рассылка: {i + 1}/{len(users)}...")
            except Exception:
                pass

    await ActionLogModel.log(
        ActionLogModel.ADMIN_BROADCAST,
        message.from_user.id,
        f"sent: {sent}, failed: {failed}"
    )

    await status_msg.edit_text(
        f"✅ <b>Рассылка завершена</b>\n\n"
        f"📤 Отправлено: <b>{sent}</b>\n"
        f"❌ Ошибок: <b>{failed}</b>",
        parse_mode="HTML"
    )


# ═══════════════════════════════════════
# BONUS DAYS (Бонусные дни)
# ═══════════════════════════════════════

@admin_router.callback_query(F.data == "users:bonus_days")
async def bonus_days_start(callback: CallbackQuery, state: FSMContext):
    """Начать начисление бонусных дней."""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    await state.set_state(AdminStates.waiting_user_id_for_bonus)

    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отмена", callback_data="admin:users")

    await callback.message.edit_text(
        "🎁 <b>Начисление бонусных дней</b>\n\n"
        "Введите ID пользователя или @username:\n\n"
        "<i>Бонусные дни добавляются к реальным дням подписки</i>",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()


@admin_router.message(AdminStates.waiting_user_id_for_bonus)
async def process_user_for_bonus(message: Message, state: FSMContext):
    """Обработка пользователя для начисления бонусов."""
    if not is_admin(message.from_user.id):
        return

    user_input = message.text.strip()
    user = None

    if user_input.startswith("@"):
        # Поиск по username (эффективный запрос с индексом)
        username = user_input[1:]
        user = await UserModel.get_by_username(username)
    else:
        try:
            user_id = int(user_input)
            user = await UserModel.get(user_id)
        except ValueError:
            await message.answer("❌ Введите корректный ID (число) или @username")
            return

    if not user:
        await message.answer("❌ Пользователь не найден в базе")
        return

    await state.update_data(bonus_user_id=user["user_id"])
    await state.set_state(AdminStates.waiting_bonus_days)

    current_bonus = user.get("bonus_days", 0) or 0
    effective_days = await UserModelExtended.get_effective_days(user["user_id"])

    await message.answer(
        f"🎁 <b>Начисление бонусных дней</b>\n\n"
        f"👤 Пользователь: <code>{user['user_id']}</code>\n"
        f"📅 Текущих бонусов: <b>{current_bonus}</b> дн.\n"
        f"📊 Эффективных дней: <b>{effective_days}</b>\n\n"
        f"Введите количество дней для начисления:\n"
        f"<i>(отрицательное число уберёт дни)</i>",
        parse_mode="HTML"
    )


@admin_router.message(AdminStates.waiting_bonus_days)
async def process_bonus_days(message: Message, state: FSMContext):
    """Обработка количества бонусных дней."""
    if not is_admin(message.from_user.id):
        return

    try:
        days = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Введите корректное число")
        return

    data = await state.get_data()
    user_id = data.get("bonus_user_id")
    await state.clear()

    new_bonus = await UserModelExtended.add_bonus_days(user_id, days)

    await ActionLogModel.log(
        ActionLogModel.BONUS_DAYS_ADDED if days > 0 else ActionLogModel.BONUS_DAYS_REMOVED,
        user_id,
        f"days: {days}, new_total: {new_bonus}, by_admin: {message.from_user.id}"
    )

    action = "начислено" if days > 0 else "снято"
    await message.answer(
        f"✅ <b>Бонусные дни {action}!</b>\n\n"
        f"👤 Пользователь: <code>{user_id}</code>\n"
        f"📊 Изменение: <b>{days:+}</b> дн.\n"
        f"🎁 Всего бонусов: <b>{new_bonus}</b> дн.",
        parse_mode="HTML"
    )


# ═══════════════════════════════════════
# BAN/UNBAN (Блокировка пользователей)
# ═══════════════════════════════════════

@admin_router.callback_query(F.data == "users:ban")
async def ban_user_start(callback: CallbackQuery, state: FSMContext):
    """Начать блокировку пользователя."""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    await state.set_state(AdminStates.waiting_user_id_for_ban)

    builder = InlineKeyboardBuilder()
    builder.button(text="📋 Список забаненных", callback_data="users:banned_list")
    builder.button(text="❌ Отмена", callback_data="admin:users")
    builder.adjust(1)

    await callback.message.edit_text(
        "🚫 <b>Блокировка пользователя</b>\n\n"
        "Введите ID пользователя или @username:\n\n"
        "<i>Заблокированный пользователь не сможет использовать бота</i>",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()


@admin_router.message(AdminStates.waiting_user_id_for_ban)
async def process_user_for_ban(message: Message, state: FSMContext):
    """Обработка пользователя для бана."""
    if not is_admin(message.from_user.id):
        return

    user_input = message.text.strip()
    user = None

    if user_input.startswith("@"):
        # Поиск по username (эффективный запрос с индексом)
        username = user_input[1:]
        user = await UserModel.get_by_username(username)
    else:
        try:
            user_id = int(user_input)
            user = await UserModel.get(user_id)
        except ValueError:
            await message.answer("❌ Введите корректный ID (число) или @username")
            return

    if not user:
        await message.answer("❌ Пользователь не найден в базе")
        return

    if user.get("is_banned"):
        builder = InlineKeyboardBuilder()
        builder.button(text="🔓 Разблокировать", callback_data=f"unban:{user['user_id']}")
        builder.button(text="❌ Отмена", callback_data="admin:users")
        builder.adjust(2)

        await state.clear()
        await message.answer(
            f"⚠️ Пользователь <code>{user['user_id']}</code> уже заблокирован!\n\n"
            f"Причина: {user.get('ban_reason') or 'не указана'}",
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
        return

    await state.update_data(ban_user_id=user["user_id"])
    await state.set_state(AdminStates.waiting_ban_reason)

    builder = InlineKeyboardBuilder()
    builder.button(text="⏩ Без причины", callback_data=f"ban_now:{user['user_id']}")
    builder.button(text="❌ Отмена", callback_data="admin:users")
    builder.adjust(1)

    await message.answer(
        f"🚫 <b>Блокировка пользователя</b>\n\n"
        f"👤 <code>{user['user_id']}</code> | @{user.get('username') or '—'}\n\n"
        f"Введите причину блокировки (или нажмите кнопку ниже):",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )


@admin_router.message(AdminStates.waiting_ban_reason)
async def process_ban_reason(message: Message, state: FSMContext, bot: Bot):
    """Обработка причины бана."""
    if not is_admin(message.from_user.id):
        return

    data = await state.get_data()
    user_id = data.get("ban_user_id")
    reason = message.text.strip()

    await state.clear()
    await do_ban_user(message, user_id, reason)


@admin_router.callback_query(F.data.startswith("ban_now:"))
async def ban_without_reason(callback: CallbackQuery, state: FSMContext):
    """Забанить без причины."""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    user_id = int(callback.data.split(":")[1])
    await state.clear()
    await do_ban_user(callback.message, user_id, None)
    await callback.answer()


async def do_ban_user(message: Message, user_id: int, reason: str = None):
    """Выполнить бан пользователя."""
    await UserModelExtended.ban_user(user_id, reason)

    await ActionLogModel.log(
        ActionLogModel.USER_BANNED,
        user_id,
        f"reason: {reason or 'not specified'}"
    )

    await message.answer(
        f"🚫 <b>Пользователь заблокирован!</b>\n\n"
        f"👤 ID: <code>{user_id}</code>\n"
        f"📝 Причина: {reason or 'не указана'}",
        parse_mode="HTML"
    )


@admin_router.callback_query(F.data.startswith("unban:"))
async def unban_user(callback: CallbackQuery):
    """Разблокировать пользователя."""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    user_id = int(callback.data.split(":")[1])
    await UserModelExtended.unban_user(user_id)

    await ActionLogModel.log(
        ActionLogModel.USER_UNBANNED,
        user_id,
        f"by_admin: {callback.from_user.id}"
    )

    await callback.message.edit_text(
        f"✅ <b>Пользователь разблокирован!</b>\n\n"
        f"👤 ID: <code>{user_id}</code>",
        parse_mode="HTML"
    )
    await callback.answer()


@admin_router.callback_query(F.data == "users:banned_list")
async def banned_list(callback: CallbackQuery):
    """Список заблокированных пользователей."""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    banned = await UserModelExtended.get_banned_users()

    if not banned:
        builder = InlineKeyboardBuilder()
        builder.button(text="◀️ Назад", callback_data="admin:users")
        await callback.message.edit_text(
            "✅ Нет заблокированных пользователей",
            reply_markup=builder.as_markup()
        )
        await callback.answer()
        return

    builder = InlineKeyboardBuilder()
    for user in banned[:10]:
        username = f"@{user['username']}" if user.get("username") else f"ID:{user['user_id']}"
        builder.button(text=f"🔓 {username}", callback_data=f"unban:{user['user_id']}")
    builder.button(text="◀️ Назад", callback_data="admin:users")
    builder.adjust(1)

    await callback.message.edit_text(
        f"🚫 <b>Заблокированные пользователи</b>\n\n"
        f"Всего: {len(banned)}\n\n"
        f"Нажмите на пользователя для разблокировки:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()


# ═══════════════════════════════════════
# SCHEDULED BROADCASTS (Отложенные рассылки)
# ═══════════════════════════════════════

@admin_router.callback_query(F.data == "admin:scheduled")
async def scheduled_menu(callback: CallbackQuery):
    """Меню отложенных рассылок."""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    upcoming = await ScheduledBroadcastModel.get_upcoming()

    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Создать рассылку", callback_data="scheduled:create")
    if upcoming:
        builder.button(text=f"📋 Ожидают ({len(upcoming)})", callback_data="scheduled:list")
    builder.button(text="📜 История", callback_data="scheduled:history")
    builder.button(text="◀️ Назад", callback_data="admin:back")
    builder.adjust(1)

    await callback.message.edit_text(
        f"⏰ <b>Отложенные рассылки</b>\n\n"
        f"📊 Ожидают отправки: <b>{len(upcoming)}</b>",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()


@admin_router.callback_query(F.data == "scheduled:create")
async def scheduled_create(callback: CallbackQuery, state: FSMContext):
    """Создание новой отложенной рассылки."""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    await state.set_state(AdminStates.waiting_scheduled_text)

    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отмена", callback_data="admin:scheduled")

    await callback.message.edit_text(
        "⏰ <b>Создание отложенной рассылки</b>\n\n"
        "Шаг 1/2: Введите текст сообщения:\n\n"
        "<i>Поддерживается HTML-форматирование</i>",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()


@admin_router.message(AdminStates.waiting_scheduled_text)
async def process_scheduled_text(message: Message, state: FSMContext):
    """Обработка текста отложенной рассылки."""
    if not is_admin(message.from_user.id):
        return

    await state.update_data(scheduled_text=message.text)
    await state.set_state(AdminStates.waiting_scheduled_datetime)

    await message.answer(
        "⏰ <b>Создание отложенной рассылки</b>\n\n"
        "Шаг 2/2: Введите дату и время отправки:\n\n"
        "Формат: <code>ДД.ММ.ГГГГ ЧЧ:ММ</code>\n"
        "Пример: <code>25.12.2024 10:00</code>\n\n"
        "<i>Время по Москве (UTC+3)</i>",
        parse_mode="HTML"
    )


@admin_router.message(AdminStates.waiting_scheduled_datetime)
async def process_scheduled_datetime(message: Message, state: FSMContext):
    """Обработка даты и времени рассылки."""
    if not is_admin(message.from_user.id):
        return

    try:
        # Парсим время как UTC
        scheduled_at = datetime.strptime(message.text.strip(), "%d.%m.%Y %H:%M").replace(tzinfo=timezone.utc)
    except ValueError:
        await message.answer(
            "❌ Неверный формат!\n\n"
            "Используйте: <code>ДД.ММ.ГГГГ ЧЧ:ММ</code>\n"
            "Например: <code>25.12.2024 10:00</code>",
            parse_mode="HTML"
        )
        return

    # Сравниваем с текущим временем UTC
    if scheduled_at <= datetime.now(timezone.utc):
        await message.answer("❌ Дата должна быть в будущем!")
        return

    data = await state.get_data()
    text = data.get("scheduled_text")
    await state.clear()

    broadcast_id = await ScheduledBroadcastModel.create(
        text=text,
        scheduled_at=scheduled_at,
        created_by=message.from_user.id
    )

    await ActionLogModel.log(
        ActionLogModel.SCHEDULED_BROADCAST_CREATED,
        message.from_user.id,
        f"id: {broadcast_id}, scheduled_at: {scheduled_at}"
    )

    await message.answer(
        f"✅ <b>Рассылка запланирована!</b>\n\n"
        f"📅 Дата: <b>{scheduled_at.strftime('%d.%m.%Y %H:%M')}</b>\n"
        f"🆔 ID: <code>{broadcast_id}</code>\n\n"
        f"📝 Текст:\n{text[:200]}{'...' if len(text) > 200 else ''}",
        parse_mode="HTML"
    )


@admin_router.callback_query(F.data == "scheduled:list")
async def scheduled_list(callback: CallbackQuery):
    """Список ожидающих рассылок."""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    upcoming = await ScheduledBroadcastModel.get_upcoming()

    if not upcoming:
        builder = InlineKeyboardBuilder()
        builder.button(text="➕ Создать", callback_data="scheduled:create")
        builder.button(text="◀️ Назад", callback_data="admin:scheduled")
        builder.adjust(2)

        await callback.message.edit_text(
            "📋 Нет запланированных рассылок",
            reply_markup=builder.as_markup()
        )
        await callback.answer()
        return

    builder = InlineKeyboardBuilder()
    for bc in upcoming[:10]:
        scheduled_at = parse_date(bc["scheduled_at"]) or datetime.now()
        builder.button(
            text=f"🗑 {scheduled_at.strftime('%d.%m %H:%M')}",
            callback_data=f"scheduled:delete:{bc['id']}"
        )
    builder.button(text="◀️ Назад", callback_data="admin:scheduled")
    builder.adjust(1)

    text = "📋 <b>Запланированные рассылки</b>\n\n"
    for bc in upcoming[:5]:
        scheduled_at = parse_date(bc["scheduled_at"]) or datetime.now()
        text += f"• {scheduled_at.strftime('%d.%m.%Y %H:%M')}\n"
        text += f"  <i>{bc['text'][:50]}{'...' if len(bc['text']) > 50 else ''}</i>\n\n"

    await callback.message.edit_text(
        text + "\nНажмите для удаления:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()


@admin_router.callback_query(F.data.startswith("scheduled:delete:"))
async def scheduled_delete(callback: CallbackQuery):
    """Удаление запланированной рассылки."""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    broadcast_id = int(callback.data.split(":")[2])
    await ScheduledBroadcastModel.delete(broadcast_id)

    await callback.answer("✅ Рассылка удалена", show_alert=True)

    # Обновляем список
    upcoming = await ScheduledBroadcastModel.get_upcoming()
    if upcoming:
        await scheduled_list(callback)
    else:
        builder = InlineKeyboardBuilder()
        builder.button(text="➕ Создать", callback_data="scheduled:create")
        builder.button(text="◀️ Назад", callback_data="admin:scheduled")
        builder.adjust(2)

        await callback.message.edit_text(
            "📋 Нет запланированных рассылок",
            reply_markup=builder.as_markup()
        )


@admin_router.callback_query(F.data == "scheduled:history")
async def scheduled_history(callback: CallbackQuery):
    """История отправленных рассылок."""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    all_broadcasts = await ScheduledBroadcastModel.get_all(20)
    sent = [bc for bc in all_broadcasts if bc.get("is_sent")]

    builder = InlineKeyboardBuilder()
    builder.button(text="◀️ Назад", callback_data="admin:scheduled")

    if not sent:
        await callback.message.edit_text(
            "📜 История рассылок пуста",
            reply_markup=builder.as_markup()
        )
        await callback.answer()
        return

    text = "📜 <b>История рассылок</b>\n\n"
    for bc in sent[:10]:
        sent_at = parse_date(bc["sent_at"]) or datetime.now()
        text += (
            f"• {sent_at.strftime('%d.%m.%Y %H:%M')}\n"
            f"  📤 {bc['sent_count']} | ❌ {bc['failed_count']}\n\n"
        )

    await callback.message.edit_text(
        text,
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()
