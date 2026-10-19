"""Re-encode raw FAERS text files as clean UTF-8 (invalid bytes replaced)."""
from pathlib import Path

RAW = Path("data/raw")
fixed = 0
for f in sorted(RAW.glob("*/*.txt")):
    b = f.read_bytes()
    try:
        b.decode("utf-8")
        continue
    except UnicodeDecodeError:
        pass
    f.write_bytes(b.decode("utf-8", errors="replace").encode("utf-8"))
    fixed += 1
    print("fixed", f)
print(f"done, {fixed} files re-encoded")
