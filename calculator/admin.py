from django.contrib import admin
from .models import CurrencyRate, UserBuild

@admin.register(UserBuild)
class UserBuildAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "cpu",
        "gpu",
        "motherboard",
        "ram",
        "storage",
        "psu",
        "cooler",
        "case",
        "thermal_paste",
        "budget",
        "mode",
        "created_at",
    )
    list_filter = ("mode", "created_at")
    search_fields = ("user__username", "cpu__model", "gpu__model", "motherboard__name")

    # Optional: make the linked hardware clickable
    raw_id_fields = ("cpu", "gpu", "motherboard", "ram", "storage", "psu", "cooler", "case", "thermal_paste")

@admin.register(CurrencyRate)
class CurrencyRateAdmin(admin.ModelAdmin):
    list_display = (
        "currency",
        "rate_to_usd",
        "updated_at",
    )
    search_fields = (
        "currency",
        "rate_to_usd",
        "updated_at",
    )
    search_fields = ("currency",)
    ordering = ("currency",)
    readonly_fields = ("updated_at",)
    list_filter = ("updated_at",)