"""Export cleaned tables to Parquet and upload pipeline outputs to Azure Blob Storage."""
import os
from pathlib import Path

import duckdb
from azure.storage.blob import BlobServiceClient


def load_env(path=".env"):
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key, value)


load_env()
service = BlobServiceClient.from_connection_string(os.environ["AZURE_STORAGE_CONNECTION_STRING"])
container = service.get_container_client("processed")

clean = Path("data/processed/clean")
clean.mkdir(parents=True, exist_ok=True)
con = duckdb.connect("data/faers.duckdb", read_only=True)
for table in ["cases", "case_ps", "case_reaction", "signals"]:
    out = clean / f"{table}.parquet"
    con.execute(f"COPY {table} TO '{out}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    print(f"exported {table}")
con.close()

uploads = [(f, f"clean/{f.name}") for f in sorted(clean.glob("*.parquet"))]
uploads += [(f, f"results/{f.name}") for f in sorted(Path("app_data").iterdir())]

for local, blob in uploads:
    with open(local, "rb") as fh:
        container.upload_blob(name=blob, data=fh, overwrite=True, max_concurrency=4)
    print(f"uploaded {blob} ({local.stat().st_size / 1e6:.1f} MB)")

print("\nBlobs now in the 'processed' container:")
for b in container.list_blobs():
    print(f"  {b.name}  {b.size / 1e6:.1f} MB")
