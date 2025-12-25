import aiosqlite
from config import DATABASE_PATH


class Database:
    def __init__(self, db_path: str = DATABASE_PATH):
        self.db_path = db_path
        self.connection = None

    async def connect(self):
        """Подключение к базе данных."""
        self.connection = await aiosqlite.connect(self.db_path)
        self.connection.row_factory = aiosqlite.Row
        await self._create_tables()

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
                last_check DATETIME
            );

            CREATE TABLE IF NOT EXISTS channels (
                channel_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                days_required INTEGER DEFAULT 0,
                is_main BOOLEAN DEFAULT 0
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

            CREATE INDEX IF NOT EXISTS idx_users_active ON users(is_active);
            CREATE INDEX IF NOT EXISTS idx_user_channels_user ON user_channels(user_id);
        """)
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
