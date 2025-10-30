from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
from django.db.models import Sum, Count, Q, Case, When, Value, F
from django.db.models.functions import Coalesce
from decimal import Decimal
from datetime import timedelta


class CustomUser(AbstractUser):
    service = models.ForeignKey('common.Service', on_delete=models.PROTECT, null=True, blank=True)
    allowed_models = models.ManyToManyField('parser.Profile', blank=True)
    allowed_model_groups = models.ManyToManyField('parser.ProfileGroup', blank=True)
    transaction_ending = models.IntegerField(default=0)
    tg_username = models.CharField(max_length=255, blank=True, null=True)
    experience = models.CharField(max_length=255, blank=True, null=True)
    test_date = models.DateTimeField(blank=True, null=True)
    claim_timeout = models.IntegerField(default=0, help_text="Timeout in days")

    class Meta:
        db_table = 'crm_customuser'

    def get_claimable_transactions(self, profile_group_id: str | None = None, claim_filter_value: str | None = None):
        from crm.models import Transaction
        timeout_threshold = timezone.now() - timedelta(days=self.claim_timeout)
        
        filters = {'of_created_at__gte': timeout_threshold}
        
        if profile_group_id:
            filters['profile__group__id'] = profile_group_id
        else:
            allowed_ids = list(self.allowed_model_groups.values_list('id', flat=True))
            filters['profile__group__id__in'] = allowed_ids
        
        qs = (
            Transaction.for_service(self.service.name)
            .filter(**filters)
        ).annotate(num_claims=Count('claims'))

        if claim_filter_value:
            if claim_filter_value == 'with':
                qs = qs.filter(num_claims__gt=0)
            elif claim_filter_value == 'without':
                qs = qs.filter(num_claims=0)
        return qs.order_by('-of_created_at')
    
    def get_earnings(self, days: int, from_day_start: bool = True):
        now = timezone.now()
        start_time = now - timedelta(days=days)
        if from_day_start:
            start_time = start_time.replace(hour=0, minute=0, second=0, microsecond=0)
        claims = self.claims.filter(transaction__of_created_at__gte=start_time)
        if claims:
            return round(claims.aggregate(Sum('transaction__net'))['transaction__net__sum'], 2) or 0
        else:
            return 0
    
    def get_own_rating(self, range_type: str = 'month'):
        from crm.utils import get_start_of_week, get_start_of_month
        now = timezone.now()

        if range_type == 'week':
            start_date = get_start_of_week()
        elif range_type == 'month':
            start_date = get_start_of_month()
        else:
            raise ValueError("Invalid range_type. Use 'week' or 'month'.")

        days = (now - start_date).days
        self_earnings = self.get_earnings(days)
        
        qs = CustomUser.objects.filter(is_staff=False, service=self.service).annotate(
            total_earnings=Coalesce(
                Sum(
                    Case(
                        When(claims__transaction__of_created_at__gte=start_date, then=F('claims__transaction__net')),
                        default=Value(0, output_field=models.DecimalField()),
                        output_field=models.DecimalField(),
                    )
                ),
                Value(0, output_field=models.DecimalField())
            )
        )
        
        higher_earners = qs.filter(total_earnings__gt=self_earnings).count()
        
        rank = higher_earners + 1
        return rank

    def get_rating_against_other_users(self, range_type: str = 'month'):
        from crm.utils import get_start_of_week, get_start_of_month
        now = timezone.now()

        if range_type == 'week':
            current_start = get_start_of_week()
            previous_start = current_start - timedelta(weeks=1)
            previous_start = previous_start.replace(hour=0, minute=0, second=0, microsecond=0)
            previous_end = current_start
        elif range_type == 'month':
            current_start = get_start_of_month()
            if current_start.month == 1:
                previous_start = current_start.replace(year=current_start.year - 1, month=12)
            else:
                previous_start = current_start.replace(month=current_start.month - 1)
            previous_end = current_start
        else:
            raise ValueError("Invalid range_type. Use 'week' or 'month'.")

        users_with_earnings = CustomUser.objects.filter(is_staff=False, service=self.service, is_active=True).exclude(first_name__in=['subscription', 'subscription_fn']).annotate(
            current_earnings=Coalesce(
                Sum(
                    'claims__transaction__net',
                    filter=Q(claims__transaction__of_created_at__gte=current_start)
                ),
                Value(0),
                output_field=models.FloatField()
            ),
            previous_earnings=Coalesce(
                Sum(
                    'claims__transaction__net',
                    filter=Q(
                        claims__transaction__of_created_at__gte=previous_start,
                        claims__transaction__of_created_at__lt=previous_end
                    )
                ),
                Value(0),
                output_field=models.FloatField()
            )
        )
        
        shifts_count = CustomUser.objects.filter(
            is_staff=False, 
            service=self.service, 
            is_active=True
        ).exclude(first_name__in=['subscription', 'subscription_fn']).annotate(
            current_shifts_count=Coalesce(
                Count(
                    'shifts',
                    filter=Q(shifts__started_at__gte=current_start),
                    distinct=True
                ),
                Value(0),
                output_field=models.IntegerField()
            ),
            previous_shifts_count=Coalesce(
                Count(
                    'shifts',
                    filter=Q(
                        shifts__started_at__gte=previous_start,
                        shifts__started_at__lt=previous_end
                    ),
                    distinct=True
                ),
                Value(0),
                output_field=models.IntegerField()
            )
        ).values('id', 'current_shifts_count', 'previous_shifts_count')
        
        shifts_count_map = {item['id']: {'current': item['current_shifts_count'], 'previous': item['previous_shifts_count']} for item in shifts_count}

        users_data = []
        for user in users_with_earnings:
            shifts_data = shifts_count_map.get(user.id, {'current': 0, 'previous': 0})
            current_shifts = shifts_data['current']
            previous_shifts = shifts_data['previous']
            
            current_average = user.current_earnings / current_shifts if current_shifts > 0 else 0
            previous_average = user.previous_earnings / previous_shifts if previous_shifts > 0 else 0
            
            users_data.append({
                'user': user,
                'current_shifts': current_shifts,
                'previous_shifts': previous_shifts,
                'current_average': current_average,
                'previous_average': previous_average
            })
        
        users_data_by_prev_avg = sorted(users_data, key=lambda x: x['previous_average'], reverse=True)
        previous_rank_map = {}
        for rank, user_data in enumerate(users_data_by_prev_avg, start=1):
            previous_rank_map[user_data['user'].id] = rank
        
        users_data_by_current_avg = sorted(users_data, key=lambda x: x['current_average'], reverse=True)
        
        table_rows = []
        for current_rank, user_data in enumerate(users_data_by_current_avg, start=1):
            user = user_data['user']
            prev_rank = previous_rank_map.get(user.id, len(users_data_by_prev_avg) + 1)
            difference = prev_rank - current_rank
            
            table_rows.append([
                current_rank, 
                user.first_name, 
                round(user.current_earnings), 
                round(user.previous_earnings), 
                prev_rank, 
                difference, 
                user_data['current_shifts'], 
                user_data['previous_shifts'],
                round(user_data['current_average'], 2),
                round(user_data['previous_average'], 2)
            ])

        return table_rows
    
    @property
    def bonus_points(self):
        task_points = self.bonus_task_claims.filter(is_approved=True).aggregate(total=Sum('points'))['total'] or 0
        reward_points = self.bonus_reward_claims.filter(is_approved=True).aggregate(total=Sum('points'))['total'] or 0
        return task_points - reward_points

    def __str__(self):
        return f"{self.username}"
    
    @classmethod
    def for_service(cls, service_name: str):
        return cls.objects.filter(service__name=service_name)


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

