from django.contrib import admin
from .models import Profile, ChatMessage


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('uuid', 'model_name', 'is_active', 'last_parsed_at')
    list_filter = ('is_active',)
    search_fields = ('uuid', 'model_name')


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ('from_username', 'message_text_short', 'message_date', 'is_from_model', 'created_at')
    list_filter = ('is_from_model', 'created_at')
    search_fields = ('from_username', 'message_text', 'chat_url')
    
    def message_text_short(self, obj):
        return obj.message_text[:50] + '...' if len(obj.message_text) > 50 else obj.message_text
    message_text_short.short_description = 'Message'

