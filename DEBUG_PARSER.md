# Діагностика Chat Parser

## Перевірка чому парсер не запускається

### 1. Перевірте логи в реальному часі

```bash
cd ~/AIsexter
docker-compose logs -f web
```

Ви маєте побачити:
```
🚀 Starting ChatParser for profile UUID and URL...
```

### 2. Перевірте чи працює Octo Browser

```bash
# Перевірте статус Octo
docker-compose ps octo

# Перевірте логи Octo
docker-compose logs octo

# Тест API Octo Browser
curl http://localhost:58889/api/profiles
# або з хоста
curl http://octo:58888/api/profiles
```

### 3. Перевірте підключення до Octo з контейнера web

```bash
# Зайдіть в контейнер
docker-compose exec web bash

# Перевірте чи резолвиться hostname 'octo'
ping -c 3 octo

# Перевірте підключення до Octo API
curl http://octo:58888/api/profiles

# Вийдіть
exit
```

### 4. Перевірте змінні середовища

```bash
# Перевірте .env
cat .env | grep OCTO

# Має бути:
# OCTO_HOST=octo
# OCTO_PORT=58888
# OCTO_EMAIL=...
# OCTO_PASSWORD=...
# OCTO_API_TOKEN=...
```

### 5. Запустіть парсер вручну для тестування

```bash
docker-compose exec web python manage.py shell
```

В shell введіть:

```python
import asyncio
from parser.services import ChatParser

# Замініть на ваші дані
profile_uuid = "your-profile-uuid"
chat_url = "https://onlyfans.com/my/chats/chat/177355017/"

parser = ChatParser(profile_uuid, chat_url)
result = asyncio.run(parser.run())
print(result)
```

### 6. Типові проблеми

#### Проблема: Octo Browser не запущений

```bash
docker-compose restart octo
docker-compose logs -f octo
```

Шукайте в логах:
- `Profile started successfully` - добре
- `Login failed` - неправильні credentials
- `Connection refused` - Octo не запущений

#### Проблема: Неправильні credentials Octo

Перевірте в `.env`:
```bash
OCTO_EMAIL=ваш-правильний-email
OCTO_PASSWORD=ваш-правильний-пароль
```

Після зміни:
```bash
docker-compose restart web
```

#### Проблема: Profile UUID не існує

Отримайте список профілів:
```python
from parser.services import OctoAPIClient
from django.conf import settings

client = OctoAPIClient(settings.OCTO_API_TOKEN)
profiles = client.get_chat_parser_profiles()
for p in profiles:
    print(f"UUID: {p['uuid']}, Title: {p['title']}")
```

### 7. Детальний debug

Додайте в код тимчасовий debug:

```python
# В parser/services.py, в методі ChatParser.run():
async def run(self):
    print("=" * 50)
    print(f"DEBUG: Starting parser for profile {self.profile_uuid}")
    print(f"DEBUG: Chat URL: {self.chat_url}")
    print(f"DEBUG: Octo settings: {settings.OCTO_HOST}:{settings.OCTO_PORT}")
    print("=" * 50)
    
    # ... rest of code
```

### 8. Перевірка портів на сервері

```bash
# Перевірте що порти доступні
sudo netstat -tulpn | grep -E '8004|58889'

# Має показати:
# 8004 - aisexter_web
# 58889 - aisexter_octo
```

### 9. Швидка перезбірка

Якщо нічого не допомагає:

```bash
cd ~/AIsexter
docker-compose down
docker-compose up --build -d
docker-compose logs -f
```

### 10. Перевірка активних threads

В Django shell:

```python
import threading
print("Active threads:")
for thread in threading.enumerate():
    print(f"  - {thread.name}: {thread.is_alive()}")
```

Має бути thread типу `ChatParser-XXXXXXXX` якщо парсер запущений.

## Корисні команди

```bash
# Статус всіх контейнерів
docker-compose ps

# Логи всіх сервісів
docker-compose logs

# Логи тільки web
docker-compose logs -f web

# Логи тільки octo
docker-compose logs -f octo

# Рестарт конкретного сервісу
docker-compose restart web
docker-compose restart octo

# Зайти в контейнер
docker-compose exec web bash
docker-compose exec octo bash

# Перевірити використання ресурсів
docker stats
```

## Що має бути в логах при успішному запуску

```
🚀 Starting ChatParser for profile abc123 and URL https://onlyfans.com/...
Starting profile...
Profile started successfully
Navigating to chat: https://onlyfans.com/...
Scrolling chat messages... attempt 1 (collected 0 messages so far)
...
💾 Saving batch: 50 new messages
✅ Batch saved successfully!
✅ Parser finished with result: {'status': 'ok'}
```

## Підтримка

Якщо проблема не вирішується:
1. Збережіть повні логи: `docker-compose logs > parser_logs.txt`
2. Перевірте версії: `docker --version`, `docker-compose --version`
3. Перевірте доступність портів та мережі

