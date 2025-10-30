import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'AIsexter.settings')
django.setup()

from parser.services import OctoAPIClient
from django.conf import settings
import requests

print('🔍 Getting all available profiles from Octo Browser...\n')

# Используем API токен для получения всех профилей
api_token = settings.OCTO_API_TOKEN
url = "https://app.octobrowser.net/api/v2/automation/profiles"
headers = {"X-Octo-Api-Token": api_token}

try:
    # Получаем все профили без фильтра по тегам
    response = requests.get(
        url,
        params={
            "page_len": "100",  # Максимум профилей на странице
            "fields": "title,tags"  # Запрашиваем также теги
        },
        headers=headers,
        timeout=30
    )
    
    if not response.ok:
        print(f'❌ Error: {response.status_code}')
        print(response.text)
        exit(1)
    
    data = response.json()
    
    if not data.get('success'):
        print(f"❌ API Error: {data.get('error')}")
        exit(1)
    
    profiles = data.get('data', [])
    
    print(f'📊 Found {len(profiles)} profiles:\n')
    print('=' * 80)
    
    # Группируем профили по тегам
    profiles_by_tag = {}
    profiles_without_tags = []
    
    for profile in profiles:
        uuid = profile.get('uuid', 'Unknown')
        title = profile.get('title', 'No title')
        tags = profile.get('tags', [])
        
        if not tags:
            profiles_without_tags.append((uuid, title, tags))
        else:
            for tag in tags:
                if tag not in profiles_by_tag:
                    profiles_by_tag[tag] = []
                profiles_by_tag[tag].append((uuid, title, tags))
    
    # Выводим профили по тегам
    for tag in sorted(profiles_by_tag.keys()):
        print(f'\n🏷️  Tag: {tag}')
        print('-' * 80)
        for uuid, title, tags in profiles_by_tag[tag]:
            print(f'   UUID: {uuid}')
            print(f'   Title: {title}')
            if len(tags) > 1:
                other_tags = [t for t in tags if t != tag]
                print(f'   Other tags: {", ".join(other_tags)}')
            print()
    
    # Выводим профили без тегов
    if profiles_without_tags:
        print(f'\n📝 Profiles without tags:')
        print('-' * 80)
        for uuid, title, tags in profiles_without_tags:
            print(f'   UUID: {uuid}')
            print(f'   Title: {title}')
            print()
    
    print('=' * 80)
    print(f'\n✅ Total: {len(profiles)} profiles')
    
    # Дополнительная статистика
    chat_parser_profiles = [p for p in profiles if 'parserChat' in p.get('tags', [])]
    print(f'📱 Chat parser profiles (parserChat tag): {len(chat_parser_profiles)}')
    
except Exception as e:
    print(f'❌ Error: {e}')
    import traceback
    traceback.print_exc()

