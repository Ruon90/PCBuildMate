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

# -----------------------------
# Tokens and endpoints
# -----------------------------
GITHUB_TOKEN_MINI = os.getenv("GITHUB_TOKEN_MINI") or os.getenv("GITHUB_TOKEN")
GITHUB_TOKEN_FULL = os.getenv("GITHUB_TOKEN_FULL") or os.getenv("GITHUB_TOKEN")

CACHE_FILE = "cpu_enrich_cache.json"

ENDPOINTS = {
    "gpt-4.1-mini": "https://models.inference.ai.azure.com/openai/deployments/gpt-4.1-mini/chat/completions",
    "gpt-4.1": "https://models.inference.ai.azure.com/openai/deployments/gpt-4.1/chat/completions"
}
TOKENS = {
    "gpt-4.1-mini": GITHUB_TOKEN_MINI or "",
    "gpt-4.1": GITHUB_TOKEN_FULL or ""
}

# -----------------------------
# Final output schema (15 fields)
# -----------------------------
TARGET_FIELDS = [
    "brand", "model", "socket", "name", "price",
    "core_count", "core_clock", "boost_clock", "microarchitecture",
    "tdp", "graphics", "thread_count",
    "userbenchmark_score", "blender_score",
    "power_consumption_overclocked", "slug"
]

# -----------------------------
# Cache helpers
# -----------------------------
def load_cache():
    return json.load(open(CACHE_FILE, "r", encoding="utf-8")) if os.path.exists(CACHE_FILE) else {}

def save_cache(cache):
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2)

# -----------------------------
# Row mapping (strict to schema)
# -----------------------------
def map_row(row):
    def clean(v):
        if v in [None, "", "0", "N/A", "NA", "None"]:
            return ""
        return str(v).strip()
    return {f: clean(row.get(f)) for f in TARGET_FIELDS}

# -----------------------------
# AI enrichment (batch)
# -----------------------------
def call_ai_batch(category, models, debug=False, model="gpt-4.1-mini"):
    prompt = f"""
You are enriching {category} hardware data.
Return ONLY valid JSON (array). Each element must have:
- model_name (string, match input exactly)
- thread_count (integer)
- release_date (string, YYYY-MM-DD or null)
- power_consumption_overclocked (integer watts under typical OC load; null if unknown)
Rules:
- If SMT/HyperThreading supported, threads = cores*2 else cores.
- Intel often +50–100W over TDP, AMD +20–50W.
Models:
{chr(10).join(models)}
"""
    url = ENDPOINTS[model]
    token = TOKENS[model]
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0
    }

    for attempt in range(2):
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=(10, 90))
            if r.status_code != 200:
                if debug:
                    print(f"[{model}] Non-200: {r.status_code} -> {r.text[:300]}")
                time.sleep(1.5)
                continue
            content = r.json()["choices"][0]["message"]["content"].strip()
            cleaned = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", content, flags=re.MULTILINE).strip()
            data = json.loads(cleaned)
            return data if isinstance(data, list) else []
        except Exception as e:
            if debug:
                print(f"[{model}] post/parse error: {e}")
            time.sleep(1.5)
    return []

# -----------------------------
# Fallback rule for OC power
# -----------------------------
def fallback_oc_power(cpu_row):
    try:
        tdp = int(str(cpu_row.get("tdp") or "0").strip())
    except Exception:
        return ""
    brand = (cpu_row.get("brand") or "").lower()
    if "intel" in brand:
        return str(tdp + 75)
    elif "amd" in brand:
        return str(tdp + 35)
    return str(tdp + 25)

# -----------------------------
# Benchmark merge helpers
# -----------------------------
def normalize(s: str) -> str:
    if not s:
        return ""
    s = s.lower()
    # remove brand words
    s = re.sub(r"\b(intel|amd|ryzen|core|processor|cpu)\b", "", s)
    # remove non-alphanumeric
    s = re.sub(r"[^a-z0-9]", "", s)
    return s.strip()

def build_cpu_slug(name: str) -> str:
    if not isinstance(name, str):
        return ""
    s = name.upper()

    # Remove vendor noise
    s = re.sub(r"\b(INTEL|AMD|PROCESSOR|CPU)\b", "", s)
    s = re.sub(r"\b(CORE|RYZEN)\b", "", s)

    # Normalize whitespace
    s = re.sub(r"\s+", " ", s).strip()

    # Intel tokens: i3/i5/i7/i9 + gen-number + optional suffixes
    m_intel = re.search(r"\b(I[3579])[-\s]*(\d{4,5})(?:[-\s]*(KF|KS|K|F|T))?\b", s)
    if m_intel:
        series, num, suf = m_intel.groups()
        slug = f"{series.lower()}-{num.lower()}"
        if suf:
            slug += f"-{suf.lower()}"
        return slug

    # AMD Ryzen tokens: 3/5/7/9 + model + optional X/X3D/XT/GE/G/GT/F
    m_amd = re.search(r"\b([3579])\b.*?\b(\d{4}x3d|\d{4}xt|\d{4}ge|\d{4}gt|\d{4}g|\d{4}f|\d{4}x|\d{4})\b", s)
    if m_amd:
        family, model = m_amd.groups()
        # strip spaces/dashes inside model
        model = re.sub(r"[-\s]", "", model.lower())
        return f"{model}"

    # EPYC / Xeon: take main numeric block (best‑effort)
    m_server = re.search(r"\b(EPYC|XEON)\b.*?\b(\d{4,5}[A-Z]{0,2})\b", s)
    if m_server:
        return re.sub(r"[-\s]", "", m_server.group(2).lower())

    # Fallback: compact alphanumerics
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")

def make_slug_for_cpu(name: str) -> str:
    # Reuse same logic as build_cpu_slug to ensure identical keys in output
    return build_cpu_slug(name)

def add_benchmarks_inplace(output_file: Path, debug=False):
    try:
        df = pd.read_csv(output_file)
    except Exception:
        df = pd.read_csv(output_file, engine="python", on_bad_lines="warn")

    if "model" not in df.columns:
        df["model"] = df["name"].fillna("").astype(str)

    base = Path(__file__).resolve().parent
    ub_file = base.parent.parent / "data/benchmark/CPU_UserBenchmarks_clean.csv"
    blender_file = base.parent.parent / "data/benchmark/Blender_CPU_clean.csv"

    if debug:
        print(f"Loading cleaned benchmarks:\n- {ub_file}\n- {blender_file}")

    df_ub = pd.read_csv(ub_file, encoding="utf-8-sig")
    df_blender = pd.read_csv(blender_file, encoding="utf-8-sig")

    # --- Slug generation for CPUs ---
    df["slug"] = df["model"].astype(str).map(build_cpu_slug)  # <-- keep slug column in output

    # Build lookups
    ub_lookup = dict(zip(df_ub["Slug"].astype(str), df_ub["Benchmark"]))
    bl_lookup = dict(zip(df_blender["Slug"].astype(str), df_blender["Median Score"]))

    # Map scores by slug
    df["userbenchmark_score"] = df["slug"].map(ub_lookup)
    df["blender_score"] = df["slug"].map(bl_lookup)

    # Keep slug column visible for debugging
    cols_with_slug = TARGET_FIELDS + ["slug"]
    for col in cols_with_slug:
        if col not in df.columns:
            df[col] = ""
    df = df[cols_with_slug]

    import csv as _csv
    df.to_csv(output_file, index=False, quoting=_csv.QUOTE_MINIMAL)
    print(f"Benchmarks + slug added to {output_file}")


# -----------------------------
# Enrichment pipeline
# -----------------------------
def enrich_csv(input_file, output_file, category="CPU", batch_size=50, debug=False,
               resume=False, fresh=False):
    # Fresh start: clear cache and output to avoid header mismatches
    if fresh:
        if os.path.exists(CACHE_FILE):
            os.remove(CACHE_FILE)
        if os.path.exists(output_file):
            os.remove(output_file)

    cache = load_cache() if (resume and os.path.exists(CACHE_FILE)) else {}

    stats = {"mini": 0, "full": 0, "fallback": 0}

    # Track already enriched names (resume mode)
    enriched_models = set()
    if resume and os.path.exists(output_file):
        with open(output_file, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                enriched_models.add(row.get("name", ""))

    # Prepare writer (always with final schema)
    outfh = open(output_file, "a", newline="", encoding="utf-8")
    writer = csv.DictWriter(outfh, fieldnames=TARGET_FIELDS, extrasaction="ignore", quoting=csv.QUOTE_ALL)
    if not resume or (resume and os.path.getsize(output_file) == 0):
        writer.writeheader()

    # Read input rows
    with open(input_file, newline="", encoding="utf-8") as infh:
        input_rows = list(csv.DictReader(infh))

    # Helper: write row and apply fallback if needed
    def write_row_with_source(r, e, source=None):
        merged = {
            **r,
            "thread_count": e.get("thread_count", ""),
            "release_date": e.get("release_date", ""),
            "power_consumption_overclocked": e.get("power_consumption_overclocked", "")
        }
        if merged["power_consumption_overclocked"]:
            if source == "mini":
                stats["mini"] += 1
            elif source == "full":
                stats["full"] += 1
        else:
            merged["power_consumption_overclocked"] = fallback_oc_power(r)
            stats["fallback"] += 1

        writer.writerow(map_row(merged))
        cache[r.get("name", "")] = merged

    # Process rows in batches with two-pass AI
    batch, buf = [], []
    for row in tqdm(input_rows, desc="Enriching CPUs", unit="cpu"):
        name = (row.get("name") or "").strip()
        if not name:
            continue
        if resume and name in enriched_models:
            continue

        # Cache hit path
        if name in cache:
            cached = cache[name]
            if not cached.get("power_consumption_overclocked"):
                cached["power_consumption_overclocked"] = fallback_oc_power(row)
                stats["fallback"] += 1
            writer.writerow(map_row({**row, **cached}))
            continue

        # Accumulate batch
        batch.append(name)
        buf.append(row)

        # Flush when batch full
        if len(batch) >= batch_size:
            # Two passes: mini then full
            enriched_map = {}

            # Pass 1: mini
            res_mini = call_ai_batch(category, batch, debug=debug, model="gpt-4.1-mini")
            mini_map = {e.get("model_name", ""): e for e in (res_mini or [])}
            enriched_map.update(mini_map)

            # Pass 2: full (fill gaps or override where present)
            res_full = call_ai_batch(category, batch, debug=debug, model="gpt-4.1")
            full_map = {e.get("model_name", ""): e for e in (res_full or [])}
            # Merge: prefer full where it provides fields
            for k, v in full_map.items():
                base = enriched_map.get(k, {})
                merged_choice = {
                    "model_name": k,
                    "thread_count": v.get("thread_count", base.get("thread_count")),
                    "release_date": v.get("release_date", base.get("release_date")),
                    "power_consumption_overclocked": v.get("power_consumption_overclocked", base.get("power_consumption_overclocked"))
                }
                enriched_map[k] = merged_choice

            # Write rows
            for r in buf:
                name_key = r.get("name", "")
                e = enriched_map.get(name_key, {})
                # Decide source for stats (if full added value, count full; else mini if present)
                src = None
                if name_key in full_map and full_map[name_key].get("power_consumption_overclocked"):
                    src = "full"
                elif name_key in mini_map and mini_map[name_key].get("power_consumption_overclocked"):
                    src = "mini"
                write_row_with_source(r, e, source=src)

            batch, buf = [], []
            time.sleep(1)

    # Flush remaining
    if batch:
        enriched_map = {}
        res_mini = call_ai_batch(category, batch, debug=debug, model="gpt-4.1-mini")
        mini_map = {e.get("model_name", ""): e for e in (res_mini or [])}
        enriched_map.update(mini_map)

        res_full = call_ai_batch(category, batch, debug=debug, model="gpt-4.1")
        full_map = {e.get("model_name", ""): e for e in (res_full or [])}
        for k, v in full_map.items():
            base = enriched_map.get(k, {})
            merged_choice = {
                "model_name": k,
                "thread_count": v.get("thread_count", base.get("thread_count")),
                "release_date": v.get("release_date", base.get("release_date")),
                "power_consumption_overclocked": v.get("power_consumption_overclocked", base.get("power_consumption_overclocked"))
            }
            enriched_map[k] = merged_choice

        for r in buf:
            name_key = r.get("name", "")
            e = enriched_map.get(name_key, {})
            src = None
            if name_key in full_map and full_map[name_key].get("power_consumption_overclocked"):
                src = "full"
            elif name_key in mini_map and mini_map[name_key].get("power_consumption_overclocked"):
                src = "mini"
            write_row_with_source(r, e, source=src)

    outfh.close()
    save_cache(cache)

    # Attach benchmarks in place
    add_benchmarks_inplace(Path(output_file), debug=debug)

    # Summary
    total = stats["mini"] + stats["full"] + stats["fallback"]
    pct = lambda x: f"{(x / total * 100):.1f}%" if total else "0.0%"
    print("\n=== Enrichment Summary ===")
    print(f"Total CPUs processed: {total}")
    print(f"Mini model OC power: {stats['mini']} ({pct(stats['mini'])})")
    print(f"Full model OC power: {stats['full']} ({pct(stats['full'])})")
    print(f"Fallback applied: {stats['fallback']} ({pct(stats['fallback'])})")
    print(f"Enriched CPU CSV written to {output_file}")

# -----------------------------
# CLI entrypoint
# -----------------------------
def main():
    parser = argparse.ArgumentParser(description="CPU enrichment (two-pass AI) + OC power fallback + benchmark merge")
    parser.add_argument("--file", required=True, help="Path to input CSV (e.g., data/cpu/cpu-clean.csv)")
    parser.add_argument("--batch-size", type=int, default=50, help="Number of CPUs per batch")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--resume", action="store_true", help="Resume from existing cache and CSV")
    parser.add_argument("--fresh", action="store_true", help="Clear cache/output and start fresh")
    args = parser.parse_args()

    input_file = args.file
    output_file = input_file.replace(".csv", "_enriched.csv")

    enrich_csv(
        input_file=input_file,
        output_file=output_file,
        batch_size=args.batch_size,
        debug=args.debug,
        resume=args.resume,
        fresh=args.fresh
    )

if __name__ == "__main__":
    main()
