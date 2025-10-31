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
    Парсер для полного сбора сообщений из чата OnlyFans или Fansly
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
        
        # Получаем model_id из ModelInfo по profile_uuid
        try:
            model_info = ModelInfo.objects.filter(model_octo_profile=profile_uuid).first()
            self.model_id = model_info.model_id if model_info else None
            print(f"🔍 Found model_id: {self.model_id} for profile {profile_uuid}")
        except Exception as e:
            print(f"⚠️ Error getting model_id: {e}")
            self.model_id = None
    
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
        
        if parsing_successful:
            try:
                profile, created = await sync_to_async(Profile.objects.get_or_create)(
                    uuid=self.profile_uuid,
                    defaults={
                        'model_name': f'Chat Parser Profile {self.profile_uuid[:8]}',
                        'is_active': True,
                        'parsing_interval': 30,
                    }
                )
                profile.last_parsed_at = timezone.now()
                await sync_to_async(profile.save)()
            except Exception as e:
                print(f"Error updating profile: {e}")
        
        if parsing_successful and len(self.messages) > 0:
            print(f"Parsing completed. Collected {len(self.messages)} messages. Stopping profile.")
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
        """Обработка ответов API для сбора сообщений"""
        if "onlyfans.com/api2/v2/chats" in response.url and "/messages" in response.url:
            if "application/json" in response.headers.get("content-type", ""):
                try:
                    json_body = await response.json()
                    if 'list' in json_body:
                        for message in json_body['list']:
                            await self._process_message(message)
                except Exception as e:
                    print(f"Failed to parse OnlyFans messages: {e}")
        
        elif "fansly.com/api" in response.url and "messages" in response.url:
            if "application/json" in response.headers.get("content-type", ""):
                try:
                    json_body = await response.json()
                    if 'data' in json_body:
                        for message in json_body['data']:
                            await self._process_fansly_message(message)
                except Exception as e:
                    print(f"Failed to parse Fansly messages: {e}")
    
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
    
    async def _process_fansly_message(self, message: dict):
        """Обработка сообщения Fansly"""
        try:
            from_user = message.get('sender', {})
            from_user_id = from_user.get('id')
            from_username = from_user.get('username', '')
            
            is_from_model = from_user_id == self.model_user_id
            
            # Проверяем информацию о платном сообщении из API
            is_paid = False
            amount_paid = 0
            
            # В Fansly API может быть информация о цене в разных полях
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
            print(f"Collected Fansly message from {from_username}: {message_data['message_text'][:50]}...")
            
        except Exception as e:
            print(f"Error processing Fansly message: {e}")
    
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
            
            await page.wait_for_timeout(3 * 1000)
            
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
        """Синхронное сохранение списка сообщений"""
        try:
            profile, created = Profile.objects.get_or_create(
                uuid=self.profile_uuid,
                defaults={
                    'model_name': f'Chat Parser Profile {self.profile_uuid[:8]}',
                    'is_active': True,
                    'parsing_interval': 30,
                }
            )
            if created:
                print(f"Created new profile for chat parser: {profile.model_name}")
        except Exception as e:
            print(f"Error creating profile: {e}")
            return
        
        saved_count = 0
        saved_full_count = 0
        
        for message_data in messages_to_save:
            try:
                # Сохраняем в ChatMessage (старая логика)
                existing = ChatMessage.objects.filter(
                    profile=profile,
                    chat_url=self.chat_url,
                    message_text=message_data['message_text'],
                    from_username=message_data['from_username'],
                    message_date=message_data['message_date']
                ).first()
                
                if not existing:
                    ChatMessage.objects.create(
                        profile=profile,
                        chat_url=self.chat_url,
                        from_user_id=message_data['from_user_id'],
                        from_username=message_data['from_username'],
                        message_text=message_data['message_text'],
                        message_date=message_data['message_date'],
                        is_from_model=message_data['is_from_model']
                    )
                    saved_count += 1
                
                # Сохраняем в FullChatMessage (новая логика)
                if self.model_id:
                    user_id = message_data.get('from_user_id', '')
                    # Определяем is_from_model: сравниваем user_id с model_id из ModelInfo
                    # Нормализуем значения: str(user_id).strip() и str(self.model_id).strip()
                    user_id_str = str(user_id).strip() if user_id else ''
                    model_id_str = str(self.model_id).strip() if self.model_id else ''
                    
                    # Проверяем, что значения не пустые, и сравниваем
                    is_from_model = (user_id_str == model_id_str) and (user_id_str != '') and (model_id_str != '')
                    
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
                        
            except Exception as e:
                print(f"Error saving message: {e}")
        
        print(f"Saved {saved_count} new messages to ChatMessage")
        if self.model_id:
            print(f"Saved {saved_full_count} new messages to FullChatMessage with model_id: {self.model_id}")
    
    def save_messages(self):
        """Сохранение всех оставшихся сообщений в базу данных"""
        new_messages = self.messages[self.last_saved_count:]
        if new_messages:
            print(f"💾 Final save: {len(new_messages)} remaining messages")
            self._save_messages_sync(new_messages)
            self.last_saved_count = len(self.messages)
        else:
            print("✅ All messages already saved during parsing")

