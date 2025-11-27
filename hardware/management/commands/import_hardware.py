import csv
from django.core.management.base import BaseCommand
from hardware.models import CPU, GPU, RAM, PSU, Storage, Motherboard

class Command(BaseCommand):
    help = "Import enriched hardware CSVs into the database"

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True, help="Path to enriched CSV file")
        parser.add_argument("--category", required=True,
                            choices=["CPU", "GPU", "RAM", "SSD", "PSU", "Motherboard"],
                            help="Hardware category to import")

    def handle(self, *args, **options):
        file_path = options["file"]
        category = options["category"]

        model_map = {
            "CPU": CPU,
            "GPU": GPU,
            "RAM": RAM,
            "SSD": Storage,
            "PSU": PSU,
            "Motherboard": Motherboard,
        }

        model = model_map[category]

        self.stdout.write(self.style.NOTICE(f"Importing {category} from {file_path}..."))

        with open(file_path, newline="", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)
            count = 0
            for row in reader:
                if not row.get("Benchmark") or float(row["Benchmark"]) < 50:
                    continue

                obj, created = model.objects.update_or_create(
                    brand=row.get("Brand"),
                    name=row.get("Model"),
                    defaults={
                        "benchmark": float(row.get("Benchmark", 0)),
                        "power_consumption": int(row.get("PowerConsumption", 0)) if row.get("PowerConsumption") else None,
                        "msrp": row.get("MSRP") or None,
                        "live_min": row.get("LiveMin") or None,
                        "live_max": row.get("LiveMax") or None,
                        "image_url": row.get("ImageURL") or None,
                        "socket": row.get("Socket") if category in ["CPU", "Motherboard"] else None,
                    }
                )
                count += 1

        self.stdout.write(self.style.SUCCESS(f"Imported {count} {category} records."))
