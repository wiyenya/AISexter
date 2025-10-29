# Розгортання AIsexter на сервері

## Швидке виправлення помилки ALLOWED_HOSTS

Якщо ви бачите помилку:
```
DisallowedHost at /
Invalid HTTP_HOST header: 'YOUR_IP:8004'. 
You may need to add 'YOUR_IP' to ALLOWED_HOSTS.
```

### Рішення:

1. **Відредагуйте .env файл на сервері:**

```bash
cd ~/AIsexter
nano .env
```

2. **Додайте або змініть ALLOWED_HOSTS:**

```bash
ALLOWED_HOSTS=64.226.88.238,localhost,127.0.0.1
```

3. **Перезапустіть контейнер:**

```bash
docker-compose restart web
```

4. **Оновіть сторінку в браузері**

## Повне розгортання

### 1. Підключення до сервера

```bash
ssh katya@64.226.88.238
```

### 2. Клонування проекту

```bash
cd ~
git clone https://github.com/wiyenya/AIsexter.git
cd AIsexter
```

### 3. Налаштування .env

```bash
cp .env.server.example .env
nano .env
```

**Важливі параметри для сервера:**

```bash
SECRET_KEY=ваш-секретний-ключ-мінімум-50-символів
DEBUG=False  # Для production
ALLOWED_HOSTS=64.226.88.238,ваш-домен.com

# PostgreSQL (зовнішня база)
POSTGRES_HOST=164.92.206.141
POSTGRES_PORT=8080
POSTGRES_PASSWORD=ваш-пароль

# Octo Browser
OCTO_EMAIL=ваш-email
OCTO_PASSWORD=ваш-пароль
OCTO_API_TOKEN=ваш-токен
```

### 4. Перевірка портів

```bash
# Перевірте що порти 8004 та 58889 вільні
sudo netstat -tulpn | grep -E '8004|58889'
```

### 5. Firewall

```bash
# Відкрийте порти
sudo ufw allow 8004/tcp
sudo ufw allow 58889/tcp
sudo ufw status
```

### 6. Запуск

```bash
docker-compose up --build -d
```

### 7. Перевірка логів

```bash
# Всі логи
docker-compose logs -f

# Тільки web
docker-compose logs -f web

# Тільки octo
docker-compose logs -f octo
```

### 8. Доступ

- **Веб-інтерфейс:** http://64.226.88.238:8004
- **Octo Browser API:** http://64.226.88.238:58889

## Оновлення проекту

```bash
cd ~/AIsexter
git pull origin main
docker-compose down
docker-compose up --build -d
```

## Зупинка проекту

```bash
docker-compose down

# З видаленням volumes
docker-compose down -v
```

## Моніторинг

```bash
# Статус контейнерів
docker-compose ps

# Використання ресурсів
docker stats

# Логи в реальному часі
docker-compose logs -f
```

## Backup

### База даних (зовнішня)

База даних на 164.92.206.141, backup робиться там.

### Octo профілі

```bash
# Backup volume
docker run --rm -v aisexter_octo_profiles:/data -v $(pwd):/backup ubuntu tar czf /backup/octo_profiles_backup.tar.gz -C /data .

# Restore
docker run --rm -v aisexter_octo_profiles:/data -v $(pwd):/backup ubuntu tar xzf /backup/octo_profiles_backup.tar.gz -C /data
```

## Troubleshooting

### DisallowedHost помилка

```bash
# Додайте IP до ALLOWED_HOSTS в .env
nano .env
# ALLOWED_HOSTS=64.226.88.238,localhost

docker-compose restart web
```

### Порт зайнятий

```bash
# Знайдіть процес
sudo lsof -i :8004

# Зупиніть контейнер який використовує порт
docker stop aisexter_web
```

### Не можу підключитися до Octo Browser

```bash
# Перевірте логи
docker-compose logs octo

# Перезапустіть
docker-compose restart octo

# Перевірте чи запущений
docker-compose ps octo
```

### База даних не підключається

```bash
# Перевірте змінні в .env
cat .env | grep POSTGRES

# Перевірте доступність бази з контейнера
docker-compose exec web ping 164.92.206.141

# Тест підключення
docker-compose exec web python manage.py dbshell
```

## Production налаштування

### 1. Змініть DEBUG на False

```bash
DEBUG=False
```

### 2. Згенеруйте новий SECRET_KEY

```python
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

### 3. Використайте домен замість IP

```bash
ALLOWED_HOSTS=aisexter.yourdomain.com,64.226.88.238
```

### 4. Налаштуйте Nginx reverse proxy

Створіть `/etc/nginx/sites-available/aisexter`:

```nginx
server {
    listen 80;
    server_name aisexter.yourdomain.com;

    location / {
        proxy_pass http://localhost:8004;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/aisexter /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 5. SSL сертифікат (Let's Encrypt)

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d aisexter.yourdomain.com
```

## Автозапуск при перезавантаженні

Docker контейнери з `restart: unless-stopped` автоматично запускаються.

Перевірка:

```bash
sudo systemctl status docker
```

Якщо потрібно включити автозапуск Docker:

```bash
sudo systemctl enable docker
```

