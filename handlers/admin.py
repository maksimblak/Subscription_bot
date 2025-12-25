import logging
from aiogram import Router, Bot, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import ADMIN_IDS, CHANNELS_CONFIG, MAIN_CHANNEL_ID
from database.models import UserModel, ChannelModel, UserChannelModel
from services.subscription import SubscriptionService
from services.scheduler import SchedulerService
from utils.helpers import is_admin

logger = logging.getLogger(__name__)

admin_router = Router()


# Фильтр для проверки админа
class AdminFilter:
    def __call__(self, message: Message) -> bool:
        return is_admin(message.from_user.id)


@admin_router.message(Command("admin"))
async def cmd_admin(message: Message):
    """Главное меню админ-панели."""
    if not is_admin(message.from_user.id):
        await message.answer("❌ У вас нет доступа к админ-панели.")
        return

    builder = InlineKeyboardBuilder()
    builder.button(text="📊 Статистика", callback_data="admin:stats")
    builder.button(text="👥 Пользователи", callback_data="admin:users")
    builder.button(text="📺 Каналы", callback_data="admin:channels")
    builder.button(text="🔄 Запустить проверку", callback_data="admin:run_check")
    builder.adjust(2)

    await message.answer(
        "🔧 <b>Админ-панель</b>\n\nВыберите действие:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )


@admin_router.callback_query(F.data == "admin:stats")
async def admin_stats(callback: CallbackQuery):
    """Показать статистику."""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    total_users = await UserModel.count_total()
    active_users = await UserModel.count_active()

    # Статистика по каналам
    channels_stats = []
    for channel in CHANNELS_CONFIG:
        if channel["id"] != 0:
            # Подсчитываем пользователей с доступом к этому каналу
            users_with_access = await UserChannelModel.get_user_channels_count(channel["id"])
            channels_stats.append(f"  • {channel['name']}: {users_with_access} чел.")

    channels_text = "\n".join(channels_stats) if channels_stats else "  Нет данных"

    await callback.message.edit_text(
        f"📊 <b>Статистика бота</b>\n\n"
        f"👥 <b>Пользователи:</b>\n"
        f"  • Всего: {total_users}\n"
        f"  • Активных: {active_users}\n"
        f"  • Неактивных: {total_users - active_users}\n\n"
        f"📺 <b>Доступ к каналам:</b>\n{channels_text}",
        parse_mode="HTML"
    )
    await callback.answer()


@admin_router.callback_query(F.data == "admin:users")
async def admin_users(callback: CallbackQuery):
    """Список пользователей."""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    users = await UserModel.get_all_users()

    if not users:
        await callback.message.edit_text("👥 Пользователей пока нет.")
        await callback.answer()
        return

    # Показываем первых 20 пользователей
    users_list = users[:20]
    text_lines = []

    for user in users_list:
        status = "✅" if user["is_active"] else "❌"
        username = f"@{user['username']}" if user["username"] else "—"
        text_lines.append(
            f"{status} {user['user_id']} | {username} | {user['first_name'] or '—'}"
        )

    text = "\n".join(text_lines)
    total_text = f"\n\n📊 Показано {len(users_list)} из {len(users)}" if len(users) > 20 else ""

    await callback.message.edit_text(
        f"👥 <b>Пользователи</b>\n\n"
        f"<code>{text}</code>"
        f"{total_text}",
        parse_mode="HTML"
    )
    await callback.answer()


@admin_router.callback_query(F.data == "admin:channels")
async def admin_channels(callback: CallbackQuery):
    """Информация о каналах."""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    text_lines = [f"🏠 <b>Материнский канал:</b> {MAIN_CHANNEL_ID}\n"]

    for channel in CHANNELS_CONFIG:
        if channel["id"] != 0:
            text_lines.append(
                f"📺 <b>{channel['name']}</b>\n"
                f"   ID: {channel['id']}\n"
                f"   Требуется дней: {channel['days_required']}"
            )

    await callback.message.edit_text(
        f"📺 <b>Настроенные каналы</b>\n\n" + "\n\n".join(text_lines),
        parse_mode="HTML"
    )
    await callback.answer()


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

    await callback.message.edit_text(
        f"✅ <b>Проверка завершена</b>\n\n"
        f"📊 Результаты:\n"
        f"  • Проверено: {stats['checked']}\n"
        f"  • Новых доступов: {stats['new_access_granted']}\n"
        f"  • Деактивировано: {stats['deactivated']}\n"
        f"  • Ошибок: {stats['errors']}",
        parse_mode="HTML"
    )


@admin_router.message(Command("stats"))
async def cmd_stats(message: Message):
    """Быстрая команда для статистики."""
    if not is_admin(message.from_user.id):
        return

    total_users = await UserModel.count_total()
    active_users = await UserModel.count_active()

    await message.answer(
        f"📊 <b>Быстрая статистика</b>\n\n"
        f"👥 Всего: {total_users}\n"
        f"✅ Активных: {active_users}\n"
        f"❌ Неактивных: {total_users - active_users}",
        parse_mode="HTML"
    )


@admin_router.message(Command("broadcast"))
async def cmd_broadcast(message: Message, bot: Bot):
    """Рассылка сообщения всем активным пользователям."""
    if not is_admin(message.from_user.id):
        return

    # Получаем текст для рассылки
    text = message.text.replace("/broadcast", "").strip()

    if not text:
        await message.answer(
            "📢 <b>Рассылка</b>\n\n"
            "Использование: /broadcast Текст сообщения\n\n"
            "Сообщение будет отправлено всем активным пользователям.",
            parse_mode="HTML"
        )
        return

    users = await UserModel.get_active_users()
    sent = 0
    failed = 0

    await message.answer(f"⏳ Начинаю рассылку для {len(users)} пользователей...")

    for user in users:
        try:
            await bot.send_message(user["user_id"], text, parse_mode="HTML")
            sent += 1
        except Exception:
            failed += 1

    await message.answer(
        f"✅ <b>Рассылка завершена</b>\n\n"
        f"📤 Отправлено: {sent}\n"
        f"❌ Ошибок: {failed}",
        parse_mode="HTML"
    )
