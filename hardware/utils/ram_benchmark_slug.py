import pandas as pd
import re

def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")

def add_slugs_to_benchmarks(input_file, output_file):
    df = pd.read_csv(input_file)

    slugs = []
    for _, row in df.iterrows():
        brand = slugify(row["Brand"])
        model = slugify(row["Model"])

        ddr_match = re.search(r"(ddr\d+)", model)
        ddr = ddr_match.group(1) if ddr_match else ""

        freq_match = re.search(r"(\d{4,5})", model)
        freq = freq_match.group(1) if freq_match else ""

        tokens = model.split("-")
        core_tokens = tokens[:3]
        slug_parts = [brand] + core_tokens + [ddr, freq]
        slug = "-".join([p for p in slug_parts if p])
        slugs.append(slug)

    df["slug"] = slugs
    df.to_csv(output_file, index=False)
    print(f"Benchmark file with slugs written to {output_file}")

# Example usage
add_slugs_to_benchmarks("data/benchmark/RAM_UserBenchmarks.csv", "data/benchmark/RAM_UserBenchmarks_slugs.csv")
