import argparse
import json
import os
import re
import time
from pathlib import Path

import pandas as pd
import requests


# Tokens and endpoints
GITHUB_TOKEN_MINI = os.getenv("GITHUB_TOKEN_MINI") or os.getenv("GITHUB_TOKEN")
GITHUB_TOKEN_FULL = os.getenv("GITHUB_TOKEN_FULL") or os.getenv("GITHUB_TOKEN")

AI_BASE = "https://models.inference.ai.azure.com/openai/deployments/"

ENDPOINTS = {
    "gpt-4.1-mini": AI_BASE + "gpt-4.1-mini/chat/completions",
    "gpt-4.1": AI_BASE + "gpt-4.1/chat/completions",
}


def select_token(model: str) -> str:
    return GITHUB_TOKEN_MINI if model == "gpt-4.1-mini" else GITHUB_TOKEN_FULL


TARGET_FIELDS = [
    "name",
    "price",
    "rpm",
    "noise_level",
    "color",
    "size",
    "liquid",
    "power_throughput",
]


# -----------------------------
# AI enrichment
# -----------------------------
def call_ai_batch(items, debug=False, model="gpt-4.1-mini"):
    prompt = f"""
You are enriching CPU cooler hardware data. Return ONLY valid JSON array.
Rules:
- Each element must have: model_name (string, match input exactly),
  liquid (true/false),
  power_throughput (number in watts or null).
- If unknown, set value to null.
- Do not add extra fields or text.
List:
{chr(10).join(items)}
"""
    token = select_token(model)
    endpoint = ENDPOINTS[model]

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
    }

    for attempt in range(3):
        try:
            resp = requests.post(
                endpoint, headers=headers, json=payload, timeout=(10, 90)
            )
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
            return []

        content = data["choices"][0]["message"]["content"].strip()
        cleaned = re.sub(
            r"^```[a-zA-Z]*\s*|\s*```$", "", content, flags=re.MULTILINE
        ).strip()

        try:
            parsed = json.loads(cleaned)
            return parsed if isinstance(parsed, list) else []
        except Exception:
            if debug:
                print(f"[AI] Parse error ({model}); preview: {content[:300]}")
            return []
    return []


# -----------------------------
# Fallback throughput rules
# -----------------------------
def fallback_throughput(size: str, liquid: bool) -> int:
    try:
        s = int(re.findall(r"\d+", str(size))[0])
    except Exception:
        return None

    if liquid:
        if s <= 120:
            return 180
        elif s <= 240:
            return 250
        elif s <= 360:
            return 300
        else:
            return 350
    else:
        if s <= 92:
            return 95
        elif s <= 120:
            return 150
        elif s <= 140:
            return 180
        else:
            return 200


# -----------------------------
# Enrichment pipeline
# -----------------------------
def enrich_coolers(input_file, output_file, debug=False, batch_size=25):
    df = pd.read_csv(input_file)
    names = df.get("name", pd.Series(dtype=str)).astype(str).tolist()

    enriched_data = {}

    # Pass 1: gpt-4.1-mini
    for i in range(0, len(names), batch_size):
        batch = names[i:i+batch_size]
        results = call_ai_batch(batch, debug=debug, model="gpt-4.1-mini")
        for r in results or []:
            enriched_data[r["model_name"]] = r

    # Pass 2: gpt-4.1 for missing
    missing = [n for n in names if n not in enriched_data]
    if debug:
        print("[DEBUG] Missing after pass 1:", len(missing), "coolers")

    for i in range(0, len(missing), batch_size):
        batch = missing[i:i+batch_size]
        results = call_ai_batch(batch, debug=debug, model="gpt-4.1")
        for r in results or []:
            enriched_data[r["model_name"]] = r

    # Merge back into dataframe
    df["liquid"] = df["name"].map(
        lambda n: enriched_data.get(n, {}).get("liquid")
    )
    df["power_throughput"] = df.apply(
        lambda row: enriched_data.get(row["name"], {}).get("power_throughput")
        or fallback_throughput(row["size"], row["liquid"]),
        axis=1,
    )

    # Ensure field order
    for f in TARGET_FIELDS:
        if f not in df.columns:
            df[f] = ""
    df = df[TARGET_FIELDS + [c for c in df.columns if c not in TARGET_FIELDS]]

    df.to_csv(output_file, index=False)
    print(f"Cooler enrichment complete -> {output_file}")

    # Coverage summary
    total = len(df)
    liquid_count = df["liquid"].sum() if "liquid" in df.columns else 0
    air_count = total - liquid_count
    avg_throughput = df["power_throughput"].dropna().astype(float).mean()

    print("\n=== Cooler Coverage Summary ===")
    print(f"Total coolers: {total}")
    # Shorter, split output for line-length
    print("Liquid:", liquid_count, f"({(liquid_count/total*100 if total else 0):.1f}%)")
    print(f"Air: {air_count} ({(air_count/total*100 if total else 0):.1f}%)")
    print(f"Average throughput: {avg_throughput:.1f} W")

    if debug:
        print("\n[DEBUG] Sample rows after enrichment:")
        print(df.head(10))


# -----------------------------
# CLI
# -----------------------------
def main():
    parser = argparse.ArgumentParser(
        description="CPU cooler enrichment: classify and add throughput"
    )
    parser.add_argument("--file", required=True, help="Path to cooler CSV")
    parser.add_argument(
        "--debug", action="store_true", help="Enable debug logging"
    )
    args = parser.parse_args()

    input_path = Path(args.file)
    output_path = input_path.with_name(input_path.stem + "_enriched.csv")

    enrich_coolers(str(input_path), str(output_path), debug=args.debug)


if __name__ == "__main__":
    main()
