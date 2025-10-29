import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'AIsexter.settings')
django.setup()

from parser.services import OctoClient
from django.conf import settings

print('🔌 Connecting to Octo Browser...')
octo = OctoClient.init_from_settings()

print('\n📊 Checking running profiles...')
try:
    running = octo.get_running_profiles()
    print(f'Running profiles: {len(running)}')
    
    if running:
        for profile in running:
            uuid = profile.get('uuid', 'Unknown')
            title = profile.get('title', 'No title')
            print(f'\n  🔴 Running: {title} ({uuid})')
            
            # Остановим каждый запущенный профиль
            print(f'  🛑 Stopping profile {uuid}...')
            try:
                result = octo.stop_profile(uuid)
                print(f'  ✅ Stopped: {result}')
            except Exception as e:
                print(f'  ❌ Error stopping: {e}')
    else:
        print('✅ No profiles are running')
        
except Exception as e:
    print(f'❌ Error getting running profiles: {e}')
    import traceback
    traceback.print_exc()

