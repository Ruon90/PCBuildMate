import argparse
import pandas as pd
import re

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

def run_pipeline(storage_file: str, output_file: str, debug=False):
    df = pd.read_csv(storage_file)

    # Filter out rows without price
    before = len(df)
    df = df.dropna(subset=["price"])
    df = df[df["price"].astype(str).str.strip() != ""]
    after_price_filter = len(df)

    # Normalize interface
    df["interface"] = df["interface"].apply(normalize_interface)

    # Save cleaned file
    df.to_csv(output_file, index=False)

    # Summary
    print("\n=== Storage Cleaning Summary ===")
    print(f"Rows in input: {before}")
    print(f"Rows after price filter: {after_price_filter} (dropped {before - after_price_filter})")
    print(f"Enriched storage CSV written to {output_file}")

    if debug:
        print("Sample cleaned rows:\n", df.head(5))

# -----------------------------
# CLI
# -----------------------------
def main():
    parser = argparse.ArgumentParser(description="Storage pipeline: filter by price, normalize interface to motherboard convention")
    parser.add_argument("--storage", required=True, help="Path to storage.csv")
    parser.add_argument("--output", required=False, help="Path to output CSV")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    output_file = args.output or args.storage.replace(".csv", "_cleaned.csv")
    run_pipeline(args.storage, output_file, debug=args.debug)

if __name__ == "__main__":
    main()
