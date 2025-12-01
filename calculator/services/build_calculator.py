from dataclasses import dataclass
from typing import Optional, List

HEADROOM_RATIO = 0.30

RES_WEIGHTS = {
    "1080p": {"cpu": 1.2, "gpu": 0.9},
    "1440p": {"cpu": 1.0, "gpu": 1.0},
    "4k": {"cpu": 0.7, "gpu": 1.3},
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


# --- Scoring functions ---
def cpu_score(cpu, mode: str) -> float:
    score = float(cpu.blender_score or 0) if mode == "workstation" else float(cpu.userbenchmark_score or 0)
    print(f"CPU {getattr(cpu, 'name', cpu)} scored {score}")
    return score

def gpu_score(gpu, mode: str) -> float:
    score = float(gpu.blender_score or 0) if mode == "workstation" else float(gpu.userbenchmark_score or 0)
    print(f"GPU {getattr(gpu, 'gpu_name', gpu)} scored {score}")
    return score

def ram_score(ram) -> float:
    score = float(ram.benchmark or 0)
    print(f"RAM {getattr(ram, 'name', ram)} scored {score}")
    return score

def weighted_scores(cpu, gpu, ram, mode: str, resolution: str) -> float:
    w = RES_WEIGHTS[resolution]
    score = cpu_score(cpu, mode) * w["cpu"] + gpu_score(gpu, mode) * w["gpu"] + ram_score(ram)
    print(f"Weighted score for build: {score}")
    return score


# --- Compatibility checks ---
def compatible_cpu_mobo(cpu, mobo) -> bool:
    if not cpu.socket or not mobo.socket:
        print(f"CPU {getattr(cpu, 'name', cpu)} or Mobo {getattr(mobo, 'name', mobo)} missing socket -> False")
        return False
    result = (cpu.socket in mobo.socket) or (mobo.socket in cpu.socket)
    print(f"CPU {cpu.name} socket {cpu.socket} vs Mobo {mobo.name} socket {mobo.socket} -> {result}")
    return result

def compatible_mobo_ram(mobo, ram) -> bool:
    if not mobo.ddr_version or not ram.ddr_generation:
        print(f"Mobo {getattr(mobo, 'name', mobo)} or RAM {getattr(ram, 'name', ram)} missing DDR info -> False")
        return False
    version_match = (mobo.ddr_version in ram.ddr_generation) or (ram.ddr_generation in mobo.ddr_version)
    speed_ok = ram.frequency_mhz <= (mobo.ddr_max_speed or 99999)
    result = version_match and speed_ok
    print(f"RAM {ram.name} DDR {ram.ddr_generation} @ {ram.frequency_mhz}MHz vs Mobo {mobo.name} DDR {mobo.ddr_version} max {mobo.ddr_max_speed}MHz -> {result}")
    return result

def compatible_storage(mobo, storage) -> bool:
    if storage.interface and "nvme" in storage.interface.lower():
        result = str(mobo.nvme_support).lower() == "true"
        print(f"Storage {storage.name} interface {storage.interface} vs Mobo {mobo.name} NVMe support {mobo.nvme_support} -> {result}")
        return result
    print(f"Storage {storage.name} interface {storage.interface} assumed compatible -> True")
    return True

def compatible_case(mobo, case) -> bool:
    if not mobo.form_factor or not case.case_type:
        print(f"Mobo {getattr(mobo, 'name', mobo)} or Case {getattr(case, 'name', case)} missing form factor -> False")
        return False

    mobo_ff = mobo.form_factor.lower()
    case_ff = case.case_type.lower()

    if mobo_ff in case_ff or case_ff in mobo_ff:
        print(f"Mobo {mobo.name} form {mobo.form_factor} vs Case {case.name} type {case.case_type} -> True (substring match)")
        return True

    if "microatx" in mobo_ff and "atx" in case_ff:
        print(f"Mobo {mobo.name} MicroATX fits in Case {case.name} ATX -> True")
        return True

    if "mini" in mobo_ff and ("microatx" in case_ff or "atx" in case_ff):
        print(f"Mobo {mobo.name} Mini-ITX fits in Case {case.name} MicroATX/ATX -> True")
        return True

    print(f"Mobo {mobo.name} form {mobo.form_factor} vs Case {case.name} type {case.case_type} -> False")
    return False

def psu_ok(psu, cpu, gpu) -> bool:
    required = (cpu.power_consumption_overclocked or cpu.tdp or 0) + (gpu.tdp or 0)
    result = psu.wattage and psu.wattage >= int(required * (1 + HEADROOM_RATIO))
    print(f"PSU {psu.name} wattage {psu.wattage} vs required {required * (1 + HEADROOM_RATIO)} -> {result}")
    return result

def cooler_ok(cooler, cpu) -> bool:
    required = cpu.power_consumption_overclocked or cpu.tdp or 0
    result = float(cooler.power_throughput or 0) >= required
    print(f"Cooler {cooler.name} throughput {cooler.power_throughput} vs CPU {cpu.name} required {required} -> {result}")
    return result



# --- Utility ---
def total_price(parts: List[object]) -> float:
    names = [getattr(p, "name", str(p)) for p in parts]
    print("Calculating total price for parts:", names)
    return sum(float(getattr(p, "price") or 0) for p in parts if p is not None)


# --- Prefilter ---
def prefilter_components(cpus, gpus, rams, budget):
    print(f"Prefiltering components for budget {budget}...")

    # Remove items with no price
    cpus = [c for c in cpus if c.price is not None and c.price > 0]
    gpus = [g for g in gpus if g.price is not None and g.price > 0]
    rams = [r for r in rams if r.price is not None and r.price > 0]

    # Apply budget-based filtering
    if budget < 600:
        cpus = [c for c in cpus if c.price < 300]
        gpus = [g for g in gpus if g.price < 300]
    elif budget < 800:
        cpus = [c for c in cpus if c.price < 400]
        gpus = [g for g in gpus if g.price < 400]
    elif budget < 1000:
        cpus = [c for c in cpus if c.price < 500]
        gpus = [g for g in gpus if g.price < 500]
    else:
        print("High budget detected, keeping all CPUs/GPUs.")

    print(f"Remaining CPUs: {len(cpus)}, GPUs: {len(gpus)}, RAMs: {len(rams)}")
    return cpus, gpus, rams

# --- Build logic ---
def find_best_build(budget, mode, resolution,
                    cpus, gpus, mobos, rams, storages, psus, coolers, cases):
    print("Starting build calculation...")
    cpus, gpus, rams = prefilter_components(cpus, gpus, rams, budget)

    sorted_cpus = sorted(cpus, key=lambda c: cpu_score(c, mode), reverse=True)
    sorted_gpus = sorted(gpus, key=lambda g: gpu_score(g, mode), reverse=True)
    sorted_rams = sorted(rams, key=lambda r: ram_score(r), reverse=True)

    progress = []

    for cpu in sorted_cpus:
        for gpu in sorted_gpus:
            for ram in sorted_rams:
                trio_price = (cpu.price or 0) + (gpu.price or 0) + (ram.price or 0)
                print(f"Trying trio: CPU {cpu.name}, GPU {gpu.gpu_name}, RAM {ram.name} -> price {trio_price}")
                if trio_price > budget:
                    print("Trio exceeds budget, skipping.")
                    continue

                mobos_compat = [m for m in mobos if compatible_cpu_mobo(cpu, m) and compatible_mobo_ram(m, ram)]
                print(f"Compatible motherboards for trio: {len(mobos_compat)}")
                if not mobos_compat:
                    print("No compatible motherboard for this trio.")
                    continue
                mobo = min(mobos_compat, key=lambda m: float(m.price or 0))
                print(f"Selected motherboard: {mobo.name} (price {mobo.price})")

                storage = min(storages, key=lambda s: float(s.price or 0))
                print(f"Selected storage: {storage.name} (price {storage.price})")

                psus_compat = [p for p in psus if psu_ok(p, cpu, gpu)]
                print(f"Compatible PSUs: {len(psus_compat)}")
                if not psus_compat:
                    print("No compatible PSU found.")
                    continue
                psu = min(psus_compat, key=lambda p: float(p.price or 0))
                print(f"Selected PSU: {psu.name} (price {psu.price})")

                coolers_compat = [c for c in coolers if cooler_ok(c, cpu)]
                print(f"Compatible coolers: {len(coolers_compat)}")
                if not coolers_compat:
                    print("No compatible cooler found.")
                    continue
                cooler = min(coolers_compat, key=lambda c: float(c.price or 0))
                print(f"Selected cooler: {cooler.name} (price {cooler.price})")

                cases_compat = [c for c in cases if compatible_case(mobo, c)]
                print(f"Compatible cases: {len(cases_compat)}")
                if not cases_compat:
                    print("No compatible case found.")
                    continue
                case = min(cases_compat, key=lambda c: float(c.price or 0))
                print(f"Selected case: {case.name} (price {case.price})")

                parts = [cpu, gpu, mobo, ram, storage, psu, cooler, case]
                price = total_price(parts)

                if price <= budget:
                    score = weighted_scores(cpu, gpu, ram, mode, resolution)
                    print(f"Build valid under budget {budget}: price {price}, score {score}")
                    progress.append("Best build found successfully!")
                    return BuildCandidate(cpu, gpu, mobo, ram, storage, psu, cooler, case, price, score), progress
                else:
                    print(f"Build exceeds budget {budget}: price {price}")

    print("No valid build found within budget.")
    progress.append("No valid build found within budget.")
    return None, progress
