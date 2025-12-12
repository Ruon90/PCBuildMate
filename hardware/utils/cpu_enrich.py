import argparse
import csv
import json
import os
import re
import time
from pathlib import Path

import pandas as pd
import requests
from tqdm import tqdm


# -------------------------------------------------
# Tokens and endpoints
# -------------------------------------------------
GITHUB_TOKEN_MINI = os.getenv("GITHUB_TOKEN_MINI") or os.getenv("GITHUB_TOKEN")
GITHUB_TOKEN_FULL = os.getenv("GITHUB_TOKEN_FULL") or os.getenv("GITHUB_TOKEN")

CACHE_FILE = "cpu_enrich_cache.json"

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
    "gpt-4.1-mini": GITHUB_TOKEN_MINI or "",
    "gpt-4.1": GITHUB_TOKEN_FULL or "",
}

# -------------------------------------------------
# Final output schema
# -------------------------------------------------
TARGET_FIELDS = [
    "brand",
    "model",
    "socket",
    "name",
    "price",
    "core_count",
    "core_clock",
    "boost_clock",
    "microarchitecture",
    "tdp",
    "graphics",
    "thread_count",
    "userbenchmark_score",
    "blender_score",
    "power_consumption_overclocked",
    "release_date",
    "slug",
]

# -------------------------------------------------
# Socket mapping for deterministic fill
# -------------------------------------------------
SOCKET_MAP = {
    "Zen 5": "AM5",
    "Zen 4": "AM5",
    "Zen 3": "AM4",
    "Zen 2": "AM4",
    "Zen+": "AM4",
    "Alder Lake": "LGA1700",
    "Raptor Lake": "LGA1700",
    "Comet Lake": "LGA1200",
    "Coffee Lake": "LGA1151",
    "Skylake": "LGA1151",
    "Threadripper": "sTRX4",
    "Sapphire Rapids": "LGA4677",
    "Cascade Lake": "LGA3647",
}


# -------------------------------------------------
# Cache helpers
# -------------------------------------------------
def load_cache():
    return (
        json.load(open(CACHE_FILE, "r", encoding="utf-8"))
        if os.path.exists(CACHE_FILE)
        else {}
    )


def save_cache(cache):
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2)


# -------------------------------------------------
# Row mapping
# -------------------------------------------------
def map_row(row):
    def clean(v):
        if v in [None, "", "N/A", "NA", "None"]:
            return ""
        return str(v).strip()

    return {f: clean(row.get(f)) for f in TARGET_FIELDS}


# -------------------------------------------------
# AI enrichment (batch)
# -------------------------------------------------
def call_ai_batch(category, models, debug=False, model="gpt-4.1-mini"):
    prompt = f"""
You are enriching {category} hardware data.
Return ONLY valid JSON (array). Each element must have:
- model_name (string, match input exactly)
- thread_count (integer)
- release_date (string, YYYY-MM-DD or null)
- power_consumption_overclocked (integer watts under typical
    OC load; null if unknown)

Rules:
- If SMT/HyperThreading supported, threads = cores*2 else cores.
-- For Intel CPUs: use Max Turbo TDP (MT TDP) as a proxy for
    overclocked power. If unavailable, assume TDP + 50–100W.
-- For AMD CPUs: use PPT max (Package Power Tracking) as a proxy for
    overclocked power. If unavailable, assume TDP + 20–50W.
- Always return a numeric wattage if any of these values are known.

Models:
{chr(10).join(models)}
"""
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

    for attempt in range(2):
        try:
            r = requests.post(
                url, headers=headers, json=payload, timeout=(10, 90)
            )
            if r.status_code != 200:
                if debug:
                    print(
                        f"[{model}] Non-200: {r.status_code} -> {r.text[:300]}"
                    )
                time.sleep(1.5)
                continue
            content = r.json()["choices"][0]["message"]["content"].strip()
            cleaned = re.sub(
                r"^```[a-zA-Z]*\s*|\s*```$", "", content, flags=re.MULTILINE
            ).strip()
            data = json.loads(cleaned)
            return data if isinstance(data, list) else []
        except Exception as e:
            if debug:
                print(f"[{model}] post/parse error: {e}")
            time.sleep(1.5)
    return []


# -------------------------------------------------
# Fallback rule for OC power
# -------------------------------------------------
def fallback_oc_power(cpu_row):
    try:
        tdp = int(float(str(cpu_row.get("tdp") or "0").strip()))
    except Exception:
        tdp = 100
    brand = (cpu_row.get("brand") or "").strip().lower()
    if "intel" in brand:
        return str(tdp + 75)
    elif "amd" in brand:
        return str(tdp + 35)
    return str(tdp + 25)


# -------------------------------------------------
# Slug builder
# -------------------------------------------------
def build_cpu_slug(name: str) -> str:
    if not isinstance(name, str):
        return ""
    s = name.upper().strip()
    s = re.sub(r"\b(INTEL|AMD|RYZEN|CORE|PROCESSOR|CPU|I3|I5|I7|I9)\b", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    m = re.search(r"\b(\d{4,5}(?:X3D|XT|X|G|GT|GE|F|K|KF|KS|T)?)\b", s)
    if m:
        return m.group(1).lower()
    m_server = re.search(r"\b(\d{4,5}[A-Z]{0,2})\b", s)
    if m_server:
        return m_server.group(1).lower()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


# -------------------------------------------------
# Benchmark merge
# -------------------------------------------------
def add_benchmarks_inplace(output_file: Path, debug=False):
    try:
        df = pd.read_csv(output_file)
    except Exception:
        df = pd.read_csv(output_file, engine="python", on_bad_lines="warn")

    df.columns = df.columns.str.strip().str.lower()
    if "model" not in df.columns:
        df["model"] = df["name"].fillna("").astype(str)

    base = Path(__file__).resolve().parent
    ub_file = (
        base.parent.parent / "data/benchmark/CPU_UserBenchmarks_clean.csv"
    )
    blender_file = base.parent.parent / "data/benchmark/Blender_CPU_clean.csv"

    df_ub = pd.read_csv(ub_file, encoding="utf-8-sig")
    df_blender = pd.read_csv(blender_file, encoding="utf-8-sig")
    df_ub.columns = df_ub.columns.str.strip().str.lower()
    df_blender.columns = df_blender.columns.str.strip().str.lower()

    if "slug" not in df.columns:
        df["slug"] = df["model"].astype(str).map(build_cpu_slug)

    ub_lookup = dict(
        zip(
            df_ub["slug"].astype(str).str.lower().str.strip(),
            df_ub["benchmark"],
        )
    )
    bl_lookup = dict(
        zip(
            df_blender["slug"].astype(str).str.lower().str.strip(),
            df_blender["median score"],
        )
    )

    norm_slug = df["slug"].astype(str).str.lower().str.strip()
    df["userbenchmark_score"] = norm_slug.map(ub_lookup)
    df["blender_score"] = norm_slug.map(bl_lookup)

    for col in TARGET_FIELDS:
        if col not in df.columns:
            df[col] = ""
    df = df[TARGET_FIELDS]

    import csv as _csv

    df.to_csv(output_file, index=False, quoting=_csv.QUOTE_MINIMAL)
    print(f"Benchmarks added to {output_file}")


# -------------------------------------------------
# Socket merge (deterministic mapping)
# -------------------------------------------------
def add_sockets_inplace(output_file: Path, debug=False):
    df = pd.read_csv(output_file)
    df.columns = df.columns.str.strip().str.lower()

    def fallback_socket(row):
        arch = (row.get("microarchitecture") or "").strip()
        return SOCKET_MAP.get(arch, "")

    df["socket"] = df.apply(fallback_socket, axis=1)

    for col in TARGET_FIELDS:
        if col not in df.columns:
            df[col] = ""
    df = df[TARGET_FIELDS]

    import csv as _csv

    df.to_csv(output_file, index=False, quoting=_csv.QUOTE_MINIMAL)
    print(f"Sockets added to {output_file}")


# -------------------------------------------------
# Enrichment pipeline
# -------------------------------------------------
def enrich_csv(
    input_file,
    output_file,
    category="CPU",
    batch_size=50,
    debug=False,
    resume=False,
    fresh=False,
):
    if fresh:
        if os.path.exists(CACHE_FILE):
            os.remove(CACHE_FILE)
        if os.path.exists(output_file):
            os.remove(output_file)

    cache = load_cache() if (resume and os.path.exists(CACHE_FILE)) else {}
    stats = {"mini": 0, "full": 0, "fallback": 0}

    enriched_models = set()
    if resume and os.path.exists(output_file):
        with open(output_file, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                enriched_models.add(row.get("name", ""))

    outfh = open(output_file, "a", newline="", encoding="utf-8")
    writer = csv.DictWriter(
        outfh,
        fieldnames=TARGET_FIELDS,
        extrasaction="ignore",
        quoting=csv.QUOTE_ALL,
    )
    if not resume or (resume and os.path.getsize(output_file) == 0):
        writer.writeheader()

    with open(input_file, newline="", encoding="utf-8") as infh:
        input_rows = list(csv.DictReader(infh))

    def write_row_with_source(r, e, source=None):
        merged = {
            **r,
            "thread_count": e.get("thread_count", ""),
            "release_date": e.get("release_date", ""),
            "power_consumption_overclocked": e.get(
                "power_consumption_overclocked", ""
            ),
        }

        if merged["power_consumption_overclocked"]:
            if source == "mini":
                stats["mini"] += 1
            elif source == "full":
                stats["full"] += 1
        else:
            merged["power_consumption_overclocked"] = fallback_oc_power(r)
            stats["fallback"] += 1

        if not merged.get("slug"):
            merged["slug"] = build_cpu_slug(
                merged.get("model") or merged.get("name") or ""
            )

        writer.writerow(map_row(merged))
        cache[r.get("name", "")] = {
            **merged,
            "power_consumption_overclocked": str(
                merged.get("power_consumption_overclocked") or ""
            ),
            "release_date": str(merged.get("release_date") or ""),
        }

    # Batch process with two-pass AI
    batch, buf = [], []
    for row in tqdm(input_rows, desc="Enriching CPUs", unit="cpu"):
        name = (row.get("name") or "").strip()
        if not name:
            continue
        if resume and name in enriched_models:
            continue

        # Cache hit
        if name in cache:
            cached = cache[name]
            merged_row = {
                **row,
                "thread_count": cached.get("thread_count", ""),
                "release_date": cached.get("release_date", ""),
                "power_consumption_overclocked": cached.get(
                    "power_consumption_overclocked", ""
                ),
                "slug": cached.get("slug")
                or build_cpu_slug(
                    cached.get("model") or cached.get("name") or ""
                ),
            }
            writer.writerow(map_row(merged_row))
            continue

        batch.append(name)
        buf.append(row)

        if len(batch) >= batch_size:
            enriched_map = {}

            # Pass 1: mini
            res_mini = call_ai_batch(
                category, batch, debug=debug, model="gpt-4.1-mini"
            )
            mini_map = {e.get("model_name", ""): e for e in (res_mini or [])}
            for k, v in mini_map.items():
                enriched_map[k] = {
                    "model_name": k,
                    "thread_count": v.get("thread_count"),
                    "release_date": v.get("release_date"),
                    "power_consumption_overclocked": v.get(
                        "power_consumption_overclocked"
                    ),
                }

            # Pass 2: full
            res_full = call_ai_batch(
                category, batch, debug=debug, model="gpt-4.1"
            )
            full_map = {e.get("model_name", ""): e for e in (res_full or [])}
            for k, v in full_map.items():
                base = enriched_map.get(k, {})
                enriched_map[k] = {
                    "model_name": k,
                    "thread_count": v.get(
                        "thread_count", base.get("thread_count")
                    ),
                    "release_date": v.get(
                        "release_date", base.get("release_date")
                    ),
                    "power_consumption_overclocked": v.get(
                        "power_consumption_overclocked",
                        base.get("power_consumption_overclocked"),
                    ),
                }

            # Write rows
            for r in buf:
                name_key = r.get("name", "")
                e = enriched_map.get(name_key, {})
                src = None
                if (
                    name_key in full_map
                    and full_map[name_key].get("power_consumption_overclocked")
                    is not None
                ):
                    src = "full"
                elif (
                    name_key in mini_map
                    and mini_map[name_key].get("power_consumption_overclocked")
                    is not None
                ):
                    src = "mini"
                write_row_with_source(r, e, source=src)

            batch, buf = [], []
            time.sleep(1)

    # Flush remaining
    if batch:
        enriched_map = {}

        res_mini = call_ai_batch(
            category, batch, debug=debug, model="gpt-4.1-mini"
        )
        mini_map = {e.get("model_name", ""): e for e in (res_mini or [])}
        for k, v in mini_map.items():
            enriched_map[k] = {
                "model_name": k,
                "thread_count": v.get("thread_count"),
                "release_date": v.get("release_date"),
                "power_consumption_overclocked": v.get(
                    "power_consumption_overclocked"
                ),
            }

        res_full = call_ai_batch(category, batch, debug=debug, model="gpt-4.1")
        full_map = {e.get("model_name", ""): e for e in (res_full or [])}
        for k, v in full_map.items():
            base = enriched_map.get(k, {})
            enriched_map[k] = {
                "model_name": k,
                "thread_count": v.get(
                    "thread_count", base.get("thread_count")
                ),
                "release_date": v.get(
                    "release_date", base.get("release_date")
                ),
                "power_consumption_overclocked": v.get(
                    "power_consumption_overclocked",
                    base.get("power_consumption_overclocked"),
                ),
            }

        for r in buf:
            name_key = r.get("name", "")
            e = enriched_map.get(name_key, {})
            src = None
            if (
                name_key in full_map
                and full_map[name_key].get("power_consumption_overclocked")
                is not None
            ):
                src = "full"
            elif (
                name_key in mini_map
                and mini_map[name_key].get("power_consumption_overclocked")
                is not None
            ):
                src = "mini"
            write_row_with_source(r, e, source=src)

    outfh.close()
    save_cache(cache)

    # Attach benchmarks in place (keeps schema order)
    add_benchmarks_inplace(Path(output_file), debug=debug)

    # Summary
    total = stats["mini"] + stats["full"] + stats["fallback"]

    def pct(x):
        return f"{(x / total * 100):.1f}%" if total else "0.0%"

    print("\n=== Enrichment Summary ===")
    print(f"Total CPUs processed: {total}")
    print(f"Mini model OC power: {stats['mini']} ({pct(stats['mini'])})")
    print(f"Full model OC power: {stats['full']} ({pct(stats['full'])})")
    print(f"Fallback applied: {stats['fallback']} ({pct(stats['fallback'])})")
    print(f"Enriched CPU CSV written to {output_file}")


# -------------------------------------------------
# CLI entrypoint
# -------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description=(
            "CPU enrichment with OC power, release date, "
            "benchmarks, sockets"
        )
    )
    parser.add_argument("--file", required=True)
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--fresh", action="store_true")
    parser.add_argument("--benchmark", action="store_true")
    parser.add_argument("--socket", action="store_true")
    args = parser.parse_args()

    input_file = args.file
    output_file = input_file.replace(".csv", "_enriched.csv")

    if args.benchmark:
        import shutil

        shutil.copy(input_file, output_file)
        add_benchmarks_inplace(Path(output_file), debug=args.debug)
        print(
            "\n=== Benchmark-only mode ===\nBenchmarks attached to "
            + str(output_file)
        )
    elif args.socket:
        # Instead of copying the raw input, operate on the enriched file
        add_sockets_inplace(Path(output_file), debug=args.debug)
        print(f"\n=== Socket-only mode ===\nSockets attached to {output_file}")
    else:
        enrich_csv(
            input_file=input_file,
            output_file=output_file,
            batch_size=args.batch_size,
            debug=args.debug,
            resume=args.resume,
            fresh=args.fresh,
        )


if __name__ == "__main__":
    main()
