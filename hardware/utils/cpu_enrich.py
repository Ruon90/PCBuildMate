import os
import csv
import argparse
import requests
import json
import time
import re
from tqdm import tqdm
import pandas as pd
from pathlib import Path

import env  # ensure env.py sets tokens

# Dual-key support
GITHUB_TOKEN_MINI = os.getenv("GITHUB_TOKEN_MINI") or os.getenv("GITHUB_TOKEN")
GITHUB_TOKEN_FULL = os.getenv("GITHUB_TOKEN_FULL") or os.getenv("GITHUB_TOKEN")

CACHE_FILE = "cpu_enrich_cache.json"

ENDPOINTS = {
    "gpt-4.1-mini": "https://models.inference.ai.azure.com/openai/deployments/gpt-4.1-mini/chat/completions",
    "gpt-4.1": "https://models.inference.ai.azure.com/openai/deployments/gpt-4.1/chat/completions"
}

TOKENS = {
    "gpt-4.1-mini": GITHUB_TOKEN_MINI,
    "gpt-4.1": GITHUB_TOKEN_FULL
}

# Target fields aligned with CPU schema (model kept explicitly)
TARGET_FIELDS = [
    "brand",
    "model",
    "name",
    "core_count",
    "thread_count",
    "release_date",
    "core_clock",
    "boost_clock",
    "microarchitecture",
    "tdp",
    "graphics",
    "price",
    "userbenchmark_score",
    "blender_score"
]

def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_cache(cache):
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2)

def map_row(row):
    """Normalize a raw/enriched row to TARGET_FIELDS only."""
    def clean(val):
        if val is None:
            return ""
        val = str(val).strip()
        return "" if val in ["", "0", "N/A", "NA", "None"] else val

    return {
        "brand": clean(row.get("brand")),
        "model": clean(row.get("model")),
        "name": clean(row.get("name")),
        "core_count": clean(row.get("core_count")),
        "thread_count": clean(row.get("thread_count")),
        "release_date": clean(row.get("release_date")),
        "core_clock": clean(row.get("core_clock")),
        "boost_clock": clean(row.get("boost_clock")),
        "microarchitecture": clean(row.get("microarchitecture")),
        "tdp": clean(row.get("tdp")),
        "graphics": clean(row.get("graphics")),
        "price": clean(row.get("price")),
        "userbenchmark_score": clean(row.get("userbenchmark_score")),
        "blender_score": clean(row.get("blender_score")),
    }

def call_ai_batch(category, models, debug=False, model="gpt-4.1-mini"):
    prompt = f"""
You are enriching {category} hardware data.
Return ONLY valid JSON (array). Each element must have:

- model_name (string, match input exactly)
- thread_count (integer, correct threads for this CPU)
- release_date (string, YYYY-MM-DD format; if only year known use YYYY-01-01; if unknown use None)

Rules:
- Do not invent unrealistic values.
- If SMT/HyperThreading is supported, thread_count = core_count * 2; otherwise = core_count.
- Treat "0" or "N/A" as missing values.
- Ensure JSON is valid and parsable.

Models:
{chr(10).join(models)}
"""
    url = ENDPOINTS[model]
    token = TOKENS.get(model) or ""
    headers = {
        "Authorization": f"Bearer {token.strip() if token else ''}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0
    }

    for attempt in range(3):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=(10, 90))
            if debug:
                print(f"DEBUG: Response status {response.status_code}")
        except Exception as e:
            print(f"\n--- HTTP REQUEST ERROR (attempt {attempt+1}) ---")
            print(e)
            time.sleep(5 * (attempt + 1))
            continue

        if response.status_code != 200:
            print(f"\n--- NON-200 STATUS {response.status_code} ---")
            print(response.text)
            time.sleep(5 * (attempt + 1))
            continue

        try:
            response_json = response.json()
        except Exception as e:
            print(f"\n--- RESPONSE JSON DECODE ERROR ---")
            print(e)
            print(response.text)
            time.sleep(5 * (attempt + 1))
            continue

        if "error" in response_json:
            print("\n--- API ERROR RESPONSE ---")
            print(json.dumps(response_json, indent=2))
            return []

        if "choices" not in response_json or not response_json.get("choices"):
            print("\n--- API RESPONSE MISSING CHOICES ---")
            print(json.dumps(response_json, indent=2))
            return []

        content = response_json["choices"][0]["message"]["content"]
        cleaned = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", content.strip(), flags=re.MULTILINE).strip()

        try:
            data = json.loads(cleaned)
            return data if isinstance(data, list) else []
        except Exception as e:
            print("\n--- RAW API RESPONSE ---")
            print(content)
            print("--- JSON PARSE ERROR ---")
            print(e)
            return []

    return []

def normalize(s: str) -> str:
    if not s:
        return ""
    return re.sub(r"[^a-z0-9]", "", s.lower())

def add_benchmarks_inplace(output_file: Path, debug=False):
    """Load enriched CSV, attach userbenchmark_score and blender_score, and write back."""
    # Defensive read: pandas C engine can raise ParserError for malformed rows.
    try:
        df = pd.read_csv(output_file)
    except pd.errors.ParserError as e:
        # Diagnose offending rows by counting delimiter occurrences per line
        print(f"CSV parse error reading {output_file}: {e}")
        print("Scanning file for malformed rows (mismatched field counts)...")
        import csv as _csv
        with open(output_file, newline='', encoding='utf-8') as _f:
            reader = _csv.reader(_f)
            header = next(reader, None)
            expected = len(header) if header else None
            print(f"Header fields: {expected} -> {header}")
            for i, row in enumerate(reader, start=2):
                if expected is not None and len(row) != expected:
                    print(f"Line {i}: expected {expected}, saw {len(row)}")
                    # show a short preview of the row to help debugging
                    preview = row[:6]
                    if len(row) > 6:
                        preview = preview + ['...']
                    print("Preview:", preview)
        # Try a more tolerant read (python engine) and let the caller decide
    print("Reading with python engine (on_bad_lines='warn') to try salvage...")
    df = pd.read_csv(output_file, engine='python', on_bad_lines='warn')

    # If model column is missing, derive it from name naively
    if "model" not in df.columns:
        df["model"] = df["name"].fillna("").astype(str)

    ub_file = Path(__file__).resolve().parent.parent.parent / "data/benchmark/CPU_UserBenchmarks.csv"
    blender_file = Path(__file__).resolve().parent.parent.parent / "data/benchmark/Blender - Open Data - CPU.csv"

    if debug:
        print(f"Loading benchmarks:\n - {ub_file}\n - {blender_file}")

    df_ub = pd.read_csv(ub_file, encoding="utf-8-sig")
    df_blender = pd.read_csv(blender_file, encoding="utf-8-sig")

    # Normalize keys for matching
    df["norm_model"] = df["model"].apply(normalize)

    # UserBenchmarks: expect columns 'Model' and 'Benchmark'
    ub_cols = {c.lower(): c for c in df_ub.columns}
    col_model_ub = ub_cols.get("model")
    col_bench_ub = ub_cols.get("benchmark")
    if not (col_model_ub and col_bench_ub):
        raise ValueError("CPU_UserBenchmarks.csv must contain 'Model' and 'Benchmark' columns.")

    df_ub["norm_model"] = df_ub[col_model_ub].apply(normalize)
    ub_lookup = dict(zip(df_ub["norm_model"], df_ub[col_bench_ub]))
    df["userbenchmark_score"] = df["norm_model"].map(ub_lookup)

    # Fallback: for rows that didn't match directly, try relaxed substring matching.
    missing_mask = df["userbenchmark_score"].isna()
    if missing_mask.any():
        if debug:
            print(f"Userbenchmark direct matches: {df['userbenchmark_score'].notna().sum()}, trying substring fallback for {missing_mask.sum()} rows")
        for idx in df[missing_mask].index:
            nm = df.at[idx, "norm_model"]
            if not nm:
                continue
            # Candidates where benchmark norm contains the model norm
            try:
                candidates = df_ub[df_ub["norm_model"].str.contains(nm, na=False)]
            except Exception:
                candidates = pd.DataFrame()

            # If none, try the reverse: where model norm contains the benchmark norm
            if candidates.empty:
                candidates = df_ub[df_ub["norm_model"].apply(lambda x: isinstance(x, str) and x in nm)]

            if not candidates.empty:
                # choose the first candidate (could be improved with scoring)
                val = candidates.iloc[0][col_bench_ub]
                df.at[idx, "userbenchmark_score"] = val
                if debug:
                    print(f"Fallback matched '{df.at[idx, 'model']}' -> '{candidates.iloc[0][col_model_ub]}' = {val}")

    # Blender Open Data: expect 'Device Name' and 'Median Score'
    blender_cols = {c.lower(): c for c in df_blender.columns}
    col_device_bl = blender_cols.get("device name")
    col_median_bl = blender_cols.get("median score")
    if not (col_device_bl and col_median_bl):
        raise ValueError("Blender - Open Data - CPU.csv must contain 'Device Name' and 'Median Score' columns.")

    df_blender["norm_device"] = df_blender[col_device_bl].apply(normalize)

    def find_blender_score(norm_model):
        # substring match: norm_model contained in norm_device
        hits = df_blender[df_blender["norm_device"].str.contains(norm_model, na=False)]
        if not hits.empty:
            # prefer the highest median score if multiple hits
            return hits[col_median_bl].astype(float, errors="ignore").iloc[0]
        return None

    df["blender_score"] = df["norm_model"].apply(find_blender_score)

    df = df.drop(columns=["norm_model"])
    df.to_csv(output_file, index=False)
    print(f"Benchmarks added to {output_file}")

def enrich_csv(input_file, output_file, category="CPU", batch_size=50, debug=False,
               resume=False, fresh=False, model="gpt-4.1-mini"):
    if fresh:
        cache = {}
        if os.path.exists(CACHE_FILE):
            os.remove(CACHE_FILE)
        if os.path.exists(output_file):
            os.remove(output_file)
        print("Starting fresh: cache and output CSV cleared.")
    else:
        cache = load_cache() if resume else {}

    enriched_models = set()
    if resume and os.path.exists(output_file):
        with open(output_file, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if "name" in row:
                    enriched_models.add(row["name"])

    with open(input_file, newline="", encoding="utf-8") as infile, \
         open(output_file, "a", newline="", encoding="utf-8") as outfile:
        input_rows = list(csv.DictReader(infile))
        if not input_rows:
            print("No rows found in input file.")
            return

        # Use QUOTE_ALL to ensure any commas/newlines inside fields are safely quoted
        # and extrasaction='ignore' to avoid accidental extra keys causing misaligned rows.
        writer = csv.DictWriter(outfile, fieldnames=TARGET_FIELDS, extrasaction='ignore', quoting=csv.QUOTE_ALL)
        if not resume or (resume and os.path.getsize(output_file) == 0):
            writer.writeheader()

        batch, rows_buffer = [], []

        for idx, row in enumerate(tqdm(input_rows, desc=f"Enriching CPUs ({model})", unit="cpu"), start=1):
            model_name = row.get("name", "").strip()
            if not model_name:
                continue

            if resume and model_name in enriched_models:
                continue

            if model_name in cache:
                writer.writerow(map_row({**row, **cache[model_name]}))
                enriched_models.add(model_name)
                continue

            batch.append(model_name)
            rows_buffer.append(row)

            if len(batch) >= batch_size:
                enriched_batch = call_ai_batch(category, batch, debug=debug, model=model)
                if enriched_batch:
                    # Build quick dict for lookup by model_name
                    enriched_map = {e.get("model_name", ""): e for e in enriched_batch}
                    for row_item in rows_buffer:
                        name_key = row_item.get("name", "")
                        e = enriched_map.get(name_key, {})
                        merged = {
                            **row_item,
                            "thread_count": e.get("thread_count", ""),
                            "release_date": e.get("release_date", "")
                        }
                        writer.writerow(map_row(merged))
                        cache[name_key] = merged
                        enriched_models.add(name_key)
                batch, rows_buffer = [], []
                time.sleep(1)

        if batch:
            enriched_batch = call_ai_batch(category, batch, debug=debug, model=model)
            if enriched_batch:
                enriched_map = {e.get("model_name", ""): e for e in enriched_batch}
                for row_item in rows_buffer:
                    name_key = row_item.get("name", "")
                    e = enriched_map.get(name_key, {})
                    merged = {
                        **row_item,
                        "thread_count": e.get("thread_count", ""),
                        "release_date": e.get("release_date", "")
                    }
                    writer.writerow(map_row(merged))
                    cache[name_key] = merged
                    enriched_models.add(name_key)

    # Persist cache
    save_cache(cache)

    # Attach benchmark scores in place
    add_benchmarks_inplace(Path(output_file), debug=debug)

def main():
    parser = argparse.ArgumentParser(description="CPU enrichment with GPT-4.1-mini + benchmark merge")
    parser.add_argument("--file", required=True, help="Path to input CSV (e.g., data/cpu/cpu-clean.csv)")
    parser.add_argument("--batch-size", type=int, default=50, help="Number of CPUs per batch")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--resume", action="store_true", help="Resume from existing cache and CSV")
    parser.add_argument("--fresh", action="store_true", help="Clear cache and CSV, start fresh")
    args = parser.parse_args()

    input_file = args.file
    output_file = input_file.replace(".csv", "_enriched.csv")

    enrich_csv(
        input_file=input_file,
        output_file=output_file,
        category="CPU",
        batch_size=args.batch_size,
        debug=args.debug,
        resume=args.resume,
        fresh=args.fresh,
        model="gpt-4.1-mini"
    )
    print(f"Enriched CPU CSV written to {output_file}")

if __name__ == "__main__":
    main()
