from django.urls import path
from . import views

urlpatterns = [
    path('chat-parser/', views.chat_parser_view, name='chat_parser'),
    path('api/start-chat-parsing/', views.start_chat_parsing, name='start_chat_parsing'),
    path('api/stop-chat-parsing/', views.stop_chat_parsing, name='stop_chat_parsing'),
    path('api/get-active-parsers/', views.get_active_parsers, name='get_active_parsers'),
    path('api/stop-all-parsers/', views.stop_all_parsers, name='stop_all_parsers'),
    path('view-chat/<int:profile_id>/', views.view_chat_messages, name='view_chat'),
]

