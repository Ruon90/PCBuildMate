import pandas as pd
from pathlib import Path
import io
import re

EXPECTED_HEADERS = {
    "name", "price", "core_count", "core_clock", "boost_clock",
    "microarchitecture", "tdp", "graphics"
}

def sniff_sep(sample: str) -> str:
    counts = {",": sample.count(","), ";": sample.count(";"), "\t": sample.count("\t")}
    return max(counts, key=counts.get) or ","

def extract_brand_and_model(name: str):
    if name is None or pd.isna(name):
        return ("Unknown", None)
    s = str(name).strip()
    s_lower = s.lower()
    brand = "AMD" if s_lower.startswith("amd") else ("Intel" if s_lower.startswith("intel") else "Other")
    # Model: last alphanumeric token with digits
    m = re.findall(r"[A-Za-z0-9\-+]+", s)
    model = next((t for t in reversed(m) if re.search(r"\d", t)), s)
    return (brand, model)

# --- New: CPU slug builder ---
def build_cpu_slug(name: str) -> str:
    if not isinstance(name, str):
        return ""
    s = name.upper()
    s = re.sub(r"\b(INTEL|AMD|RYZEN|CORE|PROCESSOR|CPU)\b", "", s)
    s = re.sub(r"\s+", " ", s).strip()

    # AMD Ryzen: family + model
    m_amd = re.search(r"\b([3579])\b.*?\b(\d{4}(?:X3D|XT|X)?)\b", s)
    if m_amd:
        family, model = m_amd.groups()
        return f"{family}-{model.lower()}"

    # Intel: i3/i5/i7/i9 + number + suffix
    m_intel = re.search(r"\b(I[3579])[-\s]*(\d{4,5})([A-Z]{0,3})?\b", s)
    if m_intel:
        series, num, suf = m_intel.groups()
        slug = f"{series.lower()}-{num.lower()}"
        if suf:
            slug += f"-{suf.lower()}"
        return slug

    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")

def clean_cpu(file_path: Path, output_path: Path, filter_arch: bool = True, enrich_threads: bool = True):
    if not file_path.exists():
        raise FileNotFoundError(f"cpu.csv not found at {file_path}")

    raw = file_path.read_bytes()
    if len(raw) == 0:
        raise ValueError("cpu.csv is empty")

    # Decode with BOM handling
    text = raw.decode("utf-8-sig", errors="replace")
    # Determine delimiter
    sep = sniff_sep(text[:1000])

    # Read safely
    df = pd.read_csv(io.StringIO(text), sep=sep, engine="python", on_bad_lines="skip")
    if df.empty or set(df.columns) & EXPECTED_HEADERS == set():
        raise ValueError(f"cpu.csv does not contain expected headers. Found: {list(df.columns)}")

    # Normalize headers
    df.columns = df.columns.str.strip().str.lower()

    # Ensure required columns exist
    missing = list(EXPECTED_HEADERS - set(df.columns))
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    # brand + model
    df[["brand","model"]] = df["name"].apply(lambda x: pd.Series(extract_brand_and_model(x)))

    # --- New: slug column from model (or name if model missing) ---
    # Prefer precise slugs derived from the model token we extracted above
    df["slug"] = df["model"].fillna(df["name"]).astype(str).map(build_cpu_slug)

    # Filter by microarchitecture
    if filter_arch:
        def keep_row(row):
            arch = str(row["microarchitecture"]).lower()
            if row["brand"] == "AMD":
                return any(a in arch for a in ["zen 3","zen3","zen 4","zen4","zen 5","zen5"])
            if row["brand"] == "Intel":
                return any(a in arch for a in ["raptor lake", "arrow lake"])
            return False
        df = df[df.apply(keep_row, axis=1)]

    # Enrich: ThreadCount = core_count * 2 (heuristic)
    if enrich_threads:
        def parse_int(x):
            try:
                return int(str(x).strip())
            except Exception:
                return None
        df["thread_count"] = df["core_count"].apply(parse_int).apply(lambda c: c*2 if c is not None else None)

    # Enrich: ReleaseDate placeholder (to be populated later)
    df["release_date"] = pd.NaT

    # Reorder: brand, model, slug first
    cols = ["brand", "model", "slug"] + [c for c in df.columns if c not in ["brand", "model", "slug"]]
    df = df[cols]

    # Drop fully empty rows/columns
    df = df.dropna(how="all").dropna(axis=1, how="all")

    # Save
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    print(f"CPU cleaned dataset saved to {output_path} | rows={len(df)} | sep='{sep}'")

def main():
    data_dir = Path(__file__).resolve().parent.parent.parent / "data/cpu"
    cpu_file = data_dir / "cpu.csv"
    output_file = data_dir / "cpu-clean.csv"
    clean_cpu(cpu_file, output_file)

if __name__ == "__main__":
    main()
