from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.db.models import Count, Max
from collections import defaultdict
import asyncio
import threading
from datetime import datetime
from .models import Profile, ChatMessage, ModelInfo, FullChatMessage
from .services import ChatParser, OctoAPIClient, OctoClient
from django.conf import settings

# Глобальный словарь для отслеживания активных потоков парсинга
active_parsing_threads = {}
threads_lock = threading.Lock()


def chat_parser_view(request):
    """Веб-интерфейс для парсера чатов"""
    # Получаем модели из таблицы ModelInfo
    try:
        model_infos = ModelInfo.objects.all()
        
        # Создаем список моделей для выбора
        profiles = []
        for model_info in model_infos:
            # Пропускаем модели без UUID профиля OctoBrowser
            if not model_info.model_octo_profile:
                continue
                
            profiles.append({
                'uuid': model_info.model_octo_profile,  # UUID из model_octo_profile
                'title': model_info.model_name,          # Имя модели
                'name': model_info.model_name,
                'model_id': model_info.model_id          # ID модели для связи
            })
            
    except Exception as e:
        print(f"Error getting models from ModelInfo: {e}")
        profiles = []
    
    # Получаем последние распарсенные чаты из FullChatMessage, сгруппированные по моделям
    # Группируем по model_id и chat_url (chat_url = идентификатор чата)
    all_chats = FullChatMessage.objects.exclude(
        chat_url__isnull=True
    ).exclude(
        chat_url=''
    ).values(
        'model_id',
        'chat_url',
    ).annotate(
        message_count=Count('id'),
        last_message_date=Max('timestamp'),
        user_id=Max('user_id')  # Берем user_id для отображения
    ).order_by('model_id', '-last_message_date')
    
    # Создаем словарь для связи model_id с именами моделей из ModelInfo
    model_infos_dict = {m.model_id: m.model_name for m in ModelInfo.objects.all()}
    
    # Группируем чаты по моделям
    models_with_chats = defaultdict(lambda: {
        'model_name': '',
        'model_id': '',
        'chats': [],
        'total_messages': 0,
        'last_activity': None
    })
    
    for chat in all_chats:
        model_id = chat['model_id'] or 'unknown'
        model_name = model_infos_dict.get(model_id, f'Model {model_id}')
        chat_url = chat['chat_url']
        
        models_with_chats[model_id]['model_name'] = model_name
        models_with_chats[model_id]['model_id'] = model_id
        models_with_chats[model_id]['chats'].append({
            'chat_url': chat_url,
            'user_id': chat['user_id'],  # Для отображения
            'message_count': chat['message_count'],
            'last_message': chat['last_message_date']
        })
        models_with_chats[model_id]['total_messages'] += chat['message_count']
        
        # Обновляем последнюю активность
        if models_with_chats[model_id]['last_activity'] is None or \
           (chat['last_message_date'] and chat['last_message_date'] > models_with_chats[model_id]['last_activity']):
            models_with_chats[model_id]['last_activity'] = chat['last_message_date']
    
    # Сортируем модели по последней активности
    sorted_models = sorted(
        models_with_chats.values(),
        key=lambda x: x['last_activity'] if x['last_activity'] else '',
        reverse=True
    )
    
    context = {
        'profiles': profiles,
        'models_with_chats': sorted_models
    }
    
    if request.method == 'POST':
        profile_uuid = request.POST.get('profile')
        chat_url = request.POST.get('chat_url')
        
        if not profile_uuid or not chat_url:
            context['error'] = 'Please select a profile and enter a chat URL'
            return render(request, 'parser/chat_parser.html', context)
        
        try:
            # Запускаем парсер в отдельном потоке
            import logging
            import traceback
            logger = logging.getLogger(__name__)
            
            def run_parser():
                thread_id = threading.current_thread().ident
                try:
                    # Создаем парсер
                    parser = ChatParser(profile_uuid, chat_url)
                    
                    # Регистрируем поток как активный с ссылкой на парсер
                    with threads_lock:
                        active_parsing_threads[thread_id] = {
                            'profile_uuid': profile_uuid,
                            'chat_url': chat_url,
                            'thread_name': threading.current_thread().name,
                            'started_at': datetime.now().isoformat(),
                            'status': 'running',
                            'parser': parser  # Сохраняем ссылку на парсер для остановки
                        }
                    
                    logger.info(f"🚀 Starting ChatParser for profile {profile_uuid} and URL {chat_url}")
                    print(f"🚀 Starting ChatParser for profile {profile_uuid} and URL {chat_url}")
                    result = asyncio.run(parser.run())
                    logger.info(f"✅ Parser finished with result: {result}")
                    print(f"✅ Parser finished with result: {result}")
                    
                    # Обновляем статус в зависимости от результата
                    with threads_lock:
                        if thread_id in active_parsing_threads:
                            if result and result.get('status') == 'error':
                                active_parsing_threads[thread_id]['status'] = 'error'
                                active_parsing_threads[thread_id]['error_message'] = result.get('message', 'Unknown error')
                            else:
                                active_parsing_threads[thread_id]['status'] = 'completed'
                except Exception as e:
                    logger.error(f"❌ Parser error: {e}", exc_info=True)
                    print(f"❌ Parser error: {e}")
                    traceback.print_exc()
                    # Обновляем статус на error
                    with threads_lock:
                        if thread_id in active_parsing_threads:
                            active_parsing_threads[thread_id]['status'] = 'error'
                            active_parsing_threads[thread_id]['error_message'] = str(e)
                finally:
                    # Удаляем поток из активных через 30 секунд после завершения
                    # чтобы пользователь успел увидеть результат
                    import time
                    time.sleep(30)
                    with threads_lock:
                        active_parsing_threads.pop(thread_id, None)
            
            thread = threading.Thread(target=run_parser, name=f"ChatParser-{profile_uuid[:8]}")
            thread.daemon = True
            thread.start()
            
            logger.info(f"✅ Thread started: {thread.name}")
            print(f"✅ Thread started: {thread.name}")
            
            context['success'] = f'Chat parsing started for {chat_url}. Check logs: docker-compose logs -f web'
            
        except Exception as e:
            context['error'] = f'Error starting parser: {str(e)}'
            print(f"Error starting parser thread: {e}")
    
    return render(request, 'parser/chat_parser.html', context)


@csrf_exempt
@require_http_methods(["POST"])
def stop_chat_parsing(request):
    """API endpoint для остановки парсинга чата"""
    try:
        profile_uuid = request.POST.get('profile_uuid')
        
        if not profile_uuid:
            return JsonResponse({'status': 'error', 'message': 'Missing profile_uuid'})
        
        # Ищем активный поток парсера для этого профиля и устанавливаем флаг остановки
        parser_found = False
        with threads_lock:
            for thread_id, thread_info in active_parsing_threads.items():
                if thread_info.get('profile_uuid') == profile_uuid:
                    parser = thread_info.get('parser')
                    if parser:
                        parser.stop_requested = True
                        parser_found = True
                        print(f"🛑 Stop signal sent to parser for profile {profile_uuid[:8]}")
                    break
        
        # Останавливаем профиль в Octo Browser
        octo = OctoClient.init_from_settings()
        success = octo.stop_profile(profile_uuid)
        
        if success or parser_found:
            return JsonResponse({
                'status': 'success', 
                'message': f'Chat parsing stopped for profile {profile_uuid}'
            })
        else:
            return JsonResponse({
                'status': 'error', 
                'message': 'Failed to stop profile'
            })
        
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


@csrf_exempt
@require_http_methods(["POST"])
def start_chat_parsing(request):
    """API endpoint для запуска парсинга чата"""
    try:
        profile_uuid = request.POST.get('profile_uuid')
        chat_url = request.POST.get('chat_url')
        
        if not profile_uuid or not chat_url:
            return JsonResponse({'status': 'error', 'message': 'Missing required parameters'})
        
        # Запускаем парсер в отдельном потоке
        def run_parser():
            thread_id = threading.current_thread().ident
            try:
                # Создаем парсер
                parser = ChatParser(profile_uuid, chat_url)
                
                # Регистрируем поток как активный с ссылкой на парсер
                with threads_lock:
                    active_parsing_threads[thread_id] = {
                        'profile_uuid': profile_uuid,
                        'chat_url': chat_url,
                        'thread_name': threading.current_thread().name,
                        'started_at': datetime.now().isoformat(),
                        'status': 'running',
                        'parser': parser  # Сохраняем ссылку на парсер для остановки
                    }
                result = asyncio.run(parser.run())
                
                # Обновляем статус в зависимости от результата
                with threads_lock:
                    if thread_id in active_parsing_threads:
                        if result and result.get('status') == 'error':
                            active_parsing_threads[thread_id]['status'] = 'error'
                            active_parsing_threads[thread_id]['error_message'] = result.get('message', 'Unknown error')
                        else:
                            active_parsing_threads[thread_id]['status'] = 'completed'
            except Exception as e:
                print(f"Parser error: {e}")
                # Обновляем статус на error
                with threads_lock:
                    if thread_id in active_parsing_threads:
                        active_parsing_threads[thread_id]['status'] = 'error'
                        active_parsing_threads[thread_id]['error_message'] = str(e)
            finally:
                # Удаляем поток из активных через 30 секунд после завершения
                import time
                time.sleep(30)
                with threads_lock:
                    active_parsing_threads.pop(thread_id, None)
        
        thread = threading.Thread(target=run_parser, name=f"ChatParser-{profile_uuid[:8]}")
        thread.daemon = True
        thread.start()
        
        return JsonResponse({
            'status': 'success', 
            'message': f'Chat parsing started'
        })
        
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


def view_chat_messages(request, profile_id):
    """Просмотр всех сообщений конкретного чата"""
    chat_url = request.GET.get('chat_url')
    
    if not chat_url:
        context = {'error': 'Chat URL is required'}
        return render(request, 'parser/chat_parser.html', context)
    
    try:
        profile = Profile.objects.get(id=profile_id)
        chat_messages = ChatMessage.objects.filter(
            profile=profile,
            chat_url=chat_url
        ).order_by('message_date', 'created_at')
        
        # Получаем статистику
        total_messages = chat_messages.count()
        model_messages = chat_messages.filter(is_from_model=True).count()
        user_messages = total_messages - model_messages
        
        # Получаем первую и последнюю дату сообщений
        first_message = chat_messages.first()
        last_message = chat_messages.last()
        
        context = {
            'profile': profile,
            'chat_url': chat_url,
            'messages': chat_messages,
            'total_messages': total_messages,
            'model_messages': model_messages,
            'user_messages': user_messages,
            'first_message_date': first_message.message_date if first_message else None,
            'last_message_date': last_message.message_date if last_message else None,
        }
        
        return render(request, 'parser/view_chat.html', context)
        
    except Profile.DoesNotExist:
        context = {'error': 'Profile not found'}
        return render(request, 'parser/chat_parser.html', context)


def view_full_chat(request):
    """Просмотр диалога из FullChatMessage по chat_url"""
    chat_url = request.GET.get('chat_url')
    
    if not chat_url:
        context = {'error': 'chat_url is required'}
        return render(request, 'parser/chat_parser.html', context)
    
    try:
        # Получаем все сообщения для данного чата по chat_url
        # Сортируем по timestamp в обратном порядке (последние сверху)
        messages = FullChatMessage.objects.filter(
            chat_url=chat_url
        ).order_by('-timestamp')
        
        if not messages.exists():
            context = {'error': f'No messages found for chat: {chat_url}'}
            return render(request, 'parser/chat_parser.html', context)
        
        # Получаем model_id из первого сообщения (теперь это самое последнее по времени)
        first_msg = messages.first()
        model_id = first_msg.model_id if first_msg else None
        
        # Получаем информацию о модели
        model_name = 'Unknown Model'
        if model_id:
            try:
                model_info = ModelInfo.objects.get(model_id=model_id)
                model_name = model_info.model_name
            except ModelInfo.DoesNotExist:
                model_name = f'Model {model_id}'
        
        # Получаем user_id из первого сообщения (для отображения)
        user_id = first_msg.user_id if first_msg else 'unknown'
        
        # Статистика
        total_messages = messages.count()
        model_messages = messages.filter(is_from_model=True).count()
        user_messages = messages.filter(is_from_model=False).count()
        
        # Первое (самое раннее) и последнее (самое позднее) сообщение
        # Используем исходный порядок без сортировки для определения дат
        all_messages = FullChatMessage.objects.filter(chat_url=chat_url).order_by('timestamp')
        first_message = all_messages.first()
        last_message = all_messages.last()
        
        context = {
            'user_id': user_id,
            'model_id': model_id,
            'model_name': model_name,
            'messages': messages,
            'chat_url': chat_url,
            'total_messages': total_messages,
            'model_messages': model_messages,
            'user_messages': user_messages,
            'first_message_date': first_message.timestamp if first_message else None,
            'last_message_date': last_message.timestamp if last_message else None,
        }
        
        return render(request, 'parser/view_full_chat.html', context)
        
    except Exception as e:
        context = {'error': f'Error loading chat: {str(e)}'}
        return render(request, 'parser/chat_parser.html', context)


@csrf_exempt
@require_http_methods(["GET"])
def get_active_parsers(request):
    """API endpoint для получения активных парсеров (потоков парсинга)"""
    try:
        # Получаем информацию о модели по UUID профиля
        model_infos = ModelInfo.objects.exclude(model_octo_profile__isnull=True).exclude(model_octo_profile='')
        model_uuid_to_name = {m.model_octo_profile: m.model_name for m in model_infos}
        
        # Получаем активные потоки парсинга
        active_parsers = []
        with threads_lock:
            # Фильтруем только живые потоки
            threads_to_remove = []
            for thread_id, thread_info in active_parsing_threads.items():
                # Проверяем, жив ли поток
                thread_obj = None
                for t in threading.enumerate():
                    if t.ident == thread_id:
                        thread_obj = t
                        break
                
                if thread_obj and thread_obj.is_alive():
                    profile_uuid = thread_info['profile_uuid']
                    model_name = model_uuid_to_name.get(profile_uuid, f'Profile {profile_uuid[:8]}')
                    status = thread_info.get('status', 'running')
                    active_parsers.append({
                        'thread_id': thread_id,
                        'uuid': profile_uuid,
                        'name': model_name,
                        'chat_url': thread_info.get('chat_url', 'Unknown'),
                        'status': status,
                        'started_at': thread_info.get('started_at', 'Unknown'),
                        'thread_name': thread_info.get('thread_name', 'Unknown'),
                        'error_message': thread_info.get('error_message', None)
                    })
                elif thread_info.get('status') in ('error', 'completed'):
                    # Поток завершился, но еще не удален (в течение 30 секунд)
                    profile_uuid = thread_info['profile_uuid']
                    model_name = model_uuid_to_name.get(profile_uuid, f'Profile {profile_uuid[:8]}')
                    active_parsers.append({
                        'thread_id': thread_id,
                        'uuid': profile_uuid,
                        'name': model_name,
                        'chat_url': thread_info.get('chat_url', 'Unknown'),
                        'status': thread_info.get('status', 'unknown'),
                        'started_at': thread_info.get('started_at', 'Unknown'),
                        'thread_name': thread_info.get('thread_name', 'Unknown'),
                        'error_message': thread_info.get('error_message', None)
                    })
                else:
                    # Поток уже не жив и не в статусе завершения, удаляем его
                    threads_to_remove.append(thread_id)
            
            # Удаляем неактивные потоки
            for thread_id in threads_to_remove:
                active_parsing_threads.pop(thread_id, None)
        
        return JsonResponse({
            'status': 'success',
            'active_parsers': active_parsers
        })
        
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


@csrf_exempt
@require_http_methods(["POST"])
def stop_all_parsers(request):
    """API endpoint для остановки всех активных парсеров"""
    try:
        octo = OctoClient.init_from_settings()
        running_profiles = octo.get_running_profiles()
        
        # Получаем UUID профилей из ModelInfo
        model_infos = ModelInfo.objects.exclude(model_octo_profile__isnull=True).exclude(model_octo_profile='')
        model_uuid_to_name = {m.model_octo_profile: m.model_name for m in model_infos}
        chat_parser_uuids = list(model_uuid_to_name.keys())
        
        stopped_count = 0
        errors = []
        
        for profile in running_profiles:
            profile_uuid = profile.get('uuid')
            if profile_uuid in chat_parser_uuids:
                try:
                    success = octo.stop_profile(profile_uuid)
                    if success:
                        stopped_count += 1
                    else:
                        profile_name = model_uuid_to_name.get(profile_uuid, profile.get('title', 'Unknown'))
                        errors.append(f"Failed to stop {profile_name}")
                except Exception as e:
                    profile_name = model_uuid_to_name.get(profile_uuid, profile.get('title', 'Unknown'))
                    errors.append(f"Error stopping {profile_name}: {str(e)}")
        
        return JsonResponse({
            'status': 'success',
            'stopped_count': stopped_count,
            'errors': errors
        })
        
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})

