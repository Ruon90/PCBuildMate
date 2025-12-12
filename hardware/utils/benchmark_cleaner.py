import re
from pathlib import Path

import pandas as pd


# Slug builder
def build_slug(name: str) -> str:
    if not isinstance(name, str):
        return ""
    s = name.upper()
    # Remove vendor noise
    s = re.sub(r"\b(GEFORCE|RADEON|NVIDIA|AMD|INTEL)\b", "", s)
    # Normalize whitespace
    s = re.sub(r"\s+", " ", s).strip()
    # Extract tokens: RTX/RX, numbers, TI, SUPER, XT, XTX
    tokens = re.findall(r"(RTX|RX|\d{3,4}|TI|SUPER|XT|XTX)", s)
    return "-".join(tok.lower() for tok in tokens)


def clean_userbenchmark(root: Path):
    ub_file = root / "data/benchmark/GPU_UserBenchmarks.csv"
    df = pd.read_csv(ub_file, encoding="utf-8-sig")
    df["Slug"] = df.apply(
        lambda row: build_slug(str(row.get("Model", ""))), axis=1
    )
    out_file = root / "data/benchmark/GPU_UserBenchmarks_clean.csv"
    df.to_csv(out_file, index=False)
    print(f"[OK] Cleaned UserBenchmark -> {out_file}")


def clean_blender(root: Path):
    blender_file = root / "data/benchmark/Blender - Open Data - GPU.csv"
    df = pd.read_csv(blender_file, encoding="utf-8-sig")
    df["Slug"] = df["Device Name"].astype(str).map(build_slug)
    out_file = root / "data/benchmark/Blender_GPU_clean.csv"
    df.to_csv(out_file, index=False)
    print(f"[OK] Cleaned Blender -> {out_file}")


def main():
    root = Path(__file__).resolve().parent.parent.parent
    clean_userbenchmark(root)
    clean_blender(root)


if __name__ == "__main__":
    main()
