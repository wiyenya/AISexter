from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.db.models import Count, Max
from collections import defaultdict
import asyncio
import threading
from .models import Profile, ChatMessage
from .services import ChatParser, OctoAPIClient, OctoClient
from django.conf import settings


def chat_parser_view(request):
    """Веб-интерфейс для парсера чатов"""
    # Получаем профили из Octo Browser по тегу parserChat
    try:
        octo_api = OctoAPIClient(settings.OCTO_API_TOKEN)
        octo_profiles = octo_api.get_chat_parser_profiles()
        
        # Создаем список профилей для выбора
        profiles = []
        for octo_profile in octo_profiles:
            profiles.append({
                'uuid': octo_profile.get('uuid'),
                'title': octo_profile.get('title'),
                'name': octo_profile.get('title', 'Unknown Profile')
            })
            
    except Exception as e:
        print(f"Error getting Octo profiles: {e}")
        # Fallback на локальные профили
        profiles = Profile.objects.filter(is_active=True)
        profiles = [{'uuid': p.uuid, 'title': p.model_name, 'name': p.model_name} for p in profiles]
    
    # Получаем последние распарсенные чаты, сгруппированные по моделям
    all_chats = ChatMessage.objects.values(
        'profile__model_name',
        'profile_id',
        'chat_url',
    ).annotate(
        message_count=Count('id'),
        last_message_date=Max('message_date')
    ).order_by('profile__model_name', '-last_message_date')
    
    # Группируем чаты по моделям
    models_with_chats = defaultdict(lambda: {
        'model_name': '',
        'chats': [],
        'total_messages': 0,
        'last_activity': None
    })
    
    for chat in all_chats:
        profile_name = chat['profile__model_name'] or 'Unknown Profile'
        models_with_chats[profile_name]['model_name'] = profile_name
        models_with_chats[profile_name]['chats'].append({
            'url': chat['chat_url'],
            'message_count': chat['message_count'],
            'last_message': chat['last_message_date'],
            'profile_id': chat['profile_id']
        })
        models_with_chats[profile_name]['total_messages'] += chat['message_count']
        
        # Обновляем последнюю активность
        if models_with_chats[profile_name]['last_activity'] is None or \
           (chat['last_message_date'] and chat['last_message_date'] > models_with_chats[profile_name]['last_activity']):
            models_with_chats[profile_name]['last_activity'] = chat['last_message_date']
    
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
            def run_parser():
                try:
                    parser = ChatParser(profile_uuid, chat_url)
                    asyncio.run(parser.run())
                except Exception as e:
                    print(f"Parser error: {e}")
            
            thread = threading.Thread(target=run_parser)
            thread.daemon = True
            thread.start()
            
            context['success'] = f'Chat parsing started for {chat_url}. This may take several minutes.'
            
        except Exception as e:
            context['error'] = f'Error starting parser: {str(e)}'
    
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


@csrf_exempt
@require_http_methods(["GET"])
def get_active_parsers(request):
    """API endpoint для получения активных парсеров"""
    try:
        octo = OctoClient.init_from_settings()
        running_profiles = octo.get_running_profiles()
        
        # Фильтруем только профили с тегом parserChat
        octo_api = OctoAPIClient(settings.OCTO_API_TOKEN)
        chat_parser_profiles = octo_api.get_chat_parser_profiles()
        chat_parser_uuids = [p.get('uuid') for p in chat_parser_profiles]
        
        active_parsers = []
        for profile in running_profiles:
            if profile.get('uuid') in chat_parser_uuids:
                active_parsers.append({
                    'uuid': profile.get('uuid'),
                    'name': profile.get('title', 'Unknown'),
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
        
        # Получаем профили с тегом parserChat
        octo_api = OctoAPIClient(settings.OCTO_API_TOKEN)
        chat_parser_profiles = octo_api.get_chat_parser_profiles()
        chat_parser_uuids = [p.get('uuid') for p in chat_parser_profiles]
        
        stopped_count = 0
        errors = []
        
        for profile in running_profiles:
            if profile.get('uuid') in chat_parser_uuids:
                try:
                    success = octo.stop_profile(profile.get('uuid'))
                    if success:
                        stopped_count += 1
                    else:
                        errors.append(f"Failed to stop {profile.get('title', 'Unknown')}")
                except Exception as e:
                    errors.append(f"Error stopping {profile.get('title', 'Unknown')}: {str(e)}")
        
        return JsonResponse({
            'status': 'success',
            'stopped_count': stopped_count,
            'errors': errors
        })
        
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})

