import argparse
import re

import pandas as pd


# -----------------------------
# Slug helpers
# -----------------------------
def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")


def build_storage_slug(
    brand: str, model: str, capacity: str, interface: str
) -> str:
    """
    Build slug from storage brand, model, capacity, and interface.
    """
    base = slugify(f"{brand} {model}")
    cap = slugify(str(capacity)) if capacity else ""
    inter = slugify(str(interface)) if interface else ""
    parts = [p for p in [base, cap, inter] if p]
    return "-".join(parts)


# -----------------------------
# Name splitting
# -----------------------------
def split_name(full_name: str):
    """
    Split full name into brand and model.
    Assumes brand is the first token, model is the remainder.
    """
    if not full_name or pd.isna(full_name):
        return None, None
    tokens = full_name.strip().split(" ", 1)
    if len(tokens) == 1:
        return tokens[0], ""
    return tokens[0], tokens[1]


# -----------------------------
# Interface normalization
# -----------------------------
def normalize_interface(interface: str) -> str:
    """
    Map storage interface strings to motherboard nvme_support convention.
    """
    if not interface or pd.isna(interface):
        return None

    s = interface.lower()

    if "pci" in s and "5" in s:
        return "PCIe Gen5"
    if "pci" in s and "4" in s:
        return "PCIe Gen4"
    if "pci" in s and "3" in s:
        return "PCIe Gen3"
    if "sata" in s:
        return "SATA"
    if "nvme" in s and "gen4" in s:
        return "PCIe Gen4"
    if "nvme" in s and "gen3" in s:
        return "PCIe Gen3"

    return interface  # fallback


# -----------------------------
# Pipeline
# -----------------------------
def run_pipeline(storage_file: str, output_file: str, debug=False):
    df = pd.read_csv(storage_file)

    # Filter out rows without price
    before = len(df)
    df = df.dropna(subset=["price"])
    df = df[df["price"].astype(str).str.strip() != ""]
    after_price_filter = len(df)

    # Normalize interface
    df["interface"] = df["interface"].apply(normalize_interface)

    # Split name into brand + model
    df[["brand", "model"]] = df["name"].apply(
        lambda x: pd.Series(split_name(x))
    )

    # Add slug column
    df["slug"] = df.apply(
        lambda r: build_storage_slug(
            r["brand"],
            r["model"],
            r.get("capacity", ""),
            r.get("interface", ""),
        ),
        axis=1,
    )

    # Save cleaned file
    df.to_csv(output_file, index=False)

    # Summary
    print("\n=== Storage Cleaning Summary ===")
    print(f"Rows in input: {before}")
    # Shorter print to satisfy line-length checks
    print("Rows after price filter:", after_price_filter, "(dropped",
          before - after_price_filter, ")")
    print(f"Enriched storage CSV written to {output_file}")

    if debug:
        print("Sample cleaned rows:\n", df.head(5))


# -----------------------------
# CLI
# -----------------------------
def main():
    parser = argparse.ArgumentParser(
        description=(
            "Storage pipeline: filter by price, normalize interface, "
            "split brand/model, add slug"
        )
    )
    parser.add_argument("--storage", required=True, help="Path to storage.csv")
    parser.add_argument("--output", required=False, help="Path to output CSV")
    parser.add_argument(
        "--debug", action="store_true", help="Enable debug logging"
    )
    args = parser.parse_args()

    output_file = args.output or args.storage.replace(".csv", "_cleaned.csv")
    run_pipeline(args.storage, output_file, debug=args.debug)


if __name__ == "__main__":
    main()
