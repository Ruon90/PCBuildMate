from dataclasses import dataclass, field
from typing import List, Dict
from collections import defaultdict
import re
from hardware.models import CPU, GPU, Motherboard, RAM, Storage, PSU, CPUCooler, Case

HEADROOM_RATIO = 0.30

RES_WEIGHTS = {
    "1080p": {"cpu": 1.2, "gpu": 1.1},
    "1440p": {"cpu": 1.0, "gpu": 1.0},
    "4k":    {"cpu": 0.8, "gpu": 1.3},
}

PER_CPU_BUILD_LIMIT = 1
SECOND_PASS_CPU_K = 10
SECOND_PASS_GPU_K = 6
SECOND_PASS_RAM_N = 5
SECOND_PASS_PER_CPU_LIMIT = 1

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
    bottleneck_pct: float
    bottleneck_type: str
    fps_estimates: Dict[str, Dict[str, float]] = field(default_factory=dict)
    workstation_estimates: Dict[str, float] = field(default_factory=dict)

# --- Scoring ---
def cpu_score(cpu, mode: str) -> float:
    return float(getattr(cpu, "blender_score", 0) or 0) if mode == "workstation" else float(getattr(cpu, "userbenchmark_score", 0) or 0)

def gpu_score(gpu, mode: str) -> float:
    return float(getattr(gpu, "blender_score", 0) or 0) if mode == "workstation" else float(getattr(gpu, "userbenchmark_score", 0) or 0)

def ram_score(ram) -> float:
    return float(getattr(ram, "benchmark", 0) or 0)

def weighted_scores(cpu, gpu, ram, mode: str, resolution: str) -> float:
    w = RES_WEIGHTS.get(resolution, RES_WEIGHTS["1440p"])
    ram_component = min(ram_score(ram), 130)
    return cpu_score(cpu, mode) * w["cpu"] + gpu_score(gpu, mode) * w["gpu"] + ram_component

def cpu_bottleneck(cpu, gpu, mode: str, resolution: str) -> dict:
    # Compute resolution-specific FPS contributions and derive bottleneck from them.
    # Use a representative game from the baseline list to estimate relative impact.
    try:
        rep_game = next(iter(BASELINE_FPS.keys()))
    except Exception:
        rep_game = None

    if rep_game:
        try:
            cpu_fps, gpu_fps = estimate_fps_components(cpu, gpu, mode, resolution, rep_game)
            if cpu_fps <= 0 or gpu_fps <= 0:
                return {"bottleneck": 0.0, "type": "unknown"}
            ratio = cpu_fps / gpu_fps
            if ratio < 1:
                raw = round((1 - ratio) * 100, 1)
                # present a less aggressive bottleneck percentage (user requested ~half)
                return {"bottleneck": round(raw / 2.0, 1), "type": "CPU"}
            else:
                raw = round((1 - (1 / ratio)) * 100, 1)
                return {"bottleneck": round(raw / 2.0, 1), "type": "GPU"}
        except Exception:
            # fallback to score-based heuristic if FPS estimation fails
            pass

    # Fallback: use weighted score heuristic
    cpu_s = cpu_score(cpu, mode)
    gpu_s = gpu_score(gpu, mode)
    w = RES_WEIGHTS.get(resolution, RES_WEIGHTS["1440p"])
    cpu_eff = cpu_s * w["cpu"]
    gpu_eff = gpu_s * w["gpu"]
    if cpu_eff == 0 or gpu_eff == 0:
        return {"bottleneck": 0.0, "type": "unknown"}
    ratio = cpu_eff / gpu_eff
    if ratio < 1:
        raw = round((1 - ratio) * 100, 1)
        return {"bottleneck": round(raw / 2.0, 1), "type": "CPU"}
    else:
        raw = round((1 - (1 / ratio)) * 100, 1)
        return {"bottleneck": round(raw / 2.0, 1), "type": "GPU"}

# --- Compatibility (normalized) ---
def norm(s):
    """Normalize socket / interface strings to a compact alphanumeric form.

    - lowercases
    - strips the word 'socket'
    - removes any non-alphanumeric characters
    This makes matching resilient to formats like 'Socket AM5', 'AM5 ', 'AM5 (sTRX4)'.
    """
    s = str(s or "").lower()
    s = s.replace("socket", "")
    # keep only letters and digits
    s = re.sub(r"[^a-z0-9]", "", s)
    return s

def compatible_cpu_mobo(cpu, mobo) -> bool:
    cpu_socket = norm(getattr(cpu, "socket", None))
    mobo_socket = norm(getattr(mobo, "socket", None))
    # If either side lacks socket metadata, be permissive to avoid dropping
    # valid combos caused by incomplete imports. Log the situation for
    # diagnostics so we can consider a DB cleanup later.
    if not cpu_socket or not mobo_socket:
        print(f"[DEBUG] Missing socket info: CPU={getattr(cpu,'name',getattr(cpu,'model',cpu.id))} socket='{cpu_socket}' Mobo={getattr(mobo,'name',mobo.id)} socket='{mobo_socket}' - treating as compatible")
        return True
    # Allow substring matches so 'am5' matches 'am5strx4' or 'am5x' variants
    socket_match = cpu_socket == mobo_socket or cpu_socket in mobo_socket or mobo_socket in cpu_socket

    # Additional rule: For Intel K-series CPUs (overclockable), prefer Z-series
    # motherboards which are the Intel chipset families that support CPU overclocking.
    # Detect 'K' in the CPU model (e.g., '14900K') and require a Z-series mobo
    # (e.g., 'Z790') when present.
    try:
        cpu_brand = (getattr(cpu, "brand", "") or "").lower()
        cpu_model = (getattr(cpu, "model", "") or getattr(cpu, "name", "") or "").lower()
        is_intel = "intel" in cpu_brand or "intel" in cpu_model
        is_k_series = bool(re.search(r"\d+k\b", cpu_model)) or cpu_model.strip().endswith("k")
        if is_intel and is_k_series:
            if not _mobo_is_z_series(mobo):
                print(f"[DEBUG] Rejecting Mobo={getattr(mobo,'name',mobo.id)} for Intel K-series CPU {getattr(cpu,'model',getattr(cpu,'name',cpu.id))} because it's not a Z-series board")
                return False
    except Exception:
        # If detection fails for any reason, fall back to socket_match
        pass

    return socket_match


def _mobo_is_z_series(mobo) -> bool:
    """Return True if the motherboard name/slug looks like a Z-series (Intel OC) board.

    We look for patterns like 'z790', 'z690', etc. in the normalized name/slug.
    """
    name_norm = norm(getattr(mobo, "name", "") or "")
    slug_norm = norm(getattr(mobo, "slug", "") or "")
    # Match 'z' followed by digits, e.g. z790, z690
    if re.search(r"z\d", name_norm) or re.search(r"z\d", slug_norm):
        return True
    return False

def compatible_mobo_ram(mobo, ram) -> bool:
    """Return True if the motherboard and RAM are compatible.

    Simple rule implemented:
    - If both declare DDR generation, require the generation to match (substring tolerant).
    - If generations match, require RAM frequency <= motherboard ddr_max_speed when the
      motherboard reports one. If mobo.ddr_max_speed is missing, accept the pair.
    - If only one side reports DDR info, try to infer the other from speeds (>=4800 -> ddr5,
      else ddr4). If inference succeeds, apply the same rules. If inference fails, be
      permissive to avoid false negatives for incomplete/imported data.
    """
    mobo_ddr = norm(getattr(mobo, "ddr_version", None))
    ram_ddr = norm(getattr(ram, "ddr_generation", None))

    # numeric speeds
    try:
        mobo_max_val = float(getattr(mobo, "ddr_max_speed", None)) if getattr(mobo, "ddr_max_speed", None) is not None else None
    except Exception:
        mobo_max_val = None
    try:
        ram_freq_val = int(getattr(ram, "frequency_mhz", 0) or 0)
    except Exception:
        ram_freq_val = 0

    def debug_reject(reason: str):
        print(
            f"[DEBUG] incompatible mobo/ram: Mobo={getattr(mobo,'name',mobo.id)} ddr={mobo_ddr} max={mobo_max_val} "
            f"RAM={getattr(ram,'name',ram.id)} ddr={ram_ddr} freq={ram_freq_val} -> {reason}"
        )

    # If both specify generation, require match
    if mobo_ddr and ram_ddr:
        if not (mobo_ddr in ram_ddr or ram_ddr in mobo_ddr):
            debug_reject("generation_mismatch")
            return False
        # generations match; enforce speed if mobo provides it
        if mobo_max_val is None:
            return True
        if ram_freq_val <= mobo_max_val:
            return True
        debug_reject("ram_freq_exceeds_mobo_max")
        return False

    # Try inference when one side lacks explicit generation
    inferred_mobo = None
    inferred_ram = None
    if not mobo_ddr and mobo_max_val is not None:
        inferred_mobo = "ddr5" if mobo_max_val >= 4800 else "ddr4"
    if not ram_ddr and ram_freq_val:
        inferred_ram = "ddr5" if ram_freq_val >= 4800 else "ddr4"

    if inferred_mobo and inferred_ram:
        if inferred_mobo != inferred_ram:
            debug_reject("inferred_generation_mismatch")
            return False
        if mobo_max_val is None:
            return True
        if ram_freq_val <= mobo_max_val:
            return True
        debug_reject("inferred_ram_freq_exceeds_mobo_max")
        return False

    # No decisive info — be permissive but log for diagnostics
    if not mobo_ddr and not inferred_mobo:
        print(f"[DEBUG] Motherboard {getattr(mobo,'name',mobo.id)} has no DDR info and could not be inferred")
    if not ram_ddr and not inferred_ram:
        print(f"[DEBUG] RAM {getattr(ram,'name',ram.id)} has no DDR info and could not be inferred")
    return True

def compatible_storage(mobo, storage) -> bool:
    iface = norm(getattr(storage, "interface", None))
    if "nvme" in iface or "pcie" in iface or "m.2" in iface or "m2" in iface:
        nvme_flag = norm(getattr(mobo, "nvme_support", None))
        # If the motherboard record lacks nvme_support info, be permissive:
        # many modern mobos support NVMe but the field may be empty in the CSV/import.
        if not nvme_flag:
            return True
        return ("pcie" in nvme_flag) or ("nvme" in nvme_flag) or ("m2" in nvme_flag) or ("m.2" in nvme_flag) or (nvme_flag in {"true", "1", "yes", "y"})
    return True

def compatible_case(mobo, case) -> bool:
    mobo_ff = norm(getattr(mobo, "form_factor", None))
    case_ff = norm(getattr(case, "case_type", None))
    if not mobo_ff or not case_ff:
        return False
    if mobo_ff in case_ff or case_ff in mobo_ff:
        return True
    if "atx" in mobo_ff and ("tower" in case_ff or "mid" in case_ff or "full" in case_ff):
        return True
    if "microatx" in mobo_ff and ("atx" in case_ff or "tower" in case_ff or "mini" in case_ff):
        return True
    if "mini" in mobo_ff and ("microatx" in case_ff or "atx" in case_ff or "tower" in case_ff or "mini" in case_ff):
        return True
    return False

def psu_ok(psu, cpu, gpu) -> bool:
    cpu_req = (getattr(cpu, "power_consumption_overclocked", None) or getattr(cpu, "tdp", None) or 0)
    gpu_req = getattr(gpu, "tdp", None) or 0
    required = cpu_req + gpu_req
    wattage = getattr(psu, "wattage", None) or 0
    return bool(wattage and int(wattage) >= int(required * (1 + HEADROOM_RATIO)))

def cooler_ok(cooler, cpu) -> bool:
    required = (getattr(cpu, "power_consumption_overclocked", None) or getattr(cpu, "tdp", None) or 0)
    throughput = float(getattr(cooler, "power_throughput", None) or 0)
    return throughput >= required

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
        mobo_ff = norm(getattr(mobo, "form_factor", None))
        case_ff = norm(getattr(case, "case_type", None))
        print(f"[DEBUG] Checking case compatibility: Mobo={getattr(mobo,'name',mobo.id)}({mobo_ff}) vs Case={getattr(case,'name',case.id)}({case_ff})")
        if mobo_ff in case_ff or case_ff in mobo_ff:
            case_cache[key] = True
        elif "atx" in mobo_ff and ("tower" in case_ff or "mid" in case_ff or "full" in case_ff):
            case_cache[key] = True
        elif "microatx" in mobo_ff and ("atx" in case_ff or "tower" in case_ff or "mini" in case_ff):
            case_cache[key] = True
        elif "mini" in mobo_ff and ("microatx" in case_ff or "atx" in case_ff or "tower" in case_ff or "mini" in case_ff):
            case_cache[key] = True
        else:
            case_cache[key] = False
    return case_cache[key]

def compatible_storage_cached(mobo, storage):
    key = mobo.id
    if key not in storage_cache:
        val = norm(getattr(mobo, "nvme_support", None))
        # Treat missing/empty nvme_support as permissive (assume NVMe ok).
        if not val:
            storage_cache[key] = True
        else:
            # Explicitly look for positive indicators; otherwise False.
            storage_cache[key] = ("pcie" in val) or ("nvme" in val) or ("m.2" in val) or ("m2" in val) or (val in {"true", "1", "yes", "y"})
    iface = norm(getattr(storage, "interface", None))
    if "nvme" in iface or "pcie" in iface or "m.2" in iface or "m2" in iface:
        return storage_cache[key]
    return True  # SATA always works

# --- Prefilter ---
def prefilter_components(cpus, gpus, rams, cases, storages, mobos, psus, coolers, budget, mode: str):
    def valid_price(x): 
        try:
            return x.price is not None and float(x.price) > 0
        except Exception:
            return False
    cpus = [c for c in cpus if valid_price(c)]
    gpus = [g for g in gpus if valid_price(g)]
    rams = [r for r in rams if valid_price(r)]
    cases = [c for c in cases if valid_price(c)]
    storages = [s for s in storages if valid_price(s)]
    mobos = [m for m in mobos if valid_price(m)]
    psus = [p for p in psus if valid_price(p)]
    coolers = [c for c in coolers if valid_price(c)]

    print(f"[DEBUG] After price filter: CPUs={len(cpus)}, GPUs={len(gpus)}, RAMs={len(rams)}, Cases={len(cases)}, Storages={len(storages)}, Mobos={len(mobos)}, PSUs={len(psus)}, Coolers={len(coolers)}")

    # Light PSU quality/wattage screen
    def psu_eff_ok(p):
        eff = (getattr(p, 'efficiency', None) or '').strip().lower()
        return bool(eff and eff not in {'none', ''})

    psus = [p for p in psus if psu_eff_ok(p)]
    print(f"[DEBUG] After efficiency filter: PSUs={len(psus)}")

    def psu_watt_ok(p):
        try:
            return bool(getattr(p, 'wattage') and int(p.wattage) >= 500)
        except Exception:
            return False

    psus = [p for p in psus if psu_watt_ok(p)]
    print(f"[DEBUG] After wattage filter: PSUs={len(psus)}")

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
    if budget < 750:
        rams = [r for r in rams if str(getattr(r, 'ddr_generation', '')).upper() == "DDR4"]

    # Precompute scores
    for cpu in cpus: cpu.cached_score = cpu_score(cpu, mode)
    for gpu in gpus: gpu.cached_score = gpu_score(gpu, mode)
    for ram in rams: ram.cached_score = ram_score(ram)

    # Affordability prefilter
    cpus = [c for c in cpus if c.price and float(c.price) <= budget * 0.9]
    gpus = [g for g in gpus if g.price and float(g.price) <= budget * 0.9]
    rams = [r for r in rams if r.price and float(r.price) <= budget * 0.15]

    # Sort and slice
    sorted_cpus = sorted(cpus, key=lambda c: c.cached_score, reverse=True)[:50]
    sorted_gpus = sorted(gpus, key=lambda g: g.cached_score, reverse=True)[:50]

    # RAM sorting by generation groups
    def ram_generation_value(r):
        gen = (getattr(r, 'ddr_generation', '') or '')
        m = re.search(r"(\d+)", str(gen))
        try:
            return int(m.group(1)) if m else 0
        except Exception:
            return 0

    rams_by_gen = {}
    for r in rams:
        gv = ram_generation_value(r)
        rams_by_gen.setdefault(gv, []).append(r)

    sorted_rams = []
    for gv in sorted(rams_by_gen.keys(), reverse=True):
        group = rams_by_gen[gv]
        group_sorted = sorted(group, key=lambda r: (
            -(getattr(r, 'frequency_mhz', 0) or 0),
            float(getattr(r, 'price', 0) or 0),
            -float(getattr(r, 'cached_score', 0) or 0)
        ))
        sorted_rams.extend(group_sorted)
    sorted_rams = sorted_rams[:30]

    # Storage streamlining: prefer common capacities and sensible price share
    storages = [s for s in storages if getattr(s, 'capacity', None) in (512, 1000, 2000)]
    max_storage_price = budget * 0.40
    storages = [s for s in storages if s.price and float(s.price) <= max_storage_price]
    sorted_storages = sorted(storages, key=lambda s: float(s.price or 0))

    progress = []
    stats = {"trios": 0, "fail_mobo": 0, "fail_storage": 0, "fail_psu": 0, "fail_cooler": 0, "fail_case": 0, "fail_budget": 0}

    def display_name(p):
        if p is None:
            return "<None>"
        return (
            getattr(p, "name", None)
            or getattr(p, "gpu_name", None)
            or getattr(p, "model", None)
            or getattr(p, "brand", None)
            or f"id={getattr(p, 'id', None)}"
        )

    valid_builds_by_cpu = {}
    mobos_for_cpu = {}
    coolers_for_cpu = {}
    cases_for_mobo = {}
    storages_for_mobo = {}

    # Precompute per-CPU mobo/cooler
    # Build a socket -> mobos index so we can avoid scanning the full mobo list per-CPU
    socket_index = defaultdict(list)
    for m in mobos:
        socket_index[norm(getattr(m, "socket", None))].append(m)

    for cpu in sorted_cpus:
        cpu_socket = norm(getattr(cpu, "socket", None))
        candidates = []
        if cpu_socket:
            # gather mobos whose normalized socket equals / contains / is contained by cpu_socket
            for skey, mlist in socket_index.items():
                if not skey:
                    continue
                if cpu_socket == skey or cpu_socket in skey or skey in cpu_socket:
                    candidates.extend(mlist)
        # fallback: if nothing matched, consider all mobos (rare)
        if not candidates:
            candidates = list(mobos)
        # finally filter by the cached compatibility predicate
        mobos_for_cpu[cpu.id] = [m for m in candidates if compatible_cpu_mobo_cached(cpu, m)]

        # Precompute coolers for this CPU
        coolers_for_cpu[cpu.id] = [c for c in coolers if cooler_ok_cached(c, cpu)]

    # Precompute which RAM modules are actually usable per-CPU given the
    # mobos we've indexed for that CPU. This avoids repeatedly trying RAM
    # generations that no motherboard for the CPU can support (e.g. DDR5
    # sticks paired with AM4 mobos). We base this on the (already cached)
    # compatible_mobo_ram predicate.
    # Precompute per-socket maximum reported mobo DDR speed so we can quickly
    # eliminate RAM modules whose frequency exceeds any motherboard available
    # for that CPU socket. This is a lightweight aggregation and a good first
    # step toward moving filters into the DB (we can later translate this to
    # QuerySet annotations).
    socket_max_freq = {}
    for m in mobos:
        sk = norm(getattr(m, "socket", None))
        try:
            val = float(getattr(m, "ddr_max_speed", 0) or 0)
        except Exception:
            val = 0
        socket_max_freq[sk] = max(socket_max_freq.get(sk, 0), val)

    allowed_rams_for_cpu = {}
    for cpu in sorted_cpus:
        mlist = mobos_for_cpu.get(cpu.id, [])
        if not mlist:
            allowed_rams_for_cpu[cpu.id] = []
            continue
        # Only consider the small, pre-sorted RAM list (sorted_rams) for
        # candidate generation — it's already trimmed to the most relevant
        # modules. Additionally, use the per-socket max mobo speed to filter
        # out RAMs that are clearly too fast for any mobo supporting this CPU.
        cpu_socket = norm(getattr(cpu, "socket", None))
        max_for_socket = socket_max_freq.get(cpu_socket)
        if max_for_socket and max_for_socket > 0:
            allowed = [
                r for r in sorted_rams
                if (getattr(r, 'frequency_mhz', 0) or 0) <= max_for_socket
                and any(compatible_mobo_ram_cached(m, r) for m in mlist)
            ]
        else:
            allowed = [r for r in sorted_rams if any(compatible_mobo_ram_cached(m, r) for m in mlist)]
        allowed_rams_for_cpu[cpu.id] = allowed
        if not allowed:
            print(f"[DEBUG] CPU {display_name(cpu)} has no RAM compatible with its indexed mobos (checked {len(mlist)} mobos).")

    # Diagnostics: report mobos with missing socket metadata and CPUs with no mobos
    total_mobos = len(mobos)
    mobos_missing_socket = [m for m in mobos if not norm(getattr(m, "socket", None))]
    if mobos_missing_socket:
        sample = ", ".join(display_name(m) for m in mobos_missing_socket[:5])
        print(f"[DEBUG] Motherboards missing socket ({len(mobos_missing_socket)}/{total_mobos}): {sample}{'...' if len(mobos_missing_socket)>5 else ''}")

    # Report CPUs that ended up with zero compatible mobos
    cpu_no_mobo = [cpu for cpu in sorted_cpus if not mobos_for_cpu.get(cpu.id)]
    if cpu_no_mobo:
        print(f"[DEBUG] CPUs with no compatible mobos: {len(cpu_no_mobo)}")
        for cpu in cpu_no_mobo[:10]:
            # count how many candidate mobos were considered for this CPU before compatibility filter
            cpu_socket = norm(getattr(cpu, "socket", None))
            considered = 0
            if cpu_socket:
                for skey, mlist in socket_index.items():
                    if not skey:
                        continue
                    if cpu_socket == skey or cpu_socket in skey or skey in cpu_socket:
                        considered += len(mlist)
            else:
                considered = total_mobos
            print(f"[DEBUG]  CPU={display_name(cpu)} socket='{cpu_socket}' considered_mobos={considered}")

    # Precompute PSUs compatible per (cpu,gpu) pair to avoid recomputing inside the RAM loop
    psus_for_cpu_gpu = {}
    for cpu in sorted_cpus:
        for gpu in sorted_gpus:
            key = (cpu.id, gpu.id)
            # list of psus that satisfy wattage/efficiency for this cpu+gpu
            psus_for_cpu_gpu[key] = [p for p in psus if psu_ok_cached(p, cpu, gpu)]

    # Precompute cheapest compatible case/storage per mobo
    sorted_cases = sorted(cases, key=lambda c: float(c.price or 0))
    for m in mobos:
        cases_for_mobo[m.id] = next((c for c in sorted_cases if compatible_case_cached(m, c)), None)
        storages_for_mobo[m.id] = next((s for s in sorted_storages if compatible_storage_cached(m, s)), None)

    # Nested generator with access to local state
    def generate_candidates(ram_list, cpu_list=None, gpu_list=None, per_cpu_limit=None, mobos_map=None):
        """Generate build candidates.

        mobos_map: optional dict mapping cpu.id -> list of mobos to consider for that CPU.
        If not provided, the precomputed `mobos_for_cpu` is used.
        This allows a second-pass to restrict mobos to those that support the
        RAM generation being evaluated (e.g., DDR4 pass).
        """
        cpu_iter = cpu_list if cpu_list is not None else sorted_cpus
        gpu_iter = gpu_list if gpu_list is not None else sorted_gpus
        limit = per_cpu_limit if per_cpu_limit is not None else PER_CPU_BUILD_LIMIT

        for cpu in cpu_iter:
            # Use a per-CPU RAM shortlist when available to avoid trying
            # RAM generations that no indexed mobo for the CPU supports.
            ram_iter = allowed_rams_for_cpu.get(cpu.id, ram_list)
            for gpu in gpu_iter:
                for ram in ram_iter:
                    try:
                        stats["trios"] += 1
                        trio_price = (float(cpu.price or 0)) + (float(gpu.price or 0)) + (float(ram.price or 0))
                        if trio_price > float(budget):
                            stats["fail_budget"] += 1
                            continue

                        # Motherboard for CPU + RAM
                        local_mobos_map = mobos_map if mobos_map is not None else mobos_for_cpu
                        # find the cheapest compatible mobo without allocating an intermediate list
                        try:
                            mobo = min(
                                (m for m in local_mobos_map.get(cpu.id, []) if compatible_mobo_ram_cached(m, ram)),
                                key=lambda m: float(m.price or 0),
                            )
                        except ValueError:
                            stats["fail_mobo"] += 1
                            # Detailed diagnostics: list mobos that were considered for this CPU
                            print(f"[DEBUG] No compatible mobo for CPU={display_name(cpu)}, RAM={display_name(ram)}")
                            considered = local_mobos_map.get(cpu.id, [])
                            if considered:
                                print(f"[DEBUG]   Considered {len(considered)} mobos for CPU {display_name(cpu)}:")
                                for m in considered[:10]:
                                    m_name = display_name(m)
                                    m_socket = norm(getattr(m, 'socket', None))
                                    m_ddr = getattr(m, 'ddr_version', None)
                                    m_ddr_max = getattr(m, 'ddr_max_speed', None)
                                    compat = compatible_mobo_ram_cached(m, ram)
                                    print(f"[DEBUG]     Mobo={m_name} socket={m_socket} ddr_version={m_ddr} ddr_max_speed={m_ddr_max} -> compatible_mobo_ram={compat}")
                                if len(considered) > 10:
                                    print(f"[DEBUG]     ... and {len(considered)-10} more mobos considered")
                            else:
                                print(f"[DEBUG]   No mobos were indexed for CPU {display_name(cpu)} (socket may be missing or unmatched).")
                            continue

                        # Storage for mobo
                        storage = storages_for_mobo.get(mobo.id)
                        if not storage:
                            stats["fail_storage"] += 1
                            print(f"[DEBUG] No storage for Mobo={display_name(mobo)}")
                            continue

                        # PSU for CPU+GPU: use precomputed compat map to avoid repeating checks
                        psu_list = psus_for_cpu_gpu.get((cpu.id, gpu.id), [])
                        if not psu_list:
                            stats["fail_psu"] += 1
                            print(f"[DEBUG] No PSU for CPU={display_name(cpu)}, GPU={display_name(gpu)}")
                            continue
                        # choose the cheapest compatible PSU (no temporary list allocation)
                        try:
                            psu = min((p for p in psu_list), key=lambda p: float(p.price or 0))
                        except ValueError:
                            stats["fail_psu"] += 1
                            print(f"[DEBUG] No PSU for CPU={display_name(cpu)}, GPU={display_name(gpu)}")
                            continue

                        # Cooler for CPU
                        coolers_compat = coolers_for_cpu.get(cpu.id, [])
                        if not coolers_compat:
                            stats["fail_cooler"] += 1
                            print(f"[DEBUG] No cooler for CPU={display_name(cpu)}")
                            continue
                        cooler = min(coolers_compat, key=lambda c: float(c.price or 0))

                        # Case for mobo
                        case = cases_for_mobo.get(mobo.id)
                        if not case:
                            stats["fail_case"] += 1
                            print(f"[DEBUG] No case for Mobo={display_name(mobo)}")
                            continue

                        # Build candidate
                        parts = [cpu, gpu, mobo, ram, storage, psu, cooler, case]
                        price = total_price(parts)
                        if price <= float(budget):
                            score = weighted_scores(cpu, gpu, ram, mode, resolution)
                            bottleneck_info = cpu_bottleneck(cpu, gpu, mode, resolution)
                            candidate = BuildCandidate(
                                cpu=cpu, gpu=gpu, motherboard=mobo, ram=ram,
                                storage=storage, psu=psu, cooler=cooler, case=case,
                                total_price=price, total_score=score,
                                bottleneck_pct=bottleneck_info["bottleneck"],
                                bottleneck_type=bottleneck_info["type"]
                            )
                            if mode == "gaming":
                                fps_dict = {}
                                for game in BASELINE_FPS.keys():
                                    cpu_fps, gpu_fps = estimate_fps_components(cpu, gpu, mode, resolution, game)
                                    est = round(min(cpu_fps, gpu_fps), 1)
                                    fps_dict[game] = {
                                        resolution: {
                                            "cpu_fps": cpu_fps,
                                            "gpu_fps": gpu_fps,
                                            "estimated_fps": est,
                                        }
                                    }
                                candidate.fps_estimates = fps_dict
                            elif mode == "workstation":
                                candidate.workstation_estimates = {
                                    "Blender BMW Render (seconds)": estimate_render_time(cpu, gpu, mode, baseline_time=120)
                                }

                            bucket = valid_builds_by_cpu.setdefault(cpu.id, [])
                            bucket.append(candidate)
                            bucket.sort(key=lambda b: b.total_score, reverse=True)
                            if len(bucket) > limit:
                                del bucket[limit:]

                            flat_count = sum(len(v) for v in valid_builds_by_cpu.values())
                            if flat_count >= 50:
                                print(f"[DEBUG] Reached global candidate cap (50). Stats={stats}")
                                return
                    except Exception:
                        import traceback
                        print("[ERROR] Exception while evaluating trio:")
                        try:
                            print(f" CPU={display_name(cpu)} id={getattr(cpu,'id',None)}, GPU={display_name(gpu)} id={getattr(gpu,'id',None)}, RAM={display_name(ram)} id={getattr(ram,'id',None)}")
                        except Exception:
                            pass
                        traceback.print_exc()
                        stats["fail_exception"] = stats.get("fail_exception", 0) + 1
                        continue

                flat_count = sum(len(v) for v in valid_builds_by_cpu.values())
                if flat_count >= 40:
                    print("[DEBUG] Breaking GPU loop, candidates >= 40.")
                    break

            flat_count = sum(len(v) for v in valid_builds_by_cpu.values())
            if flat_count >= 30:
                print("[DEBUG] Breaking CPU loop, candidates >= 30.")
                break

        print(f"[DEBUG] Stats summary: {stats}")

    # First pass
    generate_candidates(sorted_rams)

    # DDR4 comparative pass if many DDR5 builds already exist
    def ram_generation_value_from_obj(r):
        gen = (getattr(r, 'ddr_generation', '') or '')
        m = re.search(r"(\d+)", str(gen))
        try:
            return int(m.group(1)) if m else 0
        except Exception:
            return 0

    flat_valid_builds = [b for bucket in valid_builds_by_cpu.values() for b in bucket]
    ddr5_count = sum(1 for b in flat_valid_builds if ram_generation_value_from_obj(b.ram) >= 5)

    if budget >= 750 and ddr5_count >= 20:
        rams_ddr4 = [r for r in rams if ram_generation_value(r) == 4]
        rams_ddr4_sorted = sorted(rams_ddr4, key=lambda r: (
            -(getattr(r, 'frequency_mhz', 0) or 0),
            float(getattr(r, 'price', 0) or 0),
            -float(getattr(r, 'cached_score', 0) or 0)
        ))[:SECOND_PASS_RAM_N]
        if rams_ddr4_sorted:
            cpu_sub = sorted_cpus[:SECOND_PASS_CPU_K]
            gpu_sub = sorted_gpus[:SECOND_PASS_GPU_K]
            # Precompute, for this second-pass, the subset of mobos per CPU that can support DDR4
            mobos_for_cpu_ddr4 = {}
            for cpu in cpu_sub:
                mobos_for_cpu_ddr4[cpu.id] = [m for m in mobos_for_cpu.get(cpu.id, []) if any(compatible_mobo_ram_cached(m, r) for r in rams_ddr4_sorted)]

            for cpu in cpu_sub:
                bucket = valid_builds_by_cpu.get(cpu.id, [])
                ddr5_per_cpu = sum(1 for b in bucket if ram_generation_value_from_obj(b.ram) >= 5)
                if ddr5_per_cpu < 2:
                    generate_candidates(
                        rams_ddr4_sorted,
                        cpu_list=[cpu],
                        gpu_list=gpu_sub,
                        per_cpu_limit=SECOND_PASS_PER_CPU_LIMIT,
                        mobos_map=mobos_for_cpu_ddr4,
                    )

    # Flatten and select best
    flat_valid_builds = [b for bucket in valid_builds_by_cpu.values() for b in bucket]
    # Expose the flattened candidate list for callers that want alternatives
    try:
        # create a stable-sorted list by score (descending)
        LAST_CANDIDATES = sorted(flat_valid_builds, key=lambda b: b.total_score, reverse=True)
    except Exception:
        LAST_CANDIDATES = flat_valid_builds

    if flat_valid_builds:
        best_build = max(flat_valid_builds, key=lambda b: b.total_score)
        progress.append(f"Selected best build out of {len(flat_valid_builds)} candidates.")

        # Debug output for the selected build: component names and key estimates
        try:
            print("[DEBUG] Selected build summary:")
            print(f"  Total price: {best_build.total_price}")
            print(f"  Total score: {best_build.total_score}")
            print(f"  Bottleneck: {best_build.bottleneck_type} ({best_build.bottleneck_pct}%)")
            # component names
            print("  Components:")
            print(f"    CPU: {display_name(best_build.cpu)}")
            print(f"    GPU: {display_name(best_build.gpu)}")
            print(f"    Motherboard: {display_name(best_build.motherboard)}")
            print(f"    RAM: {display_name(best_build.ram)}")
            print(f"    Storage: {display_name(best_build.storage)}")
            print(f"    PSU: {display_name(best_build.psu)}")
            print(f"    Cooler: {display_name(best_build.cooler)}")
            print(f"    Case: {display_name(best_build.case)}")

            # Estimates
            print(f"  FPS estimates: {best_build.fps_estimates}")
            print(f"  Workstation estimates: {best_build.workstation_estimates}")
        except Exception:
            # Never fail on debug printing
            import traceback
            print("[DEBUG] Failed to print selected build details:")
            traceback.print_exc()

        # attach LAST_CANDIDATES to the module so callers (views) can read them
        try:
            globals()['LAST_CANDIDATES'] = LAST_CANDIDATES
        except Exception:
            globals()['LAST_CANDIDATES'] = flat_valid_builds
        return best_build, progress

    progress.append("No valid build found within budget.")
    # Debug: when no build is found, print stats for investigation
    try:
        print("[DEBUG] No valid build found. Stats summary:")
        print(f"  {stats}")
    except Exception:
        pass
    # Ensure LAST_CANDIDATES is present even when no build found
    globals()['LAST_CANDIDATES'] = []
    return None, progress

# --- Gaming FPS estimation ---
# Baseline FPS table now contains both GPU and CPU baselines per game.
# This lets you configure a baseline FPS for a representative GPU *and*
# a representative CPU. estimate_fps_components will use the matching
# baseline FPS (gpu baseline for GPU side, cpu baseline for CPU side)
# and then scale by the component scores.
BASELINE_FPS = {
    "Cyberpunk 2077": {
        "gpu": {"rtx_3060": 60, "rtx_4070": 90, "rtx_5080": 140},
        "cpu": {"5800x3d": 65, "13600k": 95, "14900k": 140},
    },
    "CS2": {
        "gpu": {"rtx_3060": 200, "rtx_4070": 300, "rtx_5080": 450},
        "cpu": {"5800x3d": 593, "13600k": 350, "14900k": 700},
    },
    "Fortnite": {
        "gpu": {"rtx_3060": 120, "rtx_4070": 180, "rtx_5080": 280},
        "cpu": {"5800x3d": 110, "13600k": 170, "14900k": 260},
    },
}
GPU_BASELINE_SCORES = {"rtx_3060": 42, "rtx_4070": 80, "rtx_5080": 139}

# CPU baseline mapping (configurable). These are representative scores used to
# scale CPU contribution to FPS. Tune as needed for your dataset.
CPU_BASELINE_SCORES = {
    "5800x3d": 104,   # AMD Ryzen 7 5800X3D (example baseline)
    "13600k": 122,   # Intel Core i5-13600K (example baseline)
    "14900k": 131,   # Intel Core i9-14900K (example baseline)
}

def pick_cpu_baseline(cpu_s):
    """Pick a CPU baseline name for a given cpu score.

    Works similarly to pick_baseline for GPUs: returns one of the keys in
    CPU_BASELINE_SCORES based on thresholds derived from the scores.
    """
    try:
        if cpu_s < CPU_BASELINE_SCORES["13600k"]:
            return "5800x3d"
        if cpu_s < CPU_BASELINE_SCORES["14900k"]:
            return "13600k"
        return "14900k"
    except Exception:
        return "5800x3d"

def pick_baseline(gpu_s):
    if gpu_s < GPU_BASELINE_SCORES["rtx_4070"]:
        return "rtx_3060"
    elif gpu_s < GPU_BASELINE_SCORES["rtx_5080"]:
        return "rtx_4070"
    else:
        return "rtx_5080"

def estimate_fps(cpu, gpu, mode: str, resolution: str, game: str) -> float:
    # Return the final estimated FPS (min of CPU and GPU contributions)
    cpu_fps, gpu_fps = estimate_fps_components(cpu, gpu, mode, resolution, game)
    return round(min(cpu_fps, gpu_fps), 1)


def estimate_fps_components(cpu, gpu, mode: str, resolution: str, game: str) -> tuple:
    """Return (cpu_fps, gpu_fps) estimates for a given game/resolution.

    These are computed against the baseline FPS table. Caller can take the min()
    to get an overall estimated FPS or use both values to reason about bottlenecks.
    """
    gpu_s = gpu_score(gpu, mode)
    cpu_s = cpu_score(cpu, mode)
    baseline_gpu = pick_baseline(gpu_s)
    baseline_score = GPU_BASELINE_SCORES.get(baseline_gpu, 1)
    # support new BASELINE_FPS layout: {game: {"gpu": {...}, "cpu": {...}}}
    game_entry = BASELINE_FPS.get(game, {})
    if isinstance(game_entry, dict) and "gpu" in game_entry:
        baseline_fps_gpu = game_entry.get("gpu", {}).get(baseline_gpu, 60)
    else:
        # backward compatibility with older flat mapping
        baseline_fps_gpu = (game_entry or {}).get(baseline_gpu, 60) if isinstance(game_entry, dict) else 60

    res_factor = {"1080p": 1.0, "1440p": 0.75, "4k": 0.5}.get(resolution, 0.75)
    try:
        gpu_fps = baseline_fps_gpu * (gpu_s / max(baseline_score, 1)) * res_factor
    except Exception:
        gpu_fps = 0.0
    try:
        # CPU-side baseline FPS (mirror GPU approach)
        cpu_baseline = pick_cpu_baseline(cpu_s)
        cpu_baseline_score = CPU_BASELINE_SCORES.get(cpu_baseline, 5000)
        if isinstance(game_entry, dict) and "cpu" in game_entry:
            baseline_fps_cpu = game_entry.get("cpu", {}).get(cpu_baseline, baseline_fps_gpu)
        else:
            baseline_fps_cpu = baseline_fps_gpu
        cpu_fps = baseline_fps_cpu * (cpu_s / max(cpu_baseline_score, 1)) * res_factor
    except Exception:
        cpu_fps = 0.0
    return (round(cpu_fps, 1), round(gpu_fps, 1))

# --- Workstation render estimation ---
CPU_BASELINE_SCORE = 675
GPU_BASELINE_SCORE = 14952

def estimate_render_time(cpu, gpu, mode: str, baseline_time: int = 120) -> float:
    cpu_s = cpu_score(cpu, mode)
    gpu_s = gpu_score(gpu, mode)
    cpu_time = baseline_time * (CPU_BASELINE_SCORE / max(cpu_s, 1))
    gpu_time = baseline_time * (GPU_BASELINE_SCORE / max(gpu_s, 1))
    return round(max(cpu_time, gpu_time), 1)

def auto_assign_parts(budget, mode="gaming", resolution="1440p"):
    """
    Given a budget, return the best build candidate dict using the calculator logic.
    """
    cpus = CPU.objects.all()
    gpus = GPU.objects.all()
    mobos = Motherboard.objects.all()
    rams = RAM.objects.all()
    storages = Storage.objects.all()
    psus = PSU.objects.all()
    coolers = CPUCooler.objects.all()
    cases = Case.objects.all()

    best_build, progress = find_best_build(
        budget, mode, resolution,
        cpus, gpus, mobos, rams, storages, psus, coolers, cases
    )
    if not best_build:
        return None, progress  # no valid build found

    result = {
        "cpu": best_build.cpu,
        "gpu": best_build.gpu,
        "motherboard": best_build.motherboard,
        "ram": best_build.ram,
        "storage": best_build.storage,
        "psu": best_build.psu,
        "cooler": best_build.cooler,
        "case": best_build.case,
        "total_price": best_build.total_price,
        "total_score": best_build.total_score,
        "bottleneck_pct": best_build.bottleneck_pct,
        "bottleneck_type": best_build.bottleneck_type,
        "fps_estimates": best_build.fps_estimates,
        "workstation_estimates": best_build.workstation_estimates,
    }
    return result, progress
