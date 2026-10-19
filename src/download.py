"""Download FAERS quarterly ASCII files and keep only the tables we use.

Usage:
    python -m src.download 2024q4    one quarter (use this to test)
    python -m src.download           all quarters from 2019 onward
"""
import sys
import zipfile
from pathlib import Path

import requests

URL = "https://fis.fda.gov/content/Exports/faers_ascii_{y}q{q}.zip"
RAW = Path("data/raw")
KEEP = ("DEMO", "DRUG", "REAC", "OUTC", "THER")


def fetch(y: int, q: int) -> bool:
    out = RAW / f"{y}q{q}"
    if out.exists():
        print(f"{y}q{q}: already have it")
        return True
    zpath = RAW / f"{y}q{q}.zip"
    r = requests.get(URL.format(y=y, q=q), stream=True, timeout=180)
    if r.status_code != 200:
        print(f"{y}q{q}: not available (HTTP {r.status_code}), skipping")
        return False
    with open(zpath, "wb") as f:
        for chunk in r.iter_content(1 << 20):
            f.write(chunk)
    if not zipfile.is_zipfile(zpath):
        print(f"{y}q{q}: response was not a zip file, skipping")
        zpath.unlink()
        return False
    out.mkdir()
    with zipfile.ZipFile(zpath) as z:
        for name in z.namelist():
            base = Path(name).name
            if base.upper().startswith(KEEP) and base.lower().endswith(".txt"):
                (out / base.lower()).write_bytes(z.read(name))
    zpath.unlink()
    print(f"{y}q{q}: done ({len(list(out.glob('*.txt')))} files)")
    return True


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    if len(sys.argv) > 1:
        y, q = sys.argv[1].lower().split("q")
        fetch(int(y), int(q))
        return
    for y in range(2020, 2027):
        for q in range(1, 5):
            fetch(y, q)


if __name__ == "__main__":
    main()