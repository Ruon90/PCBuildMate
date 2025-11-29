import pandas as pd
from pathlib import Path
import re

field_map = {
    "manufacturer": "brand",
    "name": "GpuName",
    "generation": "Generation",
    "base_clock_mhz": "BaseClock",
    "boost_clock_mhz": "BoostClock",
    "architecture": "Architecture",
    "process_size_nm": "ProcessSize",
    "release_date": "ReleaseDate",
    "bus_interface": "BusInterface",
    "memory_clock_mhz": "MemoryClock",
    "memory_size_gb": "MemorySizeGB",
    "memory_type": "MemoryType",
    "shading_units": "ShadingUnits",
    "texture_mapping_units": "TMUs",
    "render_output_processors": "ROPs",
    "streaming_multiprocessors": "SMs",
    "tensor_cores": "TensorCores",
    "ray_tracing_cores": "RTcores",
    "l1_cache_kb": "L1CacheKB",
    "l2_cache_mb": "L2CacheMB",
    "thermal_design_power_w": "TDP",
    "board_length_mm": "BoardLength",
    "board_width_mm": "BoardWidth",
    "board_slot_width": "SlotWidth",
    "suggested_psu_w": "SuggestedPSU",
    "power_connectors": "PowerConnectors",
    "display_connectors": "DisplayConnectors",
}

def simplify_model(name: str) -> str:
    if not name:
        return ""
    s = str(name).lower()
    # remove vendor words
    s = re.sub(r"(nvidia|geforce|amd|radeon|intel|arc)", "", s)
    s = s.replace("-", " ").strip()
    # collapse spaces
    s = re.sub(r"\s+", " ", s)
    # apply suffix rules
    s = s.replace(" super", "s")
    s = s.replace(" ti", "TI")
    # remove leading 'rtx' or 'gtx' if present
    s = re.sub(r"^(rtx|gtx)\s*", "", s)
    return s.upper()

def clean_gpu(file_path: Path, output_path: Path, filter_recent: bool = True):
    df = pd.read_csv(file_path)
    df.columns = df.columns.str.strip()

    keep_cols = [col for col in df.columns if col in field_map.keys()]
    df = df[keep_cols]
    df = df.rename(columns=field_map)

    # Apply simplification directly to GpuName
    df["model"] = df["GpuName"].apply(simplify_model)

    cols = ["brand", "model"] + [c for c in df.columns if c not in ["brand", "model"]]
    df = df[cols]

    # Normalize ReleaseDate
    if "ReleaseDate" in df.columns:
        df["ReleaseDate"] = pd.to_datetime(df["ReleaseDate"], errors="coerce")

        if filter_recent:
            cutoff = pd.Timestamp(year=2022, month=1, day=1)
            df = df[df["ReleaseDate"] >= cutoff]

    df = df.dropna(how="all").dropna(axis=1, how="all")
    df.to_csv(output_path, index=False)
    print(f"GPU cleaned dataset saved to {output_path} (filter_recent={filter_recent})")

def main():
    data_dir = Path(__file__).resolve().parent.parent.parent / "data/gpu"
    gpu_file = data_dir / "2025-08.csv"
    output_file = data_dir / "gpu-clean.csv"

    # Toggle filter_recent here
    clean_gpu(gpu_file, output_file, filter_recent=True)

if __name__ == "__main__":
    main()
