import re

import pandas as pd


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")


def add_slugs_to_memory(input_file, output_file):
    df = pd.read_csv(input_file)

    # Normalize speed column "5,6000" -> DDR5 + 6000
    ddr = df["speed"].str.split(",").str[0].apply(lambda x: f"DDR{x.strip()}")
    freq = df["speed"].str.split(",").str[1].str.strip()

    df["ddr_generation"] = ddr
    df["frequency_mhz"] = freq

    # Build slug: name + DDR + frequency
    df["slug"] = (
        df["name"].apply(slugify)
        + "-"
        + df["ddr_generation"].str.lower()
        + "-"
        + df["frequency_mhz"]
    )

    # Drop old speed column
    df = df.drop(columns=["speed"])

    df.to_csv(output_file, index=False)
    print(f"Memory file with slugs written to {output_file}")


# Example usage
add_slugs_to_memory("data/ram/memory.csv", "data/ram/memory_slugs.csv")
