FROM python:3.12-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем файлы зависимостей
COPY pyproject.toml poetry.lock ./

# Устанавливаем Poetry и зависимости
RUN pip install poetry && \
    poetry config virtualenvs.create false && \
    poetry install --only main --no-interaction --no-ansi

# Копируем исходный код
COPY . .

# Создаём директорию для базы данных
RUN mkdir -p /app/data

# Переменные окружения по умолчанию
ENV DATABASE_PATH=/app/data/bot_database.db
ENV PYTHONUNBUFFERED=1

# Запуск бота
CMD ["python", "main.py"]
