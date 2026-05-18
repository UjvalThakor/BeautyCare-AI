from django.contrib import admin
from .models import Chat,Messages,Product

class MessageInline(admin.TabularInline):
    model = Messages
    extra = 0
    readonly_fields = ('id','role','content','created_at')
    fields = ('role','content','created_at')
    can_delete = False

@admin.register(Chat)
class ChatAdmin(admin.ModelAdmin):
    list_display = ('title','category','user','session_key','created_at','updated_at','is_active')
    list_filter = ('category','is_active','created_at')
    search_fields = ('title','user__username','session_key')
    readonly_fields = ('id','created_at','updated_at')
    inlines = [MessageInline]
    list_per_page = 30

    actions = ['soft_delete_session']

    def soft_delete_session(self,request,queryset):
        queryset.update(is_active=False)
        self.message_user(request,f"{queryset.count()} session deactivated.")
    soft_delete_session.short_description = "Soft delete selected session"

@admin.register(Messages)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('session','role','short_content','created_at')
    list_filter = ('role','created_at')
    search_fields = ('content','session_title')
    readonly_fields = ('id','created_at')

    def short_content(self,obj):
        return obj.content[:80]
    short_content.short_description = 'Content preview'

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name','brand','category','problem','price','in_stock')
    list_filter = ('category','problem','in_stock')
    search_fields = ('name','brand')
