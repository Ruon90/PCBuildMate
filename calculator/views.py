from urllib import request
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from .forms import BudgetForm
from .models import CPU, GPU, Motherboard, RAM, Storage, PSU, CPUCooler, Case, UserBuild
from .services.build_calculator import find_best_build
from allauth.account.forms import SignupForm, LoginForm
from django.views.decorators.http import require_POST
from .services.build_calculator import (
    auto_assign_parts,
    compatible_cpu_mobo,
    compatible_mobo_ram,
    compatible_storage,
    compatible_case,
    psu_ok,
    cooler_ok,
    total_price,
    weighted_scores,
)
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
    """Render the build preview page using either session data (anonymous) or DB (logged-in)."""

    build_data = request.session.get("preview_build")

    # If logged in and no session build, try to load the latest UserBuild
    if not build_data and request.user.is_authenticated:
        latest_build = UserBuild.objects.filter(user=request.user).order_by("-id").first()
        if latest_build:
            build_data = {
                "cpu": latest_build.cpu.id,
                "gpu": latest_build.gpu.id,
                "motherboard": latest_build.motherboard.id,
                "ram": latest_build.ram.id,
                "storage": latest_build.storage.id,
                "psu": latest_build.psu.id,
                "cooler": latest_build.cooler.id,
                "case": latest_build.case.id,
                "budget": latest_build.total_price,  # or store separately
                "mode": getattr(latest_build, "mode", None),
                "score": latest_build.total_score,
                "price": latest_build.total_price,
            }

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

    signup_form = SignupForm()
    login_form = LoginForm()

    return render(request, "calculator/build_preview.html", {
        "cpu": cpu, "gpu": gpu, "motherboard": mobo, "ram": ram,
        "storage": storage, "psu": psu, "cooler": cooler, "case": case,
        "budget": build_data.get("budget"), "mode": build_data.get("mode"),
        "score": build_data.get("score"), "price": build_data.get("price"),
        "signup_form": signup_form,
        "login_form": login_form,
    })

@login_required
def save_build(request):
    """Save the current preview build to the logged-in user's account."""
    build_data = request.session.get("preview_build")
    if not build_data:
        return redirect("home")

    try:
        build = UserBuild.objects.create(
            user=request.user,
            cpu=get_object_or_404(CPU, pk=build_data.get("cpu")),
            gpu=get_object_or_404(GPU, pk=build_data.get("gpu")),
            motherboard=get_object_or_404(Motherboard, pk=build_data.get("motherboard")),
            ram=get_object_or_404(RAM, pk=build_data.get("ram")),
            storage=get_object_or_404(Storage, pk=build_data.get("storage")),
            psu=get_object_or_404(PSU, pk=build_data.get("psu")),
            cooler=get_object_or_404(CPUCooler, pk=build_data.get("cooler")),
            case=get_object_or_404(Case, pk=build_data.get("case")),
            budget=build_data.get("budget"),
            mode=build_data.get("mode"),
            total_score=build_data.get("total_score"),
            total_price=build_data.get("total_price"),
        )
    except KeyError:
        # If any key is missing, just redirect safely
        return redirect("home")

    # Clear the cached preview build once saved
    request.session.pop("preview_build", None)

    return redirect("saved_builds")


@login_required
def saved_builds(request):
    """List all builds saved by the current user."""
    builds = UserBuild.objects.filter(user=request.user)
    return render(request, "calculator/builds.html", {"builds": builds})


@require_POST
def clear_build(request):
    """Clear the cached preview build and return to homepage."""
    request.session.pop("preview_build", None)
    return redirect("home")

@login_required
def delete_build(request, pk):
    build = get_object_or_404(UserBuild, pk=pk, user=request.user)
    build.delete()
    return redirect("saved_builds")

# --- Edit build ---
# calculator/views.py
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from .models import UserBuild
from hardware.models import CPU, GPU, Motherboard, RAM, Storage, PSU, CPUCooler, Case
from .services.build_calculator import (
    compatible_cpu_mobo,
    compatible_mobo_ram,
    compatible_storage,
    compatible_case,
    psu_ok,
    cooler_ok,
    total_price,
    weighted_scores,
)

@login_required
def edit_build(request, pk):
    build = get_object_or_404(UserBuild, pk=pk, user=request.user)

    if request.method == "POST":
        mode = request.POST.get("mode", "basic")

        if mode == "basic":
            # --- Basic mode: budget-based reassignment ---
            budget = float(request.POST.get("budget") or 0)
            build.budget = budget
            parts = auto_assign_parts(budget, mode="gaming", resolution="1440p")
            if parts:
                build.cpu = parts["cpu"]
                build.gpu = parts["gpu"]
                build.motherboard = parts["mobo"]
                build.ram = parts["ram"]
                build.storage = parts["storage"]
                build.psu = parts["psu"]
                build.cooler = parts["cooler"]
                build.case = parts["case"]
                build.total_price = parts["total_price"]
                build.total_score = parts["total_score"]
            else:
                messages.error(request, "No valid build found within budget.")
                return redirect("edit_build", pk=build.pk)

        else:  # --- Advanced mode: manual dropdowns ---
            build.cpu_id = request.POST.get("cpu")
            build.gpu_id = request.POST.get("gpu")
            build.motherboard_id = request.POST.get("motherboard")
            build.ram_id = request.POST.get("ram")
            build.storage_id = request.POST.get("storage")
            build.psu_id = request.POST.get("psu")
            build.cooler_id = request.POST.get("cooler")
            build.case_id = request.POST.get("case")

            # Compatibility checks
            if build.cpu and build.motherboard and not compatible_cpu_mobo(build.cpu, build.motherboard):
                messages.error(request, "Selected CPU and motherboard are not compatible.")
                return redirect("edit_build", pk=build.pk)

            if build.motherboard and build.ram and not compatible_mobo_ram(build.motherboard, build.ram):
                messages.error(request, "Selected RAM is not compatible with motherboard.")
                return redirect("edit_build", pk=build.pk)

            if build.motherboard and build.storage and not compatible_storage(build.motherboard, build.storage):
                messages.error(request, "Selected storage is not compatible with motherboard.")
                return redirect("edit_build", pk=build.pk)

            if build.motherboard and build.case and not compatible_case(build.motherboard, build.case):
                messages.error(request, "Selected case is not compatible with motherboard.")
                return redirect("edit_build", pk=build.pk)

            if build.psu and build.cpu and build.gpu and not psu_ok(build.psu, build.cpu, build.gpu):
                messages.error(request, "PSU wattage is insufficient for CPU + GPU.")
                return redirect("edit_build", pk=build.pk)

            if build.cooler and build.cpu and not cooler_ok(build.cooler, build.cpu):
                messages.error(request, "Cooler throughput is insufficient for CPU.")
                return redirect("edit_build", pk=build.pk)

            # Recalculate totals
            parts = [build.cpu, build.gpu, build.motherboard, build.ram,
                     build.storage, build.psu, build.cooler, build.case]
            build.total_price = total_price(parts)
            build.total_score = weighted_scores(build.cpu, build.gpu, build.ram, build.mode, "1440p")

        # Save changes
        build.save()
        messages.success(request, "Build updated successfully.")
        return redirect("saved_builds")

    # GET: render form
    context = {
        "build": build,
        "cpus": CPU.objects.all(),
        "gpus": GPU.objects.all(),
        "mobos": Motherboard.objects.all(),
        "rams": RAM.objects.all(),
        "cases": Case.objects.all(),
        "psus": PSU.objects.all(),
        "coolers": CPUCooler.objects.all(),
        "storages": Storage.objects.all(),
    }
    return render(request, "calculator/edit_build.html", context)