import os
import csv
import argparse
import requests
import json
import time
import re
from tqdm import tqdm

import env  # ensure env.py sets tokens

# Dual-key support
GITHUB_TOKEN_MINI = os.getenv("GITHUB_TOKEN_MINI") or os.getenv("GITHUB_TOKEN")
GITHUB_TOKEN_FULL = os.getenv("GITHUB_TOKEN_FULL") or os.getenv("GITHUB_TOKEN")

CACHE_FILE = "enrich_cache.json"

ENDPOINTS = {
    "gpt-4.1-mini": "https://models.inference.ai.azure.com/openai/deployments/gpt-4.1-mini/chat/completions",
    "gpt-4.1": "https://models.inference.ai.azure.com/openai/deployments/gpt-4.1/chat/completions"
}

TOKENS = {
    "gpt-4.1-mini": GITHUB_TOKEN_MINI,
    "gpt-4.1": GITHUB_TOKEN_FULL
}

# Target fields aligned with Django GPU model
TARGET_FIELDS = [
    "brand",
    "name",
    "benchmark",
    "power_consumption",
    "msrp",
    "live_min",
    "live_max",
    "image_url",
    "userbenchmark_url"
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
    """Map raw CSV/enriched row to Django GPU model fields."""
    def clean(val):
        if val is None:
            return ""
        val = str(val).strip()
        return "" if val in ["", "0", "N/A", "NA", "None"] else val

    return {
        "brand": clean(row.get("Brand")),
        "name": clean(row.get("Model")),
        "benchmark": clean(row.get("Benchmark")),
        "power_consumption": clean(row.get("PowerConsumption")),
        "msrp": clean(row.get("MSRP")),
        "live_min": clean(row.get("LiveMin")),
        "live_max": clean(row.get("LiveMax")),
        "image_url": clean(row.get("ImageURL")),
        "userbenchmark_url": clean(row.get("URL"))
    }


def call_ai_batch(category, models, debug=False, model="gpt-4.1-mini"):
    prompt = f"""
You are enriching {category} hardware data.
Return ONLY valid JSON. Each element must have:

- model_name (string, match input exactly)
- msrp (string, numeric price or approximate launch price if exact unknown)
- live_min (string, lowest current market price or typical minimum if exact unknown)
- live_max (string, highest current market price or typical maximum if exact unknown)
- power_consumption (string, watts or typical value if exact unknown)
- image_url (string, direct .jpg or .png link from manufacturer or major retailer)

Rules:
- Do not invent unrealistic values.
- If exact data is unavailable, provide the most common or typical specification from trusted sources.
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


def enrich_csv(input_file, output_file, category, batch_size=100, debug=False,
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

        writer = csv.DictWriter(outfile, fieldnames=TARGET_FIELDS)
        if not resume or (resume and os.path.getsize(output_file) == 0):
            writer.writeheader()

        batch, rows_buffer = [], []

        for idx, row in enumerate(tqdm(input_rows, desc=f"Enriching models ({model})", unit="model"), start=1):
            model_name = row.get("Model", "").strip()
            if not model_name:
                continue

            if resume and model_name in enriched_models:
                continue

            try:
                benchmark_val = float(row.get("Benchmark", 0))
                if benchmark_val < 50:
                    continue
            except Exception:
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
                    for row_item, enriched in zip(rows_buffer, enriched_batch):
                        merged = {**row_item, **{
                            "MSRP": enriched.get("msrp", ""),
                            "LiveMin": enriched.get("live_min", ""),
                            "LiveMax": enriched.get("live_max", ""),
                            "PowerConsumption": enriched.get("power_consumption", ""),
                            "ImageURL": enriched.get("image_url", "")
                        }}
                        writer.writerow(map_row(merged))
                        cache[row_item["Model"]] = merged
                        enriched_models.add(row_item["Model"])
                batch, rows_buffer = [], []
                time.sleep(1)

        if batch:
            enriched_batch = call_ai_batch(category, batch, debug=debug, model=model)
            if enriched_batch:
                for row_item, enriched in zip(rows_buffer, enriched_batch):
                    merged = {**row_item, **{
                        "MSRP": enriched.get("msrp", ""),
                        "LiveMin": enriched.get("live_min", ""),
                        "LiveMax": enriched.get("live_max", ""),
                        "PowerConsumption": enriched.get("power_consumption", ""),
                        "ImageURL": enriched.get("image_url", "")
                    }}
                    writer.writerow(map_row(merged))
                    cache[row_item["Model"]] = merged
                    enriched_models.add(row_item["Model"])

    # Optional: persist cache
    save_cache(cache)


def rows_with_missing_fields(output_file):
    """Return list of normalized rows with any missing values in TARGET_FIELDS."""
    with open(output_file, newline="", encoding="utf-8") as f:
        reader = list(csv.DictReader(f))
        if not reader:
            return [], []
        def is_missing(val):
            return val in ["", "0", "N/A", "NA", "None"]
        missing_rows = [r for r in reader if any(is_missing(r.get(field, "")) for field in TARGET_FIELDS)]
        return missing_rows, reader[0].keys()


def rerun_missing_fields(output_file, category, debug=False, batch_size=25):
    """Second pass: use GPT-4.1 to re-enrich only rows with missing fields; only fill blanks, never overwrite non-empty."""
    missing_rows, fieldnames = rows_with_missing_fields(output_file)
    if not missing_rows:
        print("No missing fields found for rerun.")
        return

    print(f"\n>>> Rerun: Found {len(missing_rows)} rows with empty fields. Re-enriching using GPT-4.1...")
    batch, rows_buffer = [], []

    temp_file = output_file + ".tmp"
    with open(output_file, newline="", encoding="utf-8") as infile, \
         open(temp_file, "w", newline="", encoding="utf-8") as outfile:
        reader_all = list(csv.DictReader(infile))
        writer = csv.DictWriter(outfile, fieldnames=fieldnames)
        writer.writeheader()

        missing_set = {r["name"] for r in missing_rows if r.get("name")}

        for row in reader_all:
            name = row.get("name", "").strip()
            if name and name in missing_set:
                # We need the original "Model" name sent to the model, but the normalized CSV has only 'name'
                # So we’ll use 'name' directly as the model identifier
                batch.append(name)
                rows_buffer.append(row)

                if len(batch) >= batch_size:
                    enriched_batch = call_ai_batch(category, batch, debug=debug, model="gpt-4.1")
                    if enriched_batch:
                        for row_item, enriched in zip(rows_buffer, enriched_batch):
                            # Only fill missing values
                            def fill(field, new_key):
                                current = row_item.get(field, "")
                                return current if current not in ["", "0", "N/A", "NA", "None"] else (enriched.get(new_key, "") or current)
                            updated = {
                                "brand": row_item.get("brand", ""),
                                "name": row_item.get("name", ""),
                                "benchmark": row_item.get("benchmark", ""),
                                "power_consumption": fill("power_consumption", "power_consumption"),
                                "msrp": fill("msrp", "msrp"),
                                "live_min": fill("live_min", "live_min"),
                                "live_max": fill("live_max", "live_max"),
                                "image_url": fill("image_url", "image_url"),
                                "userbenchmark_url": row_item.get("userbenchmark_url", "")
                            }
                            writer.writerow(updated)
                    else:
                        # Write originals to avoid data loss
                        for row_item in rows_buffer:
                            writer.writerow(row_item)
                    batch, rows_buffer = [], []
                    time.sleep(1)
            else:
                writer.writerow(row)

        # Flush remaining
        if batch:
            enriched_batch = call_ai_batch(category, batch, debug=debug, model="gpt-4.1")
            if enriched_batch:
                for row_item, enriched in zip(rows_buffer, enriched_batch):
                    def fill(field, new_key):
                        current = row_item.get(field, "")
                        return current if current not in ["", "0", "N/A", "NA", "None"] else (enriched.get(new_key, "") or current)
                    updated = {
                        "brand": row_item.get("brand", ""),
                        "name": row_item.get("name", ""),
                        "benchmark": row_item.get("benchmark", ""),
                        "power_consumption": fill("power_consumption", "power_consumption"),
                        "msrp": fill("msrp", "msrp"),
                        "live_min": fill("live_min", "live_min"),
                        "live_max": fill("live_max", "live_max"),
                        "image_url": fill("image_url", "image_url"),
                        "userbenchmark_url": row_item.get("userbenchmark_url", "")
                    }
                    writer.writerow(updated)
            else:
                for row_item in rows_buffer:
                    writer.writerow(row_item)

    os.replace(temp_file, output_file)
    print(">>> Rerun complete. Output file updated.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI enrichment for hardware CSVs with GPT-4.1-mini + rerun with GPT-4.1")
    parser.add_argument("--file", required=True, help="Path to input CSV")
    parser.add_argument("--category", required=True, choices=["CPU", "GPU", "RAM", "SSD", "PSU", "Motherboard"])
    parser.add_argument("--batch-size", type=int, default=100, help="Number of models per batch (first pass)")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--resume", action="store_true", help="Resume from existing cache and CSV")
    parser.add_argument("--fresh", action="store_true", help="Clear cache and CSV, start fresh")
    parser.add_argument("--no-rerun", action="store_true", help="Skip second pass rerun with GPT-4.1")
    parser.add_argument("--rerun-only", action="store_true", help="Run only the second pass rerun with GPT-4.1")
    args = parser.parse_args()

    input_file = args.file
    output_file = input_file.replace(".csv", "_enriched.csv")

    if args.rerun_only:
        rerun_missing_fields(output_file, args.category, debug=args.debug, batch_size=25)
    else:
        # First pass: GPT-4.1-mini
        enrich_csv(
            input_file=input_file,
            output_file=output_file,
            category=args.category,
            batch_size=args.batch_size,
            debug=args.debug,
            resume=args.resume,
            fresh=args.fresh,
            model="gpt-4.1-mini"
        )
        print(f"Enriched CSV written to {output_file}")

        # Second pass: GPT-4.1 (only rows with missing fields)
        if not args.no_rerun:
            rerun_missing_fields(output_file, args.category, debug=args.debug, batch_size=25)
