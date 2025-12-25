import logging
from aiogram import Router, Bot, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import ADMIN_IDS, CHANNELS_CONFIG, MAIN_CHANNEL_ID
from database.models import (
    UserModel, ChannelModel, UserChannelModel,
    ActionLogModel, UserModelExtended, ChannelModelExtended
)
from services.subscription import SubscriptionService
from services.scheduler import SchedulerService
from utils.helpers import is_admin
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

    # Получаем всех пользователей с доступом
    users = await UserModel.get_active_users()
    revoked = 0

    for user in users:
        if await UserChannelModel.has_access(user["user_id"], channel_id):
            try:
                await bot.ban_chat_member(channel_id, user["user_id"])
                await bot.unban_chat_member(channel_id, user["user_id"], only_if_banned=True)
                revoked += 1
            except Exception:
                pass

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
