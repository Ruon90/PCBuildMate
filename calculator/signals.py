from django.dispatch import receiver
from allauth.account.signals import user_signed_up
from .models import UserBuild, CPU, GPU, Motherboard, RAM, Storage, PSU, CPUCooler, Case

@receiver(user_signed_up)
def migrate_session_build(sender, request, user, **kwargs):
    build_data = request.session.get("preview_build")
    if not build_data:
        return

    try:
        UserBuild.objects.create(
            user=user,
            cpu=CPU.objects.get(pk=build_data["cpu"]),
            gpu=GPU.objects.get(pk=build_data["gpu"]),
            motherboard=Motherboard.objects.get(pk=build_data["motherboard"]),
            ram=RAM.objects.get(pk=build_data["ram"]),
            storage=Storage.objects.get(pk=build_data["storage"]),
            psu=PSU.objects.get(pk=build_data["psu"]),
            cooler=CPUCooler.objects.get(pk=build_data["cooler"]),
            case=Case.objects.get(pk=build_data["case"]),
            budget=build_data.get("budget"),
            mode=build_data.get("mode"),
            score=build_data.get("score"),
            price=build_data.get("price"),
        )
        # Clear session so it doesn't re‑save
        request.session.pop("preview_build", None)
    except Exception as e:
        # Optional: log error
        print(f"Failed to migrate build: {e}")
