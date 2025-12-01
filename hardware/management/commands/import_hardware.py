import csv
import datetime
from django.core.management.base import BaseCommand
from django.apps import apps

MODEL_ALIASES = {
    "GPU": {
        "GpuName": "gpu_name",
        "Generation": "generation",
        "BaseClock": "base_clock",
        "BoostClock": "boost_clock",
        "Architecture": "architecture",
        "ProcessSize": "process_size",
        "ReleaseDate": "release_date",
        "BusInterface": "bus_interface",
        "MemoryClock": "memory_clock",
        "MemorySizeGB": "memory_size_gb",
        "MemoryType": "memory_type",
        "ShadingUnits": "shading_units",
        "TMUs": "tmus",
        "ROPs": "rops",
        "SMs": "sms",
        "TensorCores": "tensor_cores",
        "RTcores": "rt_cores",
        "L1CacheKB": "l1_cache_kb",
        "L2CacheMB": "l2_cache_mb",
        "TDP": "tdp",
        "BoardLength": "board_length",
        "BoardWidth": "board_width",
        "SlotWidth": "slot_width",
        "SuggestedPSU": "suggested_psu",
        "PowerConnectors": "power_connectors",
        "DisplayConnectors": "display_connectors",
    },
    "Case": {
        "type": "case_type",
        "color": "color",
        "psu": "psu",
        "side_panel": "side_panel",
        "external_volume": "external_volume",
        "internal_35_bays": "internal_35_bays",
        "slug": "slug",
    },
    "CPU": {
        # if your CSV headers differ, add aliases here
        "userbenchmark_score": "userbenchmark_score",
        "blender_score": "blender_score",
    },
    "PSU": {
        "type": "psu_type",   # <-- add this
        "slug": "slug",       # if your CSV has slug
        "wattage": "wattage", # add other PSU fields as needed
    },
    "Storage": {
        "type": "storage_type",
    }
}

NUMERIC_FIELDS = {
    # Common
    "price": float,

    # CPU
    "core_count": int,
    "core_clock": float,
    "boost_clock": float,
    "tdp": int,
    "thread_count": int,
    "userbenchmark_score": float,
    "blender_score": float,
    "power_consumption_overclocked": int,

    # GPU
    "userbenchmark_score": float,
    "blender_score": float,
    "base_clock": float,
    "boost_clock": float,
    "process_size": int,
    "memory_clock": float,
    "memory_size_gb": int,
    "shading_units": int,
    "tmus": int,
    "rops": int,
    "sms": int,
    "tensor_cores": int,
    "rt_cores": int,
    "l1_cache_kb": int,
    "l2_cache_mb": float,
    "tdp": int,
    "board_length": float,
    "board_width": float,
    "slot_width": float,

    # Motherboard
    "max_memory": int,
    "memory_slots": int,
    "ddr_max_speed": float,

    # RAM
    "modules": int,
    "first_word_latency": int,
    "cas_latency": int,
    "frequency_mhz": int,
    "capacity_gb": int,
    "benchmark": float,

    # Storage
    "capacity": int,
    "cache": int,

    # CPUCooler
    "rpm": int,
    "noise_level": float,
    "power_throughput": float,

    # Case
    "external_volume": float,
    "internal_35_bays": int,

    # ThermalPaste
    "amount": float,
}

DATE_FIELDS = {"release_date"}

LOOKUP_FIELDS = {
    "CPU": "model",
    "GPU": "slug",
    "RAM": "slug",
    "PSU": "slug",
    "Case": "slug",
    "CPUCooler": "slug",
    "Storage": "slug",
    "Motherboard": "slug",
    "ThermalPaste": "slug",
}


def normalize_value(field, value):
    if value in ("", None, "N/A"):
        return None

    if field in NUMERIC_FIELDS:
        caster = NUMERIC_FIELDS[field]
        try:
            return caster(float(value)) if caster is int else caster(value)
        except Exception:
            return None

    if field in DATE_FIELDS:
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
            try:
                return datetime.datetime.strptime(value, fmt).date()
            except ValueError:
                continue
        return None

    return value


class Command(BaseCommand):
    help = "Generic CSV importer for hardware models"

    def add_arguments(self, parser):
        parser.add_argument("--model", required=True, help="Model name (e.g. PSU, CPU, GPU, RAM)")
        parser.add_argument("--csv", required=True, help="Path to CSV file")
        parser.add_argument("--dry-run", action="store_true", help="Preview imports without saving")

    def handle(self, *args, **options):
        model_name = options["model"]
        csv_path = options["csv"]
        dry_run = options["dry_run"]

        try:
            Model = apps.get_model("hardware", model_name)
        except LookupError:
            self.stderr.write(self.style.ERROR(f"Model {model_name} not found"))
            return

        aliases = MODEL_ALIASES.get(model_name, {})
        valid_fields = {f.name for f in Model._meta.get_fields()}
        lookup_field = LOOKUP_FIELDS.get(model_name)

        count = 0
        created = 0
        updated = 0
        skipped = 0

        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                data = {}
                for k, v in row.items():
                    field = aliases.get(k, k).lower()
                    if field in valid_fields:
                        val = normalize_value(field, v)
                        if val is not None:   # <-- only include non-empty values
                            data[field] = val   
                if not data:
                    skipped += 1
                    continue

                if dry_run:
                    print(f"Would import: {data}")
                else:
                    lookup = {}
                    if lookup_field and lookup_field in data:
                        lookup[lookup_field] = data[lookup_field]
                    elif "slug" in data:
                        lookup = {"slug": data.get("slug")}
                    else:
                        skipped += 1
                        continue

                    obj, created_flag = Model.objects.update_or_create(defaults=data, **lookup)
                    if created_flag:
                        created += 1
                    else:
                        updated += 1
                count += 1

        if dry_run:
            self.stdout.write(self.style.WARNING(
                f"Dry run complete: {count} rows parsed for {model_name}, {skipped} skipped"
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"Imported {count} rows into {model_name}: {created} created, {updated} updated, {skipped} skipped"
            ))
