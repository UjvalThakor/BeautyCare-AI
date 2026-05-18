from django.db import models
from django.contrib.auth.models import User
import uuid


def generate_uuid():
    return str(uuid.uuid4())


class Chat(models.Model):
    CATEGORY_CHOICES = [
        ('skin', 'Skincare'),
        ('hair', 'Haircare'),
        ('makeup', 'Makeup'),
        ('wellness', 'Wellness'),
        ('general', 'General'),
    ]

    id = models.CharField(max_length=36, primary_key=True, default=generate_uuid, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='chat_sessions', null=True, blank=True)
    session_key = models.CharField(max_length=40, null=True, blank=True, db_index=True)
    title = models.CharField(max_length=200, default='New consultation')
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='general')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f"{self.title} ({self.created_at.strftime('%d %b %Y')})"


class Messages(models.Model):
    ROLE_CHOICES = [
        ('user', 'User'),
        ('assistant', 'Assistant'),
    ]

    session = models.ForeignKey(Chat, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    content = models.TextField()
    products_json = models.JSONField(
        default=list,
        blank=True,
        help_text='Product cards shown with this assistant message — saved for history replay.',
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"[{self.role}] {self.content[:60]}"

    def to_api_format(self):
        return {'role': self.role, 'content': self.content}


class Product(models.Model):
    CATEGORY_CHOICES = [
        ('skin', 'Skincare'),
        ('hair', 'Haircare'),
        ('makeup', 'Makeup'),
        ('wellness', 'Wellness'),
    ]
    PROBLEM_CHOICES = [
        ('hairfall', 'Hair Fall'),
        ('dandruff', 'Dandruff'),
        ('dryness', 'Dryness'),
        ('frizz', 'Frizz'),
        ('acne', 'Acne'),
        ('dark_circles', 'Dark Circles'),
        ('oily_skin', 'Oily Skin'),
        ('pigmentation', 'Pigmentation'),
        ('general', 'General'),
    ]

    name = models.CharField(max_length=200)
    brand = models.CharField(max_length=100)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    problem = models.CharField(max_length=30, choices=PROBLEM_CHOICES, default='general')
    image = models.ImageField(upload_to='products/', blank=True, null=True)
    price = models.CharField(max_length=50)
    rating = models.DecimalField(max_digits=3, decimal_places=1, default=4.5)
    description = models.TextField()
    how_to_use = models.TextField()
    key_benefits = models.TextField(help_text='One benefit per line', blank=True)
    avoid_if = models.CharField(max_length=200, blank=True)
    in_stock = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.brand} — {self.name}"