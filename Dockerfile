FROM python:3.11-slim

# Встановлюємо робочу директорію
WORKDIR /app

# Встановлюємо системні залежності для Chromium
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    curl \
    wget \
    # Залежності для Chromium
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    libatspi2.0-0 \
    libxshmfence1 \
    fonts-liberation \
    fonts-noto-color-emoji \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Копіюємо requirements
COPY requirements.txt .

# Встановлюємо Python залежності
RUN pip install --no-cache-dir -r requirements.txt

# Встановлюємо Playwright браузери
RUN playwright install chromium

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

