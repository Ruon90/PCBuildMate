from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.urls import reverse

from .forms import BudgetForm
from .models import CPU, GPU, Motherboard, RAM, Storage, PSU, CPUCooler, Case, UserBuild
from .services.build_calculator import find_best_build


def index(request):
    """Landing page with budget form."""
    form = BudgetForm()
    return render(request, "calculator/home.html", {"form": form})


def calculate_build(request):
    """Handle form submission, run build logic, return progress + redirect."""
    if request.method == "POST":
        form = BudgetForm(request.POST)
        if form.is_valid():
            budget = float(form.cleaned_data["budget"])
            mode = form.cleaned_data["build_type"]
            resolution = form.cleaned_data["resolution"]

            best, progress = find_best_build(
                budget=budget,
                mode=mode,
                resolution=resolution,
                cpus=CPU.objects.all(),
                gpus=GPU.objects.all(),
                mobos=Motherboard.objects.all(),
                rams=RAM.objects.all(),
                storages=Storage.objects.all(),
                psus=PSU.objects.all(),
                coolers=CPUCooler.objects.all(),
                cases=Case.objects.all(),
            )

            if best:
                # Store preview in session using primary keys
                request.session["preview_build"] = {
                    "cpu": best.cpu.pk,
                    "gpu": best.gpu.pk,
                    "motherboard": best.motherboard.pk,
                    "ram": best.ram.pk,
                    "storage": best.storage.pk,
                    "psu": best.psu.pk,
                    "cooler": best.cooler.pk,
                    "case": best.case.pk,
                    "budget": budget,
                    "mode": mode,
                    "score": float(best.total_score),
                    "price": float(best.total_price),
                }
                return JsonResponse({
                    "progress": progress,
                    "redirect": reverse("build_preview")
                })
            else:
                return JsonResponse({
                    "progress": progress,
                    "error": "No valid build found"
                })
    return JsonResponse({"error": "Invalid request"})


def build_preview(request):
    """Render the build preview page using session data."""
    build_data = request.session.get("preview_build")
    if not build_data:
        return render(request, "calculator/build_preview.html", {
            "error": "No build data found. Please calculate again."
        })

    cpu = get_object_or_404(CPU, pk=build_data["cpu"])
    gpu = get_object_or_404(GPU, pk=build_data["gpu"])
    mobo = get_object_or_404(Motherboard, pk=build_data["motherboard"])
    ram = get_object_or_404(RAM, pk=build_data["ram"])
    storage = get_object_or_404(Storage, pk=build_data["storage"])
    psu = get_object_or_404(PSU, pk=build_data["psu"])
    cooler = get_object_or_404(CPUCooler, pk=build_data["cooler"])
    case = get_object_or_404(Case, pk=build_data["case"])

    return render(request, "calculator/build_preview.html", {
        "cpu": cpu, "gpu": gpu, "motherboard": mobo, "ram": ram,
        "storage": storage, "psu": psu, "cooler": cooler, "case": case,
        "budget": build_data["budget"], "mode": build_data["mode"],
        "score": build_data["score"], "price": build_data["price"],
    })


@login_required
def save_build(request):
    """Save the current preview build to the logged-in user's account."""
    build_data = request.session.get("preview_build")
    if not build_data:
        return redirect("home")

    build = UserBuild.objects.create(
        user=request.user,
        cpu=get_object_or_404(CPU, pk=build_data["cpu"]),
        gpu=get_object_or_404(GPU, pk=build_data["gpu"]),
        motherboard=get_object_or_404(Motherboard, pk=build_data["motherboard"]),
        ram=get_object_or_404(RAM, pk=build_data["ram"]),
        storage=get_object_or_404(Storage, pk=build_data["storage"]),
        psu=get_object_or_404(PSU, pk=build_data["psu"]),
        cooler=get_object_or_404(CPUCooler, pk=build_data["cooler"]),
        case=get_object_or_404(Case, pk=build_data["case"]),
        budget=build_data["budget"],
        mode=build_data["mode"],
    )
    return redirect("saved_builds")


@login_required
def saved_builds(request):
    """List all builds saved by the current user."""
    builds = UserBuild.objects.filter(user=request.user)
    return render(request, "calculator/builds.html", {"builds": builds})
