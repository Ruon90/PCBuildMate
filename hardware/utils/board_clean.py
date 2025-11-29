import os
import argparse
import re
import pandas as pd
from pathlib import Path

# Target sockets we care about
VALID_SOCKETS = {"LGA1851", "LGA1700", "AM5", "AM4"}

TARGET_FIELDS = [
    "name",
    "price",
    "socket",
    "form_factor",
    "max_memory",
    "memory_slots",
    "color",
    "slug"
]

# -----------------------------
# Slug builder for normalisation
# -----------------------------
def build_slug(name: str) -> str:
    if not isinstance(name, str):
        return ""
    s = name.upper()
    # Remove common vendor prefixes
    s = re.sub(r"\b(ASUS|MSI|GIGABYTE|ASROCK|INTEL|AMD)\b", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    # Capture alphanumeric tokens
    tokens = re.findall(r"[A-Z0-9\-]+", s)
    return "-".join(tok.lower() for tok in tokens)

# -----------------------------
# Cleaning function
# -----------------------------
def clean_boards(input_file, output_file, debug=False):
    df = pd.read_csv(input_file)

    # Filter by socket
    df = df[df["socket"].isin(VALID_SOCKETS)].copy()

    # Drop rows with missing or empty price
    df = df[df["price"].notna() & (df["price"].astype(str).str.strip() != "")].copy()

    # Normalise names into slugs
    df["slug"] = df["name"].apply(build_slug)

    # Ensure consistent field order
    for f in TARGET_FIELDS:
        if f not in df.columns:
            df[f] = ""
    df = df[TARGET_FIELDS + [c for c in df.columns if c not in TARGET_FIELDS]]

    df.to_csv(output_file, index=False)
    print(f"Motherboard cleaning complete -> {output_file}")

    # Summary report
    socket_counts = df["socket"].value_counts()
    total = len(df)
    print("\n=== Socket Coverage Summary ===")
    for socket, count in socket_counts.items():
        pct = (count / total) * 100 if total > 0 else 0
        print(f"{socket}: {count} boards ({pct:.1f}%)")

    if debug:
        print("\n[DEBUG] Sample rows after filtering:")
        print(df.head(10))

# -----------------------------
# CLI
# -----------------------------
def main():
    parser = argparse.ArgumentParser(description="Clean motherboard dataset: filter sockets, drop missing prices, and normalise names")
    parser.add_argument("--file", required=True, help="Path to raw motherboard CSV")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    input_path = Path(args.file)
    output_path = input_path.with_name(input_path.stem + "_clean.csv")

    clean_boards(str(input_path), str(output_path), debug=args.debug)

if __name__ == "__main__":
    main()
