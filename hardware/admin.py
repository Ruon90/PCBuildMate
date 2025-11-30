from django.contrib import admin
from .models import PSU, CPU, GPU, Motherboard, RAM, Storage, CPUCooler, Case, ThermalPaste

@admin.register(PSU)
class PSUAdmin(admin.ModelAdmin):
    list_display = ("brand", "name", "psu_type", "efficiency", "wattage", "modular", "color", "price", "slug")
    list_filter = ("brand", "psu_type", "efficiency", "modular", "color")

@admin.register(CPU)
class CPUAdmin(admin.ModelAdmin):
    list_display = ("brand", "model", "socket", "name", "price", "core_count", "boost_clock", "tdp", "userbenchmark_score", "blender_score")
    list_filter = ("brand", "socket", "microarchitecture")

@admin.register(GPU)
class GPUAdmin(admin.ModelAdmin):
    list_display = ("brand", "model", "gpu_name", "generation", "architecture", "process_size", "price", "tdp", "slug")
    list_filter = ("brand", "generation", "architecture")

@admin.register(Motherboard)
class MotherboardAdmin(admin.ModelAdmin):
    list_display = ("name", "socket", "form_factor", "price", "max_memory", "memory_slots", "ddr_version", "ddr_max_speed", "nvme_support", "bios_update_required")
    list_filter = ("socket", "form_factor", "ddr_version", "nvme_support")

@admin.register(RAM)
class RAMAdmin(admin.ModelAdmin):
    list_display = ("name", "price", "modules", "capacity_gb", "ddr_generation", "frequency_mhz", "cas_latency", "first_word_latency", "benchmark", "slug")
    list_filter = ("ddr_generation", "frequency_mhz", "modules")

@admin.register(Storage)
class StorageAdmin(admin.ModelAdmin):
    list_display = ("brand", "model", "name", "price", "capacity", "storage_type", "form_factor", "interface", "slug")
    list_filter = ("brand", "storage_type", "form_factor", "interface")

@admin.register(CPUCooler)
class CPUCoolerAdmin(admin.ModelAdmin):
    list_display = ("name", "price", "rpm", "noise_level", "color", "size", "liquid", "power_throughput", "slug")
    list_filter = ("liquid", "color", "size")

@admin.register(Case)
class CaseAdmin(admin.ModelAdmin):
    list_display = ("name", "price", "case_type", "color", "psu", "side_panel", "external_volume", "internal_35_bays", "slug")
    list_filter = ("case_type", "color", "side_panel")

@admin.register(ThermalPaste)
class ThermalPasteAdmin(admin.ModelAdmin):
    list_display = ("name", "price", "amount")
