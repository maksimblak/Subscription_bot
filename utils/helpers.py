import logging
from datetime import datetime
from typing import Optional, Union
from config import ADMIN_IDS

logger = logging.getLogger(__name__)


def is_admin(user_id: int) -> bool:
    """Проверяет, является ли пользователь администратором."""
    return user_id in ADMIN_IDS


def format_date(dt: datetime) -> str:
    """Форматирует дату в читаемый вид."""
    return dt.strftime("%d.%m.%Y %H:%M")


def days_since(dt: datetime) -> int:
    """Возвращает количество дней с указанной даты."""
    if dt is None:
        return 0
    delta = datetime.now() - dt
    return delta.days


def parse_date(date_value: Union[str, datetime, None]) -> Optional[datetime]:
    """
    Безопасно парсит дату из строки или возвращает datetime как есть.
    Поддерживает различные форматы даты из SQLite.
    """
    if date_value is None:
        return None
    if isinstance(date_value, datetime):
        return date_value
    if isinstance(date_value, str):
        # Пробуем разные форматы
        formats = [
            "%Y-%m-%d %H:%M:%S.%f",  # ISO с микросекундами
            "%Y-%m-%d %H:%M:%S",      # ISO без микросекунд
            "%Y-%m-%dT%H:%M:%S.%f",   # ISO с T и микросекундами
            "%Y-%m-%dT%H:%M:%S",      # ISO с T
            "%Y-%m-%d",               # Только дата
        ]
        for fmt in formats:
            try:
                return datetime.strptime(date_value, fmt)
            except ValueError:
                continue
        # Последняя попытка - fromisoformat
        try:
            return datetime.fromisoformat(date_value)
        except ValueError:
            logger.warning(f"Не удалось распарсить дату: {date_value}")
            return None
    return None
