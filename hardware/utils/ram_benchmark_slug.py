import re

import pandas as pd


def slugify(text: str) -> str:
    """Lowercase and replace non-alphanumeric with dashes."""
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")


def normalize_capacity(model: str) -> str:
    """
    Normalize capacity tokens like '2x16GB' or '32 GB' into '32-gb'.
    """
    match_combo = re.search(
        r"(\d+)\s*[xX]\s*(\d+)\s*GB", model, flags=re.IGNORECASE
    )
    if match_combo:
        sticks = int(match_combo.group(1))
        size = int(match_combo.group(2))
        return f"{sticks * size}-gb"
    match_single = re.search(r"(\d+)\s*GB", model, flags=re.IGNORECASE)
    if match_single:
        return f"{int(match_single.group(1))}-gb"
    return ""


def strip_noise_for_tokens(model: str) -> str:
    """
    Prepare model string for tokenization:
    - Remove latency tokens (C32, CL30, etc.)
    - Remove capacity patterns ('2x16GB', '32 GB', etc.)
    - Keep other descriptors
    """
    s = model

    # Remove latency tokens: CLxx or Cxx (case-insensitive)
    s = re.sub(r"\bcl?\s*\d+\b", "", s, flags=re.IGNORECASE)

    # Remove capacity patterns (but we'll compute capacity separately)
    s = re.sub(
        r"\b\d+\s*[xX]\s*\d+\s*GB\b", "", s, flags=re.IGNORECASE
    )  # 2x16GB
    s = re.sub(r"\b\d+\s*GB\b", "", s, flags=re.IGNORECASE)  # 32 GB

    # Also remove raw 'GB' leftovers without numbers
    s = re.sub(r"\bGB\b", "", s, flags=re.IGNORECASE)

    # Collapse spaces after removals
    s = re.sub(r"\s+", " ", s).strip()
    return s


def add_slugs_to_benchmarks(input_file, output_file):
    df = pd.read_csv(input_file)

    slugs = []
    for _, row in df.iterrows():
        brand = slugify(row["Brand"])
        model_raw = str(row["Model"])

        # Compute normalized capacity from the raw model string
        cap = normalize_capacity(model_raw)

        # Build a clean model string for tokenization
        model_clean = strip_noise_for_tokens(model_raw)
        model_slug = slugify(model_clean)

        # Extract DDR generation and frequency (from cleaned slug to avoid duplicates)
        ddr_match = re.search(r"(ddr\d+)", model_slug)
        ddr = ddr_match.group(1) if ddr_match else ""

        freq_match = re.search(r"(\d{4,5})", model_slug)
        freq = freq_match.group(1) if freq_match else ""

        # Remove DDR/freq from core tokens so they appear only once at the tail
        tokens = [
            t for t in model_slug.split("-") if t and t not in (ddr, freq)
        ]

        # Build slug parts in the same structure as memory.
        # Order: brand-model-capacity-ddrX-frequency
        slug_parts = [brand] + tokens[:3]
        if cap:
            slug_parts.append(cap)
        if ddr:
            slug_parts.append(ddr)
        if freq:
            slug_parts.append(freq)

        slug = "-".join(slug_parts)
        slugs.append(slug)

    df["slug"] = slugs
    df.to_csv(output_file, index=False)
    print(f"Benchmark file with slugs written to {output_file}")


if __name__ == "__main__":
    add_slugs_to_benchmarks(
        "data/benchmark/RAM_UserBenchmarks.csv",
        "data/benchmark/RAM_UserBenchmarks_slugs.csv",
    )
