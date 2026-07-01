from django.contrib import admin
from .models import Provider, ProviderTest


@admin.register(Provider)
class ProviderAdmin(admin.ModelAdmin):
    list_display = ['name', 'provider_type', 'default_model', 'is_active', 'created_at']
    list_filter = ['provider_type', 'is_active']
    search_fields = ['name', 'default_model']
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ['created_at']


@admin.register(ProviderTest)
class ProviderTestAdmin(admin.ModelAdmin):
    list_display = ['provider', 'model_name', 'status', 'response_time', 'tested_at']
    list_filter = ['status', 'provider']
    readonly_fields = ['tested_at']
