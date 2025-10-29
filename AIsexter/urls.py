"""
URL configuration for AIsexter project.
"""
from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('parser/', include('parser.urls')),
    path('', RedirectView.as_view(url='/parser/chat-parser/', permanent=False)),
]
