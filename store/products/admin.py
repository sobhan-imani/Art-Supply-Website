from django.contrib import admin

from core.admin import SoftDeleteAdmin

from .models import Category, Item


@admin.register(Category)
class CategoryAdmin(SoftDeleteAdmin):
    list_display = ("category_name", "sub_category", "withdrawn")
    list_filter = ("is_deleted",)
    search_fields = ("category_name",)
    ordering = ("is_deleted", "category_name")
    autocomplete_fields = ("sub_category",)

@admin.register(Item)
class ItemAdmin(SoftDeleteAdmin):
    list_display = ("name", "category", "final_price", "stock", "created_at", "withdrawn")
    list_filter = ("is_deleted", "category")
    search_fields = ("name",)
    ordering = ("-created_at", "name")
    autocomplete_fields = ("category",)