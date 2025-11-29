import os
import argparse
import requests
import json
import time
import re
from pathlib import Path
import pandas as pd
import env

TARGET_FIELDS = [
    "brand",
    "model",
    "GpuName",
    "userbenchmark_score",
    "userbenchmark_url",
    "blender_score",
    "price",
    "slug"
]

# Tokens and endpoints
GITHUB_TOKEN_MINI = os.getenv("GITHUB_TOKEN_MINI") or os.getenv("GITHUB_TOKEN")
GITHUB_TOKEN_FULL = os.getenv("GITHUB_TOKEN_FULL") or os.getenv("GITHUB_TOKEN")

ENDPOINTS = {
    "gpt-4.1-mini": "https://models.inference.ai.azure.com/openai/deployments/gpt-4.1-mini/chat/completions",
    "gpt-4.1": "https://models.inference.ai.azure.com/openai/deployments/gpt-4.1/chat/completions"
}

def select_token(model: str) -> str:
    return GITHUB_TOKEN_MINI if model == "gpt-4.1-mini" else GITHUB_TOKEN_FULL

def get_endpoint(model: str) -> str:
    ep = ENDPOINTS.get(model)
    if not ep:
        raise ValueError(f"Unknown model '{model}'. Available: {list(ENDPOINTS.keys())}")
    return ep

# -----------------------------
# Slug builder
# -----------------------------
def build_slug(name: str) -> str:
    if not isinstance(name, str):
        return ""
    s = name.upper()
    s = re.sub(r"\b(GEFORCE|RADEON|NVIDIA|AMD|INTEL)\b", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    tokens = re.findall(r"(RTX|RX|\d{3,4}|TI|SUPER|XT|XTX)", s)
    return "-".join(tok.lower() for tok in tokens)

# -----------------------------
# AI MSRP enrichment
# -----------------------------
def call_ai_batch(category, items, debug=False, model="gpt-4.1-mini"):
    prompt = f"""
You are enriching {category} hardware data. Return ONLY valid JSON array.
Rules:
- Each element must have: model_name (string, match input exactly), msrp (number in USD or null).
- If MSRP is unknown, set msrp to null (do not guess).
- Do not add extra fields or text.
- Output must be a valid JSON array.

List:
{chr(10).join(items)}
"""
    token = select_token(model)
    endpoint = get_endpoint(model)

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0
    }

    for attempt in range(3):
        try:
            resp = requests.post(endpoint, headers=headers, json=payload, timeout=(10, 90))
            if debug:
                print(f"[AI] {model} -> Status {resp.status_code}")
        except Exception as e:
            print(f"[AI] HTTP error ({model}): {e}")
            time.sleep(5 * (attempt + 1))
            continue

        if resp.status_code != 200:
            print(f"[AI] Non-200 ({model}): {resp.status_code} {resp.text}")
            time.sleep(5 * (attempt + 1))
            continue

        try:
            data = resp.json()
        except Exception as e:
            print(f"[AI] JSON decode error ({model}): {e}")
            continue

        if "choices" not in data or not data["choices"]:
            if debug:
                print(f"[AI] No choices in response ({model})")
            return []

        content = data["choices"][0]["message"]["content"].strip()
        cleaned = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", content, flags=re.MULTILINE).strip()

        try:
            parsed = json.loads(cleaned)
            return parsed if isinstance(parsed, list) else []
        except Exception:
            if debug:
                preview = content[:500].replace("\n", " ")
                print(f"[AI] Parse error ({model}); preview: {preview}")
            return []
    return []

# -----------------------------
# Benchmark attachment
# -----------------------------
def add_gpu_benchmarks(output_file: Path, debug=False):
    df = pd.read_csv(output_file)

    if "GpuName" not in df.columns:
        raise ValueError("Cleaned GPU CSV must contain a 'GpuName' column")

    root = Path(__file__).resolve().parent.parent.parent
    ub_file = root / "data/benchmark/GPU_UserBenchmarks_clean.csv"
    blender_file = root / "data/benchmark/Blender_GPU_clean.csv"

    df_ub = pd.read_csv(ub_file, encoding="utf-8-sig")
    df_blender = pd.read_csv(blender_file, encoding="utf-8-sig")

    def find_userbenchmark(slug: str):
        matches = df_ub[df_ub["Slug"] == slug]
        if not matches.empty:
            return matches.iloc[0]["Benchmark"], matches.iloc[0]["URL"]
        return None, None

    def find_blender(slug: str):
        matches = df_blender[df_blender["Slug"] == slug]
        if not matches.empty:
            return matches.iloc[0]["Median Score"]
        return None

    # ✅ Use slug column directly
    df[["userbenchmark_score", "userbenchmark_url"]] = df["slug"].apply(
        lambda s: pd.Series(find_userbenchmark(s))
    )
    df["blender_score"] = df["slug"].apply(find_blender)

    if debug:
        print("[DEBUG] Sample matches (first 30 rows):")
        print(df[["GpuName","slug","userbenchmark_score","blender_score"]].head(30))

    before = len(df)
    df = df.dropna(subset=["userbenchmark_score", "blender_score"], how="all")
    after = len(df)

    if debug:
        print(f"[DEBUG] Pruned GPUs without benchmarks: {before - after} removed, {after} remain")

    df.to_csv(output_file, index=False)
    print(f"GPU benchmarks attached and pruned -> {output_file}")

# -----------------------------
# Two-pass MSRP enrichment
# -----------------------------
def enrich_gpu_price(output_file: Path, debug=False, batch_size=50):
    df = pd.read_csv(output_file)
    names = df.get("GpuName", pd.Series(dtype=str)).astype(str).tolist()

    prices = {}

    # Pass 1: gpt-4.1-mini
    for i in range(0, len(names), batch_size):
        batch = names[i:i+batch_size]
        enriched = call_ai_batch("GPU", batch, debug=debug, model="gpt-4.1-mini")
        for e in enriched or []:
            name = e.get("model_name")
            msrp = e.get("msrp")
            if name is not None and msrp is not None:
                prices[name] = msrp

    missing = [n for n in names if n not in prices]
    if debug:
        print(f"[DEBUG] Missing after pass 1: {len(missing)} GPUs")

    # Pass 2: gpt-4.1
    for i in range(0, len(missing), batch_size):
        batch = missing[i:i+batch_size]
        enriched = call_ai_batch("GPU", batch, debug=debug, model="gpt-4.1")
        for e in enriched or []:
            name = e.get("model_name")
            msrp = e.get("msrp")
            if name is not None and msrp is not None:
                prices[name] = msrp

    df["price"] = df["GpuName"].map(lambda n: prices.get(n))
    df.to_csv(output_file, index=False)
    print(f"MSRP enrichment complete -> {output_file}")

# -----------------------------
# Field ordering
# -----------------------------
def ensure_fields_and_order(output_file: Path):
    df = pd.read_csv(output_file)
    for f in TARGET_FIELDS:
        if f not in df.columns:
            df[f] = ""
    cols = TARGET_FIELDS + [c for c in df.columns if c not in TARGET_FIELDS]
    df = df[cols]
    df.to_csv(output_file, index=False)

# -----------------------------
# Main enrichment pipeline
# -----------------------------
def gpu_enrich(input_file, output_file, debug=False, benchmark_only=False):
    src = Path(input_file)
    dst = Path(output_file)

    df = pd.read_csv(src)

    # ✅ Create slug column once
    df["slug"] = df["GpuName"].apply(build_slug)

    df.to_csv(dst, index=False)

    add_gpu_benchmarks(dst, debug=debug)

    if benchmark_only:
        ensure_fields_and_order(dst)
        print(f"Benchmark-only GPU file ready -> {dst}")
        return

    enrich_gpu_price(dst, debug=debug)
    ensure_fields_and_order(dst)
    print(f"GPU cleaned & enriched dataset saved to {dst}")

# -----------------------------
# CLI
# -----------------------------
def main():
    parser = argparse.ArgumentParser(
        description="GPU enrichment: attach benchmarks via Slug matching and enrich MSRP via Azure Models (two-pass)"
    )
    parser.add_argument("--file", required=True, help="Path to cleaned GPU CSV (e.g., data/gpu/gpu-clean.csv)")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--benchmark", action="store_true", help="Only run benchmark step (no MSRP AI)")
    args = parser.parse_args()

    input_path = Path(args.file)
    output_path = input_path.with_name(input_path.stem + "_enriched.csv")

    gpu_enrich(
        input_file=str(input_path),
        output_file=str(output_path),
        debug=args.debug,
        benchmark_only=args.benchmark
    )

if __name__ == "__main__":
    main()
