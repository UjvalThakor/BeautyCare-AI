from django.contrib import admin
from django.utils.html import format_html
from .models import Chat, Messages, Product


class MessageInline(admin.TabularInline):
    model = Messages
    extra = 0
    readonly_fields = ('id', 'role', 'content', 'created_at')
    fields = ('role', 'content', 'created_at')
    can_delete = False


@admin.register(Chat)
class ChatAdmin(admin.ModelAdmin):
    list_display  = ('title', 'category', 'user', 'session_key', 'created_at', 'updated_at', 'is_active')
    list_filter   = ('category', 'is_active', 'created_at')
    search_fields = ('title', 'user__username', 'session_key')
    readonly_fields = ('id', 'created_at', 'updated_at')
    inlines       = [MessageInline]
    list_per_page = 30
    actions       = ['soft_delete_session']

    def soft_delete_session(self, request, queryset):
        queryset.update(is_active=False)
        self.message_user(request, f"{queryset.count()} session(s) deactivated.")
    soft_delete_session.short_description = "Soft delete selected sessions"


@admin.register(Messages)
class MessageAdmin(admin.ModelAdmin):
    list_display  = ('session', 'role', 'short_content', 'created_at')
    list_filter   = ('role', 'created_at')
    search_fields = ('content', 'session__title')
    readonly_fields = ('id', 'created_at')

    def short_content(self, obj):
        return obj.content[:80]
    short_content.short_description = 'Content preview'


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display  = ('name', 'brand', 'category', 'problem', 'price', 'rating', 'in_stock', 'image_preview')
    list_filter   = ('category', 'problem', 'in_stock')
    search_fields = ('name', 'brand')
    list_editable = ('in_stock', 'price', 'problem')
    list_per_page = 20

    fieldsets = (
        ('Basic Info', {
            'fields': ('name', 'brand', 'category', 'problem', 'in_stock'),
        }),
        ('Pricing & Rating', {
            'fields': ('price', 'rating'),
        }),
        ('Product Details', {
            'fields': ('description', 'how_to_use', 'key_benefits', 'avoid_if'),
        }),
        ('Image', {
            'fields': ('image',),
        }),
    )

    def image_preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" width="50" height="50" style="object-fit:cover;border-radius:4px;" />', obj.image.url)
        return 'No image'
    image_preview.short_description = 'Image'

    # Show correct problem code choices in the help text
    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.base_fields['problem'].help_text = (
            'prewash = PH Balancer Prewash Shampoo | '
            'silkbond = Silk Bond Treatment | '
            'shampoo = Argan Shampoo | '
            'hairmask = Argan Hair Mask | '
            'hairserum = Argan Oil Hair Serum'
        )
        return form