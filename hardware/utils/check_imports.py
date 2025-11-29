#!/usr/bin/env python3
# scripts/check_imports.py
import ast
import os
import sys
import importlib.util
try:
    # Python 3.10+
    from importlib.metadata import packages_distributions
except Exception:
    packages_distributions = None

ROOT = os.path.abspath(".")

def find_py_files(root):
    for dirpath, dirs, files in os.walk(root):
        # skip common large folders
        if "/.venv" in dirpath or "/env" in dirpath or "/.git" in dirpath:
            continue
        for f in files:
            if f.endswith(".py"):
                yield os.path.join(dirpath, f)

def extract_top_level_modules(path):
    with open(path, "r", encoding="utf-8") as fh:
        try:
            tree = ast.parse(fh.read(), filename=path)
        except Exception:
            return set()
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for n in node.names:
                mods.add(n.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                mods.add(node.module.split(".")[0])
    return mods

def is_importable(name):
    try:
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False

def map_to_distributions(names):
    if not packages_distributions:
        return {}
    try:
        mapping = packages_distributions()
    except Exception:
        return {}
    out = {}
    for n in names:
        dists = mapping.get(n)
        if dists:
            out[n] = dists
    return out

def main():
    print("Scanning .py files for imports (this may take a few seconds)...")
    pyfiles = list(find_py_files(ROOT))
    allmods = set()
    for p in pyfiles:
        allmods.update(extract_top_level_modules(p))
    # Filter local package imports (modules that exist in repo)
    allmods = sorted(m for m in allmods if not m.startswith("_"))
    missing = []
    for mod in allmods:
        if mod in ("os","sys","re","json","time","argparse","typing","pathlib",
                   "itertools","collections","csv","inspect","logging","subprocess"):
            # skip obvious stdlib modules; extend list as needed
            continue
        if not is_importable(mod):
            missing.append(mod)
    print(f"Found {len(allmods)} top-level modules; {len(missing)} not importable in this env.")
    if missing:
        print("\nMissing modules:")
        for m in missing:
            print(f" - {m}")
        if packages_distributions:
            mapping = map_to_distributions(missing)
            print("\nSuggested distributions (from importlib.metadata):")
            for m in missing:
                if m in mapping:
                    print(f" - {m} -> {', '.join(mapping[m])}")
    else:
        print("No missing imports detected. Good job!")

if __name__ == '__main__':
    main()