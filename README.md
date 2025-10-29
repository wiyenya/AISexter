# AIsexter - Chat Parser

AIsexter - це Django-додаток для парсингу чатів з OnlyFans та Fansly за допомогою Octo Browser.

## Функціональність

- 🤖 **Автоматичний парсинг чатів** - збір всіх повідомлень з OnlyFans/Fansly чатів
- 🔄 **Octo Browser інтеграція** - використання профілів Octo Browser для парсингу
- 💾 **Зберігання в базі даних** - PostgreSQL для зберігання повідомлень
- 📊 **Веб-інтерфейс** - зручний інтерфейс для керування парсингом
- 🎯 **Статистика** - аналітика по зібраним повідомленням

## Встановлення

### Варіант 1: Docker (Рекомендовано) 🐳

**Швидкий старт:**

```bash
git clone https://github.com/wiyenya/AIsexter.git
cd AIsexter

# Створіть .env файл
cp .env.example .env
# Відредагуйте .env з вашими налаштуваннями

# Запустіть через Docker
docker-compose up --build
```

Відкрийте браузер: `http://localhost:8004`

📖 **Детальна документація Docker:** [DOCKER.md](DOCKER.md)

### Варіант 2: Локальна установка

#### 1. Клонування проекту

```bash
git clone https://github.com/wiyenya/AIsexter.git
cd AIsexter
```

#### 2. Створення віртуального середовища

```bash
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# або
venv\Scripts\activate  # Windows
```

#### 3. Встановлення залежностей

```bash
pip install -r requirements.txt
```

#### 4. Встановлення Playwright

```bash
playwright install chromium
```

#### 5. Налаштування середовища

Створіть файл `.env` на основі `.env.example`:

```bash
cp .env.example .env
```

Відредагуйте `.env` і додайте свої налаштування:
- PostgreSQL credentials
- Octo Browser credentials
- Octo API token

#### 6. Запуск проекту

Проект підключається до існуючої бази даних, тому міграції вже мають бути виконані в основному проекті.

```bash
python manage.py runserver
```

Відкрийте браузер і перейдіть на `http://localhost:8000`

## Використання

### Парсинг чату

1. Відкрийте головну сторінку
2. Виберіть профіль Octo Browser (з тегом `parserChat`)
3. Введіть URL чату OnlyFans або Fansly
4. Натисніть "Start Parsing"

### Перегляд повідомлень

1. На головній сторінці знайдіть розділ "Recent Parsed Chats by Model"
2. Клікніть "View Messages" для перегляду зібраних повідомлень

### Керування активними парсерами

- **Refresh** - оновити список активних парсерів
- **Stop All** - зупинити всі активні парсери
- **Stop** - зупинити конкретний парсер

## Структура проекту

```
AIsexter/
├── AIsexter/           # Основний модуль Django
│   ├── settings.py     # Налаштування проекту
│   ├── urls.py         # URL маршрути
│   └── wsgi.py         # WSGI конфігурація
├── parser/             # Додаток парсера
│   ├── models.py       # Моделі БД (Profile, ChatMessage)
│   ├── services.py     # Логіка парсингу (ChatParser, OctoClient)
│   ├── views.py        # Views
│   ├── urls.py         # URL маршрути парсера
│   ├── admin.py        # Django Admin
│   └── templates/      # HTML шаблони
├── requirements.txt    # Python залежності
├── .env.example        # Приклад конфігурації
└── README.md           # Документація
```

## Конфігурація бази даних

### PostgreSQL

Проект використовує **існуючу зовнішню PostgreSQL** базу даних:

```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'postgres',
        'USER': 'postgres',
        'PASSWORD': 'allStarsAllDatabases',
        'HOST': '164.92.206.141',
        'PORT': '8080',
    }
}
```

**Важливо:** База даних НЕ створюється в Docker контейнері. Таблиці `parser_profile` та `parser_chatmessage` вже існують в базі даних основного проекту OFCRM-1.

### ClickHouse (опціонально)

Для аналітики можна використовувати ClickHouse:

```python
CLICKHOUSE_CONFIG = {
    'host': '64.226.88.238',
    'port': 8123,
    'username': 'default',
    'password': 'MWrf0OaJ'
}
```

## Налаштування Octo Browser

### Вимоги

1. Встановлений Octo Browser
2. Створені профілі з тегом `parserChat`
3. API token з Octo Browser панелі

### Налаштування профілів

1. Відкрийте Octo Browser
2. Створіть профіль для OnlyFans/Fansly
3. Додайте тег `parserChat` до профілю
4. Переконайтеся, що профіль авторизований в OnlyFans/Fansly

## API Endpoints

- `GET /parser/chat-parser/` - Головна сторінка парсера
- `POST /parser/api/start-chat-parsing/` - Запуск парсингу
- `POST /parser/api/stop-chat-parsing/` - Зупинка парсингу
- `GET /parser/api/get-active-parsers/` - Отримання активних парсерів
- `POST /parser/api/stop-all-parsers/` - Зупинка всіх парсерів
- `GET /parser/view-chat/<profile_id>/` - Перегляд повідомлень чату

## Моделі даних

### Profile

```python
class Profile(models.Model):
    uuid = models.CharField(max_length=255, unique=True)
    is_active = models.BooleanField(default=False)
    model_name = models.CharField(max_length=255)
    parsing_interval = models.IntegerField(default=30)
    last_parsed_at = models.DateTimeField(null=True, blank=True)
```

### ChatMessage

```python
class ChatMessage(models.Model):
    profile = models.ForeignKey("parser.Profile", on_delete=models.CASCADE)
    chat_url = models.URLField(max_length=500)
    from_user_id = models.CharField(max_length=64, null=True, blank=True)
    from_username = models.CharField(max_length=255, null=True, blank=True)
    message_text = models.TextField()
    message_date = models.DateTimeField(null=True, blank=True)
    is_from_model = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
```

## Troubleshooting

### Playwright не встановлений

```bash
playwright install chromium
```

### Octo Browser не підключається

Переконайтеся, що:
- Octo Browser запущений
- Правильно вказано `OCTO_HOST` та `OCTO_PORT` в `.env`
- Налаштовано API token

### База даних не підключається

Перевірте:
- PostgreSQL credentials в `.env`
- Чи доступний хост бази даних
- Чи правильно вказано порт

## Ліцензія

Private project

## Підтримка

Для питань та підтримки зверніться до розробника.

