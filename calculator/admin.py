from django.contrib import admin
from .models import UserBuild

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
