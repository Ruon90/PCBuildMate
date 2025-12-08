import os
import json
import requests
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from .forms import BudgetForm
from .models import CPU, GPU, Motherboard, RAM, Storage, PSU, CPUCooler, Case, UserBuild, CurrencyRate
from .services.build_calculator import (
    find_best_build,
)
import traceback
from allauth.account.forms import SignupForm, LoginForm
from django.views.decorators.http import require_POST
from .services.build_calculator import (
    auto_assign_parts,
    compatible_cpu_mobo,
    compatible_mobo_ram,
    compatible_mobo_ram_cached,
    compatible_storage,
    compatible_case,
    compatible_case_cached,
    psu_ok,
    psu_ok_cached,
    cooler_ok,
    total_price,
    weighted_scores,
)
from .services.build_calculator import cpu_score, gpu_score, ram_score
from .services.build_calculator import (
    estimate_fps,
    estimate_fps_components,
    cpu_bottleneck,
    estimate_render_time,
)
from django.views.decorators.csrf import csrf_exempt
from types import SimpleNamespace

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
            storage_capacity_pref = form.cleaned_data.get("storage_capacity") or ""
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
            except Exception as e:
                # Log traceback to console for debugging and return a JSON error for the AJAX caller
                tb = traceback.format_exc()
                print("[ERROR] Exception in find_best_build:\n", tb)
                return JsonResponse({"error": "Internal error while calculating build. See server logs."}, status=500)

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
                    # persist the resolution the user selected for the calculation
                    "resolution": resolution,
                    # and the converted budget used for calculation (in USD)
                    "budget_usd": float(budget_usd),
                    "mode": mode,
                    "score": float(best.total_score),
                    # prices from models are in USD
                    "price": float(best.total_price),
                }
                # Persist top alternatives (2..11) in session so user can view/choose them later.
                try:
                    from .services import build_calculator as bc
                    candidates = getattr(bc, 'LAST_CANDIDATES', []) or []

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

                        # extract per-game FPS for the resolution the user selected
                        fps_summary = {}
                        try:
                            for g in ("Cyberpunk 2077", "CS2", "Fortnite"):
                                entry = cand.fps_estimates.get(g, {})
                                res_entry = entry.get(resolution, {}) if isinstance(entry, dict) else {}
                                fps_summary[g] = {
                                    'overall': res_entry.get('estimated_fps') or
                                               res_entry.get('estimated', None),
                                    'cpu': res_entry.get('cpu_fps'),
                                    'gpu': res_entry.get('gpu_fps'),
                                }
                        except Exception:
                            fps_summary = {}

                        alts.append({
                            'cpu': cand.cpu.id,
                            'gpu': cand.gpu.id,
                            'motherboard': cand.motherboard.id,
                            'ram': cand.ram.id,
                            'storage': cand.storage.id,
                            'psu': cand.psu.id,
                            'cooler': cand.cooler.id,
                            'case': cand.case.id,
                            'price': float(cand.total_price),
                            'score': float(cand.total_score),
                            'bottleneck_type': getattr(cand, 'bottleneck_type', None),
                            'bottleneck_pct': getattr(cand, 'bottleneck_pct', None),
                            'fps': fps_summary,
                        })

                        if len(alts) >= 10:
                            break

                    request.session['preview_alternatives'] = alts
                except Exception:
                    # do not fail the API if alternatives collection fails
                    request.session['preview_alternatives'] = []
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

    # Compute per-resolution FPS estimates and bottleneck readout for the preview build.
    mode = build_data.get("mode", "gaming") or "gaming"
    # If the user previously chose a resolution, use it as the default active tab
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
            perf[res] = {"bottleneck": binfo, "workstation": {"Blender BMW Render (seconds)": render_sec}}
            continue

        res_games = {}
        for g in games:
            try:
                cpu_fps, gpu_fps = estimate_fps_components(cpu, gpu, mode, res, g)
                overall = round(min(cpu_fps, gpu_fps), 1)
                res_games[g] = {"overall": overall, "cpu": cpu_fps, "gpu": gpu_fps}
            except Exception:
                res_games[g] = {"overall": None, "cpu": None, "gpu": None}

        try:
            binfo = cpu_bottleneck(cpu, gpu, mode, res)
        except Exception:
            binfo = {"bottleneck": 0.0, "type": "unknown"}

        perf[res] = {"bottleneck": binfo, "games": res_games}

    # Keep top-level keys for backward compatibility with templates expecting them
    fps_estimates = perf.get(default_resolution, {}).get("games", {})
    bottleneck_info = perf.get(default_resolution, {}).get("bottleneck", {"bottleneck": 0.0, "type": "unknown"})

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
        "perf": perf,
        "default_resolution": default_resolution,
        "fps_estimates": fps_estimates,
        "bottleneck": bottleneck_info,
    })


def alternatives(request):
    """Show the top alternative builds (stored in session by the calculator).

    GET: render alternatives page showing up to 10 alternatives.
    """
    alts = request.session.get('preview_alternatives', []) or []
    if not alts:
        messages.info(request, "No alternative builds are available. Calculate a build first.")
        return redirect('build_preview')

    rendered = []
    for idx, a in enumerate(alts):
        try:
            rendered.append({
                'index': idx,
                'cpu': get_object_or_404(CPU, pk=a['cpu']),
                'gpu': get_object_or_404(GPU, pk=a['gpu']),
                'motherboard': get_object_or_404(Motherboard, pk=a['motherboard']),
                'ram': get_object_or_404(RAM, pk=a['ram']),
                'storage': get_object_or_404(Storage, pk=a['storage']),
                'psu': get_object_or_404(PSU, pk=a['psu']),
                'cooler': get_object_or_404(CPUCooler, pk=a['cooler']),
                'case': get_object_or_404(Case, pk=a['case']),
                'price': a.get('price'),
                'score': a.get('score'),
                'bottleneck_type': a.get('bottleneck_type'),
                'bottleneck_pct': a.get('bottleneck_pct'),
                'fps': a.get('fps', {}),
            })
        except Exception:
            # skip alternatives that reference missing components
            continue

    return render(request, 'calculator/alternatives.html', {'alternatives': rendered})


@require_POST
def select_alternative(request):
    """Replace the session preview with the selected alternative (by index).

    POST params: alt_index (int)
    """
    try:
        idx = int(request.POST.get('alt_index', -1))
    except Exception:
        idx = -1
    alts = request.session.get('preview_alternatives', []) or []
    if idx < 0 or idx >= len(alts):
        messages.error(request, "Invalid alternative selected.")
        return redirect('alternatives')

    sel = alts[idx]
    # preserve user's budget/currency/mode/resolution if present in existing preview
    prev = request.session.get('preview_build', {})
    preview = {
        'cpu': sel['cpu'], 'gpu': sel['gpu'], 'motherboard': sel['motherboard'],
        'ram': sel['ram'], 'storage': sel['storage'], 'psu': sel['psu'],
        'cooler': sel['cooler'], 'case': sel['case'],
        'price': sel.get('price'), 'score': sel.get('score'),
        'budget': prev.get('budget'), 'currency': prev.get('currency', 'USD'),
        'mode': prev.get('mode', 'gaming'), 'resolution': prev.get('resolution', '1440p'),
        'budget_usd': prev.get('budget_usd'),
    }
    request.session['preview_build'] = preview
    messages.success(request, "Preview replaced with selected alternative.")
    return redirect('build_preview')


def upgrade_calculator(request):
    """Upgrade calculator: given a preview or saved build and a budget, find
    incremental upgrades that improve component benchmarks while remaining
    compatible and within the provided budget.

    This implements a greedy single-pass selection: it scores candidate
    upgrades by (score_delta / price_delta) and picks the best ones until
    budget is exhausted. It prefers to keep the original case and attempts
    to maintain compatibility for motherboard when possible.
    """

    # This upgrade calculator takes a user-specified build (all components must be selected)
    # Provide component querysets for the dropdowns on GET and validate the submitted IDs on POST.
    cpus_qs = CPU.objects.all()
    gpus_qs = GPU.objects.all()
    mobos_qs = Motherboard.objects.all()
    rams_qs = RAM.objects.all()
    storages_qs = Storage.objects.all()
    psus_qs = PSU.objects.all()
    coolers_qs = CPUCooler.objects.all()
    cases_qs = Case.objects.all()

    # default mode (can be overridden by a form field)
    mode = 'gaming'

    if request.method == 'POST':
        # If the user clicked "Use this build" for a proposed upgrade, apply it.
        if request.POST.get('proposed_index') is not None:
            try:
                idx = int(request.POST.get('proposed_index'))
                proposals = request.session.get('last_upgrade_proposals', []) or []
                if idx < 0 or idx >= len(proposals):
                    messages.error(request, 'Invalid proposed build selected.')
                    return redirect('upgrade_calculator')
                sel = proposals[idx]
                # Build preview structure from proposal (preserve user's budget/currency/mode/resolution)
                prev = request.session.get('preview_build', {})
                preview = {
                    'cpu': sel.get('cpu'), 'gpu': sel.get('gpu'), 'motherboard': sel.get('motherboard'),
                    'ram': sel.get('ram'), 'storage': sel.get('storage'), 'psu': sel.get('psu'),
                    'cooler': sel.get('cooler'), 'case': sel.get('case'),
                    'price': None, 'score': None,
                    'budget': prev.get('budget'), 'currency': prev.get('currency', 'USD'),
                    'mode': prev.get('mode', 'gaming'), 'resolution': prev.get('resolution', '1440p'),
                    'budget_usd': prev.get('budget_usd'),
                }
                request.session['preview_build'] = preview
                messages.success(request, 'Preview replaced with selected upgrade build.')
                return redirect('build_preview')
            except Exception:
                messages.error(request, 'Could not apply selected proposed build.')
                return redirect('upgrade_calculator')
        # parse upgrade budget
        try:
            budget = float(request.POST.get('upgrade_budget') or 0)
        except Exception:
            budget = 0.0

        # Require the user to have selected every component in the form (separate from preview flow)
        required_parts = ['cpu', 'gpu', 'motherboard', 'ram', 'storage', 'psu', 'cooler', 'case']
        missing = [p for p in required_parts if not request.POST.get(p)]
        if missing:
            messages.error(request, 'Please select every component (CPU, GPU, motherboard, RAM, storage, PSU, cooler and case) before running the upgrade calculator.')
            return render(request, 'calculator/upgrade_calculator.html', {
                'cpus': cpus_qs, 'gpus': gpus_qs, 'mobos': mobos_qs, 'rams': rams_qs,
                'storages': storages_qs, 'psus': psus_qs, 'coolers': coolers_qs, 'cases': cases_qs,
            })

        # Load the submitted components from the POST payload
        try:
            cur_cpu = get_object_or_404(CPU, pk=int(request.POST.get('cpu')))
            cur_gpu = get_object_or_404(GPU, pk=int(request.POST.get('gpu')))
            cur_mobo = get_object_or_404(Motherboard, pk=int(request.POST.get('motherboard')))
            cur_ram = get_object_or_404(RAM, pk=int(request.POST.get('ram')))
            cur_storage = get_object_or_404(Storage, pk=int(request.POST.get('storage')))
            cur_psu = get_object_or_404(PSU, pk=int(request.POST.get('psu')))
            cur_cooler = get_object_or_404(CPUCooler, pk=int(request.POST.get('cooler')))
            cur_case = get_object_or_404(Case, pk=int(request.POST.get('case')))
        except Exception:
            messages.error(request, 'One or more selected components could not be found. Please correct your selections.')
            return render(request, 'calculator/upgrade_calculator.html', {
                'cpus': cpus_qs, 'gpus': gpus_qs, 'mobos': mobos_qs, 'rams': rams_qs,
                'storages': storages_qs, 'psus': psus_qs, 'coolers': coolers_qs, 'cases': cases_qs,
            })

        mode = request.POST.get('mode', 'gaming') or 'gaming'

        # Prepare baseline totals for price comparisons
        def price_of(obj):
            try:
                return float(getattr(obj, 'price', 0) or 0)
            except Exception:
                return 0.0

        base_total = (
            price_of(cur_cpu) + price_of(cur_gpu) + price_of(cur_mobo) + price_of(cur_ram)
            + price_of(cur_storage) + price_of(cur_psu) + price_of(cur_cooler) + price_of(cur_case)
        )

        # helpers to compute score
        def part_score(obj, part_type):
            try:
                if part_type == 'cpu':
                    return cpu_score(obj, mode)
                if part_type == 'gpu':
                    return gpu_score(obj, mode)
                if part_type == 'ram':
                    return ram_score(obj)
            except Exception:
                return 0.0
            return 0.0

        cur_cpu_score = part_score(cur_cpu, 'cpu')
        cur_gpu_score = part_score(cur_gpu, 'gpu')

        # We'll collect best proposals keyed to cpu id and gpu id to ensure uniqueness
        cpu_best = {}
        gpu_best = {}

        # Gather CPU proposals (CPU alone or CPU+motherboard(+ram) if required)
        for cand in CPU.objects.filter(price__isnull=False).order_by('price'):
            try:
                cand_s = part_score(cand, 'cpu')
                if cand_s <= cur_cpu_score:
                    continue

                # Start with keeping current mobo/ram
                total = base_total - price_of(cur_cpu) + price_of(cand)
                swapped_mobo = None
                swapped_ram = None

                if not compatible_cpu_mobo(cand, cur_mobo):
                    # find cheapest compatible motherboard
                    cheapest_mobo = None
                    for m in Motherboard.objects.filter(price__isnull=False).order_by('price'):
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
                    # ensure RAM compat: if current RAM incompatible with new mobo, find cheapest compatible ram
                    if not compatible_mobo_ram_cached(cheapest_mobo, cur_ram):
                        cheapest_ram = None
                        for r in RAM.objects.filter(price__isnull=False).order_by('price'):
                            try:
                                if compatible_mobo_ram_cached(cheapest_mobo, r):
                                    cheapest_ram = r
                                    break
                            except Exception:
                                continue
                        if not cheapest_ram:
                            # cannot find RAM for this mobo -> skip
                            continue
                        total += price_of(cheapest_ram) - price_of(cur_ram)
                        swapped_ram = cheapest_ram

                    # Check PSU: CPU upgrade may require a stronger PSU when paired with current GPU
                    swapped_psu = None
                    try:
                        if not psu_ok_cached(cur_psu, cand, cur_gpu):
                            # find cheapest PSU that satisfies requirements for cand + current GPU
                            for p in PSU.objects.filter(price__isnull=False).order_by('price'):
                                try:
                                    if psu_ok_cached(p, cand, cur_gpu):
                                        swapped_psu = p
                                        break
                                except Exception:
                                    continue
                            if not swapped_psu:
                                # no PSU available to support this CPU + current GPU
                                continue
                            total += price_of(swapped_psu) - price_of(cur_psu)
                    except Exception:
                        # if psu check fails, be conservative and skip this candidate
                        continue

                price_delta = total - base_total
                if price_delta <= 0 or price_delta > budget:
                    continue

                percent = ((cand_s - cur_cpu_score) / cur_cpu_score) * 100.0 if cur_cpu_score > 0 else 0.0
                # store only best proposal per cpu id (highest percent)
                prev = cpu_best.get(cand.id)
                proposal = {
                    'slot': 'cpu',
                    'cpu': cand,
                    'motherboard': swapped_mobo or cur_mobo,
                    'ram': swapped_ram or cur_ram,
                    'gpu': cur_gpu, 'storage': cur_storage, 'psu': swapped_psu or cur_psu, 'cooler': cur_cooler, 'case': cur_case,
                    'percent': percent,
                    'total_price': total,
                    'price_delta': price_delta,
                }
                if not prev or proposal['percent'] > prev['percent']:
                    cpu_best[cand.id] = proposal
            except Exception:
                continue

        # Gather GPU proposals (GPU alone)
        for cand in GPU.objects.filter(price__isnull=False).order_by('price'):
            try:
                cand_s = part_score(cand, 'gpu')
                # Exclude Blackwell GPUs in gaming mode per user preference
                if mode == 'gaming':
                    try:
                        name_hint = " ".join(filter(None, [getattr(cand, 'generation', ''), getattr(cand, 'model', ''), getattr(cand, 'gpu_name', '')]))
                        if 'blackwell' in name_hint.lower():
                            continue
                    except Exception:
                        pass
                if cand_s <= cur_gpu_score:
                    continue
                total = base_total - price_of(cur_gpu) + price_of(cand)

                # Check PSU: GPU upgrade may require a stronger PSU for current CPU
                swapped_psu = None
                try:
                    if not psu_ok_cached(cur_psu, cur_cpu, cand):
                        for p in PSU.objects.filter(price__isnull=False).order_by('price'):
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

                price_delta = total - base_total
                if price_delta <= 0 or price_delta > budget:
                    continue
                percent = ((cand_s - cur_gpu_score) / cur_gpu_score) * 100.0 if cur_gpu_score > 0 else 0.0
                prev = gpu_best.get(cand.id)
                proposal = {
                    'slot': 'gpu',
                    'gpu': cand,
                    'cpu': cur_cpu, 'motherboard': cur_mobo, 'ram': cur_ram,
                    'storage': cur_storage, 'psu': swapped_psu or cur_psu, 'cooler': cur_cooler, 'case': cur_case,
                    'percent': percent,
                    'total_price': total,
                    'price_delta': price_delta,
                }
                if not prev or proposal['percent'] > prev['percent']:
                    gpu_best[cand.id] = proposal
            except Exception:
                continue

        # Build combined CPU+GPU proposals from the best cpu and gpu candidates (limit to top 10 of each)
        cpu_list = sorted(cpu_best.values(), key=lambda x: -x['percent'])[:10]
        gpu_list = sorted(gpu_best.values(), key=lambda x: -x['percent'])[:10]
        combo_best = {}
        for cprop in cpu_list:
            for gprop in gpu_list:
                try:
                    total = base_total
                    # replace cpu (+mobo/ram if present in cprop)
                    total = total - price_of(cur_cpu) - price_of(cur_mobo) - price_of(cur_ram)
                    total += price_of(cprop['cpu']) + price_of(cprop['motherboard']) + price_of(cprop['ram'])
                    # replace gpu
                    total = total - price_of(cur_gpu) + price_of(gprop['gpu'])

                    # Check PSU for combined CPU+GPU proposal
                    swapped_psu = None
                    try:
                        if not psu_ok_cached(cur_psu, cprop['cpu'], gprop['gpu']):
                            for p in PSU.objects.filter(price__isnull=False).order_by('price'):
                                try:
                                    if psu_ok_cached(p, cprop['cpu'], gprop['gpu']):
                                        swapped_psu = p
                                        break
                                except Exception:
                                    continue
                            if not swapped_psu:
                                # cannot source a PSU to support this combined upgrade
                                continue
                            total += price_of(swapped_psu) - price_of(cur_psu)
                    except Exception:
                        continue

                    price_delta = total - base_total
                    if price_delta <= 0 or price_delta > budget:
                        continue
                    # combined percent: average of cpu and gpu percent (simple heuristic)
                    percent = (cprop['percent'] + gprop['percent']) / 2.0
                    key = (cprop['cpu'].id, gprop['gpu'].id)
                    proposal = {
                        'slot': 'cpu_gpu',
                        'cpu': cprop['cpu'], 'motherboard': cprop['motherboard'], 'ram': cprop['ram'],
                        'gpu': gprop['gpu'], 'storage': cur_storage, 'psu': swapped_psu or cur_psu, 'cooler': cur_cooler, 'case': cur_case,
                        'percent': percent,
                        'total_price': total,
                        'price_delta': price_delta,
                    }
                    combo_best[key] = proposal
                except Exception:
                    continue

        # Assemble final proposals in the requested order:
        # 1) up to 2 combined CPU+GPU proposals (best percent),
        # 2) up to 2 GPU-only proposals (best percent, excluding GPUs already used),
        # 3) up to 2 CPU-only proposals (best percent, excluding CPUs already used).
        final = []
        used_cpus = set()
        used_gpus = set()

        combo_list = sorted(combo_best.values(), key=lambda x: -x['percent'])
        cpu_list_sorted = sorted(cpu_best.values(), key=lambda x: -x['percent'])
        gpu_list_sorted = sorted(gpu_best.values(), key=lambda x: -x['percent'])

        # Add up to 2 combined cpu+gpu proposals
        for item in combo_list:
            if len(final) >= 2:
                break
            final.append(item)
            used_cpus.add(getattr(item.get('cpu'), 'id', None))
            used_gpus.add(getattr(item.get('gpu'), 'id', None))

        # Add up to 2 GPU-only proposals excluding GPUs already included
        for item in gpu_list_sorted:
            if len([p for p in final if p.get('slot') == 'cpu_gpu']) >= 0:  # no-op but keeps grouping clear
                pass
            if len([p for p in final if p.get('slot') == 'gpu']) >= 2:
                break
            gid = getattr(item.get('gpu'), 'id', None)
            if gid in used_gpus:
                continue
            final.append(item)
            used_gpus.add(gid)

        # Add up to 2 CPU-only proposals excluding CPUs already included
        for item in cpu_list_sorted:
            if len([p for p in final if p.get('slot') == 'cpu']) >= 2:
                break
            cid = getattr(item.get('cpu'), 'id', None)
            if cid in used_cpus:
                continue
            final.append(item)
            used_cpus.add(cid)

        proposals = final

        # Save serializable proposals so the user can "use" a proposed build in a follow-up POST
        serial = []
        for p in proposals:
            serial.append({
                'slot': p.get('slot'),
                'cpu': getattr(p.get('cpu'), 'id', None),
                'gpu': getattr(p.get('gpu'), 'id', None),
                'motherboard': getattr(p.get('motherboard'), 'id', None),
                'ram': getattr(p.get('ram'), 'id', None),
                'storage': getattr(p.get('storage'), 'id', None),
                'psu': getattr(p.get('psu'), 'id', None),
                'cooler': getattr(p.get('cooler'), 'id', None),
                'case': getattr(p.get('case'), 'id', None),
                'percent': float(p.get('percent') or 0.0),
                'total_price': float(p.get('total_price') or 0.0),
                'price_delta': float(p.get('price_delta') or 0.0),
            })
        request.session['last_upgrade_proposals'] = serial

        # convert proposals into structure the template expects
        proposed_builds = []
        for p in proposals:
            # Build human-friendly display strings to avoid showing object reprs in templates
            def disp(obj):
                try:
                    if obj is None:
                        return "<None>"
                    return getattr(obj, 'name', None) or getattr(obj, 'gpu_name', None) or getattr(obj, 'model', None) or str(obj)
                except Exception:
                    return str(obj)

            display = {
                'cpu': disp(p.get('cpu')),
                'gpu': disp(p.get('gpu')),
                'motherboard': disp(p.get('motherboard')),
                'ram': disp(p.get('ram')),
                'storage': disp(p.get('storage')),
                'psu': disp(p.get('psu')),
                'cooler': disp(p.get('cooler')),
                'case': disp(p.get('case')),
            }

            proposed_builds.append({
                'slot': p.get('slot'),
                'build': p,
                'display': display,
                'percent': p.get('percent'),
                'total_price': p.get('total_price'),
                'price_delta': p.get('price_delta'),
            })

        remaining = budget

        return render(request, 'calculator/upgrade_calculator.html', {
            'cpus': cpus_qs, 'gpus': gpus_qs, 'mobos': mobos_qs, 'rams': rams_qs,
            'storages': storages_qs, 'psus': psus_qs, 'coolers': coolers_qs, 'cases': cases_qs,
            'current': {
                'cpu': cur_cpu, 'gpu': cur_gpu, 'motherboard': cur_mobo, 'ram': cur_ram,
                'storage': cur_storage, 'psu': cur_psu, 'cooler': cur_cooler, 'case': cur_case,
            },
            'proposed_builds': proposed_builds,
            'budget': budget,
            'remaining': remaining,
            'mode': mode,
        })

    # GET: show blank form (user will select every component)
    return render(request, 'calculator/upgrade_calculator.html', {
        'cpus': cpus_qs, 'gpus': gpus_qs, 'mobos': mobos_qs, 'rams': rams_qs,
        'storages': storages_qs, 'psus': psus_qs, 'coolers': coolers_qs, 'cases': cases_qs,
        'mode': mode,
    })

def preview_edit(request):
    """Unified edit page for the session preview build (GET shows form, POST applies changes).

    This replaces the per-component modal flow. The view tries to apply permissive
    auto-swaps where sensible and reports any auto-swaps via Django messages.
    """

    preview = request.session.get('preview_build')
    if not preview:
        messages.error(request, "No preview build in session. Calculate a build first.")
        return redirect('build_preview')

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
    cpu = load_obj('cpu', CPU) or get_object_or_404(CPU, pk=preview.get('cpu'))
    gpu = load_obj('gpu', GPU) or get_object_or_404(GPU, pk=preview.get('gpu'))
    mobo = load_obj('motherboard', Motherboard) or get_object_or_404(
        Motherboard, pk=preview.get('motherboard')
    )
    ram = load_obj('ram', RAM) or get_object_or_404(RAM, pk=preview.get('ram'))
    storage = load_obj('storage', Storage) or get_object_or_404(
        Storage, pk=preview.get('storage')
    )
    psu = load_obj('psu', PSU) or get_object_or_404(PSU, pk=preview.get('psu'))
    cooler = load_obj('cooler', CPUCooler) or get_object_or_404(
        CPUCooler, pk=preview.get('cooler')
    )
    case = load_obj('case', Case) or get_object_or_404(Case, pk=preview.get('case'))

    if request.method == 'POST':
        # Read submitted selections (fall back to existing preview values)
        sel = {
            'cpu': int(request.POST.get('cpu') or preview.get('cpu')),
            'gpu': int(request.POST.get('gpu') or preview.get('gpu')),
            'motherboard': int(request.POST.get('motherboard') or preview.get('motherboard')),
            'ram': int(request.POST.get('ram') or preview.get('ram')),
            'storage': int(request.POST.get('storage') or preview.get('storage')),
            'psu': int(request.POST.get('psu') or preview.get('psu')),
            'cooler': int(request.POST.get('cooler') or preview.get('cooler')),
            'case': int(request.POST.get('case') or preview.get('case')),
        }

        # Load the selected objects
        try:
            new_cpu = get_object_or_404(CPU, pk=sel['cpu'])
            new_gpu = get_object_or_404(GPU, pk=sel['gpu'])
            new_mobo = get_object_or_404(Motherboard, pk=sel['motherboard'])
            new_ram = get_object_or_404(RAM, pk=sel['ram'])
            new_storage = get_object_or_404(Storage, pk=sel['storage'])
            new_psu = get_object_or_404(PSU, pk=sel['psu'])
            new_cooler = get_object_or_404(CPUCooler, pk=sel['cooler'])
            new_case = get_object_or_404(Case, pk=sel['case'])
        except Exception:
            messages.error(request, "One or more selected components could not be found.")
            return redirect('preview_edit')

        auto_swaps = []

        # CPU <-> Motherboard compatibility
        if not compatible_cpu_mobo(new_cpu, new_mobo):
            # prefer swapping motherboard to match CPU (try a matching mobo)
            candidates = Motherboard.objects.order_by('-price')[:200]
            candidate = next((mb for mb in candidates if compatible_cpu_mobo(new_cpu, mb)
                              and compatible_mobo_ram(mb, new_ram)), None)
            if candidate:
                new_mobo = candidate
                auto_swaps.append(f"motherboard -> {candidate.name} (auto-swapped to match selected CPU)")
            else:
                # try swapping CPU to match motherboard
                candidates = CPU.objects.order_by('-price')[:200]
                candidate = next((c for c in candidates if compatible_cpu_mobo(c, new_mobo)), None)
                if candidate:
                    new_cpu = candidate
                    auto_swaps.append(f"cpu -> {candidate.name} (auto-swapped to match selected motherboard)")
                else:
                    messages.error(request, "Selected CPU and motherboard are incompatible and no compatible alternative was found.")
                    return redirect('preview_edit')

        # Motherboard <-> RAM compatibility
        if not compatible_mobo_ram(new_mobo, new_ram):
            candidates = RAM.objects.order_by('-price')[:200]
            candidate = next((r for r in candidates if compatible_mobo_ram(new_mobo, r)), None)
            if candidate:
                new_ram = candidate
                auto_swaps.append(f"ram -> {candidate.name} (auto-swapped to match selected motherboard)")
            else:
                # try swapping motherboard to match RAM
                candidates = Motherboard.objects.order_by('-price')[:150]
                candidate = next((mb for mb in candidates if compatible_mobo_ram(mb, new_ram)), None)
                if candidate:
                    new_mobo = candidate
                    auto_swaps.append(f"motherboard -> {candidate.name} (auto-swapped to match selected RAM)")
                else:
                    messages.error(request, "Selected motherboard and RAM are incompatible and no compatible alternative was found.")
                    return redirect('preview_edit')

        # Motherboard <-> Storage
        if new_storage and not compatible_storage(new_mobo, new_storage):
            messages.error(request, "Selected storage is not compatible with the selected motherboard.")
            return redirect('preview_edit')

        # Case compatibility with motherboard
        if new_mobo and not compatible_case(new_mobo, new_case):
            messages.error(request, "Selected case is not compatible with the selected motherboard.")
            return redirect('preview_edit')

        # Cooler compatibility
        if not cooler_ok(new_cooler, new_cpu):
            messages.error(request, "Selected cooler is not sufficient for the selected CPU.")
            return redirect('preview_edit')

        # PSU <-> CPU+GPU
        if not psu_ok(new_psu, new_cpu, new_gpu):
            # try to upgrade PSU
            candidates = PSU.objects.order_by('-wattage')[:150]
            candidate = next((p for p in candidates if psu_ok(p, new_cpu, new_gpu)), None)
            if candidate:
                new_psu = candidate
                auto_swaps.append(f"psu -> {candidate.name} (auto-swapped to provide sufficient wattage)")
            else:
                # try downgrading GPU to fit PSU
                candidates = GPU.objects.order_by('-price')[:200]
                candidate = next((g for g in candidates if psu_ok(new_psu, new_cpu, g)), None)
                if candidate:
                    new_gpu = candidate
                    auto_swaps.append(f"gpu -> {candidate.gpu_name} (auto-swapped to fit selected PSU)")
                else:
                    messages.error(request, "Selected PSU cannot support the selected CPU+GPU and no alternative was found.")
                    return redirect('preview_edit')

        # Persist new selections back to session
        mapping = {
            'cpu': new_cpu.pk,
            'gpu': new_gpu.pk,
            'motherboard': new_mobo.pk,
            'ram': new_ram.pk,
            'storage': new_storage.pk,
            'psu': new_psu.pk,
            'cooler': new_cooler.pk,
            'case': new_case.pk,
        }
        preview.update(mapping)

        # Recompute price and score
        try:
            parts_list = [
                get_object_or_404(CPU, pk=preview['cpu']),
                get_object_or_404(GPU, pk=preview['gpu']),
                get_object_or_404(Motherboard, pk=preview['motherboard']),
                get_object_or_404(RAM, pk=preview['ram']),
                get_object_or_404(Storage, pk=preview['storage']),
                get_object_or_404(PSU, pk=preview['psu']),
                get_object_or_404(CPUCooler, pk=preview['cooler']),
                get_object_or_404(Case, pk=preview['case']),
            ]
            preview['price'] = float(total_price(parts_list))
            preview['score'] = float(
                weighted_scores(parts_list[0], parts_list[1], parts_list[3], preview.get('mode'), '1440p')
            )
        except Exception:
            pass

        request.session['preview_build'] = preview

        messages.success(request, "Preview updated successfully.")
        for note in auto_swaps:
            messages.info(request, note)

        return redirect('build_preview')

    # GET: render edit form using the current selected parts
    context = {
        'build': SimpleNamespace(
            cpu=cpu, gpu=gpu, motherboard=mobo, ram=ram, storage=storage,
            psu=psu, cooler=cooler, case=case, currency=preview.get('currency', 'USD')
        ),
        'cpus': CPU.objects.order_by('-price'),
        'gpus': GPU.objects.order_by('-price'),
        'mobos': Motherboard.objects.order_by('-price'),
        'rams': RAM.objects.order_by('-price'),
        'cases': Case.objects.order_by('-price'),
        'psus': PSU.objects.order_by('-price'),
        'coolers': CPUCooler.objects.order_by('-price'),
        'storages': Storage.objects.order_by('-price'),
    }
    return render(request, 'calculator/preview_edit.html', context)

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
            _ = b.cpu and b.gpu and b.motherboard and b.ram and b.storage and b.psu and b.cooler and b.case
            valid_builds.append(b)
        except Exception:
            # If any related object was deleted or is inconsistent, skip this build
            skipped += 1

    if skipped:
        messages.warning(request, f"{skipped} saved build(s) were skipped because they reference missing components. Please edit or delete those builds.")

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
        # Pre-sort dropdowns by price desc (highest first)
        "cpus": CPU.objects.order_by('-price'),
        "gpus": GPU.objects.order_by('-price'),
        "mobos": Motherboard.objects.order_by('-price'),
        "rams": RAM.objects.order_by('-price'),
        "cases": Case.objects.order_by('-price'),
        "psus": PSU.objects.order_by('-price'),
        "coolers": CPUCooler.objects.order_by('-price'),
        "storages": Storage.objects.order_by('-price'),
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
    

