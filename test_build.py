import os

import django


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "buildmate.settings")
django.setup()


def main():
    from calculator.models import (
        CPU,
        GPU,
        PSU,
        RAM,
        Case,
        CPUCooler,
        Motherboard,
        Storage,
    )

    from calculator.services.build_calculator import find_best_build

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


if __name__ == "__main__":
    main()
