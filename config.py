import os
from dotenv import load_dotenv

load_dotenv()

# Telegram Bot Token
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")

# ID администраторов бота (могут использовать админ-команды)
ADMIN_IDS = [
    int(id.strip())
    for id in os.getenv("ADMIN_IDS", "").split(",")
    if id.strip()
]

# ID материнского канала (основной канал подписки)
MAIN_CHANNEL_ID = int(os.getenv("MAIN_CHANNEL_ID", "0"))

# Конфигурация дополнительных каналов
# days_required - количество дней непрерывной подписки для доступа
# Модуль 1 = материнский канал (MAIN_CHANNEL_ID)
CHANNELS_CONFIG = [
    {
        "id": int(os.getenv("CHANNEL_2_ID", "0")),
        "name": os.getenv("CHANNEL_2_NAME", "Модуль 2"),
        "days_required": 32,  # После 32 дней (32-63 день)
    },
    {
        "id": int(os.getenv("CHANNEL_3_ID", "0")),
        "name": os.getenv("CHANNEL_3_NAME", "Модуль 3"),
        "days_required": 64,  # После 64 дней (64-95 день)
    },
    {
        "id": int(os.getenv("CHANNEL_4_ID", "0")),
        "name": os.getenv("CHANNEL_4_NAME", "Модуль 4"),
        "days_required": 96,  # После 96 дней (96-123 день)
    },
    {
        "id": int(os.getenv("CHANNEL_5_ID", "0")),
        "name": os.getenv("CHANNEL_5_NAME", "Модуль 5"),
        "days_required": 124,  # После 124 дней (124+ день)
    },
]

# Путь к базе данных
DATABASE_PATH = os.getenv("DATABASE_PATH", "bot_database.db")

# Время запуска ежедневной проверки (час:минута)
SCHEDULER_HOUR = int(os.getenv("SCHEDULER_HOUR", "10"))
SCHEDULER_MINUTE = int(os.getenv("SCHEDULER_MINUTE", "0"))
