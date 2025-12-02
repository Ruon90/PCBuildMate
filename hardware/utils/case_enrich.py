import argparse
import pandas as pd
import re
import requests
import json
import time
import os
import env

# -----------------------------
# Case type normalization
# -----------------------------
def normalize_case_type(raw: str) -> str:
    if not isinstance(raw, str):
        return ""
    t = raw.strip().lower()

    if "mini" in t and "itx" in t:
        return "Mini-ITX"
    if "micro" in t and "atx" in t:
        return "MicroATX"
    if "mid" in t and "tower" in t:
        return "ATX Mid Tower"
    if "full" in t and "tower" in t:
        return "ATX Full Tower"
    if "tower" in t:
        return "ATX Tower"
    if "htpc" in t or "slim" in t:
        return "HTPC/Slim"
    if "cube" in t or "sff" in t or "small form" in t:
        return "SFF"
    return raw.strip().title()

# -----------------------------
# Slug helpers
# -----------------------------
def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")

def slugify_case(name: str, case_type: str) -> str:
    norm_type = normalize_case_type(case_type)
    return f"{slugify(name)}-{slugify(norm_type)}"

# -----------------------------
# Fallback convention mapping
# -----------------------------
def fallback_psu_form(case_type: str, volume: float) -> str:
    t = (case_type or "").lower()
    try:
        vol = float(str(volume).strip())
    except (ValueError, TypeError):
        vol = None

    if "mini" in t and "itx" in t:
        return "SFX-L" if vol and vol > 20 else "SFX"
    if "micro" in t and "atx" in t:
        return "ATX" if vol and vol > 30 else "SFX"
    if "tower" in t or "mid" in t or "full" in t or "atx" in t:
        return "ATX"
    if "htpc" in t or "slim" in t:
        return "TFX"
    if "cube" in t or "sff" in t or "small form" in t:
        return "SFX-L" if vol and vol < 25 else "ATX"
    return "ATX"

# -----------------------------
# AI batch enrichment
# -----------------------------
ENDPOINTS = {
    "gpt-4.1-mini": "https://models.inference.ai.azure.com/openai/deployments/gpt-4.1-mini/chat/completions",
    "gpt-4.1": "https://models.inference.ai.azure.com/openai/deployments/gpt-4.1/chat/completions"
}
TOKENS = {
    "gpt-4.1-mini": os.getenv("GITHUB_TOKEN_MINI") or os.getenv("GITHUB_TOKEN"),
    "gpt-4.1": os.getenv("GITHUB_TOKEN_FULL") or os.getenv("GITHUB_TOKEN")
}

def call_ai_batch(slugs_with_context, model="gpt-4.1-mini", debug=False):
    lines = []
    for item in slugs_with_context:
        line = f'{item["slug"]} | type={item.get("type","")}'
        if item.get("external_volume"):
            line += f' | vol={item["external_volume"]}'
        lines.append(line)

    prompt = f"""
You enrich PC case specs. For each line, infer the PSU form factor that fits the case.
Return ONLY valid JSON array. Each element:
- slug (string; match input)
- psu_form_factor (ATX, SFX, SFX-L, TFX, Flex, None if unknown)

Cases:
{chr(10).join(lines)}
""".strip()

    url = ENDPOINTS[model]
    token = TOKENS[model]
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0}

    try:
        r = requests.post(url, headers=headers, json=payload, timeout=(10, 90))
        if r.status_code != 200:
            if debug:
                print(f"[{model}] Non-200: {r.status_code} -> {r.text[:300]}")
            return {}
        content = r.json()["choices"][0]["message"]["content"].strip()
        cleaned = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", content, flags=re.MULTILINE).strip()
        data = json.loads(cleaned)
        return {d["slug"]: d.get("psu_form_factor") for d in data if isinstance(d, dict)}
    except Exception as e:
        if debug:
            print(f"[{model}] error: {e}")
        return {}

# -----------------------------
# Pipeline
# -----------------------------
def run_pipeline(case_file: str, output_file: str, debug=False):
    # force psu column to string dtype
    df = pd.read_csv(case_file, dtype={"psu": "string"})
    if "psu" not in df.columns:
        df["psu"] = ""
    df["psu"] = df["psu"].fillna("").astype(str)

    before = len(df)
    df = df.dropna(subset=["price"])
    df = df[df["price"].astype(str).str.strip() != ""]
    after_price_filter = len(df)

    # normalize case types and build slug
    df["type"] = df["type"].apply(normalize_case_type)
    df["slug"] = df.apply(lambda r: slugify_case(r["name"], r["type"]), axis=1)

    needs_psu = df[(df["psu"].str.strip() == "")]
    batch_size = 25
    ai_filled = 0
    fallback_filled = 0

    for i in range(0, len(needs_psu), batch_size):
        block = needs_psu.iloc[i:i+batch_size].copy()
        ctx = []
        for _, row in block.iterrows():
            ctx.append({
                "slug": row["slug"],
                "type": row.get("type", ""),
                "external_volume": str(row.get("external_volume", "")).strip()
            })

        res_mini = call_ai_batch(ctx, model="gpt-4.1-mini", debug=debug)
        unresolved = [c["slug"] for c in ctx if not res_mini.get(c["slug"])]
        if unresolved:
            ctx_unresolved = [c for c in ctx if c["slug"] in unresolved]
            res_full = call_ai_batch(ctx_unresolved, model="gpt-4.1", debug=debug)
            for k, v in res_full.items():
                res_mini[k] = v

        for slug, form in res_mini.items():
            if form and str(form).strip():
                df.loc[df["slug"] == slug, "psu"] = str(form).strip()
                ai_filled += 1

        time.sleep(1)

    still_missing = df[(df["psu"].str.strip() == "")]
    for _, row in still_missing.iterrows():
        fallback = fallback_psu_form(row.get("type", ""), row.get("external_volume", ""))
        df.loc[df["slug"] == row["slug"], "psu"] = fallback
        fallback_filled += 1

    df.to_csv(output_file, index=False)

    print("\n=== Case Enrichment Summary ===")
    print(f"Rows in input: {before}")
    print(f"Rows after price filter: {after_price_filter} (dropped {before - after_price_filter})")
    print(f"PSU form factor filled by AI: {ai_filled}")
    print(f"PSU form factor filled by fallback: {fallback_filled}")
    unresolved_after = len(df[(df["psu"].str.strip() == "")])
    print(f"Remaining unresolved PSU entries: {unresolved_after}")
    print(f"Enriched case CSV written to {output_file}")

    if debug:
        print("Sample enriched rows:\n", df.head(5))

# -----------------------------
# CLI
# -----------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Case pipeline: filter by price, infer PSU form factor via AI + volume-aware fallback, slug output"
    )
    parser.add_argument("--cases", required=True, help="Path to cases.csv")
    parser.add_argument("--output", required=False, help="Path to output CSV")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    output_file = args.output or args.cases.replace(".csv", "_enriched.csv")
    run_pipeline(args.cases, output_file, debug=args.debug)

if __name__ == "__main__":
    main()
