from django.contrib import admin
from .models import Profile, ChatMessage, FullChatMessage, ModelInfo


@admin.register(ModelInfo)
class ModelInfoAdmin(admin.ModelAdmin):
    list_display = ('model_name', 'model_id', 'group_id', 'model_octo_profile')
    search_fields = ('model_name', 'model_id', 'model_octo_profile')
    list_filter = ('group_id',)


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


@admin.register(FullChatMessage)
class FullChatMessageAdmin(admin.ModelAdmin):
    list_display = ('user_id', 'message_short', 'timestamp', 'is_from_model', 'is_paid', 'amount_paid', 'model_id')
    list_filter = ('is_from_model', 'is_paid', 'timestamp', 'model_id')
    search_fields = ('user_id', 'message', 'model_id')
    
    def message_short(self, obj):
        return obj.message[:50] + '...' if len(obj.message) > 50 else obj.message
    message_short.short_description = 'Message'

