"""Красивые сообщения и прогресс-бар для бота."""

from typing import List, Optional
from config import CHANNELS_CONFIG


class ProgressBar:
    """Генератор прогресс-бара."""

    FILLED = "▓"
    EMPTY = "░"
    LENGTH = 10

    @classmethod
    def generate(cls, current: int, target: int, length: int = None) -> str:
        """Создать прогресс-бар."""
        if length is None:
            length = cls.LENGTH

        if target <= 0:
            return cls.FILLED * length

        progress = min(current / target, 1.0)
        filled = int(progress * length)
        empty = length - filled

        return cls.FILLED * filled + cls.EMPTY * empty

    @classmethod
    def with_percentage(cls, current: int, target: int, length: int = None) -> str:
        """Прогресс-бар с процентами."""
        bar = cls.generate(current, target, length)
        percentage = min(int(current / target * 100), 100) if target > 0 else 100
        return f"{bar} {percentage}%"

    @classmethod
    def with_numbers(cls, current: int, target: int, length: int = None) -> str:
        """Прогресс-бар с числами."""
        bar = cls.generate(current, target, length)
        return f"{bar} {current}/{target}"


class Messages:
    """Шаблоны красивых сообщений."""

    # ═══════════════════════════════════════
    # ПРИВЕТСТВЕННЫЕ СООБЩЕНИЯ
    # ═══════════════════════════════════════

    @staticmethod
    def welcome_new(first_name: str) -> str:
        return f"""
🎉 <b>Добро пожаловать, {first_name}!</b>

Вы успешно зарегистрированы в системе.

📚 <b>Как это работает:</b>
По мере вашей подписки на основной канал, вам будут открываться дополнительные каналы с эксклюзивным контентом.

🎯 <b>Доступные команды:</b>
• /status — ваш прогресс
• /channels — получить доступ
• /settings — настройки

Оставайтесь с нами! 🚀
"""

    @staticmethod
    def welcome_back(first_name: str) -> str:
        return f"""
👋 <b>С возвращением, {first_name}!</b>

Рады видеть вас снова!

⚠️ <b>Обратите внимание:</b>
Отсчёт времени подписки начинается заново.

Используйте /status для просмотра прогресса.
"""

    @staticmethod
    def welcome_existing(first_name: str) -> str:
        return f"""
👋 <b>Привет, {first_name}!</b>

Вы уже зарегистрированы в системе.
Используйте /status для просмотра прогресса.
"""

    # ═══════════════════════════════════════
    # СТАТУС ПОЛЬЗОВАТЕЛЯ
    # ═══════════════════════════════════════

    @staticmethod
    def user_status(
        first_name: str,
        days: int,
        is_active: bool,
        channels: List[dict],
        next_channel: Optional[dict] = None
    ) -> str:
        status_emoji = "✅" if is_active else "❌"
        status_text = "Активен" if is_active else "Неактивен"

        # Список открытых каналов
        if channels:
            channels_list = "\n".join([f"   ✅ {ch['name']}" for ch in channels])
        else:
            channels_list = "   📭 Пока нет открытых каналов"

        # Прогресс до следующего канала
        progress_section = ""
        if next_channel and is_active:
            days_left = next_channel["days_required"] - days
            progress = ProgressBar.with_percentage(days, next_channel["days_required"])
            progress_section = f"""

⏳ <b>Следующий канал:</b>
   {next_channel.get('emoji', '📺')} {next_channel['name']}
   {progress}
   До открытия: <b>{days_left}</b> дн."""

        return f"""
📊 <b>Ваш статус</b>

👤 <b>Имя:</b> {first_name}
📅 <b>Дней в подписке:</b> {days}
{status_emoji} <b>Статус:</b> {status_text}

📺 <b>Открытые каналы:</b>
{channels_list}{progress_section}
"""

    # ═══════════════════════════════════════
    # ДОСТУП К КАНАЛУ
    # ═══════════════════════════════════════

    @staticmethod
    def channel_access_granted(channel_name: str, invite_link: str, emoji: str = "🎁") -> str:
        return f"""
{emoji} <b>Новый канал доступен!</b>

Вам открыт доступ к каналу:
<b>{channel_name}</b>

🔗 <b>Ссылка для вступления:</b>
{invite_link}

⚠️ Ссылка одноразовая — используйте её сейчас!
"""

    @staticmethod
    def channel_upcoming(channel_name: str, days_left: int, emoji: str = "📺") -> str:
        days_word = Messages._pluralize_days(days_left)
        return f"""
🔔 <b>Скоро новый канал!</b>

{emoji} <b>{channel_name}</b>
откроется через <b>{days_left}</b> {days_word}!

Продолжайте быть подписчиком основного канала.
"""

    # ═══════════════════════════════════════
    # ОТПИСКА
    # ═══════════════════════════════════════

    @staticmethod
    def user_left() -> str:
        return """
😔 <b>Вы отписались от основного канала</b>

Ваш доступ ко всем дополнительным каналам был отозван.

💡 Хотите вернуться?
Подпишитесь на канал снова и нажмите /start
"""

    # ═══════════════════════════════════════
    # НЕ ПОДПИСАН
    # ═══════════════════════════════════════

    @staticmethod
    def not_subscribed() -> str:
        return """
❌ <b>Подписка не найдена</b>

Для использования бота необходимо:
1️⃣ Подписаться на основной канал
2️⃣ Нажать /start ещё раз

После подписки вам откроется доступ к эксклюзивному контенту!
"""

    # ═══════════════════════════════════════
    # АДМИНСКИЕ СООБЩЕНИЯ
    # ═══════════════════════════════════════

    @staticmethod
    def admin_stats(
        total: int,
        active: int,
        inactive: int,
        retention_rate: float,
        periods: List[dict]
    ) -> str:
        periods_text = "\n".join([
            f"   • {p['period']}: {p['count']} чел."
            for p in periods
        ]) if periods else "   Нет данных"

        return f"""
📊 <b>Статистика бота</b>

👥 <b>Пользователи:</b>
   • Всего: <b>{total}</b>
   • Активных: <b>{active}</b>
   • Неактивных: <b>{inactive}</b>
   • Retention: <b>{retention_rate}%</b>

📈 <b>По периодам:</b>
{periods_text}
"""

    @staticmethod
    def admin_daily_stats(stats: List[dict]) -> str:
        if not stats:
            return "📊 Нет данных за указанный период"

        lines = []
        for day in stats[:7]:  # Последние 7 дней
            lines.append(
                f"   📅 {day['date']}: "
                f"+{day['registrations']} / -{day['left_users']} / 🔓{day['access_granted']}"
            )

        return f"""
📊 <b>Статистика по дням</b>
<i>(регистрации / отписки / доступы)</i>

{chr(10).join(lines)}
"""

    @staticmethod
    def admin_logs(logs: List[dict]) -> str:
        if not logs:
            return "📋 Лог действий пуст"

        action_emojis = {
            "user_registered": "👤",
            "user_reactivated": "🔄",
            "user_left": "👋",
            "channel_access_granted": "🔓",
            "channel_access_revoked": "🔒",
            "admin_broadcast": "📢",
            "admin_mass_grant": "✅",
            "admin_mass_revoke": "❌",
            "channel_settings_changed": "⚙️"
        }

        lines = []
        for log in logs[:15]:
            emoji = action_emojis.get(log["action_type"], "📝")
            user_info = f"@{log['username']}" if log.get("username") else f"ID:{log['user_id']}" if log.get("user_id") else "—"
            lines.append(f"{emoji} {user_info}: {log['action_type']}")

        return f"""
📋 <b>Последние действия</b>

{chr(10).join(lines)}
"""

    # ═══════════════════════════════════════
    # ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ
    # ═══════════════════════════════════════

    @staticmethod
    def _pluralize_days(n: int) -> str:
        """Склонение слова 'день'."""
        if 11 <= n % 100 <= 19:
            return "дней"
        elif n % 10 == 1:
            return "день"
        elif 2 <= n % 10 <= 4:
            return "дня"
        else:
            return "дней"


class Keyboards:
    """Описания клавиатур (для использования с InlineKeyboardBuilder)."""

    MAIN_MENU = [
        ("📊 Мой статус", "user:status"),
        ("📺 Каналы", "user:channels"),
        ("⚙️ Настройки", "user:settings"),
    ]

    USER_SETTINGS = [
        ("🔔 Уведомления", "settings:notifications"),
        ("◀️ Назад", "user:back"),
    ]

    ADMIN_MENU = [
        ("📊 Статистика", "admin:stats"),
        ("📈 Аналитика", "admin:analytics"),
        ("👥 Пользователи", "admin:users"),
        ("📺 Каналы", "admin:channels"),
        ("📋 Логи", "admin:logs"),
        ("🔄 Проверка", "admin:run_check"),
    ]

    ADMIN_ANALYTICS = [
        ("📅 По дням", "analytics:daily"),
        ("📊 Retention", "analytics:retention"),
        ("◀️ Назад", "admin:back"),
    ]

    ADMIN_CHANNELS = [
        ("➕ Добавить канал", "channels:add"),
        ("✏️ Изменить дни", "channels:edit_days"),
        ("◀️ Назад", "admin:back"),
    ]

    ADMIN_USERS = [
        ("📋 Список", "users:list"),
        ("🔍 Найти", "users:search"),
        ("✅ Массовая выдача", "users:mass_grant"),
        ("❌ Массовый отзыв", "users:mass_revoke"),
        ("◀️ Назад", "admin:back"),
    ]
