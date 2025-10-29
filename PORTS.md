# Порти AIsexter

## Зовнішні порти (на хості)

Ці порти використовуються для доступу до сервісів ззовні:

- **8004** - Django веб-інтерфейс (http://localhost:8004)
- **58889** - Octo Browser API (http://localhost:58889)

**Примітка:** PostgreSQL не запускається в Docker, використовується зовнішня БД на 164.92.206.141:8080

## Внутрішні порти (в Docker мережі)

Всередині Docker мережі сервіси використовують стандартні порти:

- **web:8000** - Django сервер
- **octo:58888** - Octo Browser

**Зовнішні підключення:**
- **164.92.206.141:8080** - PostgreSQL база даних (зовнішня)

## Зміна портів

Якщо потрібно змінити порти, відредагуйте `docker-compose.yml`:

```yaml
services:
  web:
    ports:
      - "ВАШІ_ПОРТ:8000"  # Наприклад "9000:8000"
  
  octo:
    ports:
      - "ВАШІ_ПОРТ:58888"  # Наприклад "59000:58888"
  
  postgres:
    ports:
      - "ВАШІ_ПОРТ:5432"  # Наприклад "5440:5432"
```

## Перевірка зайнятих портів

```bash
# Linux
sudo netstat -tulpn | grep LISTEN

# або
sudo ss -tulpn | grep LISTEN

# Mac
lsof -i -P -n | grep LISTEN

# Перевірка конкретного порту
lsof -i :8004
```

## Конфлікти портів

Якщо порти вже зайняті, Docker покаже помилку:

```
Error starting userland proxy: listen tcp4 0.0.0.0:8004: bind: address already in use
```

У такому випадку змініть порт в `docker-compose.yml` на вільний.

