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

    # common mappings
    if "mini" in t and "itx" in t:
        return "Mini-ITX"
    if "micro" in t and "atx" in t:
        return "MicroATX"
    if "mid" in t and "tower" in t:
        return "ATX Mid Tower"
    if "full" in t and "tower" in t:
        return "ATX Full Tower"
    if "tower" in t:  # generic tower
        return "ATX Tower"
    if "htpc" in t or "slim" in t:
        return "HTPC/Slim"
    if "cube" in t or "sff" in t or "small form" in t:
        return "SFF"
    # fallback
    return raw.strip()

# -----------------------------
# Slug helpers (updated)
# -----------------------------
def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")


def slugify_case(name: str, case_type: str) -> str:
    norm_type = normalize_case_type(case_type)
    return f"{slugify(name)}-{slugify(norm_type)}"




# -----------------------------
# Fallback convention mapping with volume thresholds
# -----------------------------
def fallback_psu_form(case_type: str, volume: float) -> str:
    """
    Convention-based inference when AI doesn't return a PSU form factor.
    Uses case type + external volume thresholds.
    """
    t = (case_type or "").lower()

    # Attempt to parse volume into float; None if not numeric
    try:
        vol = float(str(volume).strip())
    except (ValueError, TypeError):
        vol = None

    # Mini ITX: mostly SFX; larger minis can fit SFX-L
    if "mini" in t and "itx" in t:
        if vol is not None and vol > 20:
            return "SFX-L"
        return "SFX"

    # Micro ATX: many support ATX; very compact micro cases may use SFX
    if "micro" in t and "atx" in t:
        if vol is not None and vol > 30:
            return "ATX"
        return "SFX"

    # ATX Mid/Full Tower: overwhelmingly ATX PSUs
    if "tower" in t or "mid" in t or "full" in t or "atx" in t:
        return "ATX"

    # Slim/HTPC: typically TFX (or Flex in very small)
    if "htpc" in t or "slim" in t:
        return "TFX"

    # Cube / SFF: smaller tends to SFX/SFX-L; larger cubes can fit ATX
    if "cube" in t or "small form" in t or "sff" in t:
        if vol is not None and vol < 25:
            return "SFX-L"
        return "ATX"

    # Default fallback
    return "ATX"

# -----------------------------
# AI batch enrichment for PSU form factor
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
    """
    slugs_with_context: list of dicts like:
      { "slug": "...", "type": "ATX Mid Tower", "external_volume": "45" }
    Price is intentionally excluded to reduce tokens.
    """
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

Heuristics:
- ATX Mid/Full Tower -> ATX
- Micro ATX -> ATX (or SFX if very small)
- Mini ITX -> SFX (SFX-L if larger volume)
- HTPC/Slim -> TFX
- Small Form Factor/Cube -> SFX-L if compact, ATX if larger
- Use external volume as a guide: <25L = SFX/SFX-L, >40L = ATX
- If uncertain, choose the most common fit for the type.

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
    df = pd.read_csv(case_file)

    # ensure psu column exists and is string dtype
    if "psu" not in df.columns:
        df["psu"] = ""
    df["psu"] = df["psu"].astype(str)

    # Filter out rows without price
    before = len(df)
    df = df.dropna(subset=["price"])
    df = df[df["price"].astype(str).str.strip() != ""]
    after_price_filter = len(df)

    # Normalize case types before slugging
    df["type"] = df["type"].apply(normalize_case_type)
    df["slug"] = df.apply(lambda r: slugify_case(r["name"], r["type"]), axis=1)

    # Build slug
    df["slug"] = df.apply(lambda r: slugify_case(r["name"], r["type"]), axis=1)

    # Determine which rows need PSU form factor
    needs_psu = df[(df["psu"].isna()) | (df["psu"].astype(str).str.strip() == "")]
    batch_size = 25
    ai_filled = 0
    fallback_filled = 0

    # Batch AI enrichment
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
                df.loc[df["slug"] == slug, "psu"] = form
                ai_filled += 1

        time.sleep(1)

    # Apply fallback for any still missing
    still_missing = df[(df["psu"].isna()) | (df["psu"].astype(str).str.strip() == "")]
    for _, row in still_missing.iterrows():
        fallback = fallback_psu_form(row.get("type", ""), row.get("external_volume", ""))
        df.loc[df["slug"] == row["slug"], "psu"] = fallback
        fallback_filled += 1

    # Final output
    df.to_csv(output_file, index=False)

    # Summary
    print("\n=== Case Enrichment Summary ===")
    print(f"Rows in input: {before}")
    print(f"Rows after price filter: {after_price_filter} (dropped {before - after_price_filter})")
    print(f"PSU form factor filled by AI: {ai_filled}")
    print(f"PSU form factor filled by fallback: {fallback_filled}")
    unresolved_after = len(df[(df["psu"].isna()) | (df["psu"].astype(str).str.strip() == "")])
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
