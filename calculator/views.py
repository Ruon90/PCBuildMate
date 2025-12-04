import os
import json
import requests
from urllib import request
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from .forms import BudgetForm
from .models import CPU, GPU, Motherboard, RAM, Storage, PSU, CPUCooler, Case, UserBuild, CurrencyRate
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
from django.views.decorators.csrf import csrf_exempt
def index(request):
    """Landing page with budget form."""
    form = BudgetForm()
    return render(request, "calculator/home.html", {"form": form})


def calculate_build(request):
    """Handle form submission, run build logic, return progress + redirect."""
    if request.method == "POST":
        form = BudgetForm(request.POST)
        if form.is_valid():
            # Read user-entered budget and currency (site data/prices are USD)
            budget = float(form.cleaned_data["budget"])
            currency = form.cleaned_data.get("currency") or "USD"
            mode = form.cleaned_data["build_type"]
            resolution = form.cleaned_data["resolution"]
            # Convert submitted budget into USD (site/catalog prices are USD)
            # CurrencyRate.rate_to_usd is stored as 1 unit of currency -> X USD.
            try:
                sel_rate = CurrencyRate.objects.filter(currency=currency).first()
                if sel_rate:
                    budget_usd = budget * float(sel_rate.rate_to_usd)
                else:
                    # assume the user entered USD
                    budget_usd = budget
            except Exception:
                budget_usd = budget

            best, progress = find_best_build(
                budget=budget_usd,
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
                    # keep the original user-entered budget + currency
                    "budget": budget,
                    "currency": currency,
                    # and the converted budget used for calculation (in USD)
                    "budget_usd": float(budget_usd),
                    "mode": mode,
                    "score": float(best.total_score),
                    # prices from models are in USD
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
                # keep the user's entered budget (in their currency)
                "budget": latest_build.budget,
                "currency": getattr(latest_build, "currency", "USD"),
                "mode": getattr(latest_build, "mode", None),
                "score": latest_build.total_score,
                # total_price is stored in USD (catalog prices are USD)
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

    # expose currency for the template (default USD)
    currency = build_data.get("currency", "USD")
    currency_symbol = None

    return render(request, "calculator/build_preview.html", {
        "cpu": cpu, "gpu": gpu, "motherboard": mobo, "ram": ram,
        "storage": storage, "psu": psu, "cooler": cooler, "case": case,
        "budget": build_data.get("budget"), "mode": build_data.get("mode"),
        "score": build_data.get("score"), "price": build_data.get("price"),
        "signup_form": signup_form,
        "login_form": login_form,
        "is_saved_preview": False,
        "currency": currency,
        "currency_symbol": currency_symbol,
    })


def build_preview_pk(request, pk):
    """Render a preview for a specific UserBuild (by pk) without using session cache."""
    build_obj = get_object_or_404(UserBuild, pk=pk)
    # only allow the owner to preview their saved build
    if not request.user.is_authenticated or build_obj.user != request.user:
        # don't reveal existence to other users
        return get_object_or_404(UserBuild, pk=0)

    try:
        cpu = get_object_or_404(CPU, pk=build_obj.cpu.id)
        gpu = get_object_or_404(GPU, pk=build_obj.gpu.id)
        mobo = get_object_or_404(Motherboard, pk=build_obj.motherboard.id)
        ram = get_object_or_404(RAM, pk=build_obj.ram.id)
        storage = get_object_or_404(Storage, pk=build_obj.storage.id)
        psu = get_object_or_404(PSU, pk=build_obj.psu.id)
        cooler = get_object_or_404(CPUCooler, pk=build_obj.cooler.id)
        case = get_object_or_404(Case, pk=build_obj.case.id)

    except Exception:
        # If related parts were deleted or inconsistent, show a friendly error
        return render(request, "calculator/build_preview.html", {
            "error": "Saved build is missing one or more components. Please edit or delete this build.",
        })

    signup_form = SignupForm()
    login_form = LoginForm()

    # For saved builds, use the stored currency on the model if present (default USD)
    currency = getattr(build_obj, "currency", "USD")
    currency_symbol = None

    return render(request, "calculator/edit_build_preview.html", {
        "cpu": cpu, "gpu": gpu, "motherboard": mobo, "ram": ram,
        "storage": storage, "psu": psu, "cooler": cooler, "case": case,
        "budget": build_obj.budget, "mode": getattr(build_obj, "mode", None),
        "score": build_obj.total_score, "price": build_obj.total_price,
        "signup_form": signup_form, "login_form": login_form,
        "is_saved_preview": True,
        "currency": currency,
        "currency_symbol": currency_symbol,
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
            # persist user's chosen currency (fallback USD)
            currency=build_data.get("currency", "USD"),
            total_score=build_data.get("score"),
            # price stored in session is USD total from the calculator
            total_price=build_data.get("price"),
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
from django.contrib import messages


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

## Tokens and endpoints
GITHUB_TOKEN_MINI = os.getenv("GITHUB_TOKEN_MINI") or os.getenv("GITHUB_TOKEN")
GITHUB_TOKEN_FULL = os.getenv("GITHUB_TOKEN_FULL") or os.getenv("GITHUB_TOKEN")

ENDPOINTS = {
    "gpt-4.1-mini": "https://models.inference.ai.azure.com/openai/deployments/gpt-4.1-mini/chat/completions",
    "gpt-4.1": "https://models.inference.ai.azure.com/openai/deployments/gpt-4.1/chat/completions"
}

def select_token(model: str) -> str:
    return GITHUB_TOKEN_MINI if model == "gpt-4.1-mini" else GITHUB_TOKEN_FULL


# -----------------------------
# Canned responses
# -----------------------------
CANNED_RESPONSES = {
    "ram not compatible": "RAM DDR generation must match the motherboard DDR generation. DDR4 will not fit DDR5 slots.",
    "cpu not compatible": "Check socket type: CPUs must match the motherboard socket (e.g., AM5 vs LGA1700).",
    "gpu bottleneck": "Ensure your CPU and GPU are balanced. A weak CPU can bottleneck a powerful GPU.",
    "psu wattage": "Your PSU must provide enough wattage for all components. Add ~20% headroom for stability.",
    "cooler clearance": "Large air coolers may not fit in small cases. Always check case clearance specs.",
    "case size": "Ensure your case supports your motherboard form factor (ATX, Micro‑ATX, Mini‑ITX).",
}

def check_canned(message: str) -> str | None:
    msg_lower = message.lower()
    for key, reply in CANNED_RESPONSES.items():
        if key in msg_lower:
            return reply
    return None

# -----------------------------
# AI call
# -----------------------------
def call_ai(message: str, model: str, debug=False, max_chars=600) -> str:
    """Call AI model and return a concise reply."""
    token = select_token(model)
    endpoint = ENDPOINTS[model]

    # Prompt enforces numbered list formatting
    prompt = (
        f"Answer the user question as a short, readable numbered list of steps. "
        f"Keep the response under {max_chars} characters.\n\n"
        f"User question: {message}"
    )

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2
    }

    try:
        resp = requests.post(endpoint, headers=headers, json=payload, timeout=(10, 90))
        if debug:
            print(f"[AI] {model} -> Status {resp.status_code}")
            print(f"[AI] Raw: {resp.text[:300]}")
        if resp.status_code != 200:
            return None
        data = resp.json()
        if "choices" not in data or not data["choices"]:
            return None

        choice = data["choices"][0]
        reply = None

        # ✅ Correct field based on your raw JSON
        if "message" in choice and "content" in choice["message"]:
            reply = choice["message"]["content"]
        elif "text" in choice:
            reply = choice["text"]

        if reply:
            if len(reply) > max_chars:
                reply = reply[:max_chars] + "..."
            return reply.strip()

        return None
    except Exception as e:
        if debug:
            print(f"[AI] Error ({model}): {e}")
        return None



# -----------------------------
# Main chat view
# -----------------------------
@csrf_exempt
def ai_chat(request):
    if request.method == "POST":
        data = json.loads(request.body)
        user_message = data.get("message")

        # --- Check canned responses first ---
        canned = check_canned(user_message)
        if canned:
            ai_text = canned
        else:
            # --- Try GPT-4.1 first, fallback to GPT-4.1-mini ---
            ai_text = call_ai(user_message, "gpt-4.1") or call_ai(user_message, "gpt-4.1-mini")
            if not ai_text:
                ai_text = "Sorry, I couldn’t generate a response."

        # --- YouTube API call ---
        yt_url = "https://www.googleapis.com/youtube/v3/search"
        yt_params = {
            "part": "snippet",
            "q": user_message,
            "type": "video",
            "maxResults": 3,
            "key": os.environ.get("YOUTUBE_API_KEY"),
        }
        yt_response = requests.get(yt_url, params=yt_params)
        yt_data = yt_response.json()
        videos = []
        for item in yt_data.get("items", []):
            videos.append({
                "title": item["snippet"]["title"],
                "url": f"https://www.youtube.com/watch?v={item['id']['videoId']}"
            })

        return JsonResponse({"reply": ai_text, "videos": videos})