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

ENDPOINTS = {
    "gpt-4.1-mini": "https://models.inference.ai.azure.com/openai/deployments/gpt-4.1-mini/chat/completions",
    "gpt-4.1": "https://models.inference.ai.azure.com/openai/deployments/gpt-4.1/chat/completions",
}


def select_token(model: str) -> str:
    return GITHUB_TOKEN_MINI if model == "gpt-4.1-mini" else GITHUB_TOKEN_FULL


TARGET_FIELDS = [
    "name",
    "price",
    "socket",
    "form_factor",
    "max_memory",
    "memory_slots",
    "color",
    "ddr_version",
    "ddr_max_speed",
    "nvme_support",
    "bios_update_required",
]


# -----------------------------
# Normalisation (slug builder)
# -----------------------------
def build_slug(name: str) -> str:
    if not isinstance(name, str):
        return ""
    s = name.upper()
    s = re.sub(r"\b(ASUS|MSI|GIGABYTE|ASROCK|INTEL|AMD)\b", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    tokens = re.findall(r"[A-Z0-9\-]+", s)
    return "-".join(tok.lower() for tok in tokens)


# -----------------------------
# AI enrichment
# -----------------------------
def call_ai_batch(category, items, debug=False, model="gpt-4.1-mini"):
    prompt = f"""
You are enriching {category} hardware data. Return ONLY valid JSON array.
Rules:
- Each element must have: model_name (string, match input exactly),
  ddr_version (string or null),
  ddr_max_speed (number in MHz or null),
  nvme_support (string or null, e.g. "PCIe Gen4"),
  bios_update_required (true/false or null).
- If unknown, set value to null.
- Do not add extra fields or text.
- Output must be a valid JSON array.

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
# Two-pass enrichment
# -----------------------------
def enrich_boards(input_file, output_file, debug=False, batch_size=25):
    df = pd.read_csv(input_file)
    names = df.get("name", pd.Series(dtype=str)).astype(str).tolist()

    enriched_data = {}

    # Pass 1: gpt-4.1-mini
    for i in range(0, len(names), batch_size):
        batch = names[i : i + batch_size]
        results = call_ai_batch(
            "motherboard", batch, debug=debug, model="gpt-4.1-mini"
        )
        for r in results or []:
            enriched_data[r["model_name"]] = r

    # Pass 2: gpt-4.1 for missing
    missing = [n for n in names if n not in enriched_data]
    if debug:
        print(f"[DEBUG] Missing after pass 1: {len(missing)} boards")

    for i in range(0, len(missing), batch_size):
        batch = missing[i : i + batch_size]
        results = call_ai_batch(
            "motherboard", batch, debug=debug, model="gpt-4.1"
        )
        for r in results or []:
            enriched_data[r["model_name"]] = r

    # Merge back into dataframe
    df["ddr_version"] = df["name"].map(
        lambda n: enriched_data.get(n, {}).get("ddr_version")
    )
    df["ddr_max_speed"] = df["name"].map(
        lambda n: enriched_data.get(n, {}).get("ddr_max_speed")
    )
    df["nvme_support"] = df["name"].map(
        lambda n: enriched_data.get(n, {}).get("nvme_support")
    )
    df["bios_update_required"] = df["name"].map(
        lambda n: enriched_data.get(n, {}).get("bios_update_required")
    )

    # Ensure field order
    for f in TARGET_FIELDS:
        if f not in df.columns:
            df[f] = ""
    df = df[TARGET_FIELDS + [c for c in df.columns if c not in TARGET_FIELDS]]

    df.to_csv(output_file, index=False)
    print(f"Motherboard enrichment complete -> {output_file}")


# -----------------------------
# CLI
# -----------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Motherboard enrichment: add DDR/NVMe/BIOS fields via AI"
    )
    parser.add_argument(
        "--file", required=True, help="Path to motherboard CSV"
    )
    parser.add_argument(
        "--debug", action="store_true", help="Enable debug logging"
    )
    args = parser.parse_args()

    input_path = Path(args.file)
    output_path = input_path.with_name(input_path.stem + "_enriched.csv")

    enrich_boards(str(input_path), str(output_path), debug=args.debug)


if __name__ == "__main__":
    main()
