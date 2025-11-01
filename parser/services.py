from django.conf import settings
from django.utils import timezone
import requests
import asyncio
import datetime
from playwright.async_api import async_playwright, Response, Page, Browser
from asgiref.sync import sync_to_async

from .models import Profile, ChatMessage, FullChatMessage, ModelInfo
from .exceptions import (
    LoginPageException,
    OctoProfileStartException,
    OctoProfileAlreadyStartedException,
)


class OctoClient:
    """Client for interacting with Octo Browser API"""
    
    host: str
    port: int
    base_local_url: str
    email: str
    password: str

    def __init__(self, email: str, password: str, host: str = "octo", port: int = 58888):
        self.host = host
        self.port = port
        self.email = email
        self.password = password
        self.base_local_url = f"http://{self.host}:{self.port}"
    
    @classmethod
    def init_from_settings(cls):
        return cls(
            email=settings.OCTO_EMAIL,
            password=settings.OCTO_PASSWORD,
            host=settings.OCTO_HOST,
            port=settings.OCTO_PORT
        )

    def check_auth(self):
        # Check cloud API instead of local API
        api_url = "https://app.octobrowser.net/api/v2/automation/profiles"
        headers = {"X-Octo-Api-Token": settings.OCTO_API_TOKEN}
        
        try:
            response = requests.get(api_url, headers=headers, timeout=10)
            return response.ok
        except Exception as e:
            print(f"API check failed: {e}")
            return False
    
    def login(self):
        api_url = f"{self.base_local_url}/api/auth/login"
        payload = {
            "email": self.email,
            "password": self.password
        }
        response = requests.post(api_url, json=payload)

        if response.ok:
            print("Login successful")
            return True
        else:
            try:
                resp_data = response.json()
                if resp_data.get('error') == 'Already logged in':
                    print("Already logged in")
                    return True
            except Exception:
                pass
            print("Login failed")
            print(response.text)
            return False

    def start_profile(self, uuid: str, headless: bool = True, debug_port: bool = True, flags: list = ["--disable-dev-shm-usage"]):
        if not self.login():
            return False
    
        # Всегда делаем force_stop перед запуском для гарантии чистого старта
        print(f"🛑 Force stopping profile {uuid} before starting...")
        self.force_stop_profile(uuid)
        
        import time
        time.sleep(2)  # Ждем 2 секунды после остановки
        
        # Use local API for starting profile
        api_url = f"{self.base_local_url}/api/profiles/start"

        payload = {
            "uuid": uuid,
            "headless": headless,
            "debug_port": debug_port,
            "flags": flags
        }

        print(f"🚀 Запускаем профиль UUID: {uuid}")
        print(f"API URL: {api_url}")
        print(f"Payload: {payload}")

        response = requests.post(api_url, json=payload)
        print(f"Response Status: {response.status_code}")
        print(f"Response Text: {response.text}")

        if response.ok:
            print("✅ Профиль успешно запущен")
            resp_data = response.json()
            return resp_data
        else:
            print("❌ Ошибка запуска профиля")
            try:
                resp_data = response.json()
            except Exception:
                resp_data = None
            print(f"Status: {response.status_code}")
            print(f"Response: {response.text}")
            raise OctoProfileStartException(resp_data or "Failed to start profile")
    
    def stop_profile(self, uuid: str):
        # Use local API for stopping profile (as in example)
        api_url = f"{self.base_local_url}/api/profiles/stop"
        payload = {"uuid": uuid}
        response = requests.post(api_url, json=payload)
        if response.ok:
            print("Profile stopped successfully")
            return True
        return False
    
    def force_stop_profile(self, uuid: str):
        # Use local API force_stop exactly as in example
        api_url = f"{self.base_local_url}/api/profiles/force_stop"
        payload = {"uuid": uuid}
        response = requests.post(api_url, json=payload)
        if response.ok:
            print("Profile stopped successfully")
            return True
        return False

    def get_running_profiles(self):
        api_url = f"{self.base_local_url}/api/profiles"
        response = requests.get(api_url)
        
        if response.ok:
            data = response.json()
            running = [p for p in data if p.get('status') == 'running']
            return running
        return []
    
    def get_profile_info(self, uuid: str):
        """Получить полную информацию о профиле (включая ws_endpoint если запущен)"""
        api_url = f"{self.base_local_url}/api/profiles"
        response = requests.get(api_url)
        
        if response.ok:
            data = response.json()
            for profile in data:
                if profile.get('uuid') == uuid and profile.get('status') == 'running':
                    return profile
        return None

    def force_stop_all_profiles(self):
        running_profiles = self.get_running_profiles()
        stopped_count = 0
        
        for profile in running_profiles:
            if self.stop_profile(profile['uuid']):
                stopped_count += 1
                print(f"Stopped profile {profile['uuid']}")
        
        print(f"Stopped {stopped_count} profiles")
        return stopped_count

    def force_restart_profile(self, uuid: str, max_attempts: int = 3):
        import time
        
        for attempt in range(max_attempts):
            print(f"Attempt {attempt + 1} to restart profile {uuid}")
            
            self.stop_profile(uuid)
            time.sleep(5)
            
            try:
                response_data = self.start_profile(uuid)
                print(f"Successfully restarted profile {uuid}")
                return response_data
            except OctoProfileAlreadyStartedException:
                if attempt == max_attempts - 1:
                    try:
                        self.force_stop_profile(uuid)
                        time.sleep(10)
                        response_data = self.start_profile(uuid)
                        return response_data
                    except Exception as e:
                        print(f"Final restart attempt failed: {e}")
                        raise
                else:
                    print(f"Profile still running after stop, waiting...")
                    time.sleep(10)
                    continue
            except Exception as e:
                print(f"Restart attempt {attempt + 1} failed: {e}")
                if attempt == max_attempts - 1:
                    raise
                time.sleep(5)
        
        raise Exception(f"Failed to restart profile {uuid} after {max_attempts} attempts")


class OctoAPIClient:
    """Client for Octo Browser REST API"""
    
    def __init__(self, token: str):
        self.token = token

    def get_chat_parser_profiles(self) -> list[dict]:
        """Получить профили для парсинга чатов по тегу parserChat"""
        url = "https://app.octobrowser.net/api/v2/automation/profiles"
        headers = {"X-Octo-Api-Token": self.token}
        
        response = requests.get(
            url,
            params={
                "page_len": "50",
                "fields": "title",
                "search_tags": "parserChat"
            },
            headers=headers,
            timeout=30
        )

        if not response.ok:
            raise Exception(f"Failed to get chat parser profiles: {response.text}")

        resp_data = response.json()
        success = resp_data.get('success')
        if not success:
            raise Exception(f"Failed to get chat parser profiles: {resp_data.get('error')}")
        
        return resp_data.get('data', [])


class ChatParser:
    """
    Парсер для полного сбора сообщений из чата OnlyFans
    """
    
    def __init__(self, profile_uuid: str, chat_url: str, update_only: bool = False):
        self.profile_uuid = profile_uuid
        self.chat_url = chat_url
        self.messages: list[dict] = []
        self.scroll_count: int = 0
        self.max_scrolls: int = 50
        self.model_user_id = None
        self.octo = OctoClient.init_from_settings()
        self.last_saved_count: int = 0
        self.save_batch_size: int = 100
        self.stop_requested: bool = False  # Флаг для остановки парсинга по запросу
        self.update_only: bool = update_only  # Режим только обновления (без полной прокрутки)
        
        # Получаем model_id и model_name из ModelInfo по profile_uuid
        try:
            model_info = ModelInfo.objects.filter(model_octo_profile=profile_uuid).first()
            self.model_id = model_info.model_id if model_info else None
            self.model_name = model_info.model_name if model_info else None
            print(f"🔍 Found model_id: {self.model_id}, model_name: {self.model_name} for profile {profile_uuid}")
        except Exception as e:
            print(f"⚠️ Error getting model_id: {e}")
            self.model_id = None
            self.model_name = None
    
    async def run(self):
        """Основной метод запуска парсера"""
        # Проверяем флаг остановки перед запуском
        if self.stop_requested:
            print("🛑 Stop requested before starting, aborting...")
            return {'status': 'cancelled', 'message': 'Parser stopped by user'}
        
        try:
            response_data = self.octo.start_profile(self.profile_uuid)
        except OctoProfileAlreadyStartedException:
            print("Profile already started, using existing profile")
            try:
                profiles_response = requests.get(
                    f"{self.octo.base_local_url}/api/profiles/active",
                    timeout=10
                )
                if profiles_response.ok:
                    active_profiles = profiles_response.json()
                    for profile in active_profiles:
                        if profile.get('uuid') == self.profile_uuid:
                            response_data = profile
                            break
                    else:
                        response_data = await sync_to_async(self.octo.force_restart_profile)(self.profile_uuid)
                else:
                    response_data = await sync_to_async(self.octo.force_restart_profile)(self.profile_uuid)
            except Exception as e:
                print(f"Error getting active profile info: {e}")
                try:
                    response_data = await sync_to_async(self.octo.force_restart_profile)(self.profile_uuid)
                except Exception as restart_error:
                    print(f"Force restart failed: {restart_error}")
                    return {'status': 'error', 'message': f'Failed to get profile: {str(e)}'}
                
        except OctoProfileStartException as e:
            error_message = e.args[0]
            print(f"Profile start error: {error_message}")
            # Проверяем, не была ли запрошена остановка
            if self.stop_requested:
                return {'status': 'cancelled', 'message': 'Parser stopped by user'}
            return {'status': 'error', 'message': 'Failed to start profile'}

        if not response_data:
            # Проверяем флаг остановки
            if self.stop_requested:
                return {'status': 'cancelled', 'message': 'Parser stopped by user'}
            return {'status': 'error', 'message': 'Failed to start profile'}

        # Проверяем флаг остановки перед подключением
        if self.stop_requested:
            print("🛑 Stop requested before connecting, stopping profile...")
            try:
                self.octo.stop_profile(self.profile_uuid)
            except:
                pass
            return {'status': 'cancelled', 'message': 'Parser stopped by user'}

        ws_endpoint = response_data['ws_endpoint'].replace('127.0.0.1', 'octo')
        
        parsing_successful = False
        try:
            await self.parse(ws_endpoint)
            parsing_successful = True
        except LoginPageException:
            print("Login page detected - session may have expired")
            if self.stop_requested:
                return {'status': 'cancelled', 'message': 'Parser stopped by user'}
            return {'status': 'error', 'message': 'Login page detected'}
        except Exception as e:
            # Если была запрошена остановка, не считаем это ошибкой
            if self.stop_requested:
                print("🛑 Stop requested during parsing")
                return {'status': 'cancelled', 'message': 'Parser stopped by user'}
            print(f"Error during parsing: {e}")
            return {'status': 'error', 'message': f'Parsing error: {str(e)}'}
        
        if parsing_successful and len(self.messages) > 0:
            print(f"✅ OnlyFans parsing completed. Collected {len(self.messages)} messages. Stopping profile.")
            self.octo.stop_profile(self.profile_uuid)

        return {'status': 'ok' if parsing_successful else 'error'}
    
    async def check_if_login_page(self, page: Page) -> bool:
        """Проверка, является ли страница страницей логина"""
        try:
            login_indicators = [
                'input[type="email"]',
                'input[type="password"]',
                'button[type="submit"]',
                '.login-form',
                '#login',
                '[data-testid="login"]'
            ]
            
            for selector in login_indicators:
                if await page.query_selector(selector):
                    return True
            
            current_url = page.url
            if 'login' in current_url.lower() or 'signin' in current_url.lower():
                return True
                
            return False
        except Exception as e:
            print(f"Error checking login page: {e}")
            return False
        
    async def handle_response(self, response: Response):
        """Обработка ответов API для сбора сообщений OnlyFans"""
        if "onlyfans.com/api2/v2/chats" in response.url and "/messages" in response.url:
            if "application/json" in response.headers.get("content-type", ""):
                try:
                    json_body = await response.json()
                    if 'list' in json_body:
                        for message in json_body['list']:
                            await self._process_message(message)
                except Exception as e:
                    print(f"Failed to parse OnlyFans messages: {e}")
    
    async def _process_message(self, message: dict):
        """Обработка сообщения OnlyFans"""
        try:
            from_user = message.get('fromUser', {})
            from_user_id = from_user.get('id')
            from_username = from_user.get('username', '')
            
            is_from_model = from_user_id == self.model_user_id
            
            # Проверяем информацию о платном сообщении из API
            is_paid = False
            amount_paid = 0
            
            # В OnlyFans API может быть информация о цене в разных полях
            price = message.get('price') or message.get('amount')
            if price:
                is_paid = True
                amount_paid = float(price)
            
            # Также проверяем флаги
            if message.get('isPaid') or message.get('is_paid') or message.get('paid'):
                is_paid = True
                if not amount_paid and price:
                    amount_paid = float(price)
            
            message_data = {
                'from_user_id': str(from_user_id) if from_user_id else None,
                'from_username': from_username,
                'message_text': message.get('text', ''),
                'message_date': self._parse_date(message.get('createdAt')),
                'is_from_model': is_from_model,
                'is_paid': is_paid,
                'amount_paid': amount_paid
            }
            
            self.messages.append(message_data)
            print(f"Collected message from {from_username}: {message_data['message_text'][:50]}...")
            
        except Exception as e:
            print(f"Error processing OnlyFans message: {e}")
    
    def _parse_date(self, date_str):
        """Парсинг даты из ISO формата или времени типа '7:21 pm', '9 pm', 'Yesterday 11:05 pm' или 'Oct 31, 2025 02:37'"""
        if not date_str or date_str == "":
            return None
        
        # Если это уже datetime объект
        if isinstance(date_str, datetime.datetime):
            return date_str
        
        # Преобразуем в строку для парсинга
        date_str = str(date_str).strip()
        if not date_str or date_str == "":
            return None
        
        # Если это ISO формат
        try:
            return datetime.datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            pass
        
        # Обрабатываем форматы с временем типа "Oct 31, 2025 02:37" (24-часовой формат с датой)
        try:
            import re
            from datetime import timedelta
            
            # Паттерн для формата "Oct 31, 2025 02:37" или "Oct 31, 2025 14:37"
            date_time_pattern = r'([A-Za-z]{3})\s+(\d{1,2}),\s+(\d{4})\s+(\d{1,2}):(\d{2})'
            match = re.search(date_time_pattern, date_str)
            if match:
                month_abbr = match.group(1)
                day = int(match.group(2))
                year = int(match.group(3))
                hour = int(match.group(4))
                minute = int(match.group(5))
                
                # Преобразуем сокращенное название месяца в число
                months = {
                    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
                    'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
                }
                month = months.get(month_abbr.lower()[:3])
                if month:
                    try:
                        return datetime.datetime(year, month, day, hour, minute, 0)
                    except ValueError:
                        pass
        except Exception:
            pass
        
        # Обрабатываем форматы с временем типа "7:21 pm", "9 pm" или "Yesterday 11:05 pm"
        try:
            import re
            from datetime import timedelta
            
            date_str_lower = date_str.lower()
            
            # Проверяем наличие "yesterday"
            is_yesterday = 'yesterday' in date_str_lower
            
            # Паттерн для времени с минутами: "7:21 pm" или "12:45 am"
            time_pattern_with_minutes = r'(\d{1,2}):(\d{2})\s*(am|pm)'
            match = re.search(time_pattern_with_minutes, date_str_lower)
            if match:
                hour = int(match.group(1))
                minute = int(match.group(2))
                am_pm = match.group(3)
                
                # Преобразуем в 24-часовой формат
                if am_pm == 'pm' and hour != 12:
                    hour += 12
                elif am_pm == 'am' and hour == 12:
                    hour = 0
                
                # Создаем datetime с текущей датой и распарсенным временем
                now = datetime.datetime.now()
                result = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                
                # Если было "Yesterday", вычитаем один день
                if is_yesterday:
                    result = result - timedelta(days=1)
                
                return result
            
            # Паттерн для времени без минут: "9 pm" или "12 am"
            time_pattern_without_minutes = r'(\d{1,2})\s*(am|pm)(?:\s|$)'
            match = re.search(time_pattern_without_minutes, date_str_lower)
            if match:
                hour = int(match.group(1))
                am_pm = match.group(2)
                minute = 0  # Если минут нет, используем 0
                
                # Преобразуем в 24-часовой формат
                if am_pm == 'pm' and hour != 12:
                    hour += 12
                elif am_pm == 'am' and hour == 12:
                    hour = 0
                
                # Создаем datetime с текущей датой и распарсенным временем
                now = datetime.datetime.now()
                result = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                
                # Если было "Yesterday", вычитаем один день
                if is_yesterday:
                    result = result - timedelta(days=1)
                
                return result
        except Exception:
            pass
        
        # Если не получилось - возвращаем None (будет использовано текущее время как fallback)
        return None
    
    async def navigate(self, page: Page, browser: Browser):
        """Навигация по чату с прокруткой контейнера сообщений"""
        print(f"Navigating to chat: {self.chat_url}")
        try:
            # Используем domcontentloaded вместо load для более быстрой загрузки
            # и добавляем timeout для избежания бесконечного ожидания
            await page.goto(self.chat_url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(5 * 1000)
        except Exception as e:
            # Если не удалось загрузить, пробуем еще раз с более мягкими параметрами
            print(f"First navigation attempt failed: {e}, retrying with networkidle...")
            try:
                await page.goto(self.chat_url, wait_until="networkidle", timeout=90000)
                await page.wait_for_timeout(3 * 1000)
            except Exception as retry_error:
                print(f"Navigation retry also failed: {retry_error}")
                # Не поднимаем исключение сразу - возможно страница все же загрузилась частично
                await page.wait_for_timeout(3 * 1000)
        
        if await self.check_if_login_page(page):
            print("Warning: Login page indicators detected, but continuing...")
        
        self.model_user_id = self.profile_uuid
        
        try:
            await page.wait_for_selector('.b-chat__messages', timeout=10000)
            print("Chat messages container loaded")
        except Exception as e:
            print(f"Warning: Could not find chat messages container: {e}")
            if await self.check_if_login_page(page):
                print("Confirmed: Login page detected (no messages container)")
                await page.close()
                await browser.close()
                raise LoginPageException()
        
        # Если это режим обновления - собираем только текущие сообщения без прокрутки
        if self.update_only:
            print("🔄 Update mode: collecting current visible messages only")
            await page.wait_for_timeout(2 * 1000)  # Ждем загрузки текущих сообщений
            await self._collect_messages_from_dom(page)
            print(f"Total messages collected: {len(self.messages)}")
            if len(self.messages) > self.last_saved_count:
                await self._save_messages_batch()
            return
        
        # Обычный режим полного парсинга с прокруткой
        scroll_attempts = 0
        no_new_content_count = 0
        
        # Делаем первый скролл вверх, чтобы дойти до начала
        await page.evaluate("""
            () => {
                const messagesContainer = document.querySelector('.b-chat__messages');
                if (messagesContainer) {
                    messagesContainer.scrollTop = 0;
                }
            }
        """)
        await page.wait_for_timeout(3 * 1000)
        
        while not self.stop_requested:
            scroll_attempts += 1
            print(f"Scrolling chat messages... attempt {scroll_attempts} (collected {len(self.messages)} messages so far)")
            
            messages_before = await page.evaluate("""
                () => {
                    const messages = document.querySelectorAll('.b-chat__message');
                    return messages.length;
                }
            """)
            
            await page.evaluate("""
                () => {
                    const messagesContainer = document.querySelector('.b-chat__messages');
                    if (messagesContainer) {
                        messagesContainer.scrollTop = 0;
                    }
                }
            """)
            
            # Увеличиваем таймаут, чтобы загрузились новые сообщения
            await page.wait_for_timeout(5 * 1000)
            
            messages_after = await page.evaluate("""
                () => {
                    const messages = document.querySelectorAll('.b-chat__message');
                    return messages.length;
                }
            """)
            
            print(f"Messages in DOM: before={messages_before}, after={messages_after}")
            
            if messages_after == messages_before:
                no_new_content_count += 1
                print(f"No new messages loaded (count: {no_new_content_count}/5)")
                
                if no_new_content_count >= 5:
                    print(f"Reached the beginning of the chat! Total scrolls: {scroll_attempts}")
                    print(f"Total messages in DOM: {messages_after}")
                    break
            else:
                no_new_content_count = 0
                print(f"Loaded {messages_after - messages_before} new messages, continuing...")
                
                if scroll_attempts % 10 == 0:
                    await self._collect_messages_from_dom(page)
                    if len(self.messages) - self.last_saved_count >= self.save_batch_size:
                        await self._save_messages_batch()
        
        if self.stop_requested:
            print(f"🛑 Parsing stopped by user after {scroll_attempts} attempts")
        else:
            print(f"Finished scrolling after {scroll_attempts} attempts")
        
        await self._collect_messages_from_dom(page)
        
        print(f"Total messages collected: {len(self.messages)}")
        
        if len(self.messages) > self.last_saved_count:
            await self._save_messages_batch()
    
    async def _collect_messages_from_dom(self, page: Page):
        """Сбор сообщений напрямую из DOM"""
        try:
            messages_data = await page.evaluate("""
                () => {
                    const messages = document.querySelectorAll('.b-chat__message');
                    const messagesData = [];
                    
                    messages.forEach((messageEl, index) => {
                        try {
                            const textEl = messageEl.querySelector('.b-chat__message__text');
                            const messageText = textEl ? textEl.textContent.trim() : '';
                            
                            if (!messageText) return;
                            
                            const isFromMe = messageEl.classList.contains('m-from-me');
                            const fromUsername = isFromMe ? 'Model' : 'User';
                            
                            // Ищем время сообщения - может быть в разных местах
                            let messageTime = '';
                            const timeEl = messageEl.querySelector('.b-chat__message__time span');
                            if (timeEl) {
                                messageTime = timeEl.textContent.trim();
                            }
                            
                            // Ищем информацию о платном сообщении и цене
                            // Обычно это текст типа "$8.88 not paid yet, 4:57 am" или "$8.88 not paid yet"
                            let isPaid = false;
                            let amountPaid = 0;
                            
                            // Ищем специальные элементы с информацией о платеже (обычно под текстом сообщения)
                            // Ищем все элементы внутри messageEl, которые могут содержать информацию о платеже
                            const allTextNodes = messageEl.innerText || messageEl.textContent || '';
                            
                            // Более точный паттерн: ищем "$XX.XX not paid" или "$XX.XX paid" или просто цену в формате "$XX.XX"
                            // который находится отдельно от основного текста сообщения
                            const paidMessagePattern = /\\$([\\d,]+(?:\\.\\d{2})?)\\s+(?:not\\s+)?paid/i;
                            const paidMatch = allTextNodes.match(paidMessagePattern);
                            
                            if (paidMatch) {
                                isPaid = true;
                                // Извлекаем цену, убирая запятые и символ доллара
                                const priceStr = paidMatch[1].replace(/,/g, '');
                                amountPaid = parseFloat(priceStr);
                                
                                // Если в тексте есть время, используем его вместо времени из timeEl
                                // Формат: "$8.88 not paid yet, 4:57 am"
                                const timePattern = /(\\d{1,2}:?\\d{0,2}\\s*(?:am|pm)|\\d{1,2}:\\d{2})/i;
                                const timeMatch = allTextNodes.match(timePattern);
                                if (timeMatch && !messageTime) {
                                    // Проверяем, что время не является частью основного текста сообщения
                                    const timeIndex = allTextNodes.indexOf(timeMatch[1]);
                                    const messageTextIndex = allTextNodes.indexOf(messageText);
                                    // Если время находится после текста сообщения, используем его
                                    if (timeIndex > messageTextIndex + messageText.length) {
                                        messageTime = timeMatch[1].trim();
                                    }
                                }
                            } else {
                                // Также проверяем паттерн только с ценой "$XX.XX" если он находится отдельно
                                const priceOnlyPattern = /\\$([\\d,]+(?:\\.\\d{2})?)/;
                                const priceMatch = allTextNodes.match(priceOnlyPattern);
                                if (priceMatch) {
                                    // Проверяем, что цена не является частью основного текста сообщения
                                    const priceIndex = allTextNodes.indexOf(priceMatch[0]);
                                    const messageTextIndex = allTextNodes.indexOf(messageText);
                                    // Если цена находится после текста сообщения или в отдельном блоке
                                    if (priceIndex > messageTextIndex + messageText.length || 
                                        !messageText.includes(priceMatch[0])) {
                                        isPaid = true;
                                        const priceStr = priceMatch[1].replace(/,/g, '');
                                        amountPaid = parseFloat(priceStr);
                                    }
                                }
                            }
                            
                            // Если время все еще не найдено, ищем в других местах
                            if (!messageTime) {
                                // Пробуем найти текст с временем в других селекторах
                                const allText = messageEl.innerText || messageEl.textContent || '';
                                const timePattern2 = /(\\d{1,2}:?\\d{0,2}\\s*(?:am|pm)|\\d{1,2}:\\d{2})/i;
                                const timeMatch2 = allText.match(timePattern2);
                                if (timeMatch2) {
                                    messageTime = timeMatch2[1].trim();
                                }
                            }
                            
                            const avatarEl = messageEl.querySelector('.g-avatar__placeholder');
                            const fromUserId = avatarEl ? avatarEl.textContent.trim() : '';
                            
                            messagesData.push({
                                from_user_id: fromUserId,
                                from_username: fromUsername,
                                message_text: messageText,
                                message_date: messageTime,
                                is_from_model: isFromMe,
                                is_paid: isPaid,
                                amount_paid: amountPaid
                            });
                        } catch (e) {
                            console.error('Error parsing message:', e);
                        }
                    });
                    
                    return messagesData;
                }
            """)
            
            for message_data in messages_data:
                if not any(msg['message_text'] == message_data['message_text'] and 
                          msg['from_username'] == message_data['from_username'] 
                          for msg in self.messages):
                    self.messages.append(message_data)
                    print(f"Collected DOM message from {message_data['from_username']}: {message_data['message_text'][:50]}...")
            
            print(f"Total messages collected from DOM: {len(messages_data)}")
            
        except Exception as e:
            print(f"Error collecting messages from DOM: {e}")
    
    async def parse(self, ws_endpoint: str):
        """Основной метод парсинга"""
        async with async_playwright() as p:
            page = None
            browser = None
            try:
                # Проверяем флаг остановки перед подключением
                if self.stop_requested:
                    print("🛑 Stop requested before connecting, aborting...")
                    return
                    
                browser = await p.chromium.connect_over_cdp(ws_endpoint)
                context = browser.contexts[0]
                page = await context.new_page()
                
                page.on("response", lambda response: asyncio.create_task(self.handle_response(response)))
                
                # Проверяем флаг остановки перед навигацией
                if self.stop_requested:
                    print("🛑 Stop requested before navigation, aborting...")
                    return
                
                await self.navigate(page, browser)
                
            except Exception as e:
                # Если была запрошена остановка, не поднимаем исключение
                if self.stop_requested:
                    print("🛑 Stop requested, parsing aborted")
                    return
                print(f"Error during parsing: {e}")
                raise
            finally:
                if page is not None:
                    await page.close()
                if browser is not None:
                    await browser.close()
                
                try:
                    await sync_to_async(self.save_messages)()
                except Exception as e:
                    print(f"Error in final save: {e}")
    
    async def _save_messages_batch(self):
        """Периодическое сохранение батча новых сообщений"""
        new_messages = self.messages[self.last_saved_count:]
        if not new_messages:
            return
        
        print(f"💾 Saving batch: {len(new_messages)} new messages (total collected: {len(self.messages)})")
        
        try:
            await sync_to_async(self._save_messages_sync)(new_messages)
            self.last_saved_count = len(self.messages)
            print(f"✅ Batch saved successfully! Total saved so far: {self.last_saved_count}")
        except Exception as e:
            print(f"❌ Error saving batch: {e}")
    
    def _save_messages_sync(self, messages_to_save: list[dict]):
        """Синхронное сохранение списка сообщений OnlyFans (только в FullChatMessage)"""
        saved_full_count = 0
        
        for message_data in messages_to_save:
            try:
                # Сохраняем только в FullChatMessage (без Profile и ChatMessage)
                if self.model_id:
                    # Определяем is_from_model из данных сообщения (парсили из DOM по классу m-from-me)
                    is_from_model = message_data.get('is_from_model', False)
                    
                    # Определяем user_id:
                    # - Если сообщение от модели → используем model_name
                    # - Если от пользователя → используем from_user_id
                    if is_from_model:
                        user_id = self.model_name if self.model_name else 'Model'
                    else:
                        user_id = message_data.get('from_user_id', '')
                    
                    # Проверяем, не существует ли уже такое сообщение (по chat_url и message)
                    existing_full = FullChatMessage.objects.filter(
                        chat_url=self.chat_url,
                        message=message_data['message_text'],
                        model_id=self.model_id
                    ).first()
                    
                    if not existing_full:
                        # Парсим timestamp из message_date (время сообщения, а не время парсинга)
                        timestamp = None
                        if message_data.get('message_date'):
                            # Если message_date уже datetime объект - используем его
                            if isinstance(message_data['message_date'], datetime.datetime):
                                timestamp = message_data['message_date']
                            else:
                                # Пытаемся распарсить строку (может быть "9 pm", "Oct 31, 2025 02:37" и т.д.)
                                timestamp = self._parse_date(str(message_data['message_date']))
                        
                        # Если не удалось распарсить - используем текущее время как fallback
                        if timestamp is None:
                            print(f"⚠️ Warning: Could not parse message_date '{message_data.get('message_date')}', using current time as fallback")
                            timestamp = datetime.datetime.now()
                        
                        # Получаем информацию о платном сообщении из message_data
                        is_paid = message_data.get('is_paid', False)
                        amount_paid = message_data.get('amount_paid', 0) or 0
                        
                        FullChatMessage.objects.create(
                            user_id=user_id,
                            chat_url=self.chat_url,
                            is_from_model=is_from_model,
                            message=message_data['message_text'],
                            timestamp=timestamp,
                            is_paid=is_paid,
                            amount_paid=amount_paid,
                            model_id=self.model_id
                        )
                        saved_full_count += 1
                        
                        # Логирование для отладки
                        user_type = "model" if is_from_model else "user"
                        print(f"💾 Saved message from {user_type}: user_id={user_id}")
                else:
                    print(f"⚠️ Warning: model_id not found, skipping message save")
                        
            except Exception as e:
                print(f"Error saving message: {e}")
        
        if self.model_id:
            print(f"💾 Saved {saved_full_count} new OnlyFans messages to FullChatMessage with model_id: {self.model_id}")
    
    def save_messages(self):
        """Сохранение всех оставшихся сообщений в базу данных"""
        new_messages = self.messages[self.last_saved_count:]
        if new_messages:
            print(f"💾 Final save: {len(new_messages)} remaining messages")
            self._save_messages_sync(new_messages)
            self.last_saved_count = len(self.messages)
        else:
            print("✅ All messages already saved during parsing")


class ChatParserFansly:
    """
    Парсер для полного сбора сообщений из чата Fansly
    """
    
    def __init__(self, profile_uuid: str, chat_url: str, update_only: bool = False):
        self.profile_uuid = profile_uuid
        self.chat_url = chat_url
        self.messages: list[dict] = []
        self.scroll_count: int = 0
        self.max_scrolls: int = 50
        self.model_user_id = None
        self.octo = OctoClient.init_from_settings()
        self.last_saved_count: int = 0
        self.save_batch_size: int = 100
        self.stop_requested: bool = False
        self.update_only: bool = update_only
        
        # Получаем model_id и model_name из ModelInfo по profile_uuid
        try:
            model_info = ModelInfo.objects.filter(model_octo_profile=profile_uuid).first()
            self.model_id = model_info.model_id if model_info else None
            self.model_name = model_info.model_name if model_info else None
            print(f"🔍 Found model_id: {self.model_id}, model_name: {self.model_name} for profile {profile_uuid}")
        except Exception as e:
            print(f"⚠️ Error getting model_id: {e}")
            self.model_id = None
            self.model_name = None
    
    async def run(self):
        """Основной метод запуска парсера Fansly"""
        if self.stop_requested:
            print("🛑 Stop requested before starting, aborting...")
            return {'status': 'cancelled', 'message': 'Parser stopped by user'}
        
        try:
            response_data = self.octo.start_profile(self.profile_uuid)
        except OctoProfileAlreadyStartedException:
            print("Profile already started, using existing profile")
            try:
                profiles_response = requests.get(
                    f"{self.octo.base_local_url}/api/profiles/active",
                    timeout=10
                )
                if profiles_response.ok:
                    active_profiles = profiles_response.json()
                    for profile in active_profiles:
                        if profile.get('uuid') == self.profile_uuid:
                            response_data = profile
                            break
                    else:
                        response_data = await sync_to_async(self.octo.force_restart_profile)(self.profile_uuid)
                else:
                    response_data = await sync_to_async(self.octo.force_restart_profile)(self.profile_uuid)
            except Exception as e:
                print(f"Error getting active profile info: {e}")
                try:
                    response_data = await sync_to_async(self.octo.force_restart_profile)(self.profile_uuid)
                except Exception as restart_error:
                    print(f"Force restart failed: {restart_error}")
                    return {'status': 'error', 'message': f'Failed to get profile: {str(e)}'}
                
        except OctoProfileStartException as e:
            error_message = e.args[0]
            print(f"Profile start error: {error_message}")
            if self.stop_requested:
                return {'status': 'cancelled', 'message': 'Parser stopped by user'}
            return {'status': 'error', 'message': 'Failed to start profile'}

        if not response_data:
            if self.stop_requested:
                return {'status': 'cancelled', 'message': 'Parser stopped by user'}
            return {'status': 'error', 'message': 'Failed to start profile'}

        if self.stop_requested:
            print("🛑 Stop requested before connecting, stopping profile...")
            try:
                self.octo.stop_profile(self.profile_uuid)
            except:
                pass
            return {'status': 'cancelled', 'message': 'Parser stopped by user'}

        ws_endpoint = response_data['ws_endpoint'].replace('127.0.0.1', 'octo')
        
        parsing_successful = False
        try:
            await self.parse(ws_endpoint)
            parsing_successful = True
        except LoginPageException:
            print("Login page detected - session may have expired")
            if self.stop_requested:
                return {'status': 'cancelled', 'message': 'Parser stopped by user'}
            return {'status': 'error', 'message': 'Login page detected'}
        except Exception as e:
            if self.stop_requested:
                print("🛑 Stop requested during parsing")
                return {'status': 'cancelled', 'message': 'Parser stopped by user'}
            print(f"Error during parsing: {e}")
            return {'status': 'error', 'message': f'Parsing error: {str(e)}'}
        
        if parsing_successful and len(self.messages) > 0:
            print(f"✅ Fansly parsing completed. Collected {len(self.messages)} messages. Stopping profile.")
            self.octo.stop_profile(self.profile_uuid)

        return {'status': 'ok' if parsing_successful else 'error'}
    
    async def check_if_login_page(self, page: Page) -> bool:
        """Проверка, является ли страница страницей логина Fansly"""
        try:
            login_indicators = [
                'input[type="email"]',
                'input[type="password"]',
                'button[type="submit"]',
                '.login-form',
                '#login',
                '[data-testid="login"]'
            ]
            
            for selector in login_indicators:
                if await page.query_selector(selector):
                    return True
            
            current_url = page.url
            if 'login' in current_url.lower() or 'signin' in current_url.lower():
                return True
                
            return False
        except Exception as e:
            print(f"Error checking login page: {e}")
            return False
    
    async def handle_response(self, response: Response):
        """Обработка ответов API для сбора сообщений Fansly"""
        if "fansly.com/api" in response.url and "message" in response.url.lower():
            if "application/json" in response.headers.get("content-type", ""):
                try:
                    json_body = await response.json()
                    # Fansly API может возвращать данные в разных структурах
                    if 'response' in json_body and isinstance(json_body['response'], list):
                        for message in json_body['response']:
                            await self._process_message(message)
                    elif isinstance(json_body, list):
                        for message in json_body:
                            await self._process_message(message)
                except Exception as e:
                    print(f"Failed to parse Fansly messages from API: {e}")
    
    async def _process_message(self, message: dict):
        """Обработка сообщения Fansly из API"""
        try:
            # Fansly API структура может отличаться
            from_user_id = message.get('accountId') or message.get('fromAccountId')
            
            is_from_model = str(from_user_id) == str(self.model_id) if from_user_id and self.model_id else False
            
            # Проверяем информацию о платном сообщении
            is_paid = False
            amount_paid = 0
            
            if message.get('price'):
                is_paid = True
                amount_paid = float(message.get('price', 0))
            
            message_data = {
                'from_user_id': str(from_user_id) if from_user_id else None,
                'from_username': message.get('username', 'User'),
                'message_text': message.get('content', ''),
                'message_date': self._parse_date(message.get('createdAt')),
                'is_from_model': is_from_model,
                'is_paid': is_paid,
                'amount_paid': amount_paid
            }
            
            self.messages.append(message_data)
            print(f"Collected Fansly message: {message_data['message_text'][:50]}...")
            
        except Exception as e:
            print(f"Error processing Fansly message: {e}")
    
    def _parse_date(self, date_str):
        """Парсинг даты из ISO формата, timestamp или формата Fansly типа 'Oct 31, 19:46'"""
        if not date_str or date_str == "":
            return None
        
        if isinstance(date_str, datetime.datetime):
            return date_str
        
        date_str = str(date_str).strip()
        if not date_str or date_str == "":
            return None
        
        # ISO формат
        try:
            return datetime.datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            pass
        
        # Формат Fansly: "Oct 31, 19:46" или "Oct 31, 2024 19:46"
        try:
            import re
            
            # Паттерн для формата "Oct 31, 19:46" (без года, используется текущий год)
            date_time_pattern = r'([A-Za-z]{3})\s+(\d{1,2}),\s+(\d{1,2}):(\d{2})'
            match = re.search(date_time_pattern, date_str)
            if match:
                month_abbr = match.group(1)
                day = int(match.group(2))
                hour = int(match.group(3))
                minute = int(match.group(4))
                
                # Преобразуем сокращенное название месяца в число
                months = {
                    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
                    'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
                }
                month = months.get(month_abbr.lower()[:3])
                if month:
                    # Используем текущий год
                    now = datetime.datetime.now()
                    year = now.year
                    try:
                        return datetime.datetime(year, month, day, hour, minute, 0)
                    except ValueError:
                        pass
            
            # Паттерн для формата "Oct 31, 2024 19:46" (с годом)
            date_time_pattern_with_year = r'([A-Za-z]{3})\s+(\d{1,2}),\s+(\d{4})\s+(\d{1,2}):(\d{2})'
            match = re.search(date_time_pattern_with_year, date_str)
            if match:
                month_abbr = match.group(1)
                day = int(match.group(2))
                year = int(match.group(3))
                hour = int(match.group(4))
                minute = int(match.group(5))
                
                months = {
                    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
                    'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
                }
                month = months.get(month_abbr.lower()[:3])
                if month:
                    try:
                        return datetime.datetime(year, month, day, hour, minute, 0)
                    except ValueError:
                        pass
        except Exception:
            pass
        
        # Unix timestamp (в миллисекундах или секундах)
        try:
            timestamp = float(date_str)
            # Если timestamp в миллисекундах (больше 10 миллиардов)
            if timestamp > 10000000000:
                timestamp = timestamp / 1000
            return datetime.datetime.fromtimestamp(timestamp)
        except (ValueError, TypeError):
            pass
        
        return None
    
    async def navigate(self, page: Page, browser: Browser):
        """Навигация по чату Fansly с прокруткой контейнера сообщений"""
        print(f"🎯 Navigating to Fansly chat: {self.chat_url}")
        try:
            await page.goto(self.chat_url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(5 * 1000)
        except Exception as e:
            print(f"First navigation attempt failed: {e}, retrying with networkidle...")
            try:
                await page.goto(self.chat_url, wait_until="networkidle", timeout=90000)
                await page.wait_for_timeout(3 * 1000)
            except Exception as retry_error:
                print(f"Navigation retry also failed: {retry_error}")
                await page.wait_for_timeout(3 * 1000)
        
        if await self.check_if_login_page(page):
            print("Warning: Login page indicators detected, but continuing...")
        
        # Ждем загрузки контейнера сообщений Fansly
        try:
            # В Fansly сообщения находятся в app-group-message-collection
            await page.wait_for_selector('app-group-message-collection', timeout=10000)
            print("✅ Fansly chat messages container loaded")
        except Exception as e:
            print(f"⚠️ Warning: Could not find Fansly messages container: {e}")
            if await self.check_if_login_page(page):
                print("Confirmed: Login page detected (no messages container)")
                await page.close()
                await browser.close()
                raise LoginPageException()
        
        # Если это режим обновления - собираем только текущие сообщения без прокрутки
        if self.update_only:
            print("🔄 Update mode: collecting current visible messages only")
            await page.wait_for_timeout(2 * 1000)
            await self._collect_messages_from_dom(page)
            print(f"Total messages collected: {len(self.messages)}")
            if len(self.messages) > self.last_saved_count:
                await self._save_messages_batch()
            return
        
        # Обычный режим полного парсинга с прокруткой
        scroll_attempts = 0
        no_new_content_count = 0
        
        # Находим правильный скроллируемый контейнер для Fansly
        # Проверяем несколько возможных контейнеров
        scroll_container_info = await page.evaluate("""
            () => {
                // Пробуем найти скроллируемый контейнер
                const selectors = [
                    '.message-content-list',
                    '.message-collection-wrapper',
                    'app-group-message-container',
                    'app-group-message-collection',
                    '.message-collection'
                ];
                
                for (const selector of selectors) {
                    const el = document.querySelector(selector);
                    if (el) {
                        // Проверяем, имеет ли элемент прокрутку
                        const hasScroll = el.scrollHeight > el.clientHeight;
                        console.log(`Found ${selector}: scrollHeight=${el.scrollHeight}, clientHeight=${el.clientHeight}, hasScroll=${hasScroll}`);
                        // Используем ТОЛЬКО контейнеры с реальной прокруткой
                        if (hasScroll) {
                            return { selector: selector, found: true };
                        }
                    }
                }
                
                // Если не нашли, пробуем найти любой элемент с overflow
                const allElements = document.querySelectorAll('*');
                for (const el of allElements) {
                    const style = window.getComputedStyle(el);
                    if ((style.overflow === 'auto' || style.overflow === 'scroll' || style.overflowY === 'auto' || style.overflowY === 'scroll') 
                        && el.scrollHeight > el.clientHeight) {
                        return { selector: 'custom', element: el, found: true };
                    }
                }
                
                return { found: false };
            }
        """)
        
        print(f"🔍 Scroll container detection: {scroll_container_info}")
        
        # Делаем первый скролл вверх, чтобы дойти до начала
        await page.evaluate("""
            () => {
                // Пробуем разные контейнеры в порядке приоритета
                const container = document.querySelector('.message-content-list') ||
                                document.querySelector('.message-collection-wrapper') ||
                                document.querySelector('app-group-message-container') ||
                                document.querySelector('app-group-message-collection') ||
                                document.querySelector('.message-collection');
                if (container) {
                    console.log('Scrolling container:', container.tagName, container.className);
                    container.scrollTop = 0;
                } else {
                    console.log('No container found, using window scroll');
                    window.scrollTo(0, 0);
                }
            }
        """)
        await page.wait_for_timeout(3 * 1000)
        
        while not self.stop_requested:
            scroll_attempts += 1
            print(f"📜 Scrolling Fansly chat... attempt {scroll_attempts} (collected {len(self.messages)} messages so far)")
            
            # Считаем количество сообщений до прокрутки
            messages_before = await page.evaluate("""
                () => {
                    const messages = document.querySelectorAll('app-group-message');
                    return messages.length;
                }
            """)
            
            # Прокручиваем вверх к началу чата
            scroll_info = await page.evaluate("""
                () => {
                    // Ищем контейнер с прокруткой (в порядке приоритета)
                    const container = document.querySelector('.message-content-list') ||
                                    document.querySelector('.message-collection-wrapper') ||
                                    document.querySelector('app-group-message-container') ||
                                    document.querySelector('app-group-message-collection') ||
                                    document.querySelector('.message-collection');
                    if (container) {
                        const scrollTopBefore = container.scrollTop;
                        const scrollHeight = container.scrollHeight;
                        const clientHeight = container.clientHeight;
                        
                        // Прокручиваем большим шагом вверх
                        container.scrollBy(0, -2000);
                        
                        const scrollTopAfter = container.scrollTop;
                        
                        return {
                            found: true,
                            selector: container.tagName + '.' + container.className,
                            scrollTopBefore: scrollTopBefore,
                            scrollTopAfter: scrollTopAfter,
                            scrollHeight: scrollHeight,
                            clientHeight: clientHeight,
                            scrollDelta: scrollTopBefore - scrollTopAfter
                        };
                    } else {
                        window.scrollBy(0, -2000);
                        return { found: false, usedWindow: true };
                    }
                }
            """)
            
            print(f"📊 Scroll info: {scroll_info}")
            
            # Увеличиваем таймаут для Fansly, чтобы загрузились новые сообщения
            await page.wait_for_timeout(5 * 1000)
            
            # Считаем количество сообщений после прокрутки
            messages_after = await page.evaluate("""
                () => {
                    const messages = document.querySelectorAll('app-group-message');
                    return messages.length;
                }
            """)
            
            print(f"📊 Messages in DOM: before={messages_before}, after={messages_after}")
            
            # Проверяем, достигли ли мы верха контейнера
            if scroll_info.get('found') and scroll_info.get('scrollTopAfter', -1) == 0 and scroll_info.get('scrollDelta', 0) == 0:
                print(f"✅ Reached the top of the container (scrollTop=0, no scroll delta)")
                no_new_content_count += 1
            
            if messages_after == messages_before:
                no_new_content_count += 1
                print(f"⏸️ No new messages loaded (count: {no_new_content_count}/5)")
                
                if no_new_content_count >= 3:  # Уменьшаем с 5 до 3, так как теперь проверяем scrollTop
                    print(f"✅ Reached the beginning of the Fansly chat! Total scrolls: {scroll_attempts}")
                    print(f"📝 Total messages in DOM: {messages_after}")
                    break
            else:
                no_new_content_count = 0
                print(f"✨ Loaded {messages_after - messages_before} new messages, continuing...")
                
                # Периодически собираем сообщения и сохраняем
                if scroll_attempts % 10 == 0:
                    await self._collect_messages_from_dom(page)
                    if len(self.messages) - self.last_saved_count >= self.save_batch_size:
                        await self._save_messages_batch()
        
        if self.stop_requested:
            print(f"🛑 Parsing stopped by user after {scroll_attempts} attempts")
        else:
            print(f"✅ Finished scrolling after {scroll_attempts} attempts")
        
        # Финальный сбор всех сообщений из DOM
        await self._collect_messages_from_dom(page)
        
        print(f"📊 Total messages collected: {len(self.messages)}")
        
        if len(self.messages) > self.last_saved_count:
            await self._save_messages_batch()
    
    async def _collect_messages_from_dom(self, page: Page):
        """Сбор сообщений напрямую из DOM Fansly"""
        try:
            messages_data = await page.evaluate("""
                () => {
                    const messages = document.querySelectorAll('app-group-message');
                    const messagesData = [];
                    
                    messages.forEach((messageEl, index) => {
                        try {
                            // Текст сообщения находится в .message-text
                            const textEl = messageEl.querySelector('.message-text');
                            const messageText = textEl ? textEl.textContent.trim() : '';
                            
                            if (!messageText) return;
                            
                            // Определяем, от кого сообщение (my-message = от модели)
                            const isFromModel = messageEl.classList.contains('my-message');
                            
                            // Ищем timestamp - время находится в span.margin-right-text внутри .timestamp
                            // .timestamp находится на уровне родителя, не внутри app-group-message
                            // Структура: <app-group-message-collection><div class="flex-row"><div class="flex-col width-100"><div><app-group-message>...</app-group-message></div><div class="timestamp"><span class="margin-right-text">...</span></div></div></div></app-group-message-collection>
                            let messageTime = '';
                            
                            // Метод 1: Ищем через closest в app-group-message-collection
                            const messageCollection = messageEl.closest('app-group-message-collection');
                            if (messageCollection && !messageTime) {
                                const timestampEl = messageCollection.querySelector('.timestamp');
                                if (timestampEl) {
                                    const timeSpan = timestampEl.querySelector('span.margin-right-text');
                                    if (timeSpan) {
                                        messageTime = timeSpan.textContent.trim();
                                    } else {
                                        messageTime = timestampEl.textContent.trim();
                                    }
                                }
                            }
                            
                            // Метод 2: Ищем через closest в flex-col.width-100 (контейнер сообщения)
                            if (!messageTime) {
                                const parentFlexCol = messageEl.closest('.flex-col.width-100');
                                if (parentFlexCol) {
                                    const timestampEl = parentFlexCol.querySelector('.timestamp');
                                    if (timestampEl) {
                                        const timeSpan = timestampEl.querySelector('span.margin-right-text');
                                        if (timeSpan) {
                                            messageTime = timeSpan.textContent.trim();
                                        } else {
                                            messageTime = timestampEl.textContent.trim();
                                        }
                                    }
                                }
                            }
                            
                            // Метод 3: Пробуем найти через родительские элементы
                            if (!messageTime) {
                                let parent = messageEl.parentElement;
                                let attempts = 0;
                                while (parent && attempts < 5) {
                                    const timestampEl = parent.querySelector('.timestamp');
                                    if (timestampEl) {
                                        const timeSpan = timestampEl.querySelector('span.margin-right-text');
                                        if (timeSpan) {
                                            messageTime = timeSpan.textContent.trim();
                                        } else {
                                            messageTime = timestampEl.textContent.trim();
                                        }
                                        break;
                                    }
                                    parent = parent.parentElement;
                                    attempts++;
                                }
                            }
                            
                            // Метод 4: Последняя попытка - ищем в самом элементе (на случай другой структуры)
                            if (!messageTime) {
                                const timestampEl = messageEl.querySelector('.timestamp');
                                if (timestampEl) {
                                    const timeSpan = timestampEl.querySelector('span.margin-right-text');
                                    if (timeSpan) {
                                        messageTime = timeSpan.textContent.trim();
                                    } else {
                                        messageTime = timestampEl.textContent.trim();
                                    }
                                }
                            }
                            
                            // Проверяем платное сообщение
                            // В Fansly весь контент делится на купленный и некупленный
                            // Бесплатно отправленный отображается по дефолту как купленный
                            // Нужно проверить наличие purchased-content или purchased-avatar (включая not-purchased)
                            let isPaid = false;
                            let amountPaid = 0;
                            
                            // Ищем purchased-content или purchased-avatar внутри сообщения или его attachment
                            const purchasedContent = messageEl.querySelector('.purchased-content');
                            const purchasedAvatar = messageEl.querySelector('.purchased-avatar');
                            const messageAttachment = messageEl.querySelector('message-attachment');
                            
                            // Если есть message-attachment, ищем внутри него
                            let attachmentPurchasedContent = null;
                            let attachmentPurchasedAvatar = null;
                            if (messageAttachment) {
                                attachmentPurchasedContent = messageAttachment.querySelector('.purchased-content');
                                attachmentPurchasedAvatar = messageAttachment.querySelector('.purchased-avatar');
                            }
                            
                            // Если найден любой из индикаторов платного контента - это платное сообщение
                            if (purchasedContent || purchasedAvatar || attachmentPurchasedContent || attachmentPurchasedAvatar) {
                                isPaid = true;
                                // Пытаемся найти цену
                                const allText = messageEl.innerText || messageEl.textContent || '';
                                const pricePattern = /\\$([\\d,]+(?:\\.\\d{2})?)/;
                                const priceMatch = allText.match(pricePattern);
                                if (priceMatch) {
                                    const priceStr = priceMatch[1].replace(/,/g, '');
                                    amountPaid = parseFloat(priceStr);
                                }
                            }
                            
                            // Извлекаем user ID из аватара (находится в родительском контейнере)
                            let fromUserId = '';
                            
                            // Аватар находится на уровень выше, ищем его в родительском контейнере
                            // Структура: <div class="flex-row"><app-account-avatar><a href="/username"></a></app-account-avatar><div><app-group-message>...</app-group-message></div></div>
                            const parentContainer = messageEl.parentElement?.parentElement?.parentElement;
                            if (parentContainer) {
                                const avatarEl = parentContainer.querySelector('app-account-avatar a[href]');
                                if (avatarEl) {
                                    const href = avatarEl.getAttribute('href');
                                    // Извлекаем username из href типа "/alan_90"
                                    fromUserId = href ? href.replace('/', '').trim() : '';
                                }
                            }
                            
                            // Если не нашли через родителя, пробуем поискать в ближайшем контейнере
                            if (!fromUserId) {
                                const closestRow = messageEl.closest('.flex-row');
                                if (closestRow) {
                                    const avatarEl = closestRow.querySelector('app-account-avatar a[href]');
                                    if (avatarEl) {
                                        const href = avatarEl.getAttribute('href');
                                        fromUserId = href ? href.replace('/', '').trim() : '';
                                    }
                                }
                            }
                            
                            // Используем fromUserId как username, если есть
                            const finalUsername = isFromModel ? 'Model' : (fromUserId || 'User');
                            
                            messagesData.push({
                                from_user_id: fromUserId,
                                from_username: finalUsername,
                                message_text: messageText,
                                message_date: messageTime,
                                is_from_model: isFromModel,
                                is_paid: isPaid,
                                amount_paid: amountPaid
                            });
                        } catch (e) {
                            console.error('Error parsing Fansly message:', e);
                        }
                    });
                    
                    return messagesData;
                }
            """)
            
            # Добавляем только уникальные сообщения
            for message_data in messages_data:
                if not any(msg['message_text'] == message_data['message_text'] and 
                          msg['from_username'] == message_data['from_username'] 
                          for msg in self.messages):
                    self.messages.append(message_data)
                    user_id_info = f"(user_id: {message_data['from_user_id']})" if message_data['from_user_id'] else "(no user_id)"
                    print(f"✅ Collected Fansly message from {message_data['from_username']} {user_id_info}: {message_data['message_text'][:50]}...")
            
            print(f"📊 Total messages collected from Fansly DOM: {len(messages_data)}")
            
        except Exception as e:
            print(f"❌ Error collecting messages from Fansly DOM: {e}")
    
    async def parse(self, ws_endpoint: str):
        """Основной метод парсинга Fansly"""
        async with async_playwright() as p:
            page = None
            browser = None
            try:
                if self.stop_requested:
                    print("🛑 Stop requested before connecting, aborting...")
                    return
                    
                browser = await p.chromium.connect_over_cdp(ws_endpoint)
                context = browser.contexts[0]
                page = await context.new_page()
                
                # Подписываемся на ответы API
                page.on("response", lambda response: asyncio.create_task(self.handle_response(response)))
                
                if self.stop_requested:
                    print("🛑 Stop requested before navigation, aborting...")
                    return
                
                await self.navigate(page, browser)
                
            except Exception as e:
                if self.stop_requested:
                    print("🛑 Stop requested, parsing aborted")
                    return
                print(f"❌ Error during Fansly parsing: {e}")
                raise
            finally:
                if page is not None:
                    await page.close()
                if browser is not None:
                    await browser.close()
                
                try:
                    await sync_to_async(self.save_messages)()
                except Exception as e:
                    print(f"❌ Error in final save: {e}")
    
    async def _save_messages_batch(self):
        """Периодическое сохранение батча новых сообщений"""
        new_messages = self.messages[self.last_saved_count:]
        if not new_messages:
            return
        
        print(f"💾 Saving Fansly batch: {len(new_messages)} new messages (total collected: {len(self.messages)})")
        
        try:
            await sync_to_async(self._save_messages_sync)(new_messages)
            self.last_saved_count = len(self.messages)
            print(f"✅ Fansly batch saved successfully! Total saved so far: {self.last_saved_count}")
        except Exception as e:
            print(f"❌ Error saving Fansly batch: {e}")
    
    def _save_messages_sync(self, messages_to_save: list[dict]):
        """Синхронное сохранение списка сообщений Fansly (только в FullChatMessage)"""
        saved_full_count = 0
        
        for message_data in messages_to_save:
            try:
                # Сохраняем только в FullChatMessage (без Profile и ChatMessage)
                if self.model_id:
                    # Определяем is_from_model из данных сообщения (парсили из DOM по классу my-message)
                    is_from_model = message_data.get('is_from_model', False)
                    
                    # Определяем user_id:
                    # - Если сообщение от модели → используем model_name
                    # - Если от пользователя → используем from_user_id из href
                    if is_from_model:
                        user_id = self.model_name if self.model_name else 'Model'
                    else:
                        user_id = message_data.get('from_user_id', '')
                    
                    existing_full = FullChatMessage.objects.filter(
                        chat_url=self.chat_url,
                        message=message_data['message_text'],
                        model_id=self.model_id
                    ).first()
                    
                    if not existing_full:
                        timestamp = None
                        if message_data.get('message_date'):
                            if isinstance(message_data['message_date'], datetime.datetime):
                                timestamp = message_data['message_date']
                            else:
                                timestamp = self._parse_date(str(message_data['message_date']))
                        
                        if timestamp is None:
                            print(f"⚠️ Warning: Could not parse message_date '{message_data.get('message_date')}', using 000000 (1970-01-01 00:00:00) as fallback")
                            timestamp = datetime.datetime(1970, 1, 1, 0, 0, 0)
                        
                        is_paid = message_data.get('is_paid', False)
                        amount_paid = message_data.get('amount_paid', 0) or 0
                        
                        FullChatMessage.objects.create(
                            user_id=user_id,
                            chat_url=self.chat_url,
                            is_from_model=is_from_model,
                            message=message_data['message_text'],
                            timestamp=timestamp,
                            is_paid=is_paid,
                            amount_paid=amount_paid,
                            model_id=self.model_id
                        )
                        saved_full_count += 1
                        
                        # Логирование для отладки
                        user_type = "model" if is_from_model else "user"
                        print(f"💾 Saved message from {user_type}: user_id={user_id}")
                else:
                    print(f"⚠️ Warning: model_id not found, skipping message save")
                        
            except Exception as e:
                print(f"❌ Error saving Fansly message: {e}")
        
        if self.model_id:
            print(f"💾 Saved {saved_full_count} new Fansly messages to FullChatMessage with model_id: {self.model_id}")
    
    def save_messages(self):
        """Сохранение всех оставшихся сообщений Fansly в базу данных"""
        new_messages = self.messages[self.last_saved_count:]
        if new_messages:
            print(f"💾 Final Fansly save: {len(new_messages)} remaining messages")
            self._save_messages_sync(new_messages)
            self.last_saved_count = len(self.messages)
        else:
            print("✅ All Fansly messages already saved during parsing")

