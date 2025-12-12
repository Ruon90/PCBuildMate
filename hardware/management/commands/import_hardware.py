import csv
import datetime
import re

from django.apps import apps
from django.core.management.base import BaseCommand
from django.utils.text import slugify

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
        "brand": "brand",
        "model": "model",
        "userbenchmark_url": "userbenchmark_url",
        "Price": "price",
        "price": "price",
        "Slug": "slug",
        "slug": "slug",
        "userbenchmark_score": "userbenchmark_score",
        "blender_score": "blender_score",
    },
    # other models omitted for brevity...
}

NUMERIC_FIELDS = {
    "price": float,
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
    "suggested_psu": int,
}

DATE_FIELDS = {"release_date"}

LOOKUP_FIELDS = {
    "GPU": "slug",
    "CPU": "slug",
    "RAM": "slug",
    "PSU": "slug",
    "Case": "slug",
    "CPUCooler": "slug",
    "Storage": "slug",
    "Motherboard": "slug",
    "ThermalPaste": "slug",
}


def clean_number(value: str) -> str:
    if value is None:
        return ""
    s = str(value).strip().replace(",", "")
    m = re.search(r"[-+]?\d*\.?\d+", s)
    return m.group(0) if m else ""


def cast_number(field: str, value: str):
    if value in ("", None):
        return None
    raw = clean_number(value)
    if raw == "":
        return None
    caster = NUMERIC_FIELDS[field]
    try:
        return caster(float(raw)) if caster is int else caster(raw)
    except Exception:
        return None


def normalize_value(field, value):
    if value in ("", None, "N/A"):
        return None
    if field in NUMERIC_FIELDS:
        return cast_number(field, value)
    if field in DATE_FIELDS:
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%b %Y", "%B %Y"):
            try:
                return datetime.datetime.strptime(value, fmt).date()
            except ValueError:
                continue
        return None
    return value


def ensure_slug(model_name: str, data: dict) -> None:
    if "slug" in data and data["slug"]:
        return
    if model_name == "GPU":
        base = data.get("gpu_name")
        if base:
            data["slug"] = slugify(base)
            return
    base = data.get("name") or data.get("model")
    if base:
        data["slug"] = slugify(base)


def has_price(data: dict) -> bool:
    price = data.get("price")
    try:
        return price is not None and float(price) > 0
    except Exception:
        return False


class Command(BaseCommand):
    help = "Generic CSV importer for hardware models"

    def add_arguments(self, parser):
        parser.add_argument("--model", required=True)
        parser.add_argument("--csv", required=True)
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--require-price", action="store_true")

    def handle(self, *args, **options):
        model_name = options["model"]
        csv_path = options["csv"]
        dry_run = options["dry_run"]
        require_price = options["require_price"]

        try:
            Model = apps.get_model("hardware", model_name)
        except LookupError:
            self.stderr.write(
                self.style.ERROR(f"Model {model_name} not found")
            )
            return

        aliases = MODEL_ALIASES.get(model_name, {})
        valid_fields = {f.name for f in Model._meta.get_fields()}
        lookup_field = LOOKUP_FIELDS.get(model_name)

        count = created = updated = skipped = 0

        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row_idx, row in enumerate(reader, start=1):
                data = {}
                for k, v in row.items():
                    field = aliases.get(k, k).lower()
                    if field in valid_fields:
                        val = normalize_value(field, v)
                        if val is not None:
                            data[field] = val

                ensure_slug(model_name, data)

                if require_price and not has_price(data):
                    skipped += 1
                    self.stdout.write(
                        f"Row {row_idx} skipped: missing/zero price"
                    )
                    continue

                if not data:
                    skipped += 1
                    self.stdout.write(
                        f"Row {row_idx} skipped: no valid fields"
                    )
                    continue

                lookup = {}
                if lookup_field and lookup_field in data:
                    lookup[lookup_field] = data[lookup_field]
                elif "slug" in data and data["slug"]:
                    lookup = {"slug": data["slug"]}
                else:
                    skipped += 1
                    self.stdout.write(
                        f"Row {row_idx} skipped: missing lookup field"
                    )
                    continue

                if dry_run:
                    self.stdout.write(
                        f"[DRY-RUN] Row {row_idx} normalized: {data}"
                    )
                else:
                    obj, created_flag = Model.objects.update_or_create(
                        defaults=data, **lookup
                    )
                    if created_flag:
                        created += 1
                    else:
                        updated += 1
                count += 1

        summary = (
            "Processed {} rows for {}: {} created, {} updated, {} skipped"
            .format(count, model_name, created, updated, skipped)
        )
        if dry_run:
            self.stdout.write(self.style.WARNING("[DRY-RUN] " + summary))
        else:
            self.stdout.write(self.style.SUCCESS(summary))
