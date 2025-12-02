from dataclasses import dataclass
from typing import List

HEADROOM_RATIO = 0.30

RES_WEIGHTS = {
    "1080p": {"cpu": 1.2, "gpu": 0.9},
    "1440p": {"cpu": 1.0, "gpu": 1.0},
    "4k":    {"cpu": 0.7, "gpu": 1.3},
}

@dataclass
class BuildCandidate:
    cpu: object
    gpu: object
    motherboard: object
    ram: object
    storage: object
    psu: object
    cooler: object
    case: object
    total_price: float
    total_score: float

# --- Scoring ---
def cpu_score(cpu, mode: str) -> float:
    return float(getattr(cpu, "blender_score", 0) or 0) if mode == "workstation" else float(getattr(cpu, "userbenchmark_score", 0) or 0)

def gpu_score(gpu, mode: str) -> float:
    return float(getattr(gpu, "blender_score", 0) or 0) if mode == "workstation" else float(getattr(gpu, "userbenchmark_score", 0) or 0)

def ram_score(ram) -> float:
    return float(getattr(ram, "benchmark", 0) or 0)

def weighted_scores(cpu, gpu, ram, mode: str, resolution: str) -> float:
    w = RES_WEIGHTS.get(resolution, RES_WEIGHTS["1440p"])
    ram_component = min(ram_score(ram), 100)  # cap RAM influence
    return cpu_score(cpu, mode) * w["cpu"] + gpu_score(gpu, mode) * w["gpu"] + ram_component

# --- Compatibility ---
def compatible_cpu_mobo(cpu, mobo) -> bool:
    return bool(cpu.socket and mobo.socket and (cpu.socket in mobo.socket or mobo.socket in cpu.socket))

def compatible_mobo_ram(mobo, ram) -> bool:
    if not mobo.ddr_version or not ram.ddr_generation:
        return False
    version_match = (mobo.ddr_version in ram.ddr_generation) or (ram.ddr_generation in mobo.ddr_version)
    speed_ok = ram.frequency_mhz <= (mobo.ddr_max_speed or 99999)
    return version_match and speed_ok

def compatible_storage(mobo, storage) -> bool:
    iface = (storage.interface or "").lower()
    if "nvme" in iface:
        return str(getattr(mobo, "nvme_support", "")).lower() == "true"
    return True

def compatible_case(mobo, case) -> bool:
    if not mobo.form_factor or not case.case_type:
        return False
    mobo_ff = mobo.form_factor.lower()
    case_ff = case.case_type.lower()
    if mobo_ff in case_ff or case_ff in mobo_ff:
        return True
    if "microatx" in mobo_ff and "atx" in case_ff:
        return True
    if "mini" in mobo_ff and ("microatx" in case_ff or "atx" in case_ff):
        return True
    return False

def psu_ok(psu, cpu, gpu) -> bool:
    required = (cpu.power_consumption_overclocked or cpu.tdp or 0) + (gpu.tdp or 0)
    return bool(psu.wattage and psu.wattage >= int(required * (1 + HEADROOM_RATIO)))

def cooler_ok(cooler, cpu) -> bool:
    required = cpu.power_consumption_overclocked or cpu.tdp or 0
    return float(cooler.power_throughput or 0) >= required

# --- Utility ---
def total_price(parts: List[object]) -> float:
    return sum(float(getattr(p, "price") or 0) for p in parts if p is not None)

# --- Caches ---
cpu_mobo_cache, mobo_ram_cache, psu_cache, cooler_cache, case_cache, storage_cache = {}, {}, {}, {}, {}, {}

def compatible_cpu_mobo_cached(cpu, mobo):
    key = (cpu.id, mobo.id)
    if key not in cpu_mobo_cache:
        cpu_mobo_cache[key] = compatible_cpu_mobo(cpu, mobo)
    return cpu_mobo_cache[key]

def compatible_mobo_ram_cached(mobo, ram):
    key = (mobo.id, ram.id)
    if key not in mobo_ram_cache:
        mobo_ram_cache[key] = compatible_mobo_ram(mobo, ram)
    return mobo_ram_cache[key]

def psu_ok_cached(psu, cpu, gpu):
    key = (psu.id, cpu.id, gpu.id)
    if key not in psu_cache:
        psu_cache[key] = psu_ok(psu, cpu, gpu)
    return psu_cache[key]

def cooler_ok_cached(cooler, cpu):
    key = (cooler.id, cpu.id)
    if key not in cooler_cache:
        cooler_cache[key] = cooler_ok(cooler, cpu)
    return cooler_cache[key]

def compatible_case_cached(mobo, case):
    key = (mobo.id, case.id)
    if key not in case_cache:
        mobo_ff = (mobo.form_factor or "").lower().replace(" ", "")
        case_ff = (case.case_type or "").lower().replace(" ", "")

        # Debug print to see what we're comparing
        print(f"[DEBUG] Checking case compatibility: Mobo={mobo.name}({mobo_ff}) vs Case={case.name}({case_ff})")

        # Direct substring match
        if mobo_ff in case_ff or case_ff in mobo_ff:
            case_cache[key] = True
        # Looser rules: ATX mobos fit any tower case
        elif "atx" in mobo_ff and "tower" in case_ff:
            case_cache[key] = True
        # microATX mobos fit ATX cases
        elif "microatx" in mobo_ff and "atx" in case_ff:
            case_cache[key] = True
        # mini mobos fit microATX/ATX/tower cases
        elif "mini" in mobo_ff and ("microatx" in case_ff or "atx" in case_ff or "tower" in case_ff):
            case_cache[key] = True
        else:
            case_cache[key] = False

    return case_cache[key]

def compatible_storage_cached(mobo, storage):
    key = mobo.id
    if key not in storage_cache:
        storage_cache[key] = str(getattr(mobo, "nvme_support", "")).lower() == "true"

    iface = (storage.interface or "").lower()
    # Accept NVMe or any PCIe Gen variant
    if "nvme" in iface or "pcie" in iface:
        return storage_cache[key]
    return True  # SATA always works


# --- Prefilter ---
def prefilter_components(cpus, gpus, rams, cases, storages, mobos, psus, coolers, budget, mode: str):
    def valid_price(x): return x.price is not None and float(x.price) > 0
    cpus = [c for c in cpus if valid_price(c)]
    gpus = [g for g in gpus if valid_price(g)]
    rams = [r for r in rams if valid_price(r)]
    cases = [c for c in cases if valid_price(c)]
    storages = [s for s in storages if valid_price(s)]
    mobos = [m for m in mobos if valid_price(m)]
    psus = [p for p in psus if valid_price(p)]
    coolers = [c for c in coolers if valid_price(c)]
    return cpus, gpus, rams, cases, storages, mobos, psus, coolers

# --- Build logic ---
def find_best_build(
    budget, mode, resolution,
    cpus, gpus, mobos, rams, storages, psus, coolers, cases
):
    print("Starting build calculation...")

    cpus, gpus, rams, cases, storages, mobos, psus, coolers = prefilter_components(
        cpus, gpus, rams, cases, storages, mobos, psus, coolers, budget, mode
    )

    # DDR4 filter for low budgets
    if budget < 1150:
        rams = [r for r in rams if str(r.ddr_generation).upper() == "DDR4"]

    # Precompute scores
    for cpu in cpus: cpu.cached_score = cpu_score(cpu, mode)
    for gpu in gpus: gpu.cached_score = gpu_score(gpu, mode)
    for ram in rams: ram.cached_score = ram_score(ram)

    # Dynamic N and sort keys
    if budget < 800:
        cpu_n, gpu_n, ram_n = 65, 65, 15
        sort_key_cpu = lambda c: c.cached_score / float(c.price or 1)
        sort_key_gpu = lambda g: g.cached_score / float(g.price or 1)
    elif budget < 1200:
        cpu_n, gpu_n, ram_n = 50, 50, 12
        sort_key_cpu = lambda c: c.cached_score / float(c.price or 1)
        sort_key_gpu = lambda g: g.cached_score / float(g.price or 1)
    else:
        cpu_n, gpu_n, ram_n = 25, 25, 10
        sort_key_cpu = lambda c: c.cached_score
        sort_key_gpu = lambda g: g.cached_score

    # Filter by affordability first
    cpus = [c for c in cpus if c.price and float(c.price) <= budget * 0.3]
    gpus = [g for g in gpus if g.price and float(g.price) <= budget * 0.4]
    rams = [r for r in rams if r.price and float(r.price) <= budget * 0.15]

    # Sort and slice
    sorted_cpus = sorted(cpus, key=sort_key_cpu, reverse=True)[:cpu_n]
    sorted_gpus = sorted(gpus, key=sort_key_gpu, reverse=True)[:gpu_n]
    sorted_rams = sorted(rams, key=lambda r: r.cached_score, reverse=True)[:ram_n]

    # Streamline storage
    max_storage_price = budget * 0.40
    storages = [s for s in storages if s.price and s.price <= max_storage_price]
    storages = sorted(storages, key=lambda s: float(s.price or 0))

    progress = []
    stats = {"trios": 0, "fail_mobo": 0, "fail_storage": 0, "fail_psu": 0,
             "fail_cooler": 0, "fail_case": 0, "fail_budget": 0}

    valid_builds = []

    for cpu in sorted_cpus:
        for gpu in sorted_gpus:
            for ram in sorted_rams:
                stats["trios"] += 1
                trio_price = (float(cpu.price or 0)) + (float(gpu.price or 0)) + (float(ram.price or 0))
                if trio_price > float(budget):
                    stats["fail_budget"] += 1
                    continue

                mobos_compat = [m for m in mobos if compatible_cpu_mobo_cached(cpu, m) and compatible_mobo_ram_cached(m, ram)]
                if not mobos_compat:
                    stats["fail_mobo"] += 1
                    continue
                mobo = min(mobos_compat, key=lambda m: float(m.price or 0))

                storage = next((s for s in storages if compatible_storage_cached(mobo, s)), None)
                if not storage:
                    stats["fail_storage"] += 1
                    continue

                psus_compat = [p for p in psus if psu_ok_cached(p, cpu, gpu)]
                if not psus_compat:
                    stats["fail_psu"] += 1
                    continue
                psu = min(psus_compat, key=lambda p: float(p.price or 0))

                coolers_compat = [c for c in coolers if cooler_ok_cached(c, cpu)]
                if not coolers_compat:
                    stats["fail_cooler"] += 1
                    continue
                cooler = min(coolers_compat, key=lambda c: float(c.price or 0))

                cases_compat = [c for c in cases if compatible_case_cached(mobo, c)]
                if not cases_compat:
                    stats["fail_case"] += 1
                    continue
                case = min(cases_compat, key=lambda c: float(c.price or 0))

                parts = [cpu, gpu, mobo, ram, storage, psu, cooler, case]
                price = total_price(parts)

                if price <= float(budget):
                    score = weighted_scores(cpu, gpu, ram, mode, resolution)
                    candidate = BuildCandidate(cpu, gpu, mobo, ram, storage, psu, cooler, case, price, score)
                    valid_builds.append(candidate)

                    #  Stop once we have 20 builds
                    if len(valid_builds) >= 20:
                        break
            if len(valid_builds) >= 20:
                break
        if len(valid_builds) >= 20:
            break

    if valid_builds:
        # Pick the build with the highest score
        best_build = max(valid_builds, key=lambda b: b.total_score)
        progress.append(f"Selected best build out of {len(valid_builds)} candidates.")
        return best_build, progress

    progress.append("No valid build found within budget.")
    return None, progress
