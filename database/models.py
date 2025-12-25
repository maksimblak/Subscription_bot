from datetime import datetime
from typing import Optional, List
from .db import db


class UserModel:
    """Модель для работы с пользователями."""

    @staticmethod
    async def create(
        user_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None
    ) -> bool:
        """Создать нового пользователя."""
        try:
            await db.execute(
                """
                INSERT INTO users (user_id, username, first_name, join_date, is_active)
                VALUES (?, ?, ?, ?, 1)
                """,
                (user_id, username, first_name, datetime.now())
            )
            return True
        except Exception:
            return False

    @staticmethod
    async def get(user_id: int) -> Optional[dict]:
        """Получить пользователя по ID."""
        row = await db.fetchone(
            "SELECT * FROM users WHERE user_id = ?",
            (user_id,)
        )
        return dict(row) if row else None

    @staticmethod
    async def update_active(user_id: int, is_active: bool):
        """Обновить статус активности пользователя."""
        await db.execute(
            "UPDATE users SET is_active = ?, last_check = ? WHERE user_id = ?",
            (is_active, datetime.now(), user_id)
        )

    @staticmethod
    async def get_active_users() -> List[dict]:
        """Получить всех активных пользователей."""
        rows = await db.fetchall(
            "SELECT * FROM users WHERE is_active = 1"
        )
        return [dict(row) for row in rows]

    @staticmethod
    async def get_all_users() -> List[dict]:
        """Получить всех пользователей."""
        rows = await db.fetchall("SELECT * FROM users")
        return [dict(row) for row in rows]

    @staticmethod
    async def count_active() -> int:
        """Подсчитать активных пользователей."""
        row = await db.fetchone(
            "SELECT COUNT(*) as count FROM users WHERE is_active = 1"
        )
        return row["count"] if row else 0

    @staticmethod
    async def count_total() -> int:
        """Подсчитать всех пользователей."""
        row = await db.fetchone("SELECT COUNT(*) as count FROM users")
        return row["count"] if row else 0

    @staticmethod
    async def get_by_username(username: str) -> Optional[dict]:
        """Получить пользователя по username (без @, регистронезависимо)."""
        row = await db.fetchone(
            "SELECT * FROM users WHERE username = ? COLLATE NOCASE",
            (username,)
        )
        return dict(row) if row else None


class ChannelModel:
    """Модель для работы с каналами."""

    @staticmethod
    async def create(
        channel_id: int,
        name: str,
        days_required: int = 0,
        is_main: bool = False
    ) -> bool:
        """Создать или обновить канал."""
        try:
            await db.execute(
                """
                INSERT OR REPLACE INTO channels (channel_id, name, days_required, is_main)
                VALUES (?, ?, ?, ?)
                """,
                (channel_id, name, days_required, is_main)
            )
            return True
        except Exception:
            return False

    @staticmethod
    async def get(channel_id: int) -> Optional[dict]:
        """Получить канал по ID."""
        row = await db.fetchone(
            "SELECT * FROM channels WHERE channel_id = ?",
            (channel_id,)
        )
        return dict(row) if row else None

    @staticmethod
    async def get_all() -> List[dict]:
        """Получить все каналы."""
        rows = await db.fetchall(
            "SELECT * FROM channels ORDER BY days_required"
        )
        return [dict(row) for row in rows]

    @staticmethod
    async def get_additional() -> List[dict]:
        """Получить дополнительные каналы (не материнский)."""
        rows = await db.fetchall(
            "SELECT * FROM channels WHERE is_main = 0 ORDER BY days_required"
        )
        return [dict(row) for row in rows]


class UserChannelModel:
    """Модель для связи пользователей с каналами."""

    @staticmethod
    async def grant_access(
        user_id: int,
        channel_id: int,
        message_id: Optional[int] = None
    ) -> bool:
        """Выдать доступ пользователю к каналу."""
        try:
            await db.execute(
                """
                INSERT OR IGNORE INTO user_channels (user_id, channel_id, granted_at, message_id)
                VALUES (?, ?, ?, ?)
                """,
                (user_id, channel_id, datetime.now(), message_id)
            )
            return True
        except Exception:
            return False

    @staticmethod
    async def update_message_id(user_id: int, channel_id: int, message_id: int):
        """Обновить ID сообщения с приглашением."""
        await db.execute(
            """
            UPDATE user_channels SET message_id = ?
            WHERE user_id = ? AND channel_id = ?
            """,
            (message_id, user_id, channel_id)
        )

    @staticmethod
    async def get_user_channels(user_id: int) -> List[dict]:
        """Получить все каналы пользователя."""
        rows = await db.fetchall(
            """
            SELECT uc.*, c.name, c.days_required
            FROM user_channels uc
            JOIN channels c ON uc.channel_id = c.channel_id
            WHERE uc.user_id = ?
            """,
            (user_id,)
        )
        return [dict(row) for row in rows]

    @staticmethod
    async def has_access(user_id: int, channel_id: int) -> bool:
        """Проверить, есть ли у пользователя доступ к каналу."""
        row = await db.fetchone(
            "SELECT 1 FROM user_channels WHERE user_id = ? AND channel_id = ?",
            (user_id, channel_id)
        )
        return row is not None

    @staticmethod
    async def revoke_all(user_id: int) -> List[dict]:
        """Отозвать все доступы пользователя и вернуть информацию о них."""
        # Сначала получаем информацию о каналах
        rows = await db.fetchall(
            """
            SELECT uc.channel_id, uc.message_id
            FROM user_channels uc
            WHERE uc.user_id = ?
            """,
            (user_id,)
        )
        channels_info = [dict(row) for row in rows]

        # Удаляем записи
        await db.execute(
            "DELETE FROM user_channels WHERE user_id = ?",
            (user_id,)
        )

        return channels_info

    @staticmethod
    async def get_user_channels_count(channel_id: int) -> int:
        """Подсчитать количество пользователей с доступом к каналу."""
        row = await db.fetchone(
            "SELECT COUNT(*) as count FROM user_channels WHERE channel_id = ?",
            (channel_id,)
        )
        return row["count"] if row else 0

    @staticmethod
    async def revoke_access(user_id: int, channel_id: int) -> bool:
        """Отозвать доступ пользователя к конкретному каналу."""
        try:
            await db.execute(
                "DELETE FROM user_channels WHERE user_id = ? AND channel_id = ?",
                (user_id, channel_id)
            )
            return True
        except Exception:
            return False

    @staticmethod
    async def get_users_with_channel_access(channel_id: int) -> List[dict]:
        """Получить всех пользователей с доступом к каналу."""
        rows = await db.fetchall(
            """
            SELECT uc.user_id, uc.message_id, u.username, u.first_name
            FROM user_channels uc
            JOIN users u ON uc.user_id = u.user_id
            WHERE uc.channel_id = ?
            """,
            (channel_id,)
        )
        return [dict(row) for row in rows]


class ActionLogModel:
    """Модель для логирования действий."""

    # Типы действий
    USER_REGISTERED = "user_registered"
    USER_REACTIVATED = "user_reactivated"
    USER_LEFT = "user_left"
    CHANNEL_ACCESS_GRANTED = "channel_access_granted"
    CHANNEL_ACCESS_REVOKED = "channel_access_revoked"
    ADMIN_BROADCAST = "admin_broadcast"
    ADMIN_MASS_GRANT = "admin_mass_grant"
    ADMIN_MASS_REVOKE = "admin_mass_revoke"
    ADMIN_MANUAL_GRANT = "admin_manual_grant"  # Ручная выдача доступа (платное ускорение)
    CHANNEL_SETTINGS_CHANGED = "channel_settings_changed"
    USER_BANNED = "user_banned"
    USER_UNBANNED = "user_unbanned"
    BONUS_DAYS_ADDED = "bonus_days_added"
    BONUS_DAYS_REMOVED = "bonus_days_removed"
    SCHEDULED_BROADCAST_CREATED = "scheduled_broadcast_created"
    SCHEDULED_BROADCAST_SENT = "scheduled_broadcast_sent"

    @staticmethod
    async def log(
        action_type: str,
        user_id: Optional[int] = None,
        details: Optional[str] = None
    ):
        """Записать действие в лог."""
        await db.execute(
            """
            INSERT INTO action_logs (user_id, action_type, details, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, action_type, details, datetime.now())
        )

    @staticmethod
    async def get_recent(limit: int = 50) -> List[dict]:
        """Получить последние записи лога."""
        rows = await db.fetchall(
            """
            SELECT al.*, u.username, u.first_name
            FROM action_logs al
            LEFT JOIN users u ON al.user_id = u.user_id
            ORDER BY al.created_at DESC
            LIMIT ?
            """,
            (limit,)
        )
        return [dict(row) for row in rows]

    @staticmethod
    async def get_by_user(user_id: int, limit: int = 20) -> List[dict]:
        """Получить логи по пользователю."""
        rows = await db.fetchall(
            """
            SELECT * FROM action_logs
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (user_id, limit)
        )
        return [dict(row) for row in rows]

    @staticmethod
    async def get_stats_by_period(days: int = 30) -> dict:
        """Получить статистику действий за период."""
        rows = await db.fetchall(
            """
            SELECT action_type, COUNT(*) as count
            FROM action_logs
            WHERE created_at >= datetime('now', ?)
            GROUP BY action_type
            """,
            (f'-{days} days',)
        )
        return {row["action_type"]: row["count"] for row in rows}

    @staticmethod
    async def get_daily_stats(days: int = 30) -> List[dict]:
        """Получить статистику по дням."""
        rows = await db.fetchall(
            """
            SELECT
                DATE(created_at) as date,
                SUM(CASE WHEN action_type = 'user_registered' THEN 1 ELSE 0 END) as registrations,
                SUM(CASE WHEN action_type = 'user_left' THEN 1 ELSE 0 END) as left_users,
                SUM(CASE WHEN action_type = 'channel_access_granted' THEN 1 ELSE 0 END) as access_granted
            FROM action_logs
            WHERE created_at >= datetime('now', ?)
            GROUP BY DATE(created_at)
            ORDER BY date DESC
            """,
            (f'-{days} days',)
        )
        return [dict(row) for row in rows]


class SettingsModel:
    """Модель для настроек бота."""

    @staticmethod
    async def get(key: str, default: str = None) -> Optional[str]:
        """Получить значение настройки."""
        row = await db.fetchone(
            "SELECT value FROM settings WHERE key = ?",
            (key,)
        )
        return row["value"] if row else default

    @staticmethod
    async def set(key: str, value: str):
        """Установить значение настройки."""
        await db.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, value)
        )

    @staticmethod
    async def delete(key: str):
        """Удалить настройку."""
        await db.execute(
            "DELETE FROM settings WHERE key = ?",
            (key,)
        )


# Расширение ChannelModel
class ChannelModelExtended(ChannelModel):
    """Расширенная модель каналов."""

    @staticmethod
    async def update_days(channel_id: int, days_required: int):
        """Обновить количество дней для канала."""
        await db.execute(
            "UPDATE channels SET days_required = ? WHERE channel_id = ?",
            (days_required, channel_id)
        )

    @staticmethod
    async def update_info(
        channel_id: int,
        name: Optional[str] = None,
        description: Optional[str] = None,
        emoji: Optional[str] = None
    ):
        """Обновить информацию о канале."""
        updates = []
        params = []
        if name is not None:
            updates.append("name = ?")
            params.append(name)
        if description is not None:
            updates.append("description = ?")
            params.append(description)
        if emoji is not None:
            updates.append("emoji = ?")
            params.append(emoji)

        if updates:
            params.append(channel_id)
            await db.execute(
                f"UPDATE channels SET {', '.join(updates)} WHERE channel_id = ?",
                tuple(params)
            )


# Расширение UserModel
class UserModelExtended(UserModel):
    """Расширенная модель пользователей."""

    @staticmethod
    async def get_users_by_days_range(min_days: int, max_days: int) -> List[dict]:
        """Получить пользователей по диапазону дней подписки."""
        rows = await db.fetchall(
            """
            SELECT *,
                   CAST((julianday('now') - julianday(join_date)) AS INTEGER) as days_subscribed
            FROM users
            WHERE is_active = 1
            AND CAST((julianday('now') - julianday(join_date)) AS INTEGER) BETWEEN ? AND ?
            """,
            (min_days, max_days)
        )
        return [dict(row) for row in rows]

    @staticmethod
    async def get_users_approaching_milestone(days_before: int = 3) -> List[dict]:
        """Получить пользователей, которые скоро получат доступ к новому каналу."""
        rows = await db.fetchall(
            """
            SELECT u.*,
                   CAST((julianday('now') - julianday(u.join_date)) AS INTEGER) as days_subscribed,
                   c.channel_id, c.name as channel_name, c.days_required, c.emoji
            FROM users u
            CROSS JOIN channels c
            WHERE u.is_active = 1
            AND c.is_main = 0
            AND u.notifications_enabled = 1
            AND c.days_required - CAST((julianday('now') - julianday(u.join_date)) AS INTEGER) BETWEEN 1 AND ?
            AND NOT EXISTS (
                SELECT 1 FROM user_channels uc
                WHERE uc.user_id = u.user_id AND uc.channel_id = c.channel_id
            )
            ORDER BY u.user_id, c.days_required
            """,
            (days_before,)
        )
        return [dict(row) for row in rows]

    @staticmethod
    async def toggle_notifications(user_id: int, enabled: bool):
        """Включить/выключить уведомления для пользователя."""
        await db.execute(
            "UPDATE users SET notifications_enabled = ? WHERE user_id = ?",
            (enabled, user_id)
        )

    @staticmethod
    async def get_retention_stats() -> dict:
        """Получить статистику удержания."""
        # Общее количество
        total = await db.fetchone("SELECT COUNT(*) as count FROM users")
        total_count = total["count"] if total else 0

        # Активные
        active = await db.fetchone("SELECT COUNT(*) as count FROM users WHERE is_active = 1")
        active_count = active["count"] if active else 0

        # По периодам
        periods = await db.fetchall(
            """
            SELECT
                CASE
                    WHEN days < 7 THEN '0-7 дней'
                    WHEN days < 30 THEN '7-30 дней'
                    WHEN days < 60 THEN '30-60 дней'
                    WHEN days < 90 THEN '60-90 дней'
                    ELSE '90+ дней'
                END as period,
                COUNT(*) as count
            FROM (
                SELECT CAST((julianday('now') - julianday(join_date)) AS INTEGER) as days
                FROM users WHERE is_active = 1
            )
            GROUP BY period
            ORDER BY MIN(days)
            """
        )

        return {
            "total": total_count,
            "active": active_count,
            "inactive": total_count - active_count,
            "retention_rate": round(active_count / total_count * 100, 1) if total_count > 0 else 0,
            "by_period": [dict(row) for row in periods]
        }

    @staticmethod
    async def add_bonus_days(user_id: int, days: int) -> int:
        """Добавить бонусные дни пользователю. Возвращает новое количество."""
        await db.execute(
            "UPDATE users SET bonus_days = COALESCE(bonus_days, 0) + ? WHERE user_id = ?",
            (days, user_id)
        )
        user = await UserModel.get(user_id)
        return user.get("bonus_days", 0) if user else 0

    @staticmethod
    async def set_bonus_days(user_id: int, days: int):
        """Установить конкретное количество бонусных дней."""
        await db.execute(
            "UPDATE users SET bonus_days = ? WHERE user_id = ?",
            (days, user_id)
        )

    @staticmethod
    async def get_effective_days(user_id: int) -> int:
        """Получить эффективное количество дней (реальные + бонусные)."""
        row = await db.fetchone(
            """
            SELECT
                CAST((julianday('now') - julianday(join_date)) AS INTEGER) + COALESCE(bonus_days, 0) as effective_days
            FROM users WHERE user_id = ?
            """,
            (user_id,)
        )
        return row["effective_days"] if row else 0

    @staticmethod
    async def ban_user(user_id: int, reason: Optional[str] = None):
        """Заблокировать пользователя."""
        await db.execute(
            "UPDATE users SET is_banned = 1, ban_reason = ? WHERE user_id = ?",
            (reason, user_id)
        )

    @staticmethod
    async def unban_user(user_id: int):
        """Разблокировать пользователя."""
        await db.execute(
            "UPDATE users SET is_banned = 0, ban_reason = NULL WHERE user_id = ?",
            (user_id,)
        )

    @staticmethod
    async def is_banned(user_id: int) -> bool:
        """Проверить, заблокирован ли пользователь."""
        row = await db.fetchone(
            "SELECT is_banned FROM users WHERE user_id = ?",
            (user_id,)
        )
        return bool(row["is_banned"]) if row else False

    @staticmethod
    async def get_banned_users() -> List[dict]:
        """Получить список заблокированных пользователей."""
        rows = await db.fetchall(
            "SELECT * FROM users WHERE is_banned = 1"
        )
        return [dict(row) for row in rows]

    @staticmethod
    async def reactivate(user_id: int):
        """Реактивировать пользователя (сбросить дату подписки)."""
        await db.execute(
            "UPDATE users SET join_date = ?, is_active = 1, bonus_days = 0 WHERE user_id = ?",
            (datetime.now(), user_id)
        )


class ScheduledBroadcastModel:
    """Модель для отложенных рассылок."""

    @staticmethod
    async def create(
        text: str,
        scheduled_at: datetime,
        created_by: int
    ) -> int:
        """Создать отложенную рассылку. Возвращает ID."""
        await db.execute(
            """
            INSERT INTO scheduled_broadcasts (text, scheduled_at, created_by, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (text, scheduled_at, created_by, datetime.now())
        )
        row = await db.fetchone("SELECT last_insert_rowid() as id")
        return row["id"] if row else 0

    @staticmethod
    async def get(broadcast_id: int) -> Optional[dict]:
        """Получить рассылку по ID."""
        row = await db.fetchone(
            "SELECT * FROM scheduled_broadcasts WHERE id = ?",
            (broadcast_id,)
        )
        return dict(row) if row else None

    @staticmethod
    async def get_pending() -> List[dict]:
        """Получить все ожидающие рассылки (время наступило)."""
        rows = await db.fetchall(
            """
            SELECT * FROM scheduled_broadcasts
            WHERE is_sent = 0 AND scheduled_at <= datetime('now')
            ORDER BY scheduled_at
            """
        )
        return [dict(row) for row in rows]

    @staticmethod
    async def get_upcoming() -> List[dict]:
        """Получить все предстоящие рассылки."""
        rows = await db.fetchall(
            """
            SELECT * FROM scheduled_broadcasts
            WHERE is_sent = 0
            ORDER BY scheduled_at
            """
        )
        return [dict(row) for row in rows]

    @staticmethod
    async def get_all(limit: int = 20) -> List[dict]:
        """Получить все рассылки."""
        rows = await db.fetchall(
            """
            SELECT * FROM scheduled_broadcasts
            ORDER BY scheduled_at DESC
            LIMIT ?
            """,
            (limit,)
        )
        return [dict(row) for row in rows]

    @staticmethod
    async def mark_sent(broadcast_id: int, sent_count: int, failed_count: int):
        """Отметить рассылку как отправленную."""
        await db.execute(
            """
            UPDATE scheduled_broadcasts
            SET is_sent = 1, sent_at = ?, sent_count = ?, failed_count = ?
            WHERE id = ?
            """,
            (datetime.now(), sent_count, failed_count, broadcast_id)
        )

    @staticmethod
    async def delete(broadcast_id: int):
        """Удалить рассылку."""
        await db.execute(
            "DELETE FROM scheduled_broadcasts WHERE id = ?",
            (broadcast_id,)
        )

    @staticmethod
    async def delete_old_sent(days: int = 30):
        """Удалить старые отправленные рассылки."""
        await db.execute(
            """
            DELETE FROM scheduled_broadcasts
            WHERE is_sent = 1 AND sent_at < datetime('now', ?)
            """,
            (f'-{days} days',)
        )
