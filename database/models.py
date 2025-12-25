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
