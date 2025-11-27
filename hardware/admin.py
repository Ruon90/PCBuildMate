import csv
from django.contrib import admin
from django.core.management import call_command
from .models import CPU, GPU, RAM, Storage, PSU, Motherboard, UserBuild


# --- Component Admins ---

@admin.register(CPU)
class CPUAdmin(admin.ModelAdmin):
    list_display = ("brand", "name", "socket", "benchmark", "power_consumption", "msrp", "live_min", "live_max")
    search_fields = ("brand", "name", "socket")
    list_filter = ("brand", "socket")

    actions = ["reset_prices", "bulk_import"]

    def reset_prices(self, request, queryset):
        for obj in queryset:
            obj.msrp = None
            obj.live_min = None
            obj.live_max = None
            obj.save()
        self.message_user(request, f"Reset prices for {queryset.count()} CPUs.")
    reset_prices.short_description = "Reset MSRP and live prices"

    def bulk_import(self, request, queryset):
        # Example: assumes enriched CSVs are named CPU_UserBenchmarks_enriched.csv
        call_command("import_hardware", file="data/CPU_UserBenchmarks_enriched.csv", category="CPU")
        self.message_user(request, "Bulk import from enriched CPU CSV completed.")
    bulk_import.short_description = "Import CPUs from enriched CSV"


@admin.register(GPU)
class GPUAdmin(admin.ModelAdmin):
    list_display = ("brand", "name", "benchmark", "power_consumption", "msrp", "live_min", "live_max")
    search_fields = ("brand", "name")
    list_filter = ("brand",)

    actions = ["mark_high_performance", "bulk_import"]

    def mark_high_performance(self, request, queryset):
        count = 0
        for obj in queryset:
            if obj.benchmark >= 100:
                obj.name = f"{obj.name} (High Perf)"
                obj.save()
                count += 1
        self.message_user(request, f"Marked {count} GPUs as High Performance.")
    mark_high_performance.short_description = "Tag GPUs with benchmark ≥ 100"

    def bulk_import(self, request, queryset):
        call_command("import_hardware", file="data/GPU_UserBenchmarks_enriched.csv", category="GPU")
        self.message_user(request, "Bulk import from enriched GPU CSV completed.")
    bulk_import.short_description = "Import GPUs from enriched CSV"


@admin.register(RAM)
class RAMAdmin(admin.ModelAdmin):
    list_display = ("brand", "name", "type", "benchmark", "power_consumption", "msrp", "live_min", "live_max")
    search_fields = ("brand", "name", "type")
    list_filter = ("brand", "type")

    actions = ["bulk_import"]

    def bulk_import(self, request, queryset):
        call_command("import_hardware", file="data/RAM_UserBenchmarks_enriched.csv", category="RAM")
        self.message_user(request, "Bulk import from enriched RAM CSV completed.")
    bulk_import.short_description = "Import RAM from enriched CSV"


@admin.register(Storage)
class StorageAdmin(admin.ModelAdmin):
    list_display = ("brand", "name", "interface", "benchmark", "power_consumption", "msrp", "live_min", "live_max")
    search_fields = ("brand", "name", "interface")
    list_filter = ("brand", "interface")

    actions = ["bulk_import"]

    def bulk_import(self, request, queryset):
        call_command("import_hardware", file="data/SSD_UserBenchmarks_enriched.csv", category="SSD")
        self.message_user(request, "Bulk import from enriched Storage CSV completed.")
    bulk_import.short_description = "Import Storage from enriched CSV"


@admin.register(PSU)
class PSUAdmin(admin.ModelAdmin):
    list_display = ("brand", "name", "wattage", "benchmark", "msrp", "live_min", "live_max")
    search_fields = ("brand", "name")
    list_filter = ("brand", "wattage")

    actions = ["bulk_import"]

    def bulk_import(self, request, queryset):
        call_command("import_hardware", file="data/PSU_UserBenchmarks_enriched.csv", category="PSU")
        self.message_user(request, "Bulk import from enriched PSU CSV completed.")
    bulk_import.short_description = "Import PSUs from enriched CSV"


@admin.register(Motherboard)
class MotherboardAdmin(admin.ModelAdmin):
    list_display = ("brand", "name", "socket", "ram_type", "benchmark", "msrp", "live_min", "live_max")
    search_fields = ("brand", "name", "socket", "ram_type")
    list_filter = ("brand", "socket", "ram_type")

    actions = ["bulk_import"]

    def bulk_import(self, request, queryset):
        call_command("import_hardware", file="data/Motherboard_UserBenchmarks_enriched.csv", category="Motherboard")
        self.message_user(request, "Bulk import from enriched Motherboard CSV completed.")
    bulk_import.short_description = "Import Motherboards from enriched CSV"


# --- UserBuild Admin ---

@admin.register(UserBuild)
class UserBuildAdmin(admin.ModelAdmin):
    list_display = ("user", "budget", "cpu", "gpu", "ram", "psu", "storage", "motherboard", "price_range_display")
    search_fields = ("user__username",)
    list_filter = ("budget",)

    actions = ["recalculate_totals"]

    def price_range_display(self, obj):
        min_total, max_total = obj.total_price_range()
        return f"${min_total} – ${max_total}"
    price_range_display.short_description = "Total Price Range"

    def recalculate_totals(self, request, queryset):
        for build in queryset:
            min_total, max_total = build.total_price_range()
            self.message_user(request, f"Build {build.id}: ${min_total} – ${max_total}")
    recalculate_totals.short_description = "Recalculate build price ranges"
