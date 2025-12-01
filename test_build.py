import django
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "buildmate.settings")
django.setup()

from calculator.services.build_calculator import find_best_build
from calculator.models import CPU, GPU, Motherboard, RAM, Storage, PSU, CPUCooler, Case

best, progress = find_best_build(
    budget=10000,
    mode="gaming",
    resolution="1080p",
    cpus=CPU.objects.all(),
    gpus=GPU.objects.all(),
    mobos=Motherboard.objects.all(),
    rams=RAM.objects.all(),
    storages=Storage.objects.all(),
    psus=PSU.objects.all(),
    coolers=CPUCooler.objects.all(),
    cases=Case.objects.all(),
)

print("Progress:", progress)
print("Best build:", best)
