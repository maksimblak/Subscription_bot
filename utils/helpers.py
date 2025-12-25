from datetime import datetime
from config import ADMIN_IDS


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
