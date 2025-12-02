from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from .forms import BudgetForm
from .models import CPU, GPU, Motherboard, RAM, Storage, PSU, CPUCooler, Case, UserBuild
from .services.build_calculator import find_best_build
from allauth.account.forms import SignupForm, LoginForm
from django.views.decorators.http import require_POST

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

@login_required
def edit_build(request, pk):
    build = get_object_or_404(UserBuild, pk=pk, user=request.user)

    if request.method == "POST":
        # Update build with selected parts
        build.cpu_id = request.POST.get("cpu")
        build.gpu_id = request.POST.get("gpu")
        build.motherboard_id = request.POST.get("motherboard")
        build.ram_id = request.POST.get("ram")
        build.storage_id = request.POST.get("storage")
        build.psu_id = request.POST.get("psu")
        build.cooler_id = request.POST.get("cooler")
        build.case_id = request.POST.get("case")
        build.save()
        return redirect("saved_builds")

    # GET: show form with compatible parts
    cpus, gpus, rams, cases, storages, mobos, psus, coolers = prefilter_components(
        CPU.objects.all(), GPU.objects.all(), RAM.objects.all(),
        Case.objects.all(), Storage.objects.all(), Motherboard.objects.all(),
        PSU.objects.all(), CPUCooler.objects.all(),
        build.budget, build.mode
    )

    compatible_mobos = [m for m in mobos if compatible_cpu_mobo(build.cpu, m) and compatible_mobo_ram(m, build.ram)]
    compatible_rams = [r for r in rams if compatible_mobo_ram(build.motherboard, r)]
    compatible_cases = [c for c in cases if compatible_case(build.motherboard, c)]
    compatible_psus = [p for p in psus if psu_ok(p, build.cpu, build.gpu)]
    compatible_coolers = [c for c in coolers if cooler_ok(c, build.cpu)]
    compatible_storages = [s for s in storages if compatible_storage(build.motherboard, s)]

    context = {
        "build": build,
        "cpus": cpus,
        "gpus": gpus,
        "mobos": compatible_mobos,
        "rams": compatible_rams,
        "cases": compatible_cases,
        "psus": compatible_psus,
        "coolers": compatible_coolers,
        "storages": compatible_storages,
    }
    return render(request, "calculator/edit_build.html", context)