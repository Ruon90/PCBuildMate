import argparse
import re
from pathlib import Path

import pandas as pd


TARGET_FIELDS = [
    "name",
    "price",
    "rpm",
    "noise_level",
    "color",
    "size",
    "slug",
]


# -----------------------------
# Slug builder
# -----------------------------
def build_slug(name: str) -> str:
    if not isinstance(name, str):
        return ""
    s = name.upper()
    # Remove common vendor prefixes
    s = re.sub(
        r"\b(CORSAIR|NOCTUA|BEQUIET|DEEPCOOL|NZXT|ARCTIC|COOLERMASTER)\b",
        "",
        s,
    )
    s = re.sub(r"\s+", " ", s).strip()
    # Capture alphanumeric tokens
    tokens = re.findall(r"[A-Z0-9\-]+", s)
    return "-".join(tok.lower() for tok in tokens)


# -----------------------------
# Cleaning function
# -----------------------------
def clean_coolers(input_file, output_file, debug=False):
    df = pd.read_csv(input_file)

    # Drop rows with missing or empty price
    df = df[
        df["price"].notna() & (df["price"].astype(str).str.strip() != "")
    ].copy()

    # Add slug column
    df["slug"] = df["name"].apply(build_slug)

    # Ensure consistent field order
    for f in TARGET_FIELDS:
        if f not in df.columns:
            df[f] = ""
    df = df[TARGET_FIELDS + [c for c in df.columns if c not in TARGET_FIELDS]]

    df.to_csv(output_file, index=False)
    print(f"Cooler cleaning complete -> {output_file}")

    # Summary report
    total = len(df)
    print("\n=== Cooler Coverage Summary ===")
    print(f"Total coolers after cleaning: {total}")

    if debug:
        print("\n[DEBUG] Sample rows after filtering:")
        print(df.head(10))


# -----------------------------
# CLI
# -----------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Clean CPU cooler dataset: drop rows with empty price and add slug"
    )
    parser.add_argument("--file", required=True, help="Path to raw cooler CSV")
    parser.add_argument(
        "--debug", action="store_true", help="Enable debug logging"
    )
    args = parser.parse_args()

    input_path = Path(args.file)
    output_path = input_path.with_name(input_path.stem + "_clean.csv")

    clean_coolers(str(input_path), str(output_path), debug=args.debug)


if __name__ == "__main__":
    main()
