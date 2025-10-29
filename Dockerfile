FROM python:3.11-slim

# Встановлюємо робочу директорію
WORKDIR /app

# Встановлюємо системні залежності
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Копіюємо requirements
COPY requirements.txt .

# Встановлюємо Python залежності
RUN pip install --no-cache-dir -r requirements.txt

# Встановлюємо Playwright браузери
RUN playwright install chromium
RUN playwright install-deps chromium

# Копіюємо проект
COPY . .

# Створюємо директорію для статичних файлів
RUN mkdir -p /app/static

# Збираємо статичні файли
RUN python manage.py collectstatic --noinput || true

# Відкриваємо порт
EXPOSE 8000

# Запускаємо сервер
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]

