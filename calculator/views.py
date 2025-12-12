import json
import os
import traceback
from types import SimpleNamespace

import requests
from allauth.account.forms import LoginForm, SignupForm
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Max
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .forms import BudgetForm
from .models import (
    CPU,
    GPU,
    PSU,
    RAM,
    Case,
    CPUCooler,
    CurrencyRate,
    Motherboard,
    Storage,
    UserBuild,
)
from .services.build_calculator import (
    auto_assign_parts,
    compatible_case,
    compatible_cpu_mobo,
    compatible_mobo_ram,
    compatible_mobo_ram_cached,
    compatible_storage,
    cooler_ok,
    cpu_bottleneck,
    cpu_score,
    estimate_fps_components,
    estimate_render_time,
    find_best_build,
    gpu_score,
    psu_ok,
    psu_ok_cached,
    ram_score,
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
            # Read user-entered budget and currency (site data/prices are USD)
            budget = float(form.cleaned_data["budget"])
            currency = form.cleaned_data.get("currency") or "USD"
            # Optional preferences
            cpu_brand_pref = form.cleaned_data.get("cpu_brand") or ""
            gpu_brand_pref = form.cleaned_data.get("gpu_brand") or ""
            ram_size_pref = form.cleaned_data.get("ram_size") or ""
            storage_capacity_pref = (
                form.cleaned_data.get("storage_capacity") or ""
            )
            mode = form.cleaned_data["build_type"]
            resolution = form.cleaned_data["resolution"]
            # Convert submitted budget into USD (site/catalog prices are USD).
            # CurrencyRate.rate_to_usd maps 1 unit -> X USD.
            try:
                sel_rate = CurrencyRate.objects.filter(
                    currency=currency
                ).first()
                if sel_rate:
                    budget_usd = budget * float(sel_rate.rate_to_usd)
                else:
                    # assume the user entered USD
                    budget_usd = budget
            except Exception:
                budget_usd = budget

            # Apply preference filters before running the heavy build logic.
            cpus_qs = CPU.objects.all()
            gpus_qs = GPU.objects.all()
            rams_qs = RAM.objects.all()
            storages_qs = Storage.objects.all()

            if cpu_brand_pref:
                cpus_qs = cpus_qs.filter(brand__iexact=cpu_brand_pref)
            if gpu_brand_pref:
                gpus_qs = gpus_qs.filter(brand__iexact=gpu_brand_pref)
            if ram_size_pref:
                try:
                    cap = int(ram_size_pref)
                    rams_qs = rams_qs.filter(capacity_gb__gte=cap)
                except ValueError:
                    pass
            if storage_capacity_pref:
                try:
                    cap = int(storage_capacity_pref)
                    storages_qs = storages_qs.filter(capacity__gte=cap)
                except ValueError:
                    pass

            try:
                best, progress = find_best_build(
                    budget=budget_usd,
                    mode=mode,
                    resolution=resolution,
                    cpus=cpus_qs,
                    gpus=gpus_qs,
                    mobos=Motherboard.objects.all(),
                    rams=rams_qs,
                    storages=storages_qs,
                    psus=PSU.objects.all(),
                    coolers=CPUCooler.objects.all(),
                    cases=Case.objects.all(),
                )
            except Exception:
                # Log traceback to console for debugging and return a JSON
                # error for the AJAX caller.
                tb = traceback.format_exc()
                print("[ERROR] Exception in find_best_build:\n", tb)
                return JsonResponse(
                    {
                        "error": (
                            "Internal error while calculating build. "
                            "See server logs."
                        )
                    },
                    status=500,
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
                    # persist the resolution the user selected for the
                    # calculation
                    "resolution": resolution,
                    # and the converted budget used for calculation (in USD)
                    "budget_usd": float(budget_usd),
                    "mode": mode,
                    "score": float(best.total_score),
                    # prices from models are in USD
                    "price": float(best.total_price),
                }
                # Persist top alternatives (2..11) in session so the user
                # can view or choose them later.
                try:
                    from .services import build_calculator as bc

                    candidates = getattr(bc, "LAST_CANDIDATES", []) or []

                    # build a tuple key for the chosen build so we can skip it
                    chosen_key = (
                        best.cpu.id,
                        best.gpu.id,
                        best.motherboard.id,
                        best.ram.id,
                        best.storage.id,
                        best.psu.id,
                        best.cooler.id,
                        best.case.id,
                    )

                    alts = []
                    for cand in candidates:
                        cand_key = (
                            cand.cpu.id,
                            cand.gpu.id,
                            cand.motherboard.id,
                            cand.ram.id,
                            cand.storage.id,
                            cand.psu.id,
                            cand.cooler.id,
                            cand.case.id,
                        )
                        if cand_key == chosen_key:
                            continue

                        # extract per-game FPS for the resolution the user
                        # selected
                        fps_summary = {}
                        try:
                            for g in ("Cyberpunk 2077", "CS2", "Fortnite"):
                                entry = cand.fps_estimates.get(g, {})
                                res_entry = (
                                    entry.get(resolution, {})
                                    if isinstance(entry, dict)
                                    else {}
                                )
                                fps_summary[g] = {
                                    "overall": res_entry.get("estimated_fps")
                                    or res_entry.get("estimated", None),
                                    "cpu": res_entry.get("cpu_fps"),
                                    "gpu": res_entry.get("gpu_fps"),
                                }
                        except Exception:
                            fps_summary = {}

                        alts.append(
                            {
                                "cpu": cand.cpu.id,
                                "gpu": cand.gpu.id,
                                "motherboard": cand.motherboard.id,
                                "ram": cand.ram.id,
                                "storage": cand.storage.id,
                                "psu": cand.psu.id,
                                "cooler": cand.cooler.id,
                                "case": cand.case.id,
                                "price": float(cand.total_price),
                                "score": float(cand.total_score),
                                "bottleneck_type": getattr(
                                    cand, "bottleneck_type", None
                                ),
                                "bottleneck_pct": getattr(
                                    cand, "bottleneck_pct", None
                                ),
                                "fps": fps_summary,
                            }
                        )

                        if len(alts) >= 10:
                            break

                    request.session["preview_alternatives"] = alts
                except Exception:
                    # do not fail the API if alternatives collection fails
                    request.session["preview_alternatives"] = []
                return JsonResponse(
                    {
                        "progress": progress,
                        "redirect": reverse("build_preview"),
                    }
                )
            else:
                return JsonResponse(
                    {"progress": progress, "error": "No valid build found"}
                )
    return JsonResponse({"error": "Invalid request"})


def build_preview(request):
    """Render the build preview page.

    Uses either session data (anonymous) or DB (logged-in).
    """

    build_data = request.session.get("preview_build")

    # If logged in and no session build, try to load the latest UserBuild
    if not build_data and request.user.is_authenticated:
        latest_build = (
            UserBuild.objects.filter(user=request.user).order_by("-id").first()
        )
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
        return render(
            request,
            "calculator/build_preview.html",
            {"error": "No build data found. Please calculate again."},
        )

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

    # Compute per-resolution FPS estimates and bottleneck readout
    # for the preview build.
    mode = build_data.get("mode", "gaming") or "gaming"
    # If the user previously chose a resolution, use it as the
    # default active tab
    default_resolution = build_data.get("resolution", "1440p") or "1440p"
    games = ["Cyberpunk 2077", "CS2", "Fortnite"]

    perf = {}
    resolutions = ["1080p", "1440p", "4k"]
    for res in resolutions:
        # For gaming builds compute per-game FPS contributions.
        if mode == "workstation":
            # Workstation estimates are render times (seconds). Resolution is
            # not typically relevant for workstation render time but we keep
            # the per-resolution structure for UI consistency.
            try:
                render_sec = estimate_render_time(cpu, gpu, mode)
            except Exception:
                render_sec = None
            try:
                binfo = cpu_bottleneck(cpu, gpu, mode, res)
            except Exception:
                binfo = {"bottleneck": 0.0, "type": "unknown"}
            perf[res] = {
                "bottleneck": binfo,
                "workstation": {"Blender BMW Render (seconds)": render_sec},
            }
            continue

        res_games = {}
        for g in games:
            try:
                cpu_fps, gpu_fps = estimate_fps_components(
                    cpu, gpu, mode, res, g
                )
                overall = round(min(cpu_fps, gpu_fps), 1)
                res_games[g] = {
                    "overall": overall,
                    "cpu": cpu_fps,
                    "gpu": gpu_fps,
                }
            except Exception:
                res_games[g] = {"overall": None, "cpu": None, "gpu": None}

        try:
            binfo = cpu_bottleneck(cpu, gpu, mode, res)
        except Exception:
            binfo = {"bottleneck": 0.0, "type": "unknown"}

        perf[res] = {"bottleneck": binfo, "games": res_games}

    # Fallback: if perf dictionary ended up empty for any reason, synthesize
    # a minimal structure for the default resolution so the UI has content.
    if not perf:
        try:
            res = (
                default_resolution
                if default_resolution in resolutions
                else "1440p"
            )
            if mode == "workstation":
                try:
                    render_sec = estimate_render_time(cpu, gpu, mode)
                except Exception:
                    render_sec = None
                try:
                    binfo = cpu_bottleneck(cpu, gpu, mode, res)
                except Exception:
                    binfo = {"bottleneck": 0.0, "type": "unknown"}
                perf[res] = {
                    "bottleneck": binfo,
                    "workstation": {
                        "Blender BMW Render (seconds)": render_sec
                    },
                }
            else:
                res_games = {}
                for g in games:
                    try:
                        cpu_fps, gpu_fps = estimate_fps_components(
                            cpu, gpu, mode, res, g
                        )
                        overall = round(min(cpu_fps, gpu_fps), 1)
                        res_games[g] = {
                            "overall": overall,
                            "cpu": cpu_fps,
                            "gpu": gpu_fps,
                        }
                    except Exception:
                        res_games[g] = {
                            "overall": None,
                            "cpu": None,
                            "gpu": None,
                        }
                try:
                    binfo = cpu_bottleneck(cpu, gpu, mode, res)
                except Exception:
                    binfo = {"bottleneck": 0.0, "type": "unknown"}
                perf[res] = {"bottleneck": binfo, "games": res_games}
        except Exception:
            pass

    # Keep top-level keys for backward compatibility with
    # templates expecting them
    fps_estimates = perf.get(default_resolution, {}).get("games", {})
    bottleneck_info = perf.get(default_resolution, {}).get(
        "bottleneck", {"bottleneck": 0.0, "type": "unknown"}
    )

    # Build an ordered list of per-resolution entries, like upgrade
    # preview uses. Initialize lists early to avoid UnboundLocalError
    # in template context
    fps_res_list = []
    for res in resolutions:
        entry = perf.get(res, {})
        fps_res_list.append(
            {
                "res": res,
                "games": entry.get("games", {}),
                "bottleneck": entry.get(
                    "bottleneck", {"bottleneck": 0.0, "type": "unknown"}
                ),
                "workstation": entry.get("workstation", {}),
            }
        )

    # Compute simple component "performance" scores per user request
    # Gaming: CPU/GPU use UserBenchmark; Workstation: CPU/GPU use Blender.
    # RAM uses its unified 'benchmark' field.
    def safe_float(v):
        try:
            return float(v or 0)
        except Exception:
            return 0.0

    cpu_field = (
        "blender_score" if mode == "workstation" else "userbenchmark_score"
    )
    gpu_field = (
        "blender_score" if mode == "workstation" else "userbenchmark_score"
    )
    # RAM model uses a single 'benchmark' field universally
    ram_field = "benchmark"

    cpu_val = safe_float(getattr(cpu, cpu_field, 0))
    gpu_val = safe_float(getattr(gpu, gpu_field, 0))
    ram_val = safe_float(getattr(ram, ram_field, 0))

    cpu_top = safe_float(CPU.objects.aggregate(m=Max(cpu_field)).get("m"))
    gpu_top = safe_float(GPU.objects.aggregate(m=Max(gpu_field)).get("m"))
    ram_top = safe_float(RAM.objects.aggregate(m=Max(ram_field)).get("m"))

    def perf(top, val):
        # Scale: current / top * 100 (percentage)
        try:
            if top and val:
                return round((val / top) * 100.0, 1)
        except Exception:
            pass
        return None

    cpu_perf = perf(cpu_top, cpu_val)
    gpu_perf = perf(gpu_top, gpu_val)
    ram_perf = perf(ram_top, ram_val)

    # Total performance as percentage of the sum of category maxima (0–100)
    try:
        total_top = (cpu_top or 0) + (gpu_top or 0) + (ram_top or 0)
        total_val = (cpu_val or 0) + (gpu_val or 0) + (ram_val or 0)
        if total_top:
            total_perf_pct = round((total_val / total_top) * 100.0, 1)
        else:
            total_perf_pct = None
    except Exception:
        total_perf_pct = None

    # Provide a direct workstation render-time value for templates
    # that want a simple display
    workstation_render_time = None
    if mode == "workstation":
        try:
            workstation_render_time = estimate_render_time(cpu, gpu, mode)
        except Exception:
            workstation_render_time = None

    return render(
        request,
        "calculator/build_preview.html",
        {
            "cpu": cpu,
            "gpu": gpu,
            "motherboard": mobo,
            "ram": ram,
            "storage": storage,
            "psu": psu,
            "cooler": cooler,
            "case": case,
            # Always expose budget/currency; include session fallbacks to
            # guarantee availability
            "budget": build_data.get("budget"),
            "preview_budget": request.session.get("preview_build", {}).get(
                "budget"
            ),
            "mode": build_data.get("mode"),
            "score": build_data.get("score"),
            "price": build_data.get("price"),
            "signup_form": signup_form,
            "login_form": login_form,
            "is_saved_preview": False,
            "currency": currency,
            "preview_currency": request.session.get("preview_build", {}).get(
                "currency", "USD"
            ),
            "currency_symbol": currency_symbol,
            "perf_map": perf,
            "perf": perf,  # backward-compat for templates that still
            # reference 'perf'
            "default_resolution": default_resolution,
            "fps_estimates": fps_estimates,
            "bottleneck": bottleneck_info,
            "fps_res_list": fps_res_list,
            "workstation_render_time": workstation_render_time,
            "cpu_perf": cpu_perf,
            "gpu_perf": gpu_perf,
            "ram_perf": ram_perf,
            "total_perf_pct": total_perf_pct,
        },
    )


def alternatives(request):
    """Show the top alternative builds (stored in session by the calculator).

    GET: render alternatives page showing up to 10 alternatives.
    """
    alts = request.session.get("preview_alternatives", []) or []
    if not alts:
        messages.info(
            request,
            "No alternative builds are available. Calculate a build first.",
        )
        return redirect("build_preview")

    rendered = []
    for idx, a in enumerate(alts):
        try:
            rendered.append(
                {
                    "index": idx,
                    "cpu": get_object_or_404(CPU, pk=a["cpu"]),
                    "gpu": get_object_or_404(GPU, pk=a["gpu"]),
                    "motherboard": get_object_or_404(
                        Motherboard, pk=a["motherboard"]
                    ),
                    "ram": get_object_or_404(RAM, pk=a["ram"]),
                    "storage": get_object_or_404(Storage, pk=a["storage"]),
                    "psu": get_object_or_404(PSU, pk=a["psu"]),
                    "cooler": get_object_or_404(CPUCooler, pk=a["cooler"]),
                    "case": get_object_or_404(Case, pk=a["case"]),
                    "price": a.get("price"),
                    "score": a.get("score"),
                    "bottleneck_type": a.get("bottleneck_type"),
                    "bottleneck_pct": a.get("bottleneck_pct"),
                    "fps": a.get("fps", {}),
                }
            )
        except Exception:
            # skip alternatives that reference missing components
            continue

    return render(
        request, "calculator/alternatives.html", {"alternatives": rendered}
    )


def upgrade_preview(request):
    """Show a focused preview page for a selected upgrade proposal.

    Expects a query parameter 'index' pointing to the proposal stored in
    `request.session['last_upgrade_proposals']` (the serializer created by
    the upgrade calculator). The view shows only components that will change
    as part of the upgrade, displays the estimated FPS or render-time, and
    offers a Save button that marks the saved record as an upgrade.
    """
    try:
        idx = int(request.GET.get("index", 0))
    except Exception:
        idx = 0

    proposals = request.session.get("last_upgrade_proposals", []) or []
    if not proposals or idx < 0 or idx >= len(proposals):
        messages.error(
            request,
            "No upgrade proposal found. Run the upgrade calculator first.",
        )
        return redirect("upgrade_calculator")

    sel = proposals[idx]

    # Determine the authoritative base to compare against. Prefer the exact
    # base that was used to generate the upgrade proposals (stored in
    # `last_upgrade_base`) so upgrade previews are deterministic and do not
    # get mixed with unrelated session preview builds. If that is missing,
    # fall back to the session preview_build or the user's latest saved build.
    base_ids = request.session.get("last_upgrade_base")
    if not base_ids:
        # No explicit upgrade base recorded; try session preview
        # or latest saved
        build_data = request.session.get("preview_build")
        if not build_data and request.user.is_authenticated:
            latest_build = (
                UserBuild.objects.filter(user=request.user)
                .order_by("-id")
                .first()
            )
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
                    "mode": getattr(latest_build, "mode", "gaming"),
                    "resolution": (
                        getattr(latest_build, "resolution", "1440p")
                        if hasattr(latest_build, "resolution")
                        else "1440p"
                    ),
                }

        if not build_data:
            messages.error(
                request,
                (
                    "No base build available to compare against. "
                    "Calculate a preview build first."
                ),
            )
            return redirect("build_preview")

        base_ids = build_data or {}

    # Load objects for the base build so we can compute FPS
    # fallbacks where needed
    try:
        cur_cpu = (
            get_object_or_404(CPU, pk=base_ids.get("cpu"))
            if base_ids.get("cpu")
            else None
        )
        cur_gpu = (
            get_object_or_404(GPU, pk=base_ids.get("gpu"))
            if base_ids.get("gpu")
            else None
        )
        cur_mobo = (
            get_object_or_404(Motherboard, pk=base_ids.get("motherboard"))
            if base_ids.get("motherboard")
            else None
        )
        cur_ram = (
            get_object_or_404(RAM, pk=base_ids.get("ram"))
            if base_ids.get("ram")
            else None
        )
        cur_storage = (
            get_object_or_404(Storage, pk=base_ids.get("storage"))
            if base_ids.get("storage")
            else None
        )
        cur_psu = (
            get_object_or_404(PSU, pk=base_ids.get("psu"))
            if base_ids.get("psu")
            else None
        )
        cur_cooler = (
            get_object_or_404(CPUCooler, pk=base_ids.get("cooler"))
            if base_ids.get("cooler")
            else None
        )
        cur_case = (
            get_object_or_404(Case, pk=base_ids.get("case"))
            if base_ids.get("case")
            else None
        )
    except Exception:
        messages.error(
            request,
            "One or more components from the base build could not be loaded.",
        )
        return redirect("build_preview")

    # Load proposal target parts (some may be None)
    def safe_load(key, Model):
        try:
            pk = sel.get(key)
            if not pk:
                return None
            return get_object_or_404(Model, pk=pk)
        except Exception:
            return None

    new_cpu = safe_load("cpu", CPU)
    new_gpu = safe_load("gpu", GPU)
    new_mobo = safe_load("motherboard", Motherboard)
    new_ram = safe_load("ram", RAM)
    new_storage = safe_load("storage", Storage)
    new_psu = safe_load("psu", PSU)
    new_cooler = safe_load("cooler", CPUCooler)
    new_case = safe_load("case", Case)

    # Build display mappings for current and estimated builds
    def disp(obj):
        try:
            if obj is None:
                return "<None>"
            return (
                getattr(obj, "name", None)
                or getattr(obj, "gpu_name", None)
                or getattr(obj, "model", None)
                or str(obj)
            )
        except Exception:
            return str(obj)

    current_build = {
        "cpu": cur_cpu,
        "gpu": cur_gpu,
        "motherboard": cur_mobo,
        "ram": cur_ram,
        "storage": cur_storage,
        "psu": cur_psu,
        "cooler": cur_cooler,
        "case": cur_case,
        "display": {
            "cpu": disp(cur_cpu),
            "gpu": disp(cur_gpu),
            "motherboard": disp(cur_mobo),
            "ram": disp(cur_ram),
            "storage": disp(cur_storage),
            "psu": disp(cur_psu),
            "cooler": disp(cur_cooler),
            "case": disp(cur_case),
        },
    }
    estimated_build = {
        "cpu": new_cpu or cur_cpu,
        "gpu": new_gpu or cur_gpu,
        "motherboard": new_mobo or cur_mobo,
        "ram": new_ram or cur_ram,
        "storage": new_storage or cur_storage,
        "psu": new_psu or cur_psu,
        "cooler": new_cooler or cur_cooler,
        "case": new_case or cur_case,
        "display": {
            "cpu": disp(new_cpu or cur_cpu),
            "gpu": disp(new_gpu or cur_gpu),
            "motherboard": disp(new_mobo or cur_mobo),
            "ram": disp(new_ram or cur_ram),
            "storage": disp(new_storage or cur_storage),
            "psu": disp(new_psu or cur_psu),
            "cooler": disp(new_cooler or cur_cooler),
            "case": disp(new_case or cur_case),
        },
    }

    # Determine which items changed (compare serialized ids to the base ids)
    # We'll store a mapping key ->
    # {'obj': <Model instance>, 'percent': <float or None>}
    changed = {}

    def id_eq(a, b):
        if a is None and b is None:
            return True
        try:
            return str(a) == str(b)
        except Exception:
            return False

    # For each component, if the proposal provides a different id
    # than the base, include it
    for key, Model in (
        ("cpu", CPU),
        ("gpu", GPU),
        ("motherboard", Motherboard),
        ("ram", RAM),
        ("storage", Storage),
        ("psu", PSU),
        ("cooler", CPUCooler),
        ("case", Case),
    ):
        prop_id = sel.get(key)
        base_id = base_ids.get(key)
        if prop_id and not id_eq(prop_id, base_id):
            # load the proposed object for display
            try:
                changed[key] = {
                    "obj": get_object_or_404(Model, pk=prop_id),
                    "percent": None,
                }
            except Exception:
                # skip missing objects but continue
                continue

    # Compute FPS or workstation estimate for the proposal
    # (recreate the estimate logic)
    # Use the mode/resolution from the authoritative base_ids (which came from
    # last_upgrade_base or preview_build fallback)
    mode = base_ids.get("mode", "gaming") or "gaming"
    default_resolution = base_ids.get("resolution", "1440p") or "1440p"

    # Compute per-resolution FPS estimates (for UI resolution toggles) or
    # workstation render-time estimates. We build a list of resolutions where
    # each entry contains per-game FPS and bottleneck info so the template can
    # switch client-side without additional server calls.
    fps_res_list = []
    fps_res_list_current = []
    fps_compare_list = (
        []
    )  # ensure defined for all modes to avoid UnboundLocalError
    workstation_estimate = None
    workstation_estimate_current = None
    workstation_delta = None
    try:
        if mode == "workstation":
            # Workstation: render-time estimate only (no FPS or
            # resolution toggles)
            render_sec = estimate_render_time(
                new_cpu or cur_cpu, new_gpu or cur_gpu, mode
            )
            workstation_estimate = render_sec
            # Also compute current/base render time for comparison
            workstation_estimate_current = estimate_render_time(
                cur_cpu, cur_gpu, mode
            )
            try:
                workstation_delta = (
                    (workstation_estimate_current or 0) - (render_sec or 0)
                )
            except Exception:
                workstation_delta = None
            # Optional bottleneck info if needed elsewhere; avoid building
            # FPS lists. Keep fps_res_list empty in workstation mode to
            # simplify template rendering
        else:
            games = ["Cyberpunk 2077", "CS2", "Fortnite"]
            resolutions = ["1080p", "1440p", "4k"]
            for res in resolutions:
                games_map = {}
                for g in games:
                    try:
                        cpu_fps, gpu_fps = estimate_fps_components(
                            new_cpu or cur_cpu,
                            new_gpu or cur_gpu,
                            mode,
                            res,
                            g,
                        )
                        est = (
                            round(min(cpu_fps, gpu_fps), 1)
                            if cpu_fps is not None and gpu_fps is not None
                            else None
                        )
                        games_map[g] = {
                            "overall": est,
                            "cpu": cpu_fps,
                            "gpu": gpu_fps,
                        }
                    except Exception:
                        games_map[g] = {
                            "overall": None,
                            "cpu": None,
                            "gpu": None,
                        }
                try:
                    binfo = cpu_bottleneck(
                        new_cpu or cur_cpu, new_gpu or cur_gpu, mode, res
                    )
                except Exception:
                    binfo = {"bottleneck": 0.0, "type": "unknown"}
                fps_res_list.append(
                    {"res": res, "games": games_map, "bottleneck": binfo}
                )

            # Build current (base) FPS list for direct comparison
            for res in resolutions:
                cur_games_map = {}
                for g in games:
                    try:
                        c_cpu_fps, c_gpu_fps = estimate_fps_components(
                            cur_cpu, cur_gpu, mode, res, g
                        )
                        c_est = (
                            round(min(c_cpu_fps, c_gpu_fps), 1)
                            if c_cpu_fps is not None and c_gpu_fps is not None
                            else None
                        )
                        cur_games_map[g] = {
                            "overall": c_est,
                            "cpu": c_cpu_fps,
                            "gpu": c_gpu_fps,
                        }
                    except Exception:
                        cur_games_map[g] = {
                            "overall": None,
                            "cpu": None,
                            "gpu": None,
                        }
                try:
                    c_binfo = cpu_bottleneck(cur_cpu, cur_gpu, mode, res)
                except Exception:
                    c_binfo = {"bottleneck": 0.0, "type": "unknown"}
                fps_res_list_current.append(
                    {"res": res, "games": cur_games_map, "bottleneck": c_binfo}
                )

            # Build comparison list: pair current vs estimated with
            # deltas per game
            try:
                for res in resolutions:
                    cur_entry = next(
                        (
                            e
                            for e in fps_res_list_current
                            if e.get("res") == res
                        ),
                        None,
                    )
                    new_entry = next(
                        (e for e in fps_res_list if e.get("res") == res), None
                    )
                    comp_games = {}
                    for g in games:
                        cur_vals = (
                            (cur_entry or {}).get("games", {}).get(g, {})
                        )
                        new_vals = (
                            (new_entry or {}).get("games", {}).get(g, {})
                        )
                        cur_ovr = cur_vals.get("overall")
                        new_ovr = new_vals.get("overall")
                        delta = None
                        try:
                            if cur_ovr is not None and new_ovr is not None:
                                delta = round(new_ovr - cur_ovr, 1)
                        except Exception:
                            delta = None
                        comp_games[g] = {
                            "current": cur_ovr,
                            "estimated": new_ovr,
                            "delta": delta,
                        }
                    fps_compare_list.append(
                        {
                            "res": res,
                            "games": comp_games,
                            "bottleneck_current": (cur_entry or {}).get(
                                "bottleneck",
                                {"bottleneck": 0.0, "type": "unknown"},
                            ),
                            "bottleneck_estimated": (new_entry or {}).get(
                                "bottleneck",
                                {"bottleneck": 0.0, "type": "unknown"},
                            ),
                        }
                    )
            except Exception:
                fps_compare_list = []
    except Exception:
        fps_res_list = []

    # Robust fallback: if compare list didn't populate but we have
    # per-res lists, rebuild it outside the try/except to avoid a
    # blank UI.
    try:
        if (
            mode != "workstation"
            and (not fps_compare_list)
            and fps_res_list
            and fps_res_list_current
        ):
            # derive the set of resolutions available in both lists
            res_new = {e.get("res") for e in fps_res_list if e.get("res")}
            res_cur = {
                e.get("res") for e in fps_res_list_current if e.get("res")
            }
            common = [
                r
                for r in ["1080p", "1440p", "4k"]
                if r in res_new and r in res_cur
            ]
            games = ["Cyberpunk 2077", "CS2", "Fortnite"]
            fps_compare_list = []
            for res in common:
                cur_entry = next(
                    (e for e in fps_res_list_current if e.get("res") == res),
                    {},
                )
                new_entry = next(
                    (e for e in fps_res_list if e.get("res") == res), {}
                )
                comp_games = {}
                # union of game keys in case one side is missing a title
                gkeys = set((cur_entry.get("games") or {}).keys()) | set(
                    (new_entry.get("games") or {}).keys()
                )
                if not gkeys:
                    gkeys = set(games)
                for g in gkeys:
                    c = (cur_entry.get("games") or {}).get(g, {})
                    n = (new_entry.get("games") or {}).get(g, {})
                    c_ovr = c.get("overall")
                    n_ovr = n.get("overall")
                    d = None
                    try:
                        if c_ovr is not None and n_ovr is not None:
                            d = round((n_ovr - c_ovr), 1)
                    except Exception:
                        d = None
                    comp_games[g] = {
                        "current": c_ovr,
                        "estimated": n_ovr,
                        "delta": d,
                    }
                fps_compare_list.append(
                    {
                        "res": res,
                        "games": comp_games,
                        "bottleneck_current": cur_entry.get(
                            "bottleneck",
                            {"bottleneck": 0.0, "type": "unknown"},
                        ),
                        "bottleneck_estimated": new_entry.get(
                            "bottleneck",
                            {"bottleneck": 0.0, "type": "unknown"},
                        ),
                    }
                )
            # ensure default_resolution points to an available res for display
            if default_resolution not in [
                e.get("res") for e in fps_compare_list
            ]:
                try:
                    default_resolution = common[0]
                except Exception:
                    pass
    except Exception:
        # keep calm and render whatever we have
        pass

    # Backwards-compatible per-resolution default for templates that expect a
    # single-resolution mapping called `fps_estimates` (games -> stats).
    try:
        fps_estimates = {}
        for entry in fps_res_list:
            if entry.get("res") == default_resolution:
                fps_estimates = entry.get("games", {})
                break
    except Exception:
        fps_estimates = {}

    # Price delta and percent are already stored in the serial;
    # use them when available
    price_delta = sel.get("price_delta") or 0.0
    percent = sel.get("percent") or 0.0

    # Compute per-component improvement percentages for CPU, GPU and RAM
    cpu_percent = 0.0
    gpu_percent = 0.0
    ram_percent = 0.0
    try:
        try:
            cur_cpu_score = cpu_score(cur_cpu, mode) if cur_cpu else 0.0
        except Exception:
            cur_cpu_score = 0.0
        try:
            new_cpu_score = cpu_score(new_cpu, mode) if new_cpu else 0.0
        except Exception:
            new_cpu_score = 0.0
        if cur_cpu_score and cur_cpu_score > 0:
            cpu_percent = (
                (new_cpu_score - cur_cpu_score) / cur_cpu_score
            ) * 100.0
        else:
            cpu_percent = 0.0
        cpu_performance = new_cpu_score or 0.0
    except Exception:
        cpu_percent = 0.0
        cpu_performance = 0.0

    try:
        try:
            cur_gpu_score = gpu_score(cur_gpu, mode) if cur_gpu else 0.0
        except Exception:
            cur_gpu_score = 0.0
        try:
            new_gpu_score = gpu_score(new_gpu, mode) if new_gpu else 0.0
        except Exception:
            new_gpu_score = 0.0
        if cur_gpu_score and cur_gpu_score > 0:
            gpu_percent = (
                (new_gpu_score - cur_gpu_score) / cur_gpu_score
            ) * 100.0
        else:
            gpu_percent = 0.0
        gpu_performance = new_gpu_score or 0.0
    except Exception:
        gpu_percent = 0.0
        gpu_performance = 0.0

    try:
        try:
            cur_ram_score = ram_score(cur_ram) if cur_ram else 0.0
        except Exception:
            cur_ram_score = 0.0
        try:
            new_ram_score = ram_score(new_ram) if new_ram else 0.0
        except Exception:
            new_ram_score = 0.0
        if cur_ram_score and cur_ram_score > 0:
            ram_percent = (
                (new_ram_score - cur_ram_score) / cur_ram_score
            ) * 100.0
        else:
            ram_percent = 0.0
        ram_performance = new_ram_score or 0.0
    except Exception:
        ram_percent = 0.0
        ram_performance = 0.0

    # Attach per-component percents into changed mapping where relevant
    for k in list(changed.keys()):
        entry = changed.get(k)
        if not entry:
            continue
        if k == "cpu":
            entry["percent"] = cpu_percent
            entry["performance"] = cpu_performance
        elif k == "gpu":
            entry["percent"] = gpu_percent
            entry["performance"] = gpu_performance
        elif k == "ram":
            entry["percent"] = ram_percent
            entry["performance"] = ram_performance
        else:
            entry["percent"] = None
        changed[k] = entry

    # Determine currency for display: prefer preview session currency.
    # Otherwise use any currency recorded on the base_ids (rare) or
    # default to USD.
    currency = (
        request.session.get("preview_build", {}).get("currency")
        or base_ids.get("currency")
        or "USD"
    )

    # Compute normalized performance percentages for CPU/GPU/RAM
    # like build preview
    from django.db.models import Max

    def safe_float(v):
        try:
            return float(v or 0)
        except Exception:
            return 0.0

    cpu_field = (
        "blender_score" if mode == "workstation" else "userbenchmark_score"
    )
    gpu_field = (
        "blender_score" if mode == "workstation" else "userbenchmark_score"
    )
    ram_field = "benchmark"
    cpu_top = safe_float(CPU.objects.aggregate(m=Max(cpu_field)).get("m"))
    gpu_top = safe_float(GPU.objects.aggregate(m=Max(gpu_field)).get("m"))
    ram_top = safe_float(RAM.objects.aggregate(m=Max(ram_field)).get("m"))
    cpu_val = (
        safe_float(getattr(estimated_build.get("cpu"), cpu_field, 0))
        if estimated_build.get("cpu")
        else 0.0
    )
    gpu_val = (
        safe_float(getattr(estimated_build.get("gpu"), gpu_field, 0))
        if estimated_build.get("gpu")
        else 0.0
    )
    ram_val = (
        safe_float(getattr(estimated_build.get("ram"), ram_field, 0))
        if estimated_build.get("ram")
        else 0.0
    )

    def perf_pct(top, val):
        try:
            if top and val:
                return round((val / top) * 100.0, 1)
        except Exception:
            pass
        return None

    cpu_perf = perf_pct(cpu_top, cpu_val)
    gpu_perf = perf_pct(gpu_top, gpu_val)
    ram_perf = perf_pct(ram_top, ram_val)

    # FPS estimates were built above for both current and estimated builds.
    # Avoid recomputing here to prevent empty lists due to undefined vars
    # and keep template behavior consistent.

    # Determine if this preview was initiated from a saved upgrade view
    came_from_saved_upgrade = bool(
        request.session.pop("from_saved_upgrade", False)
    )

    return render(
        request,
        "calculator/upgrade_preview.html",
        {
            "changed_items": changed,
            "percent": percent,
            "cpu_percent": cpu_percent,
            "gpu_percent": gpu_percent,
            "ram_percent": ram_percent,
            "cpu_performance": cpu_performance,
            "gpu_performance": gpu_performance,
            "ram_performance": ram_performance,
            "cpu_perf": cpu_perf,
            "gpu_perf": gpu_perf,
            "ram_perf": ram_perf,
            "price_delta": price_delta,
            "fps_estimates": fps_estimates,
            "fps_res_list": fps_res_list,
            "fps_res_list_current": fps_res_list_current,
            "workstation_estimate": workstation_estimate,
            "workstation_estimate_current": workstation_estimate_current,
            "workstation_delta": workstation_delta,
            "mode": mode,
            "default_resolution": default_resolution,
            "fps_compare_list": fps_compare_list,
            "currency": currency,
            "came_from_saved_upgrade": came_from_saved_upgrade,
            # Include budget for save form.
            # Prefer preview session budget, else base_ids budget,
            # else any recorded last_upgrade_base.
            "budget": (
                (request.session.get("preview_build", {}) or {}).get("budget")
                or base_ids.get("budget")
                or (
                    (request.session.get("last_upgrade_base", {}) or {}).get(
                        "budget"
                    )
                )
            ),
            "proposal_index": idx,
            "current_build": current_build,
            "estimated_build": estimated_build,
        },
    )


@require_POST
def select_alternative(request):
    """Replace the session preview with the selected alternative (by index).

    POST params: alt_index (int)
    """
    try:
        idx = int(request.POST.get("alt_index", -1))
    except Exception:
        idx = -1
    alts = request.session.get("preview_alternatives", []) or []
    if idx < 0 or idx >= len(alts):
        messages.error(request, "Invalid alternative selected.")
        return redirect("alternatives")

    sel = alts[idx]
    # Preserve budget/currency/mode/resolution if present
    # in existing preview.
    prev = request.session.get("preview_build", {})
    preview = {
        "cpu": sel["cpu"],
        "gpu": sel["gpu"],
        "motherboard": sel["motherboard"],
        "ram": sel["ram"],
        "storage": sel["storage"],
        "psu": sel["psu"],
        "cooler": sel["cooler"],
        "case": sel["case"],
        "price": sel.get("price"),
        "score": sel.get("score"),
        "budget": prev.get("budget"),
        "currency": prev.get("currency", "USD"),
        "mode": prev.get("mode", "gaming"),
        "resolution": prev.get("resolution", "1440p"),
        "budget_usd": prev.get("budget_usd"),
    }
    request.session["preview_build"] = preview
    messages.success(request, "Preview replaced with selected alternative.")
    return redirect("build_preview")


def upgrade_calculator(request):
    """Upgrade calculator: given a preview or saved build and a budget, find
    incremental upgrades that improve component benchmarks while remaining
    compatible and within the provided budget.

    This implements a greedy single-pass selection: it scores candidate
    upgrades by (score_delta / price_delta) and picks the best ones until
    budget is exhausted. It prefers to keep the original case and attempts
    to maintain compatibility for motherboard when possible.
    """

    # This upgrade calculator takes a user-specified build.
    # All components must be selected.
    # Provide component querysets for dropdowns on GET.
    # Validate submitted IDs on POST.
    cpus_qs = CPU.objects.all()
    gpus_qs = GPU.objects.all()
    mobos_qs = Motherboard.objects.all()
    rams_qs = RAM.objects.all()
    storages_qs = Storage.objects.all()
    psus_qs = PSU.objects.all()
    coolers_qs = CPUCooler.objects.all()
    cases_qs = Case.objects.all()

    # default mode (can be overridden by a form field)
    mode = "gaming"
    # default resolution used for UI toggles (taken from preview if present)
    default_resolution = (
        request.session.get("preview_build", {}).get("resolution") or "1440p"
    )

    if request.method == "POST":
        # If user clicked "Use this build" for a proposed upgrade, apply it.
        if request.POST.get("proposed_index") is not None:
            try:
                idx = int(request.POST.get("proposed_index"))
                proposals = (
                    request.session.get("last_upgrade_proposals", []) or []
                )
                if idx < 0 or idx >= len(proposals):
                    messages.error(request, "Invalid proposed build selected.")
                    return redirect("upgrade_calculator")
                sel = proposals[idx]
                # Build preview structure from proposal.
                # Preserve user's budget/currency/mode/resolution.
                prev = request.session.get("preview_build", {})
                preview = {
                    "cpu": sel.get("cpu"),
                    "gpu": sel.get("gpu"),
                    "motherboard": sel.get("motherboard"),
                    "ram": sel.get("ram"),
                    "storage": sel.get("storage"),
                    "psu": sel.get("psu"),
                    "cooler": sel.get("cooler"),
                    "case": sel.get("case"),
                    "price": None,
                    "score": None,
                    "budget": prev.get("budget"),
                    "currency": prev.get("currency", "USD"),
                    "mode": prev.get("mode", "gaming"),
                    "resolution": prev.get("resolution", "1440p"),
                    "budget_usd": prev.get("budget_usd"),
                }
                request.session["preview_build"] = preview
                messages.success(
                    request, "Preview replaced with selected upgrade build."
                )
                return redirect("build_preview")
            except Exception:
                messages.error(
                    request, "Could not apply selected proposed build."
                )
                return redirect("upgrade_calculator")
        # parse upgrade budget (user-entered amount in their selected currency)
        try:
            budget = float(request.POST.get("upgrade_budget") or 0)
        except Exception:
            budget = 0.0

        # Determine currency for this upgrade flow.
        # Prefer POSTed currency, else preview session.
        currency = (
            request.POST.get("currency")
            or request.session.get("preview_build", {}).get("currency")
            or "USD"
        )

        # Convert submitted budget into USD for internal comparisons.
        # Catalog prices are in USD.
        try:
            sel_rate = CurrencyRate.objects.filter(currency=currency).first()
            if sel_rate:
                budget_usd = budget * float(sel_rate.rate_to_usd)
            else:
                budget_usd = budget
        except Exception:
            budget_usd = budget

        # Require user to have selected every component in the form.
        # This is separate from the preview flow.
        required_parts = [
            "cpu",
            "gpu",
            "motherboard",
            "ram",
            "storage",
            "psu",
            "cooler",
            "case",
        ]
        missing = [p for p in required_parts if not request.POST.get(p)]
        if missing:
            messages.error(
                request,
                "Please select every component (CPU, GPU, motherboard, "
                "RAM, storage, PSU, cooler and case) before running the "
                "upgrade calculator.",
            )
            return render(
                request,
                "calculator/upgrade_calculator.html",
                {
                    "cpus": cpus_qs,
                    "gpus": gpus_qs,
                    "mobos": mobos_qs,
                    "rams": rams_qs,
                    "storages": storages_qs,
                    "psus": psus_qs,
                    "coolers": coolers_qs,
                    "cases": cases_qs,
                    "currencies": CurrencyRate.objects.all(),
                    "currency": request.session.get("preview_build", {}).get(
                        "currency", "USD"
                    ),
                },
            )

        # Load the submitted components from the POST payload
        try:
            cur_cpu = get_object_or_404(CPU, pk=int(request.POST.get("cpu")))
            cur_gpu = get_object_or_404(GPU, pk=int(request.POST.get("gpu")))
            cur_mobo = get_object_or_404(
                Motherboard, pk=int(request.POST.get("motherboard"))
            )
            cur_ram = get_object_or_404(RAM, pk=int(request.POST.get("ram")))
            cur_storage = get_object_or_404(
                Storage, pk=int(request.POST.get("storage"))
            )
            cur_psu = get_object_or_404(PSU, pk=int(request.POST.get("psu")))
            cur_cooler = get_object_or_404(
                CPUCooler, pk=int(request.POST.get("cooler"))
            )
            cur_case = get_object_or_404(
                Case, pk=int(request.POST.get("case"))
            )
        except Exception:
            messages.error(
                request,
                "One or more selected components could not be found. "
                "Please correct your selections.",
            )
            return render(
                request,
                "calculator/upgrade_calculator.html",
                {
                    "cpus": cpus_qs,
                    "gpus": gpus_qs,
                    "mobos": mobos_qs,
                    "rams": rams_qs,
                    "storages": storages_qs,
                    "psus": psus_qs,
                    "coolers": coolers_qs,
                    "cases": cases_qs,
                    "currencies": CurrencyRate.objects.all(),
                    "currency": request.session.get("preview_build", {}).get(
                        "currency", "USD"
                    ),
                },
            )

        # Read mode from the submitted form (override default)
        mode = request.POST.get("mode", "gaming") or "gaming"
    # resolution default (UI toggles control which resolution is
    # shown client-side)
        default_resolution = (
            request.session.get("preview_build", {}).get("resolution")
            or "1440p"
        )
        # Currency for price display: prefer POSTed value, else preview
        # session value or USD
        currency = (
            request.POST.get("currency")
            or request.session.get("preview_build", {}).get("currency")
            or "USD"
        )

        # Prepare baseline totals for price comparisons
        def price_of(obj):
            try:
                return float(getattr(obj, "price", 0) or 0)
            except Exception:
                return 0.0

        base_total = (
            price_of(cur_cpu)
            + price_of(cur_gpu)
            + price_of(cur_mobo)
            + price_of(cur_ram)
            + price_of(cur_storage)
            + price_of(cur_psu)
            + price_of(cur_cooler)
            + price_of(cur_case)
        )

        # helpers to compute score
        def part_score(obj, part_type):
            try:
                if part_type == "cpu":
                    return cpu_score(obj, mode)
                if part_type == "gpu":
                    return gpu_score(obj, mode)
                if part_type == "ram":
                    return ram_score(obj)
            except Exception:
                return 0.0
            return 0.0

        cur_cpu_score = part_score(cur_cpu, "cpu")
        cur_gpu_score = part_score(cur_gpu, "gpu")

    # We'll collect best proposals keyed to cpu id and gpu id to
    # ensure uniqueness
        cpu_best = {}
        gpu_best = {}

        # Gather CPU proposals (CPU alone or CPU+motherboard(+ram) if required)
        for cand in CPU.objects.filter(price__isnull=False).order_by("price"):
            try:
                cand_s = part_score(cand, "cpu")
                if cand_s <= cur_cpu_score:
                    continue

                # Start with keeping current mobo/ram
                total = base_total - price_of(cur_cpu) + price_of(cand)
                swapped_mobo = None
                swapped_ram = None

                if not compatible_cpu_mobo(cand, cur_mobo):
                    # find cheapest compatible motherboard
                    cheapest_mobo = None
                    for m in Motherboard.objects.filter(
                        price__isnull=False
                    ).order_by("price"):
                        try:
                            if compatible_cpu_mobo(cand, m):
                                cheapest_mobo = m
                                break
                        except Exception:
                            continue
                    if not cheapest_mobo:
                        continue
                    total += price_of(cheapest_mobo) - price_of(cur_mobo)
                    swapped_mobo = cheapest_mobo
                    # ensure RAM compat: if current RAM incompatible with
                    # new mobo, find cheapest compatible ram
                    if not compatible_mobo_ram_cached(cheapest_mobo, cur_ram):
                        cheapest_ram = None
                        for r in RAM.objects.filter(
                            price__isnull=False
                        ).order_by("price"):
                            try:
                                if compatible_mobo_ram_cached(
                                    cheapest_mobo, r
                                ):
                                    cheapest_ram = r
                                    break
                            except Exception:
                                continue
                        if not cheapest_ram:
                            # cannot find RAM for this mobo -> skip
                            continue
                        total += price_of(cheapest_ram) - price_of(cur_ram)
                        swapped_ram = cheapest_ram

                    # Check PSU: CPU upgrade may require a stronger PSU
                    # when paired with current GPU
                    swapped_psu = None
                    try:
                        if not psu_ok_cached(cur_psu, cand, cur_gpu):
                            # find cheapest PSU that satisfies requirements for
                            # cand + current GPU
                            for p in PSU.objects.filter(
                                price__isnull=False
                            ).order_by("price"):
                                try:
                                    if psu_ok_cached(p, cand, cur_gpu):
                                        swapped_psu = p
                                        break
                                except Exception:
                                    continue
                            if not swapped_psu:
                                # no PSU available to support this CPU +
                                # current GPU
                                continue
                            total += price_of(swapped_psu) - price_of(cur_psu)
                    except Exception:
                        # if psu check fails, be conservative and skip
                        # this candidate
                        continue

                # Calculate price delta as the cost of the new parts only
                # (assume the user already owns the current parts). This is
                # the sum of prices for components that will be changed.
                try:
                    new_cost = 0.0
                    # CPU is changing to 'cand'
                    new_cost += price_of(cand)
                    # motherboard/ram swaps (only charge for them if they're
                    # actually different)
                    if swapped_mobo and getattr(
                        swapped_mobo, "id", None
                    ) != getattr(cur_mobo, "id", None):
                        new_cost += price_of(swapped_mobo)
                    if swapped_ram and getattr(
                        swapped_ram, "id", None
                    ) != getattr(cur_ram, "id", None):
                        new_cost += price_of(swapped_ram)
                    if (
                        "swapped_psu" in locals()
                        and swapped_psu
                        and getattr(swapped_psu, "id", None)
                        != getattr(cur_psu, "id", None)
                    ):
                        new_cost += price_of(swapped_psu)
                except Exception:
                    new_cost = total - base_total

                price_delta = new_cost
                # Compare against USD-converted budget
                if price_delta <= 0 or price_delta > budget_usd:
                    continue

                # Compute percent based only on CPU+GPU combined scores
                # (exclude RAM)
                baseline_combo = (cur_cpu_score or 0.0) + (
                    cur_gpu_score or 0.0
                )
                new_combo = (cand_s or 0.0) + (cur_gpu_score or 0.0)
                percent = (
                    ((new_combo - baseline_combo) / baseline_combo) * 100.0
                    if baseline_combo > 0
                    else 0.0
                )
                # store only best proposal per cpu id (highest percent)
                prev = cpu_best.get(cand.id)
                proposal = {
                    "slot": "cpu",
                    "cpu": cand,
                    "motherboard": swapped_mobo or cur_mobo,
                    "ram": swapped_ram or cur_ram,
                    "gpu": cur_gpu,
                    "storage": cur_storage,
                    "psu": swapped_psu or cur_psu,
                    "cooler": cur_cooler,
                    "case": cur_case,
                    "percent": percent,
                    "total_price": total,
                    "price_delta": price_delta,
                }
                if not prev or proposal["percent"] > prev["percent"]:
                    cpu_best[cand.id] = proposal
            except Exception:
                continue

        # Gather GPU proposals (GPU alone)
        for cand in GPU.objects.filter(price__isnull=False).order_by("price"):
            try:
                cand_s = part_score(cand, "gpu")
                # Exclude Blackwell GPUs in gaming mode per user preference
                if mode == "gaming":
                    try:
                        name_hint = " ".join(
                            filter(
                                None,
                                [
                                    getattr(cand, "generation", ""),
                                    getattr(cand, "model", ""),
                                    getattr(cand, "gpu_name", ""),
                                ],
                            )
                        )
                        if "blackwell" in name_hint.lower():
                            continue
                    except Exception:
                        pass
                if cand_s <= cur_gpu_score:
                    continue
                total = base_total - price_of(cur_gpu) + price_of(cand)

                # Check PSU: GPU upgrade may require a stronger PSU
                # for current CPU
                swapped_psu = None
                try:
                    if not psu_ok_cached(cur_psu, cur_cpu, cand):
                        for p in PSU.objects.filter(
                            price__isnull=False
                        ).order_by("price"):
                            try:
                                if psu_ok_cached(p, cur_cpu, cand):
                                    swapped_psu = p
                                    break
                            except Exception:
                                continue
                        if not swapped_psu:
                            # no PSU can support this GPU with current CPU
                            continue
                        total += price_of(swapped_psu) - price_of(cur_psu)
                except Exception:
                    continue

                # Price delta should be the cost of the new GPU and any new PSU
                try:
                    new_cost = 0.0
                    new_cost += price_of(cand)
                    if swapped_psu and getattr(
                        swapped_psu, "id", None
                    ) != getattr(cur_psu, "id", None):
                        new_cost += price_of(swapped_psu)
                except Exception:
                    new_cost = total - base_total

                price_delta = new_cost
                if price_delta <= 0 or price_delta > budget_usd:
                    continue
                # Compute percent based only on CPU+GPU combined scores
                # (exclude RAM)
                baseline_combo = (cur_cpu_score or 0.0) + (
                    cur_gpu_score or 0.0
                )
                new_combo = (cur_cpu_score or 0.0) + (cand_s or 0.0)
                percent = (
                    ((new_combo - baseline_combo) / baseline_combo) * 100.0
                    if baseline_combo > 0
                    else 0.0
                )
                prev = gpu_best.get(cand.id)
                proposal = {
                    "slot": "gpu",
                    "gpu": cand,
                    "cpu": cur_cpu,
                    "motherboard": cur_mobo,
                    "ram": cur_ram,
                    "storage": cur_storage,
                    "psu": swapped_psu or cur_psu,
                    "cooler": cur_cooler,
                    "case": cur_case,
                    "percent": percent,
                    "total_price": total,
                    "price_delta": price_delta,
                }
                if not prev or proposal["percent"] > prev["percent"]:
                    gpu_best[cand.id] = proposal
            except Exception:
                continue

    # Build combined CPU+GPU proposals from the best cpu and gpu
    # candidates (limit to top 10 of each)
        cpu_list = sorted(cpu_best.values(), key=lambda x: -x["percent"])[:10]
        gpu_list = sorted(gpu_best.values(), key=lambda x: -x["percent"])[:10]
        combo_best = {}
        for cprop in cpu_list:
            for gprop in gpu_list:
                try:
                    total = base_total
                    # replace cpu (+mobo/ram if present in cprop)
                    total = (
                        total
                        - price_of(cur_cpu)
                        - price_of(cur_mobo)
                        - price_of(cur_ram)
                    )
                    total += (
                        price_of(cprop["cpu"])
                        + price_of(cprop["motherboard"])
                        + price_of(cprop["ram"])
                    )
                    # replace gpu
                    total = total - price_of(cur_gpu) + price_of(gprop["gpu"])

                    # Check PSU for combined CPU+GPU proposal
                    swapped_psu = None
                    try:
                        if not psu_ok_cached(
                            cur_psu, cprop["cpu"], gprop["gpu"]
                        ):
                            for p in PSU.objects.filter(
                                price__isnull=False
                            ).order_by("price"):
                                try:
                                    if psu_ok_cached(
                                        p, cprop["cpu"], gprop["gpu"]
                                    ):
                                        swapped_psu = p
                                        break
                                except Exception:
                                    continue
                            if not swapped_psu:
                                # cannot source a PSU to support this combined
                                # upgrade
                                continue
                            total += price_of(swapped_psu) - price_of(cur_psu)
                    except Exception:
                        continue

                    # Price delta for combined proposal should be cost
                    # of any new parts
                    try:
                        new_cost = 0.0
                        # cpu/mobo/ram from cprop; gpu from gprop
                        if getattr(cprop.get("cpu"), "id", None) != getattr(
                            cur_cpu, "id", None
                        ):
                            new_cost += price_of(cprop.get("cpu"))
                        if getattr(
                            cprop.get("motherboard"), "id", None
                        ) != getattr(cur_mobo, "id", None):
                            new_cost += price_of(cprop.get("motherboard"))
                        if getattr(cprop.get("ram"), "id", None) != getattr(
                            cur_ram, "id", None
                        ):
                            new_cost += price_of(cprop.get("ram"))
                        if getattr(gprop.get("gpu"), "id", None) != getattr(
                            cur_gpu, "id", None
                        ):
                            new_cost += price_of(gprop.get("gpu"))
                        if swapped_psu and getattr(
                            swapped_psu, "id", None
                        ) != getattr(cur_psu, "id", None):
                            new_cost += price_of(swapped_psu)
                    except Exception:
                        new_cost = total - base_total

                    price_delta = new_cost
                    if price_delta <= 0 or price_delta > budget_usd:
                        continue
                    # combined percent: sum of cpu and gpu percent
                    # (the total estimated improvement)
                    # For combined CPU+GPU proposals, compute percent as
                    # change in combined CPU+GPU scores
                    baseline_combo = (cur_cpu_score or 0.0) + (
                        cur_gpu_score or 0.0
                    )
                    new_combo = (cprop.get("percent") is None and 0.0) or 0.0
                    # cprop and gprop store 'percent' as previously computed.
                    # Instead derive percent from the component parts below.
                    try:
                        c_cpu_score = getattr(
                            cprop.get("cpu"), "cached_score", None
                        ) or cpu_score(cprop.get("cpu"), mode)
                    except Exception:
                        c_cpu_score = 0.0
                    try:
                        g_gpu_score = getattr(
                            gprop.get("gpu"), "cached_score", None
                        ) or gpu_score(gprop.get("gpu"), mode)
                    except Exception:
                        g_gpu_score = 0.0
                    # Strict improvement guard:
                    # both CPU and GPU in a combo must be strictly
                    # better than current
                    if (
                        c_cpu_score is None
                        or c_cpu_score <= (cur_cpu_score or 0.0)
                    ) or (
                        g_gpu_score is None
                        or g_gpu_score <= (cur_gpu_score or 0.0)
                    ):
                        # Skip combos that do not improve both parts
                        # individually
                        continue
                    new_combo = (c_cpu_score or 0.0) + (g_gpu_score or 0.0)
                    percent = (
                        ((new_combo - baseline_combo) / baseline_combo) * 100.0
                        if baseline_combo > 0
                        else 0.0
                    )
                    key = (cprop["cpu"].id, gprop["gpu"].id)
                    proposal = {
                        "slot": "cpu_gpu",
                        "cpu": cprop["cpu"],
                        "motherboard": cprop["motherboard"],
                        "ram": cprop["ram"],
                        "gpu": gprop["gpu"],
                        "storage": cur_storage,
                        "psu": swapped_psu or cur_psu,
                        "cooler": cur_cooler,
                        "case": cur_case,
                        "percent": percent,
                        "total_price": total,
                        "price_delta": price_delta,
                    }
                    combo_best[key] = proposal
                except Exception:
                    continue

    # Assemble final proposals in the requested order:
    # 1) up to 2 combined CPU+GPU proposals (best percent)
    # 2) up to 2 GPU-only proposals (best percent, excluding GPUs already used)
    # 3) up to 2 CPU-only proposals (best percent, excluding CPUs already used)
        final = []
        used_cpus = set()
        used_gpus = set()

        combo_list = sorted(combo_best.values(), key=lambda x: -x["percent"])
        cpu_list_sorted = sorted(
            cpu_best.values(), key=lambda x: -x["percent"]
        )
        gpu_list_sorted = sorted(
            gpu_best.values(), key=lambda x: -x["percent"]
        )

        # Add up to 2 combined cpu+gpu proposals
        for item in combo_list:
            if len(final) >= 2:
                break
            final.append(item)
            used_cpus.add(getattr(item.get("cpu"), "id", None))
            used_gpus.add(getattr(item.get("gpu"), "id", None))

        # Add up to 2 GPU-only proposals excluding GPUs already included
        for item in gpu_list_sorted:
            if (
                len([p for p in final if p.get("slot") == "cpu_gpu"]) >= 0
            ):  # no-op but keeps grouping clear
                pass
            if len([p for p in final if p.get("slot") == "gpu"]) >= 2:
                break
            gid = getattr(item.get("gpu"), "id", None)
            if gid in used_gpus:
                continue
            final.append(item)
            used_gpus.add(gid)

        # Add up to 2 CPU-only proposals excluding CPUs already included
        for item in cpu_list_sorted:
            if len([p for p in final if p.get("slot") == "cpu"]) >= 2:
                break
            cid = getattr(item.get("cpu"), "id", None)
            if cid in used_cpus:
                continue
            final.append(item)
            used_cpus.add(cid)

        proposals = final

    # Save serializable proposals so the user can "use" a proposed build
    # in a follow-up POST
        serial = []
        for p in proposals:
            serial.append(
                {
                    "slot": p.get("slot"),
                    "cpu": getattr(p.get("cpu"), "id", None),
                    "gpu": getattr(p.get("gpu"), "id", None),
                    "motherboard": getattr(p.get("motherboard"), "id", None),
                    "ram": getattr(p.get("ram"), "id", None),
                    "storage": getattr(p.get("storage"), "id", None),
                    "psu": getattr(p.get("psu"), "id", None),
                    "cooler": getattr(p.get("cooler"), "id", None),
                    "case": getattr(p.get("case"), "id", None),
                    "percent": float(p.get("percent") or 0.0),
                    "total_price": float(p.get("total_price") or 0.0),
                    "price_delta": float(p.get("price_delta") or 0.0),
                }
            )
        request.session["last_upgrade_proposals"] = serial
        # Persist the base build used to generate these proposals so preview
        # pages can compare correctly even when the session preview_build
        # isn't present or is different. Store minimal ids + mode/resolution.
        try:
            # Persist the base used to compute proposals including the user's
            # entered upgrade budget and chosen currency. This ensures the
            # upgrade_preview save path can post the same budget/currency.
            request.session["last_upgrade_base"] = {
                "cpu": getattr(cur_cpu, "id", None),
                "gpu": getattr(cur_gpu, "id", None),
                "motherboard": getattr(cur_mobo, "id", None),
                "ram": getattr(cur_ram, "id", None),
                "storage": getattr(cur_storage, "id", None),
                "psu": getattr(cur_psu, "id", None),
                "cooler": getattr(cur_cooler, "id", None),
                "case": getattr(cur_case, "id", None),
                "mode": mode,
                "resolution": default_resolution,
                # Store the upgrade budget as entered (in selected currency)
                "budget": float(budget),
                "currency": currency,
            }
        except Exception:
            # best-effort; don't fail upgrade flow if session write fails
            pass

    # Compute DB averages for mode-aware score and typical prices
    # to ground B4B
        try:
            import math

            score_field = (
                "blender_score"
                if mode == "workstation"
                else "userbenchmark_score"
            )
            from django.db.models import Avg

            def trimmed_avg(model_qs, field_name):
                qs = model_qs.exclude(**{field_name: None}).exclude(
                    **{field_name + "__lte": 0}
                )
                n = qs.count()
                if n == 0:
                    return 0.0
                # Compute 20th and 80th percentile cut points via
                # sorted indexing
                lower_idx = int(math.floor(n * 0.2))
                upper_idx = max(lower_idx, int(math.floor(n * 0.8)) - 1)
                vals = qs.values_list(field_name, flat=True).order_by(
                    field_name
                )
                try:
                    lower_val = vals[lower_idx]
                    upper_val = vals[upper_idx]
                except Exception:
                    # fallback to simple average
                    avg = qs.aggregate(avg=Avg(field_name)).get("avg") or 0.0
                    return float(avg)
                trimmed = qs.filter(
                    **{
                        f"{field_name}__gte": lower_val,
                        f"{field_name}__lte": upper_val,
                    }
                )
                avg = trimmed.aggregate(avg=Avg(field_name)).get("avg") or 0.0
                return float(avg)

            cpu_avg_score = trimmed_avg(CPU.objects.all(), score_field)
            gpu_avg_score = trimmed_avg(GPU.objects.all(), score_field)
            cpu_avg_price = trimmed_avg(CPU.objects.all(), "price")
            gpu_avg_price = trimmed_avg(GPU.objects.all(), "price")
        except Exception:
            cpu_avg_score = gpu_avg_score = cpu_avg_price = gpu_avg_price = 0.0

        # convert proposals into structure the template expects
        proposed_builds = []
        for p in proposals:
            # Build human-friendly display strings to avoid showing
            # object reprs in templates
            def disp(obj):
                try:
                    if obj is None:
                        return "<None>"
                    return (
                        getattr(obj, "name", None)
                        or getattr(obj, "gpu_name", None)
                        or getattr(obj, "model", None)
                        or str(obj)
                    )
                except Exception:
                    return str(obj)

            display = {
                "cpu": disp(p.get("cpu")),
                "gpu": disp(p.get("gpu")),
                "motherboard": disp(p.get("motherboard")),
                "ram": disp(p.get("ram")),
                "storage": disp(p.get("storage")),
                "psu": disp(p.get("psu")),
                "cooler": disp(p.get("cooler")),
                "case": disp(p.get("case")),
            }

            # Compute FPS estimates for all resolutions so client-side
            # toggles can switch without reloading
            games = ("Cyberpunk 2077", "CS2", "Fortnite")
            resolutions = ["1080p", "1440p", "4k"]
            fps_by_res = {res: {} for res in resolutions}
            bottleneck_by_res = {}
            try:
                for res in resolutions:
                    for g in games:
                        try:
                            cpu_obj = p.get("cpu")
                            gpu_obj = p.get("gpu")
                            cpu_fps, gpu_fps = estimate_fps_components(
                                cpu_obj, gpu_obj, mode, res, g
                            )
                            est = round(min(cpu_fps, gpu_fps), 1)
                            fps_by_res[res][g] = {
                                "cpu_fps": cpu_fps,
                                "gpu_fps": gpu_fps,
                                "estimated_fps": est,
                            }
                        except Exception:
                            fps_by_res[res][g] = {
                                "cpu_fps": None,
                                "gpu_fps": None,
                                "estimated_fps": None,
                            }
                    try:
                        bottleneck_by_res[res] = (
                            cpu_bottleneck(
                                p.get("cpu"), p.get("gpu"), mode, res
                            )
                            if p.get("cpu") and p.get("gpu")
                            else {"bottleneck": 0.0, "type": "unknown"}
                        )
                    except Exception:
                        bottleneck_by_res[res] = {
                            "bottleneck": 0.0,
                            "type": "unknown",
                        }
            except Exception:
                fps_by_res = {res: {} for res in resolutions}
                bottleneck_by_res = {}

            # Convert fps_by_res dict into a list for easier template iteration
            fps_res_list = []
            try:
                for res in resolutions:
                    fps_res_list.append(
                        {
                            "res": res,
                            "games": fps_by_res.get(res, {}),
                            "bottleneck": bottleneck_by_res.get(
                                res, {"bottleneck": 0.0, "type": "unknown"}
                            ),
                        }
                    )
            except Exception:
                fps_res_list = []

            # If in workstation mode, compute a render-time estimate
            # for the proposal
            workstation_estimate = None
            workstation_estimate_current = None
            workstation_delta = None
            try:
                if mode == "workstation":
                    workstation_estimate = estimate_render_time(
                        p.get("cpu"), p.get("gpu"), mode
                    )
                    # Ensure we also have the current/base estimate to
                    # show comparison
                    workstation_estimate_current = estimate_render_time(
                        cur_cpu, cur_gpu, mode
                    )
                    try:
                        workstation_delta = (
                            workstation_estimate_current or 0
                        ) - (workstation_estimate or 0)
                    except Exception:
                        workstation_delta = None
            except Exception:
                workstation_estimate = None

            # Compute B4B using averages and upgrade deltas:
            # - perf_vs_avg: proposal CPU+GPU performance vs catalog
            #   trimmed-average
            # - cost_vs_avg: proposal CPU+GPU price vs catalog
            #   trimmed-average
            # - b4b_percent: ratio of upgrade performance increase (%) to
            #   upgrade cost increase (% of avg price). Small perf
            #   gains only score well if the added cost is also small.
            b4b = {
                "perf_vs_avg": None,
                "cost_vs_avg": None,
                "b4b_percent": None,
                "grade": None,
            }
            try:
                # Performance (CPU+GPU) vs averages
                p_cpu_s = (
                    cpu_score(p.get("cpu"), mode) if p.get("cpu") else 0.0
                )
                p_gpu_s = (
                    gpu_score(p.get("gpu"), mode) if p.get("gpu") else 0.0
                )
                cpu_perf_pct = (
                    (p_cpu_s / cpu_avg_score * 100.0)
                    if cpu_avg_score
                    else None
                )
                gpu_perf_pct = (
                    (p_gpu_s / gpu_avg_score * 100.0)
                    if gpu_avg_score
                    else None
                )
                if cpu_perf_pct is not None and gpu_perf_pct is not None:
                    combined_perf_pct = (cpu_perf_pct + gpu_perf_pct) / 2.0
                else:
                    combined_perf_pct = None

                # Cost (CPU+GPU) vs averages. Include PSU/mobo/ram only
                # if changed for clarity
                p_cpu_price = price_of(p.get("cpu"))
                p_gpu_price = price_of(p.get("gpu"))
                cpu_cost_pct = (
                    (p_cpu_price / cpu_avg_price * 100.0)
                    if cpu_avg_price
                    else None
                )
                gpu_cost_pct = (
                    (p_gpu_price / gpu_avg_price * 100.0)
                    if gpu_avg_price
                    else None
                )
                if cpu_cost_pct is not None and gpu_cost_pct is not None:
                    combined_cost_pct = (cpu_cost_pct + gpu_cost_pct) / 2.0
                else:
                    combined_cost_pct = None

                b4b["perf_vs_avg"] = combined_perf_pct
                b4b["cost_vs_avg"] = combined_cost_pct
                # Upgrade-aware B4B: use delta performance (%) over the
                # current build divided by delta cost (%) normalized by
                # average CPU+GPU prices. This penalizes proposals with
                # small performance gains but large added cost.
                perf_delta_pct = p.get("percent")
                # already computed as combined gain vs current
                # Normalize cost delta against average CPU+GPU typical
                # prices to get a percentage-scale
                avg_cpu_gpu_price = None
                try:
                    if cpu_avg_price and gpu_avg_price:
                        avg_cpu_gpu_price = (
                            cpu_avg_price + gpu_avg_price
                        ) / 2.0
                except Exception:
                    avg_cpu_gpu_price = None

                cost_delta_pct = None
                try:
                    if avg_cpu_gpu_price and p.get("price_delta") is not None:
                        cost_delta_pct = (
                            p.get("price_delta") / max(avg_cpu_gpu_price, 1e-6)
                        ) * 100.0
                except Exception:
                    cost_delta_pct = None

                if perf_delta_pct is not None and cost_delta_pct is not None:
                    b4b_val = (
                        perf_delta_pct / max(cost_delta_pct, 1e-6)
                    ) * 100.0
                    # Upgrade-aware grade thresholds (delta-based):
                    # A: > 30, B: >= 20 (else C/D lower)
                    if b4b_val > 30.0:
                        grade = "A"
                    elif b4b_val >= 20.0:
                        grade = "B"
                    elif b4b_val >= 10.0:
                        grade = "C"
                    else:
                        grade = "D"
                    b4b["b4b_percent"] = b4b_val
                    b4b["grade"] = grade
            except Exception:
                pass

            proposed_builds.append(
                {
                    "slot": p.get("slot"),
                    "build": p,
                    "display": display,
                    "percent": p.get("percent"),
                    "total_price": p.get("total_price"),
                    "price_delta": p.get("price_delta"),
                    "fps_res_list": fps_res_list,
                    "workstation_estimate": workstation_estimate,
                    "workstation_estimate_"
                    "current": workstation_estimate_current,
                    "workstation_delta": workstation_delta,
                    "show_fps": (mode != "workstation"),
                    "b4b": b4b,
                    "b4b_mode": (
                        "workstation" if mode == "workstation" else "gaming"
                    ),
                }
            )

        remaining = budget

        return render(
            request,
            "calculator/upgrade_calculator.html",
            {
                "cpus": cpus_qs,
                "gpus": gpus_qs,
                "mobos": mobos_qs,
                "rams": rams_qs,
                "storages": storages_qs,
                "psus": psus_qs,
                "coolers": coolers_qs,
                "cases": cases_qs,
                "current": {
                    "cpu": cur_cpu,
                    "gpu": cur_gpu,
                    "motherboard": cur_mobo,
                    "ram": cur_ram,
                    "storage": cur_storage,
                    "psu": cur_psu,
                    "cooler": cur_cooler,
                    "case": cur_case,
                },
                "proposed_builds": proposed_builds,
                "budget": budget,
                "remaining": remaining,
                "mode": mode,
                "resolution": default_resolution,
                "currencies": CurrencyRate.objects.all(),
                "currency": currency,
            },
        )

    # GET: show blank form (user will select every component)
    return render(
        request,
        "calculator/upgrade_calculator.html",
        {
            "cpus": cpus_qs,
            "gpus": gpus_qs,
            "mobos": mobos_qs,
            "rams": rams_qs,
            "storages": storages_qs,
            "psus": psus_qs,
            "coolers": coolers_qs,
            "cases": cases_qs,
            "mode": mode,
            "currencies": CurrencyRate.objects.all(),
            "currency": request.session.get("preview_build", {}).get(
                "currency", "USD"
            ),
        },
    )


def preview_edit(request):
    """Unified edit page for the session preview build.

    GET shows form, POST applies changes. This replaces the
    per-component modal flow. The view tries to apply permissive
    auto-swaps where sensible and reports any auto-swaps via Django
    messages.
    """

    preview = request.session.get("preview_build")
    if not preview:
        messages.error(
            request, "No preview build in session. Calculate a build first."
        )
        return redirect("build_preview")

    # Helper to load objects safely
    def load_obj(key, ModelClass):
        pk = preview.get(key)
        if not pk:
            return None
        try:
            return ModelClass.objects.get(pk=pk)
        except Exception:
            return None

    # Current selected parts (fallbacks to DB lookups)
    cpu = load_obj("cpu", CPU) or get_object_or_404(CPU, pk=preview.get("cpu"))
    gpu = load_obj("gpu", GPU) or get_object_or_404(GPU, pk=preview.get("gpu"))
    mobo = load_obj("motherboard", Motherboard) or get_object_or_404(
        Motherboard, pk=preview.get("motherboard")
    )
    ram = load_obj("ram", RAM) or get_object_or_404(RAM, pk=preview.get("ram"))
    storage = load_obj("storage", Storage) or get_object_or_404(
        Storage, pk=preview.get("storage")
    )
    psu = load_obj("psu", PSU) or get_object_or_404(PSU, pk=preview.get("psu"))
    cooler = load_obj("cooler", CPUCooler) or get_object_or_404(
        CPUCooler, pk=preview.get("cooler")
    )
    case = load_obj("case", Case) or get_object_or_404(
        Case, pk=preview.get("case")
    )

    if request.method == "POST":
        # Read submitted selections (fall back to existing preview values)
        sel = {
            "cpu": int(request.POST.get("cpu") or preview.get("cpu")),
            "gpu": int(request.POST.get("gpu") or preview.get("gpu")),
            "motherboard": int(
                request.POST.get("motherboard") or preview.get("motherboard")
            ),
            "ram": int(request.POST.get("ram") or preview.get("ram")),
            "storage": int(
                request.POST.get("storage") or preview.get("storage")
            ),
            "psu": int(request.POST.get("psu") or preview.get("psu")),
            "cooler": int(request.POST.get("cooler") or preview.get("cooler")),
            "case": int(request.POST.get("case") or preview.get("case")),
        }

        # Load the selected objects
        try:
            new_cpu = get_object_or_404(CPU, pk=sel["cpu"])
            new_gpu = get_object_or_404(GPU, pk=sel["gpu"])
            new_mobo = get_object_or_404(Motherboard, pk=sel["motherboard"])
            new_ram = get_object_or_404(RAM, pk=sel["ram"])
            new_storage = get_object_or_404(Storage, pk=sel["storage"])
            new_psu = get_object_or_404(PSU, pk=sel["psu"])
            new_cooler = get_object_or_404(CPUCooler, pk=sel["cooler"])
            new_case = get_object_or_404(Case, pk=sel["case"])
        except Exception:
            messages.error(
                request, "One or more selected components could not be found."
            )
            return redirect("preview_edit")

        auto_swaps = []

        # CPU <-> Motherboard compatibility
        if not compatible_cpu_mobo(new_cpu, new_mobo):
            # prefer swapping motherboard to match CPU (try a matching mobo)
            candidates = Motherboard.objects.order_by("-price")[:200]
            candidate = next(
                (
                    mb
                    for mb in candidates
                    if compatible_cpu_mobo(new_cpu, mb)
                    and compatible_mobo_ram(mb, new_ram)
                ),
                None,
            )
            if candidate:
                new_mobo = candidate
                auto_swaps.append(
                    f"motherboard -> {candidate.name} "
                    "(auto-swapped to match selected CPU)"
                )
            else:
                # try swapping CPU to match motherboard
                candidates = CPU.objects.order_by("-price")[:200]
                candidate = next(
                    (
                        c
                        for c in candidates
                        if compatible_cpu_mobo(c, new_mobo)
                    ),
                    None,
                )
                if candidate:
                    new_cpu = candidate
                    auto_swaps.append(
                        f"cpu -> {candidate.name} "
                        "(auto-swapped to match selected motherboard)"
                    )
                else:
                    messages.error(
                        request,
                        (
                            "Selected CPU and motherboard are incompatible "
                            "and no compatible alternative was found."
                        ),
                    )
                    return redirect("preview_edit")

        # Motherboard <-> RAM compatibility
        if not compatible_mobo_ram(new_mobo, new_ram):
            candidates = RAM.objects.order_by("-price")[:200]
            candidate = next(
                (r for r in candidates if compatible_mobo_ram(new_mobo, r)),
                None,
            )
            if candidate:
                new_ram = candidate
                auto_swaps.append(
                    f"ram -> {candidate.name} "
                    "(auto-swapped to match selected motherboard)"
                )
            else:
                # try swapping motherboard to match RAM
                candidates = Motherboard.objects.order_by("-price")[:150]
                candidate = next(
                    (
                        mb
                        for mb in candidates
                        if compatible_mobo_ram(mb, new_ram)
                    ),
                    None,
                )
                if candidate:
                    new_mobo = candidate
                    auto_swaps.append(
                        f"motherboard -> {candidate.name} "
                        "(auto-swapped to match selected RAM)"
                    )
                else:
                    messages.error(
                        request,
                        (
                            "Selected motherboard and RAM are incompatible "
                            "and no compatible alternative was found."
                        ),
                    )
                    return redirect("preview_edit")

        # Motherboard <-> Storage
        if new_storage and not compatible_storage(new_mobo, new_storage):
            messages.error(
                request,
                (
                    "Selected storage is not compatible with the "
                    "selected motherboard."
                ),
            )
            return redirect("preview_edit")

        # Case compatibility with motherboard
        if new_mobo and not compatible_case(new_mobo, new_case):
            messages.error(
                request,
                (
                    "Selected case is not compatible with the "
                    "selected motherboard."
                ),
            )
            return redirect("preview_edit")

        # Cooler compatibility
        if not cooler_ok(new_cooler, new_cpu):
            messages.error(
                request,
                (
                    "Selected cooler is not sufficient for the "
                    "selected CPU."
                ),
            )
            return redirect("preview_edit")

        # PSU <-> CPU+GPU
        if not psu_ok(new_psu, new_cpu, new_gpu):
            # try to upgrade PSU
            candidates = PSU.objects.order_by("-wattage")[:150]
            candidate = next(
                (p for p in candidates if psu_ok(p, new_cpu, new_gpu)), None
            )
            if candidate:
                new_psu = candidate
                auto_swaps.append(
                    f"psu -> {candidate.name} "
                    "(auto-swapped to provide sufficient wattage)"
                )
            else:
                # try downgrading GPU to fit PSU
                candidates = GPU.objects.order_by("-price")[:200]
                candidate = next(
                    (g for g in candidates if psu_ok(new_psu, new_cpu, g)),
                    None,
                )
                if candidate:
                    new_gpu = candidate
                    auto_swaps.append(
                        f"gpu -> {candidate.gpu_name} "
                        "(auto-swapped to fit selected PSU)"
                    )
                else:
                    messages.error(
                        request,
                        (
                            "Selected PSU cannot support the selected "
                            "CPU+GPU and no alternative was found."
                        ),
                    )
                    return redirect("preview_edit")

        # Persist new selections back to session
        mapping = {
            "cpu": new_cpu.pk,
            "gpu": new_gpu.pk,
            "motherboard": new_mobo.pk,
            "ram": new_ram.pk,
            "storage": new_storage.pk,
            "psu": new_psu.pk,
            "cooler": new_cooler.pk,
            "case": new_case.pk,
        }
        preview.update(mapping)

        # Recompute price and score
        try:
            parts_list = [
                get_object_or_404(CPU, pk=preview["cpu"]),
                get_object_or_404(GPU, pk=preview["gpu"]),
                get_object_or_404(Motherboard, pk=preview["motherboard"]),
                get_object_or_404(RAM, pk=preview["ram"]),
                get_object_or_404(Storage, pk=preview["storage"]),
                get_object_or_404(PSU, pk=preview["psu"]),
                get_object_or_404(CPUCooler, pk=preview["cooler"]),
                get_object_or_404(Case, pk=preview["case"]),
            ]
            preview["price"] = float(total_price(parts_list))
            preview["score"] = float(
                weighted_scores(
                    parts_list[0],
                    parts_list[1],
                    parts_list[3],
                    preview.get("mode"),
                    "1440p",
                )
            )
        except Exception:
            pass

        request.session["preview_build"] = preview

        messages.success(request, "Preview updated successfully.")
        for note in auto_swaps:
            messages.info(request, note)

        return redirect("build_preview")

    # GET: render edit form using the current selected parts
    context = {
        "build": SimpleNamespace(
            cpu=cpu,
            gpu=gpu,
            motherboard=mobo,
            ram=ram,
            storage=storage,
            psu=psu,
            cooler=cooler,
            case=case,
            currency=preview.get("currency", "USD"),
        ),
        "cpus": CPU.objects.order_by("-price"),
        "gpus": GPU.objects.order_by("-price"),
        "mobos": Motherboard.objects.order_by("-price"),
        "rams": RAM.objects.order_by("-price"),
        "cases": Case.objects.order_by("-price"),
        "psus": PSU.objects.order_by("-price"),
        "coolers": CPUCooler.objects.order_by("-price"),
        "storages": Storage.objects.order_by("-price"),
    }
    return render(request, "calculator/preview_edit.html", context)


def build_preview_pk(request, pk):
    """Render a preview for a specific UserBuild (by pk).

    This preview does not use the session cache.
    """
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
        return render(
            request,
            "calculator/build_preview.html",
            {
                "error": (
                    "Saved build is missing one or more components. "
                    "Please edit or delete this build."
                ),
            },
        )

    signup_form = SignupForm()
    login_form = LoginForm()

    # For saved builds, use the stored currency on the model if present
    # (default USD)
    currency = getattr(build_obj, "currency", "USD")
    currency_symbol = None

    # Compute normalized performance percentages (CPU/GPU/RAM) like
    # build preview
    from django.db.models import Max

    def safe_float(v):
        try:
            return float(v or 0)
        except Exception:
            return 0.0

    mode = getattr(build_obj, "mode", "gaming") or "gaming"
    # Default resolution for FPS display
    default_resolution = getattr(build_obj, "resolution", None) or "1440p"
    cpu_field = (
        "blender_score" if mode == "workstation" else "userbenchmark_score"
    )
    gpu_field = (
        "blender_score" if mode == "workstation" else "userbenchmark_score"
    )
    ram_field = "benchmark"  # RAM uses generic benchmark field
    cpu_top = safe_float(CPU.objects.aggregate(m=Max(cpu_field)).get("m"))
    gpu_top = safe_float(GPU.objects.aggregate(m=Max(gpu_field)).get("m"))
    # Compute top RAM benchmark (use the configured ram_field)
    ram_top_candidate = RAM.objects.aggregate(mb=Max(ram_field))
    ram_top = safe_float(ram_top_candidate.get("mb"))
    cpu_val = safe_float(getattr(cpu, cpu_field, 0))
    gpu_val = safe_float(getattr(gpu, gpu_field, 0))
    # RAM benchmark value (use ram_field variable)
    ram_val = safe_float(getattr(ram, ram_field, None))

    def perf_pct(top, val):
        try:
            if top and val:
                return round((val / top) * 100.0, 1)
        except Exception:
            pass
        return None

    cpu_perf = perf_pct(cpu_top, cpu_val)
    gpu_perf = perf_pct(gpu_top, gpu_val)
    ram_perf = perf_pct(ram_top, ram_val)

    # Build per-resolution FPS estimates for saved build preview
    # (gaming mode only)
    fps_res_list = []
    bottleneck_info = {"bottleneck": 0.0, "type": "unknown"}
    workstation_render_time = None
    try:
        if mode == "workstation":
            try:
                workstation_render_time = estimate_render_time(cpu, gpu, mode)
            except Exception:
                workstation_render_time = None
        else:
            games = ["Cyberpunk 2077", "CS2", "Fortnite"]
            resolutions = ["1080p", "1440p", "4k"]
            for res in resolutions:
                games_map = {}
                for g in games:
                    try:
                        cpu_fps, gpu_fps = estimate_fps_components(
                            cpu, gpu, mode, res, g
                        )
                        est = (
                            round(min(cpu_fps, gpu_fps), 1)
                            if cpu_fps is not None and gpu_fps is not None
                            else None
                        )
                        games_map[g] = {
                            "overall": est,
                            "cpu": cpu_fps,
                            "gpu": gpu_fps,
                        }
                    except Exception:
                        games_map[g] = {
                            "overall": None,
                            "cpu": None,
                            "gpu": None,
                        }
                try:
                    binfo = cpu_bottleneck(cpu, gpu, mode, res)
                except Exception:
                    binfo = {"bottleneck": 0.0, "type": "unknown"}
                fps_res_list.append(
                    {"res": res, "games": games_map, "bottleneck": binfo}
                )
            # pick bottleneck for default resolution
            try:
                bottleneck_info = next(
                    (
                        e.get("bottleneck")
                        for e in fps_res_list
                        if e.get("res") == default_resolution
                    ),
                    bottleneck_info,
                )
            except Exception:
                pass
    except Exception:
        fps_res_list = []

    return render(
        request,
        "calculator/edit_build_preview.html",
        {
            "cpu": cpu,
            "gpu": gpu,
            "motherboard": mobo,
            "ram": ram,
            "storage": storage,
            "psu": psu,
            "cooler": cooler,
            "case": case,
            "budget": build_obj.budget,
            "mode": getattr(build_obj, "mode", None),
            "score": build_obj.total_score,
            "price": build_obj.total_price,
            "signup_form": signup_form,
            "login_form": login_form,
            "is_saved_preview": True,
            "currency": currency,
            "currency_symbol": currency_symbol,
            "cpu_perf": cpu_perf,
            "gpu_perf": gpu_perf,
            "ram_perf": ram_perf,
            "default_resolution": default_resolution,
            "fps_res_list": fps_res_list,
            "bottleneck": bottleneck_info,
            "workstation_render_time": workstation_render_time,
        },
    )


@login_required
@login_required
def save_build(request):
    """Save the current preview build to the logged-in user's account.

    This view requires authentication. Anonymous callers will be redirected
    to the login page. Requiring login prevents anonymous saves from being
    persisted to other users' accounts or orphaned records.
    """
    # Debug: entry logs
    try:
        print("[save_build] ENTRY method=", request.method)
        print("[save_build] POST keys=", list(request.POST.keys()))
        # Show full POST mapping for troubleshooting
        try:
            print(
                "[save_build] POST map=",
                {k: request.POST.get(k) for k in request.POST.keys()},
            )
        except Exception:
            pass
    except Exception:
        pass
    # Allow callers to mark this saved build as an upgrade snapshot by posting
    # 'is_upgrade' in the save form. This is useful for distinguishing saved
    # upgrade snapshots from full builds in the UI.
    is_upgrade_flag = bool(request.POST.get("is_upgrade"))

    build_data = request.session.get("preview_build")

    # If there's no session preview but the caller is saving an upgrade (from
    # the upgrade_preview page), attempt to reconstruct the preview from the
    # last upgrade proposal stored in session (using the posted upgrade_index).
    if not build_data and is_upgrade_flag:
        try:
            # Accept either 'upgrade_index' (from upgrade_preview) or
            # 'proposed_index' (from upgrade_calculator)
            idx_raw = request.POST.get("upgrade_index")
            if idx_raw is None:
                idx_raw = request.POST.get("proposed_index")
            idx = int(idx_raw or 0)
        except Exception:
            idx = 0
        proposals = request.session.get("last_upgrade_proposals", []) or []
        base = request.session.get("last_upgrade_base") or {}
        if proposals and 0 <= idx < len(proposals):
            sel = proposals[idx]
            # Build a preview-like dict from the proposal + base
            build_data = {
                "cpu": sel.get("cpu") or base.get("cpu"),
                "gpu": sel.get("gpu") or base.get("gpu"),
                "motherboard": sel.get("motherboard")
                or base.get("motherboard"),
                "ram": sel.get("ram") or base.get("ram"),
                "storage": sel.get("storage") or base.get("storage"),
                "psu": sel.get("psu") or base.get("psu"),
                "cooler": sel.get("cooler") or base.get("cooler"),
                "case": sel.get("case") or base.get("case"),
                # Prefer budget/currency from recorded upgrade base for
                # deterministic saved upgrades
                "budget": base.get(
                    "budget",
                    request.session.get("preview_build", {}).get(
                        "budget", 0.0
                    ),
                ),
                "currency": base.get(
                    "currency",
                    request.session.get("preview_build", {}).get(
                        "currency", "USD"
                    ),
                ),
                "mode": base.get("mode")
                or request.session.get("preview_build", {}).get(
                    "mode", "gaming"
                ),
                "resolution": base.get("resolution")
                or request.session.get("preview_build", {}).get(
                    "resolution", "1440p"
                ),
                "price": sel.get("total_price") or None,
                "score": sel.get("score") or None,
            }

    if not build_data:
        try:
            print("[save_build] build_data missing -> redirect home")
        except Exception:
            pass
        return redirect("home")

    try:
        # Determine budget/currency to store. For upgrade snapshots prefer the
        # explicit last_upgrade_base values (if present) so the saved record is
        # self-contained. Fall back to the preview_build values otherwise.
        last_upgrade_base = request.session.get("last_upgrade_base") or {}
        if is_upgrade_flag:
            # prefer budget from the recorded upgrade base, else the
            # preview build
            try:
                if last_upgrade_base.get("budget") is not None:
                    _budget_val = float(last_upgrade_base.get("budget"))
                elif request.POST.get("budget") is not None:
                    # Prefer POSTed 'budget' for upgrade saves (now posted
                    # by the calculator form)
                    _budget_val = float(request.POST.get("budget"))
                else:
                    _budget_val = float(
                        build_data.get("budget")
                        if build_data.get("budget") is not None
                        else 0.0
                    )
            except Exception:
                # Final fallback
                _budget_val = float(
                    build_data.get("budget")
                    if build_data.get("budget") is not None
                    else 0.0
                )

            # Prefer posted currency if provided, then recorded upgrade base
            # currency, then build_data
            currency_val = (
                request.POST.get("currency")
                or last_upgrade_base.get("currency")
                or build_data.get("currency")
                or "USD"
            )

            # Ensure the stored upgrade_base contains budget + currency for
            # later deterministic previews
            stored_upgrade_base = (
                dict(last_upgrade_base)
                if isinstance(last_upgrade_base, dict)
                else {}
            )
            try:
                stored_upgrade_base["budget"] = _budget_val
                stored_upgrade_base["currency"] = currency_val
            except Exception:
                # ignore failures to mutate stored_upgrade_base
                pass

        else:
            # Regular builds: use preview budget/currency (fallbacks)
            try:
                _budget_val = float(
                    build_data.get("budget")
                    if build_data.get("budget") is not None
                    else 0.0
                )
            except Exception:
                # Consider POSTed budget as a last resort (e.g., if the
                # preview_build is partial)
                try:
                    _budget_val = float(request.POST.get("budget") or 0.0)
                except Exception:
                    _budget_val = 0.0
            currency_val = (
                request.POST.get("currency")
                or build_data.get("currency")
                or "USD"
            )
            stored_upgrade_base = {}

        # --- Debug logging for budget persistence ---
        try:
            print("[save_build] is_upgrade=", is_upgrade_flag)
            print("[save_build] POST.budget=", request.POST.get("budget"))
            print("[save_build] POST.currency=", request.POST.get("currency"))
            try:
                print(
                    "[save_build] session.preview_build=",
                    request.session.get("preview_build"),
                )
                print(
                    "[save_build] session.last_upgrade_base=",
                    request.session.get("last_upgrade_base"),
                )
            except Exception:
                pass
            print(
                "[save_build] session.preview_build.budget=",
                request.session.get("preview_build", {}).get("budget"),
            )
            print(
                "[save_build] session.last_upgrade_base.budget=",
                (request.session.get("last_upgrade_base") or {}).get("budget"),
            )
            print(
                "[save_build] resolved _budget_val=",
                _budget_val,
                "currency=",
                currency_val,
            )
        except Exception:
            pass

        UserBuild.objects.create(
            user=request.user,
            cpu=get_object_or_404(CPU, pk=build_data.get("cpu")),
            gpu=get_object_or_404(GPU, pk=build_data.get("gpu")),
            motherboard=get_object_or_404(
                Motherboard, pk=build_data.get("motherboard")
            ),
            ram=get_object_or_404(RAM, pk=build_data.get("ram")),
            storage=get_object_or_404(Storage, pk=build_data.get("storage")),
            psu=get_object_or_404(PSU, pk=build_data.get("psu")),
            cooler=get_object_or_404(CPUCooler, pk=build_data.get("cooler")),
            case=get_object_or_404(Case, pk=build_data.get("case")),
            budget=_budget_val,
            mode=build_data.get("mode"),
            # persist user's chosen currency (fallback USD)
            currency=currency_val,
            total_score=build_data.get("score"),
            # price stored in session is USD total from the calculator
            total_price=build_data.get("price"),
            is_upgrade=is_upgrade_flag,
            # If this save is an upgrade snapshot, persist the base used to
            # compute it
            upgrade_base=stored_upgrade_base if is_upgrade_flag else {},
        )
    except KeyError:
        # If any key is missing, just redirect safely
        return redirect("home")

    # Clear the cached preview build once saved
    request.session.pop("preview_build", None)
    # Clear any cached alternatives now that the build is saved
    request.session.pop("preview_alternatives", None)

    return redirect("saved_builds")


@login_required
def saved_builds(request):
    """List all builds saved by the current user."""
    qs = UserBuild.objects.filter(user=request.user)
    valid_builds = []
    skipped = 0
    for b in qs:
        try:
            # Touch related fields to ensure they exist and are loadable
            _ = (
                b.cpu
                and b.gpu
                and b.motherboard
                and b.ram
                and b.storage
                and b.psu
                and b.cooler
                and b.case
            )

            # Prepare display fields for the template.
            # For upgrades show price_delta and estimated gain (combined
            # CPU+GPU percent vs the base); for regular builds expose the
            # total price and zero/blank gain.
            def price_of_obj(o):
                try:
                    return float(getattr(o, "price", 0) or 0)
                except Exception:
                    return 0.0

            # Defaults
            b.display_price = float(b.total_price or 0.0)
            b.estimated_gain = 0.0
            # Prepare a display_budget which templates should use. Default to
            # the saved build's budget if present; for upgrades try the
            # stored upgrade_base or fall back to the user's latest
            # non-upgrade build's budget.
            try:
                # Show budget even if it's 0.0; only hide when truly
                # missing (None)
                if hasattr(b, "budget") and getattr(b, "budget") is not None:
                    b.display_budget = float(getattr(b, "budget"))
                else:
                    b.display_budget = None
            except Exception:
                b.display_budget = None

            if getattr(b, "is_upgrade", False):
                # Determine base: prefer stored upgrade_base, else latest
                # non-upgrade saved build
                base = getattr(b, "upgrade_base", None) or {}
                if not base:
                    base_obj = (
                        UserBuild.objects.filter(
                            user=request.user, is_upgrade=False
                        )
                        .exclude(pk=b.pk)
                        .order_by("-id")
                        .first()
                    )
                    if base_obj:
                        base = {
                            "cpu": base_obj.cpu.id if base_obj.cpu else None,
                            "gpu": base_obj.gpu.id if base_obj.gpu else None,
                            "motherboard": (
                                base_obj.motherboard.id
                                if base_obj.motherboard
                                else None
                            ),
                            "ram": base_obj.ram.id if base_obj.ram else None,
                            "storage": (
                                base_obj.storage.id
                                if base_obj.storage
                                else None
                            ),
                            "psu": base_obj.psu.id if base_obj.psu else None,
                            "cooler": (
                                base_obj.cooler.id if base_obj.cooler else None
                            ),
                            "case": (
                                base_obj.case.id if base_obj.case else None
                            ),
                            "mode": getattr(base_obj, "mode", "gaming"),
                            "resolution": (
                                getattr(base_obj, "resolution", "1440p")
                                if hasattr(base_obj, "resolution")
                                else "1440p"
                            ),
                        }

                # If no display budget yet, try to derive it from the base
                # or base_obj. If display_budget is still None, try to
                # derive from upgrade_base or the latest base build
                if b.display_budget is None:
                    try:
                        # prefer an explicit budget stored in upgrade_base
                        ub = getattr(b, "upgrade_base", {}) or {}
                        if "budget" in ub and ub.get("budget") is not None:
                            b.display_budget = float(ub.get("budget"))
                        elif base_obj and getattr(base_obj, "budget", None):
                            b.display_budget = float(base_obj.budget)
                        else:
                            b.display_budget = None
                    except Exception:
                        b.display_budget = None

                # Compute price_delta: sum prices of components that differ
                # from the base
                try:
                    price_delta = 0.0
                    base_cpu = None
                    base_gpu = None
                    if base.get("cpu"):
                        try:
                            base_cpu = CPU.objects.get(pk=base.get("cpu"))
                        except Exception:
                            base_cpu = None
                    if base.get("gpu"):
                        try:
                            base_gpu = GPU.objects.get(pk=base.get("gpu"))
                        except Exception:
                            base_gpu = None

                    if b.cpu and (
                        not base_cpu
                        or int(b.cpu.id) != int(getattr(base_cpu, "id", None))
                    ):
                        price_delta += price_of_obj(b.cpu)
                    if b.gpu and (
                        not base_gpu
                        or int(b.gpu.id) != int(getattr(base_gpu, "id", None))
                    ):
                        price_delta += price_of_obj(b.gpu)
                    if b.motherboard and b.motherboard.id != base.get(
                        "motherboard"
                    ):
                        price_delta += price_of_obj(b.motherboard)
                    if b.ram and b.ram.id != base.get("ram"):
                        price_delta += price_of_obj(b.ram)
                    if b.storage and b.storage.id != base.get("storage"):
                        price_delta += price_of_obj(b.storage)
                    if b.psu and b.psu.id != base.get("psu"):
                        price_delta += price_of_obj(b.psu)
                    if b.cooler and b.cooler.id != base.get("cooler"):
                        price_delta += price_of_obj(b.cooler)
                    if b.case and b.case.id != base.get("case"):
                        price_delta += price_of_obj(b.case)
                except Exception:
                    price_delta = float(b.total_price or 0.0)

                b.display_price = float(price_delta)

                # Compute percent (combined CPU+GPU) if base cpu/gpu available
                try:
                    base_cpu_obj = None
                    base_gpu_obj = None
                    if base.get("cpu"):
                        try:
                            base_cpu_obj = CPU.objects.get(pk=base.get("cpu"))
                        except Exception:
                            base_cpu_obj = None
                    if base.get("gpu"):
                        try:
                            base_gpu_obj = GPU.objects.get(pk=base.get("gpu"))
                        except Exception:
                            base_gpu_obj = None

                    baseline_combo = (
                        cpu_score(base_cpu_obj, base.get("mode"))
                        if base_cpu_obj
                        else 0.0
                    ) + (
                        gpu_score(base_gpu_obj, base.get("mode"))
                        if base_gpu_obj
                        else 0.0
                    )
                    new_combo = (
                        cpu_score(b.cpu, b.mode) if b.cpu else 0.0
                    ) + (gpu_score(b.gpu, b.mode) if b.gpu else 0.0)
                    if baseline_combo and baseline_combo > 0:
                        try:
                            b.estimated_gain = (
                                (new_combo - baseline_combo) / baseline_combo
                            ) * 100.0
                        except Exception:
                            b.estimated_gain = 0.0
                    else:
                        b.estimated_gain = 0.0
                except Exception:
                    b.estimated_gain = 0.0

            valid_builds.append(b)
        except Exception:
            # If any related object was deleted or is inconsistent, skip
            # this build
            skipped += 1

    if skipped:
        messages.warning(
            request,
            (
                f"{skipped} saved build(s) were skipped because they "
                "reference missing components. "
                "Please edit or delete those builds."
            ),
        )

    return render(request, "calculator/builds.html", {"builds": valid_builds})


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
def view_saved_upgrade(request, pk):
    """Prepare session data so a saved upgrade can be displayed using the
    existing `upgrade_preview` view. We create a single proposal entry
    from the saved build and set `last_upgrade_proposals` and
    `last_upgrade_base` in session so `upgrade_preview` can render it.
    """
    build = get_object_or_404(UserBuild, pk=pk, user=request.user)
    # Only meaningful for saved upgrades. If not marked, redirect to the
    # normal preview view
    if not getattr(build, "is_upgrade", False):
        return redirect("build_preview_pk", pk=build.pk)

    # Helper to safely extract price
    def price_of_obj(o):
        try:
            return float(getattr(o, "price", 0) or 0)
        except Exception:
            return 0.0

    # Determine a base build to compare against. Prefer the explicit base
    # stored on the saved upgrade itself (upgrade_base). This ensures the
    # saved upgrade preview is deterministic across sessions. If that's not
    # present, prefer the user's most recent non-upgrade saved build. We do
    # NOT use the transient session `preview_build` here to avoid mixing
    # unrelated preview state into saved-upgrade views.
    base = None
    if getattr(build, "upgrade_base", None):
        base = build.upgrade_base or None
    if not base:
        # Try to find the user's latest non-upgrade saved build to act
        # as the base
        base_obj = (
            UserBuild.objects.filter(user=request.user, is_upgrade=False)
            .exclude(pk=build.pk)
            .order_by("-id")
            .first()
        )
        if base_obj:
            base = {
                "cpu": base_obj.cpu.id if base_obj.cpu else None,
                "gpu": base_obj.gpu.id if base_obj.gpu else None,
                "motherboard": (
                    base_obj.motherboard.id if base_obj.motherboard else None
                ),
                "ram": base_obj.ram.id if base_obj.ram else None,
                "storage": base_obj.storage.id if base_obj.storage else None,
                "psu": base_obj.psu.id if base_obj.psu else None,
                "cooler": base_obj.cooler.id if base_obj.cooler else None,
                "case": base_obj.case.id if base_obj.case else None,
                "mode": getattr(base_obj, "mode", "gaming"),
                "resolution": (
                    getattr(base_obj, "resolution", "1440p")
                    if hasattr(base_obj, "resolution")
                    else "1440p"
                ),
            }
        else:
            # No reasonable base available: compare against the saved
            # build itself
            base = {
                "cpu": build.cpu.id if build.cpu else None,
                "gpu": build.gpu.id if build.gpu else None,
                "motherboard": (
                    build.motherboard.id if build.motherboard else None
                ),
                "ram": build.ram.id if build.ram else None,
                "storage": build.storage.id if build.storage else None,
                "psu": build.psu.id if build.psu else None,
                "cooler": build.cooler.id if build.cooler else None,
                "case": build.case.id if build.case else None,
                "mode": getattr(build, "mode", "gaming"),
                "resolution": (
                    getattr(build, "resolution", "1440p")
                    if hasattr(build, "resolution")
                    else "1440p"
                ),
            }
    base_obj = None
    if not base:
        base_obj = (
            UserBuild.objects.filter(user=request.user, is_upgrade=False)
            .exclude(pk=build.pk)
            .order_by("-id")
            .first()
        )
        if base_obj:
            base = {
                "cpu": base_obj.cpu.id,
                "gpu": base_obj.gpu.id,
                "motherboard": base_obj.motherboard.id,
                "ram": base_obj.ram.id,
                "storage": base_obj.storage.id,
                "psu": base_obj.psu.id,
                "cooler": base_obj.cooler.id,
                "case": base_obj.case.id,
                "mode": getattr(base_obj, "mode", "gaming"),
                "resolution": getattr(base_obj, "resolution", "1440p"),
            }
        else:
            # fallback: compare against the saved build itself. This will
            # show no changed items
            base = {
                "cpu": build.cpu.id,
                "gpu": build.gpu.id,
                "motherboard": build.motherboard.id,
                "ram": build.ram.id,
                "storage": build.storage.id,
                "psu": build.psu.id,
                "cooler": build.cooler.id,
                "case": build.case.id,
                "mode": getattr(build, "mode", "gaming"),
                "resolution": getattr(build, "resolution", "1440p"),
            }

    # Build the proposal serial representing this saved upgrade
    sel = {
        "slot": "saved_upgrade",
        "cpu": getattr(build.cpu, "id", None),
        "gpu": getattr(build.gpu, "id", None),
        "motherboard": getattr(build.motherboard, "id", None),
        "ram": getattr(build.ram, "id", None),
        "storage": getattr(build.storage, "id", None),
        "psu": getattr(build.psu, "id", None),
        "cooler": getattr(build.cooler, "id", None),
        "case": getattr(build.case, "id", None),
        "percent": 0.0,
        "total_price": float(build.total_price or 0.0),
        "price_delta": 0.0,
    }

    # Compute price_delta as sum of prices for components that differ from base
    try:
        price_delta = 0.0
        # load base objects where available
        if base.get("cpu"):
            try:
                base_cpu = CPU.objects.get(pk=base.get("cpu"))
            except Exception:
                base_cpu = None
        else:
            base_cpu = None
        if base.get("gpu"):
            try:
                base_gpu = GPU.objects.get(pk=base.get("gpu"))
            except Exception:
                base_gpu = None
        else:
            base_gpu = None

        # compare each part
        if sel.get("cpu") and (
            not base_cpu
            or int(sel.get("cpu")) != int(getattr(base_cpu, "id", None))
        ):
            price_delta += price_of_obj(build.cpu)
        if sel.get("gpu") and (
            not base_gpu
            or int(sel.get("gpu")) != int(getattr(base_gpu, "id", None))
        ):
            price_delta += price_of_obj(build.gpu)
        # other parts
        if sel.get("motherboard") and sel.get("motherboard") != base.get(
            "motherboard"
        ):
            price_delta += price_of_obj(build.motherboard)
        if sel.get("ram") and sel.get("ram") != base.get("ram"):
            price_delta += price_of_obj(build.ram)
        if sel.get("storage") and sel.get("storage") != base.get("storage"):
            price_delta += price_of_obj(build.storage)
        if sel.get("psu") and sel.get("psu") != base.get("psu"):
            price_delta += price_of_obj(build.psu)
        if sel.get("cooler") and sel.get("cooler") != base.get("cooler"):
            price_delta += price_of_obj(build.cooler)
        if sel.get("case") and sel.get("case") != base.get("case"):
            price_delta += price_of_obj(build.case)
    except Exception:
        price_delta = float(build.total_price or 0.0)

    sel["price_delta"] = float(price_delta)

    # Compute percent (combined CPU+GPU) if base cpu/gpu available
    try:
        base_cpu_obj = None
        base_gpu_obj = None
        if base.get("cpu"):
            try:
                base_cpu_obj = CPU.objects.get(pk=base.get("cpu"))
            except Exception:
                base_cpu_obj = None
        if base.get("gpu"):
            try:
                base_gpu_obj = GPU.objects.get(pk=base.get("gpu"))
            except Exception:
                base_gpu_obj = None

        baseline_combo = (
            cpu_score(base_cpu_obj, base.get("mode")) if base_cpu_obj else 0.0
        ) + (
            gpu_score(base_gpu_obj, base.get("mode")) if base_gpu_obj else 0.0
        )
        new_combo = (
            cpu_score(build.cpu, build.mode) if build.cpu else 0.0
        ) + (gpu_score(build.gpu, build.mode) if build.gpu else 0.0)
        if baseline_combo and baseline_combo > 0:
            sel["percent"] = (
                (new_combo - baseline_combo) / baseline_combo
            ) * 100.0
        else:
            sel["percent"] = 0.0
    except Exception:
        sel["percent"] = 0.0

    # Persist the single proposal and the chosen base into session
    # and redirect to preview
    request.session["last_upgrade_proposals"] = [sel]
    request.session["last_upgrade_base"] = base
    # Indicate the preview came from a saved upgrade so the UI can offer
    # a back link to the saved builds page.
    request.session["from_saved_upgrade"] = True

    return redirect(f"{reverse('upgrade_preview')}?index=0")


# --- Edit build ---


@login_required
def edit_build(request, pk):
    build = get_object_or_404(UserBuild, pk=pk, user=request.user)

    if request.method == "POST":
        mode = request.POST.get("mode", "basic")

        if mode == "basic":
            # --- Basic mode: budget-based reassignment ---
            budget = float(request.POST.get("budget") or 0)
            build.budget = budget
            parts = auto_assign_parts(
                budget, mode="gaming", resolution="1440p"
            )
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
            if (
                build.cpu
                and build.motherboard
                and not compatible_cpu_mobo(build.cpu, build.motherboard)
            ):
                messages.error(
                    request, "Selected CPU and motherboard are not compatible."
                )
                return redirect("edit_build", pk=build.pk)

            if (
                build.motherboard
                and build.ram
                and not compatible_mobo_ram(build.motherboard, build.ram)
            ):
                messages.error(
                    request, "Selected RAM is not compatible with motherboard."
                )
                return redirect("edit_build", pk=build.pk)

            if (
                build.motherboard
                and build.storage
                and not compatible_storage(build.motherboard, build.storage)
            ):
                messages.error(
                    request,
                    "Selected storage is not compatible with motherboard.",
                )
                return redirect("edit_build", pk=build.pk)

            if (
                build.motherboard
                and build.case
                and not compatible_case(build.motherboard, build.case)
            ):
                messages.error(
                    request,
                    "Selected case is not compatible with motherboard.",
                )
                return redirect("edit_build", pk=build.pk)

            if (
                build.psu
                and build.cpu
                and build.gpu
                and not psu_ok(build.psu, build.cpu, build.gpu)
            ):
                messages.error(
                    request, "PSU wattage is insufficient for CPU + GPU."
                )
                return redirect("edit_build", pk=build.pk)

            if (
                build.cooler
                and build.cpu
                and not cooler_ok(build.cooler, build.cpu)
            ):
                messages.error(
                    request, "Cooler throughput is insufficient for CPU."
                )
                return redirect("edit_build", pk=build.pk)

            # Recalculate totals
            parts = [
                build.cpu,
                build.gpu,
                build.motherboard,
                build.ram,
                build.storage,
                build.psu,
                build.cooler,
                build.case,
            ]
            build.total_price = total_price(parts)
            build.total_score = weighted_scores(
                build.cpu, build.gpu, build.ram, build.mode, "1440p"
            )

        # Save changes
        build.save()
        messages.success(request, "Build updated successfully.")
        return redirect("saved_builds")

    # GET: render form
    context = {
        "build": build,
        # Pre-sort dropdowns by price desc (highest first)
        "cpus": CPU.objects.order_by("-price"),
        "gpus": GPU.objects.order_by("-price"),
        "mobos": Motherboard.objects.order_by("-price"),
        "rams": RAM.objects.order_by("-price"),
        "cases": Case.objects.order_by("-price"),
        "psus": PSU.objects.order_by("-price"),
        "coolers": CPUCooler.objects.order_by("-price"),
        "storages": Storage.objects.order_by("-price"),
    }
    return render(request, "calculator/edit_build.html", context)


# Tokens and endpoints
GITHUB_TOKEN_MINI = os.getenv("GITHUB_TOKEN_MINI") or os.getenv("GITHUB_TOKEN")
GITHUB_TOKEN_FULL = os.getenv("GITHUB_TOKEN_FULL") or os.getenv("GITHUB_TOKEN")

ENDPOINTS = {
    "gpt-4.1-mini": (
        "https://models.inference.ai.azure.com/openai/deployments/"
        "gpt-4.1-mini/chat/completions"
    ),
    "gpt-4.1": (
        "https://models.inference.ai.azure.com/openai/deployments/"
        "gpt-4.1/chat/completions"
    ),
}


def select_token(model: str) -> str:
    return GITHUB_TOKEN_MINI if model == "gpt-4.1-mini" else GITHUB_TOKEN_FULL


# -----------------------------
# Canned responses
# -----------------------------
CANNED_RESPONSES = {
    "ram not compatible": (
        "RAM DDR generation must match the motherboard DDR generation. "
        "DDR4 will not fit DDR5 slots."
    ),
    "cpu not compatible": (
        "Check socket type: CPUs must match the motherboard socket "
        "(e.g., AM5 vs LGA1700)."
    ),
    "gpu bottleneck": (
        "Ensure your CPU and GPU are balanced. A weak CPU can "
        "bottleneck a powerful GPU."
    ),
    "psu wattage": (
        "Your PSU must provide enough wattage for all components. "
        "Add ~20% headroom for stability."
    ),
    "cooler clearance": (
        "Large air coolers may not fit in small cases. "
        "Always check case clearance specs."
    ),
    "case size": (
        "Ensure your case supports your motherboard form factor "
        "(ATX, Micro‑ATX, Mini‑ITX)."
    ),
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
        f"Answer the user question as a short, readable numbered list "
        f"of steps. "
        f"Keep the response under {max_chars} characters.\n\n"
        f"User question: {message}"
    )

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
    }

    try:
        resp = requests.post(
            endpoint, headers=headers, json=payload, timeout=(10, 90)
        )
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

        #  Correct field based on your raw JSON
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
            ai_text = call_ai(user_message, "gpt-4.1") or call_ai(
                user_message, "gpt-4.1-mini"
            )
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
            videos.append(
                {
                    "title": item["snippet"]["title"],
                    "url": (
                        "https://www.youtube.com/watch?v="
                        + item["id"]["videoId"]
                    ),
                }
            )

        return JsonResponse({"reply": ai_text, "videos": videos})
