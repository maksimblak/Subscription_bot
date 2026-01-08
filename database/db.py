import logging
import aiosqlite
from config import DATABASE_PATH

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, db_path: str = DATABASE_PATH):
        self.db_path = db_path
        self.connection = None

    async def connect(self):
        """Подключение к базе данных."""
        try:
            self.connection = await aiosqlite.connect(self.db_path)
            self.connection.row_factory = aiosqlite.Row
            await self._create_tables()
            await self._apply_migrations()
            logger.info(f"База данных подключена: {self.db_path}")
        except Exception as e:
            logger.error(f"Ошибка подключения к базе данных: {e}")
            raise

    async def disconnect(self):
        """Отключение от базы данных."""
        if self.connection:
            await self.connection.close()

    async def _create_tables(self):
        """Создание таблиц при первом запуске."""
        await self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                join_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT 1,
                last_check DATETIME,
                notifications_enabled BOOLEAN DEFAULT 1,
                bonus_days INTEGER DEFAULT 0,
                is_banned BOOLEAN DEFAULT 0,
                ban_reason TEXT
            );

            CREATE TABLE IF NOT EXISTS channels (
                channel_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                days_required INTEGER DEFAULT 0,
                is_main BOOLEAN DEFAULT 0,
                description TEXT,
                emoji TEXT DEFAULT '📺'
            );

            CREATE TABLE IF NOT EXISTS user_channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                granted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                message_id INTEGER,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                FOREIGN KEY (channel_id) REFERENCES channels(channel_id),
                UNIQUE(user_id, channel_id)
            );

            CREATE TABLE IF NOT EXISTS action_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action_type TEXT NOT NULL,
                details TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );

            CREATE TABLE IF NOT EXISTS scheduled_broadcasts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT NOT NULL,
                scheduled_at DATETIME NOT NULL,
                created_by INTEGER NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                is_sent BOOLEAN DEFAULT 0,
                sent_at DATETIME,
                sent_count INTEGER DEFAULT 0,
                failed_count INTEGER DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_users_active ON users(is_active);
            CREATE INDEX IF NOT EXISTS idx_users_banned ON users(is_banned);
            CREATE INDEX IF NOT EXISTS idx_users_username ON users(username COLLATE NOCASE);
            CREATE INDEX IF NOT EXISTS idx_broadcasts_scheduled ON scheduled_broadcasts(scheduled_at, is_sent);
            CREATE INDEX IF NOT EXISTS idx_user_channels_user ON user_channels(user_id);
            CREATE INDEX IF NOT EXISTS idx_user_channels_channel ON user_channels(channel_id);
            CREATE INDEX IF NOT EXISTS idx_logs_user ON action_logs(user_id);
            CREATE INDEX IF NOT EXISTS idx_logs_type ON action_logs(action_type);
            CREATE INDEX IF NOT EXISTS idx_logs_date ON action_logs(created_at);
        """)
        await self.connection.commit()

    async def _apply_migrations(self):
        """Применение миграций для существующих баз данных."""
        # Проверяем и добавляем новые колонки в users
        cursor = await self.connection.execute("PRAGMA table_info(users)")
        columns = {row[1] for row in await cursor.fetchall()}

        if "bonus_days" not in columns:
            await self.connection.execute(
                "ALTER TABLE users ADD COLUMN bonus_days INTEGER DEFAULT 0"
            )
        if "is_banned" not in columns:
            await self.connection.execute(
                "ALTER TABLE users ADD COLUMN is_banned BOOLEAN DEFAULT 0"
            )
        if "ban_reason" not in columns:
            await self.connection.execute(
                "ALTER TABLE users ADD COLUMN ban_reason TEXT"
            )

        await self.connection.commit()

    async def execute(self, query: str, params: tuple = ()):
        """Выполнение запроса без возврата результата."""
        await self.connection.execute(query, params)
        await self.connection.commit()

    async def fetchone(self, query: str, params: tuple = ()):
        """Получение одной записи."""
        cursor = await self.connection.execute(query, params)
        return await cursor.fetchone()

    async def fetchall(self, query: str, params: tuple = ()):
        """Получение всех записей."""
        cursor = await self.connection.execute(query, params)
        return await cursor.fetchall()


# Глобальный экземпляр базы данных
db = Database()
