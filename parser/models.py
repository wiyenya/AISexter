from django.db import models
from django.contrib.auth.models import AbstractUser


class CustomUser(AbstractUser):
    """Упрощенная модель пользователя для авторизации в админке"""
    
    class Meta:
        db_table = 'crm_customuser'

    def __str__(self):
        return self.username


class Profile(models.Model):
    uuid = models.CharField(max_length=255, unique=True)
    is_active = models.BooleanField(default=False)
    model_name = models.CharField(max_length=255)
    parsing_interval = models.IntegerField(default=30)
    last_parsed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'parser_profile'
    
    def __str__(self):
        return f"Profile {self.uuid} ({self.model_name})"


class ChatMessage(models.Model):
    profile = models.ForeignKey("parser.Profile", on_delete=models.CASCADE)
    chat_url = models.URLField(max_length=500)
    from_user_id = models.CharField(max_length=64, null=True, blank=True)
    from_username = models.CharField(max_length=255, null=True, blank=True)
    message_text = models.TextField()
    message_date = models.DateTimeField(null=True, blank=True)
    is_from_model = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'parser_chatmessage'
        ordering = ['message_date', 'created_at']
    
    def __str__(self):
        return f"Message from {self.from_username} at {self.message_date}"


class ModelInfo(models.Model):
    model_name = models.TextField()
    group_id = models.BigIntegerField()
    model_id = models.CharField(max_length=255)
    model_octo_profile = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        db_table = 'parser_modelinfo'
    
    def __str__(self):
        return f"ModelInfo {self.model_name} (group: {self.group_id})"


class FullChatMessage(models.Model):
    user_id = models.CharField(max_length=64)
    is_from_model = models.BooleanField(default=False)
    message = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    is_paid = models.BooleanField(default=False)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    model_id = models.CharField(max_length=255, default='', blank=True)

    class Meta:
        db_table = 'parser_fullchatmessage'
        ordering = ['timestamp']
    
    def __str__(self):
        return f"Message from user {self.user_id} at {self.timestamp}"

