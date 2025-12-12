import argparse
import re

import pandas as pd


# -----------------------------
# Slug helpers
# -----------------------------
def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")


def build_psu_slug(
    brand: str, model: str, wattage: str, efficiency: str
) -> str:
    """
    Build slug from PSU brand, model, wattage, and efficiency.
    """
    base = slugify(f"{brand} {model}")
    watt = slugify(str(wattage)) if wattage else ""
    eff = slugify(str(efficiency)) if efficiency else ""
    parts = [p for p in [base, watt, eff] if p]
    return "-".join(parts)


# -----------------------------
# Normalization helpers
# -----------------------------
def normalize_modular(value: str) -> str:
    if not isinstance(value, str):
        return ""
    v = value.strip().lower()
    if "full" in v:
        return "Full"
    if "semi" in v:
        return "Semi"
    if v in ("false", "no", "none", "non-modular"):
        return "Non-modular"
    return value[:50]  # guarantee <=50 chars


# -----------------------------
# Pipeline
# -----------------------------
def run_pipeline(psu_file: str, output_file: str, debug=False):
    df = pd.read_csv(psu_file)

    # Normalize modular column
    if "modular" in df.columns:
        df["modular"] = df["modular"].apply(normalize_modular)

    # Filter out rows without price
    before = len(df)
    df = df.dropna(subset=["price"])
    df = df[df["price"].astype(str).str.strip() != ""]
    after = len(df)

    # Split name into brand + model
    def split_name(full_name: str):
        if not full_name or pd.isna(full_name):
            return None, None
        tokens = full_name.strip().split(" ", 1)
        if len(tokens) == 1:
            return tokens[0], ""
        return tokens[0], tokens[1]

    df[["brand", "name"]] = df["name"].apply(
        lambda x: pd.Series(split_name(x))
    )

    # Add slug column
    df["slug"] = df.apply(
        lambda r: build_psu_slug(
            r["brand"],
            r["name"],
            r.get("wattage", ""),
            r.get("efficiency", ""),
        ),
        axis=1,
    )

    # Save cleaned file
    df.to_csv(output_file, index=False)

    # Summary
    print("\n=== PSU Cleaning Summary ===")
    print(f"Rows in input: {before}")
    print(f"Rows after price filter: {after} (dropped {before - after})")
    print(f"Enriched PSU CSV written to {output_file}")

    if debug:
        print("Sample cleaned rows:\n", df.head(5))


# -----------------------------
# CLI
# -----------------------------
def main():
    parser = argparse.ArgumentParser(
        description="PSU pipeline: filter by price, split brand/name, add slug"
    )
    parser.add_argument("--psu", required=True, help="Path to psu.csv")
    parser.add_argument("--output", required=False, help="Path to output CSV")
    parser.add_argument(
        "--debug", action="store_true", help="Enable debug logging"
    )
    args = parser.parse_args()

    output_file = args.output or args.psu.replace(".csv", "_cleaned.csv")
    run_pipeline(args.psu, output_file, debug=args.debug)


if __name__ == "__main__":
    main()
