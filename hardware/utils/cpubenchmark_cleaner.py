import re
from pathlib import Path

import pandas as pd


# Slug builder for CPUs (drop family prefixes like i5/i7, Ryzen 7/9)
def build_cpu_slug(name: str) -> str:
    if not isinstance(name, str):
        return ""
    s = name.upper().strip()

    # Remove vendor noise and family words
    s = re.sub(r"\b(INTEL|AMD|RYZEN|CORE|PROCESSOR|CPU|I3|I5|I7|I9)\b", "", s)
    s = re.sub(r"\s+", " ", s).strip()

    # AMD/Intel: capture the 4–5 digit model + optional suffix
    m = re.search(r"\b(\d{4,5}(?:X3D|XT|X|G|GT|GE|F|K|KF|KS|T)?)\b", s)
    if m:
        return m.group(1).lower()

    # Server parts (EPYC / XEON): extract main numeric block
    m_server = re.search(r"\b(\d{4,5}[A-Z]{0,2})\b", s)
    if m_server:
        return m_server.group(1).lower()

    # Fallback: compact alphanumerics
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def clean_userbenchmark_cpu(root: Path):
    ub_file = root / "data/benchmark/CPU_UserBenchmarks.csv"
    df = pd.read_csv(ub_file, encoding="utf-8-sig")
    cols = {c.lower(): c for c in df.columns}
    col_model = cols.get("model") or "Model"
    col_bench = cols.get("benchmark") or "Benchmark"
    if col_model not in df.columns or col_bench not in df.columns:
        raise ValueError(
            "CPU_UserBenchmarks.csv must contain 'Model' and 'Benchmark' columns."
        )
    df["Slug"] = df[col_model].astype(str).map(build_cpu_slug)
    out_file = root / "data/benchmark/CPU_UserBenchmarks_clean.csv"
    df.to_csv(out_file, index=False)
    print(f"[OK] Cleaned UserBenchmark -> {out_file}")


def clean_blender_cpu(root: Path):
    blender_file = root / "data/benchmark/Blender - Open Data - CPU.csv"
    df = pd.read_csv(blender_file, encoding="utf-8-sig")
    cols = {c.lower(): c for c in df.columns}
    col_device = cols.get("device name") or "Device Name"
    col_score = cols.get("median score") or "Median Score"
    if col_device not in df.columns or col_score not in df.columns:
        raise ValueError(
            "Blender CPU file must contain 'Device Name' and 'Median Score' columns."
        )
    df["Slug"] = df[col_device].astype(str).map(build_cpu_slug)
    out_file = root / "data/benchmark/Blender_CPU_clean.csv"
    df.to_csv(out_file, index=False)
    print(f"[OK] Cleaned Blender -> {out_file}")


def main():
    root = Path(__file__).resolve().parent.parent.parent
    clean_userbenchmark_cpu(root)
    clean_blender_cpu(root)


if __name__ == "__main__":
    main()
