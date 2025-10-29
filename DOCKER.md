# Docker Setup для AIsexter

## Швидкий старт з Docker

### 1. Development режим

```bash
# Клонуйте репозиторій
git clone https://github.com/wiyenya/AIsexter.git
cd AIsexter

# Створіть .env файл
cp .env.example .env
# Відредагуйте .env з вашими налаштуваннями

# Запустіть через docker-compose
docker-compose up --build
```

Відкрийте браузер: `http://localhost:8004`

### 2. Production режим

```bash
# Використовуйте production конфігурацію
docker-compose -f docker-compose.prod.yml up --build -d
```

## Команди Docker

### Запуск

```bash
# Development
docker-compose up

# Production (в фоні)
docker-compose -f docker-compose.prod.yml up -d

# Перебудова образів
docker-compose up --build
```

### Зупинка

```bash
docker-compose down

# Зупинити та видалити volumes
docker-compose down -v
```

### Перегляд логів

```bash
# Всі сервіси
docker-compose logs -f

# Тільки web
docker-compose logs -f web

# Тільки postgres
docker-compose logs -f postgres
```

### Виконання команд в контейнері

```bash
# Django shell
docker-compose exec web python manage.py shell

# Django admin створення суперюзера
docker-compose exec web python manage.py createsuperuser

# Міграції (якщо потрібно)
docker-compose exec web python manage.py migrate

# Збір статичних файлів
docker-compose exec web python manage.py collectstatic --noinput
```

## Структура Docker

### Сервіси

1. **web** - Django додаток
   - Порт: 8004 (зовнішній) -> 8000 (внутрішній)
   - Playwright з Chromium
   - Підключення до зовнішньої PostgreSQL (164.92.206.141:8080)
   - Підключення до Octo Browser

2. **octo** - Octo Browser
   - Порт: 58889 (зовнішній) -> 58888 (внутрішній)
   - Headless режим з Xvfb
   - Volume для профілів браузера
   - Hostname: `octo` (для підключення з web)

3. **nginx** (тільки production)
   - Порт: 80, 443
   - Reverse proxy для Django
   - Статичні файли

### Volumes

- `octo_profiles` - профілі Octo Browser
- `static_volume` - статичні файли (production)
- `media_volume` - медіа файли (production)

## База даних

**Важливо:** Проект використовує **зовнішню PostgreSQL базу даних**, яка вже існує:

```
Host: 164.92.206.141
Port: 8080
Database: postgres
User: postgres
```

PostgreSQL **НЕ** запускається в Docker контейнері. Підключення налаштовується через змінні середовища в `.env` файлі.

## Робота з Octo Browser

### Доступ до Octo Browser

Octo Browser запускається в headless режимі і доступний через API на порту 58889:

```bash
# Перевірка статусу Octo Browser
curl http://localhost:58889/api/profiles

# Логи Octo Browser
docker-compose logs -f octo
```

### Налаштування профілів

1. Octo Browser працює в headless режимі
2. Підключення з Django: `OCTO_HOST=octo` (hostname в docker network)
3. Порт: `OCTO_PORT=58888`

### Troubleshooting Octo Browser

```bash
# Перезапуск Octo Browser
docker-compose restart octo

# Доступ до контейнера
docker-compose exec octo bash

# Перевірка процесів
docker-compose exec octo ps aux | grep Octo
```

## Конфігурація для production

### 1. Змінні середовища

Важливо встановити в `.env`:

```bash
DEBUG=False
SECRET_KEY=your-very-secure-secret-key
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
```

### 2. HTTPS

Для production з HTTPS додайте SSL сертифікати:

```bash
# Отримайте сертифікати Let's Encrypt
docker run -it --rm \
  -v /etc/letsencrypt:/etc/letsencrypt \
  -v /var/lib/letsencrypt:/var/lib/letsencrypt \
  certbot/certbot certonly --standalone \
  -d yourdomain.com
```

Оновіть `nginx.conf` для HTTPS.

## Конфігурація бази даних

Проект використовує зовнішню PostgreSQL. Налаштуйте підключення в `.env`:

```bash
POSTGRES_HOST=164.92.206.141
POSTGRES_PORT=8080
POSTGRES_DB=postgres
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your_password
```

База даних вже має таблиці `parser_profile` та `parser_chatmessage` з основного проекту OFCRM-1.

## Troubleshooting

### Playwright не працює

```bash
# Перебудуйте з встановленням браузерів
docker-compose build --no-cache web
```

### Проблеми з правами доступу

```bash
# Виправте права на volumes
docker-compose exec web chown -R www-data:www-data /app
```

### База даних не підключається

```bash
# Перевірте чи запущена БД
docker-compose ps

# Перевірте логи
docker-compose logs postgres

# Перезапустіть сервіс
docker-compose restart postgres
```

## Backup та Restore

### Backup бази даних

```bash
docker-compose exec postgres pg_dump -U postgres aisexter > backup.sql
```

### Restore бази даних

```bash
docker-compose exec -T postgres psql -U postgres aisexter < backup.sql
```

## Моніторинг

### Використання ресурсів

```bash
docker stats
```

### Інформація про контейнери

```bash
docker-compose ps
docker-compose top
```

