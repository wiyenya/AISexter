from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.db.models import Count, Max
from collections import defaultdict
import asyncio
import threading
from .models import Profile, ChatMessage, ModelInfo, FullChatMessage
from .services import ChatParser, OctoAPIClient, OctoClient
from django.conf import settings


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
    # Группируем по model_id и user_id (user_id = идентификатор чата)
    all_chats = FullChatMessage.objects.values(
        'model_id',
        'user_id',
    ).annotate(
        message_count=Count('id'),
        last_message_date=Max('timestamp')
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
        
        models_with_chats[model_id]['model_name'] = model_name
        models_with_chats[model_id]['model_id'] = model_id
        models_with_chats[model_id]['chats'].append({
            'user_id': chat['user_id'],
            'message_count': chat['message_count'],
            'last_message': chat['last_message_date'],
            'chat_id': chat['user_id']  # Используем user_id как идентификатор чата
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
                try:
                    logger.info(f"🚀 Starting ChatParser for profile {profile_uuid} and URL {chat_url}")
                    print(f"🚀 Starting ChatParser for profile {profile_uuid} and URL {chat_url}")
                    parser = ChatParser(profile_uuid, chat_url)
                    result = asyncio.run(parser.run())
                    logger.info(f"✅ Parser finished with result: {result}")
                    print(f"✅ Parser finished with result: {result}")
                except Exception as e:
                    logger.error(f"❌ Parser error: {e}", exc_info=True)
                    print(f"❌ Parser error: {e}")
                    traceback.print_exc()
            
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
        
        # Останавливаем профиль в Octo Browser
        octo = OctoClient.init_from_settings()
        success = octo.stop_profile(profile_uuid)
        
        if success:
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
            try:
                parser = ChatParser(profile_uuid, chat_url)
                asyncio.run(parser.run())
            except Exception as e:
                print(f"Parser error: {e}")
        
        thread = threading.Thread(target=run_parser)
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
    """Просмотр диалога из FullChatMessage по user_id и model_id"""
    user_id = request.GET.get('user_id')
    model_id = request.GET.get('model_id')
    
    if not user_id or not model_id:
        context = {'error': 'user_id and model_id are required'}
        return render(request, 'parser/chat_parser.html', context)
    
    try:
        # Получаем все сообщения для данного чата
        messages = FullChatMessage.objects.filter(
            user_id=user_id,
            model_id=model_id
        ).order_by('timestamp')
        
        # Получаем информацию о модели
        try:
            model_info = ModelInfo.objects.get(model_id=model_id)
            model_name = model_info.model_name
        except ModelInfo.DoesNotExist:
            model_name = f'Model {model_id}'
        
        # Статистика
        total_messages = messages.count()
        model_messages = messages.filter(is_from_model=True).count()
        user_messages = messages.filter(is_from_model=False).count()
        
        # Первое и последнее сообщение
        first_message = messages.first()
        last_message = messages.last()
        
        # URL чата
        chat_url = f"https://onlyfans.com/my/chats/chat/{user_id}/"
        
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
    """API endpoint для получения активных парсеров"""
    try:
        octo = OctoClient.init_from_settings()
        running_profiles = octo.get_running_profiles()
        
        # Получаем UUID профилей из ModelInfo
        model_infos = ModelInfo.objects.exclude(model_octo_profile__isnull=True).exclude(model_octo_profile='')
        model_uuid_to_name = {m.model_octo_profile: m.model_name for m in model_infos}
        chat_parser_uuids = list(model_uuid_to_name.keys())
        
        active_parsers = []
        for profile in running_profiles:
            profile_uuid = profile.get('uuid')
            if profile_uuid in chat_parser_uuids:
                active_parsers.append({
                    'uuid': profile_uuid,
                    'name': model_uuid_to_name.get(profile_uuid, profile.get('title', 'Unknown')),
                    'status': 'running'
                })
        
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

