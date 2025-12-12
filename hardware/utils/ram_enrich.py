import argparse
import json
import os
import re
import time

import pandas as pd
import requests


# -----------------------------
# Slug helpers
# -----------------------------
def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")


def clean_name_for_slug(name: str) -> str:
    # Remove capacity tokens like "16 GB", "32 GB", "64 GB"
    base = re.sub(r"\b\d+\s*gb\b", "", name.lower())
    base = re.sub(r"\b\d+\b", "", base)  # remove standalone numbers
    base = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
    return base


# -----------------------------
# AI enrichment for price (batch)
# -----------------------------
ENDPOINTS = {
    "gpt-4.1-mini": (
        "https://models.inference.ai.azure.com/openai/deployments/"
        "gpt-4.1-mini/chat/completions"
    ),
    "gpt-4.1": (
        "https://models.inference.ai.azure.com/openai/deployments/"
        "gpt-4.1/chat/completions"
    ),
}
TOKENS = {
    "gpt-4.1-mini": os.getenv("GITHUB_TOKEN_MINI")
    or os.getenv("GITHUB_TOKEN"),
    "gpt-4.1": os.getenv("GITHUB_TOKEN_FULL") or os.getenv("GITHUB_TOKEN"),
}


def call_ai_batch(slugs, model="gpt-4.1-mini", debug=False):
    prompt_lines = [
        "You are enriching RAM hardware data.",
        "Return ONLY valid JSON: a dictionary mapping each slug to its",
        "price (USD float).",
        "",
        "Rules:",
        "- Estimate MSRP based on typical market value.",
        "- If unknown, return null.",
        "",
        "Slugs:",
        *slugs,
    ]
    prompt = "\n".join(prompt_lines)
    url = ENDPOINTS[model]
    token = TOKENS[model]
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
    }

    try:
        r = requests.post(url, headers=headers, json=payload, timeout=(10, 90))
        if r.status_code != 200:
            if debug:
                print(f"[{model}] Non-200: {r.status_code} -> {r.text[:300]}")
            return {}
        content = r.json()["choices"][0]["message"]["content"].strip()
        cleaned = re.sub(
            r"^```[a-zA-Z]*\s*|\s*```$", "", content, flags=re.MULTILINE
        ).strip()
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return data
        else:
            if debug:
                print(f"[{model}] Unexpected format: {type(data)}")
            return {}
    except Exception as e:
        if debug:
            print(f"[{model}] error: {e}")
        return {}


# -----------------------------
# Memory slugging + modules parsing
# -----------------------------
def slug_memory(df_mem: pd.DataFrame) -> pd.DataFrame:
    # Expect slug already present in input CSV
    if "slug" not in df_mem.columns:
        raise ValueError("Input memory CSV must contain a slug column")

    # Parse DDR/frequency from speed column if present
    if "speed" in df_mem.columns:
        ddr = (
            df_mem["speed"]
            .str.split(",")
            .str[0]
            .apply(lambda x: f"DDR{x.strip()}")
        )
        freq = df_mem["speed"].str.split(",").str[1].str.strip()
        df_mem["ddr_generation"] = ddr
        df_mem["frequency_mhz"] = freq
        df_mem = df_mem.drop(columns=["speed"])

    # Parse modules like "2,8"
    def parse_modules(val):
        try:
            sticks, size = val.split(",")
            sticks, size = int(sticks), int(size)
            return sticks, sticks * size
        except Exception:
            return None, None

    if "modules" in df_mem.columns:
        df_mem[["modules", "capacity_gb"]] = df_mem["modules"].apply(
            lambda x: pd.Series(parse_modules(str(x)))
        )

    return df_mem


# -----------------------------
# Benchmark slugging
# -----------------------------
def slug_benchmarks(df_bench: pd.DataFrame) -> pd.DataFrame:
    # Expect slug already present in benchmark CSV
    if "slug" not in df_bench.columns:
        raise ValueError("Benchmark CSV must contain a slug column")
    return df_bench[["slug", "Benchmark"]]


# -----------------------------
# Pipeline
# -----------------------------
def run_pipeline(memory_file, benchmark_file, output_file, debug=False):
    df_mem = pd.read_csv(memory_file)
    df_bench = pd.read_csv(benchmark_file)

    df_mem_slugged = slug_memory(df_mem)
    df_bench_slugged = slug_benchmarks(df_bench)

    df_enriched = df_mem_slugged.merge(df_bench_slugged, on="slug", how="left")

    before = len(df_enriched)
    df_enriched = df_enriched.dropna(subset=["Benchmark"])
    after = len(df_enriched)

    # Batch AI enrichment for missing prices
    batch_size = 25
    missing_slugs = df_enriched[df_enriched["price"].isna()]["slug"].tolist()
    filled_count = 0

    for i in range(0, len(missing_slugs), batch_size):
        batch = missing_slugs[i:i+batch_size]

        # Pass 1: mini
        results_mini = call_ai_batch(batch, model="gpt-4.1-mini", debug=debug)
        # Pass 2: full for any still missing
        still_missing = [s for s in batch if not results_mini.get(s)]
        if still_missing:
            results_full = call_ai_batch(
                still_missing, model="gpt-4.1", debug=debug
            )
            results_mini.update(results_full)

        # Update dataframe
        for slug, price in results_mini.items():
            if price is not None:  # skip nulls
                df_enriched.loc[df_enriched["slug"] == slug, "price"] = price
                filled_count += 1

        time.sleep(1)

    df_enriched.to_csv(output_file, index=False)

    pct = (after / before * 100) if before else 0
    print("\n=== RAM Enrichment Summary ===")
    print(f"Total memory modules in input: {before}")
    print(f"Matched with benchmarks: {after} ({pct:.1f}%)")
    print(f"Dropped (no benchmark): {before - after}")
    print(f"AI filled missing prices: {filled_count}")
    print(f"Enriched RAM CSV written to {output_file}")

    if debug:
        print("Sample enriched rows:\n", df_enriched.head(5))


# -----------------------------
# CLI
# -----------------------------
def main():
    parser = argparse.ArgumentParser(
        description=(
            "RAM pipeline with batch AI price fill, modules split, "
            "benchmark join"
        )
    )
    parser.add_argument("--memory", required=True, help="Path to memory.csv")
    parser.add_argument(
        "--benchmarks", required=True, help="Path to RAM_UserBenchmarks.csv"
    )
    parser.add_argument("--output", required=False, help="Path to output CSV")
    parser.add_argument(
        "--debug", action="store_true", help="Enable debug logging"
    )
    args = parser.parse_args()

    output_file = args.output or args.memory.replace(".csv", "_enriched.csv")
    run_pipeline(args.memory, args.benchmarks, output_file, debug=args.debug)


if __name__ == "__main__":
    main()
