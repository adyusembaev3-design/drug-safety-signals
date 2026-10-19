"""Export the small result files the dashboard needs into app_data/."""
import shutil
from pathlib import Path

import duckdb

from src.definitions import GROUPS

OUT = Path("app_data")
OUT.mkdir(exist_ok=True)

con = duckdb.connect("data/faers.duckdb")

con.execute("""
    COPY (
        SELECT ingredient, pt, a AS cases, n_drug, n_event,
               round(expected, 2) AS expected,
               round(prr, 2) AS prr, round(prr_lo, 2) AS prr_lo,
               round(ror, 2) AS ror, round(ror_lo, 2) AS ror_lo,
               round(ic, 2) AS ic, round(ic025, 2) AS ic025,
               flag_evans, flag_strict
        FROM signals
        WHERE n_drug >= 100
    ) TO 'app_data/signals.parquet' (FORMAT PARQUET, COMPRESSION ZSTD)
""")

parts = []
for i, (name, cond) in enumerate(GROUPS.items()):
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE ev{i} AS
        SELECT DISTINCT primaryid FROM case_reaction WHERE {cond}
    """)
    safe = name.replace("'", "''")
    parts.append(f"""
        SELECT o.ingredient AS drug, '{safe}' AS risk_group, o.onset_days
        FROM onset o JOIN ev{i} e USING (primaryid)
    """)
con.execute(
    "COPY (" + " UNION ALL ".join(parts) + ") "
    "TO 'app_data/onset_events.parquet' (FORMAT PARQUET, COMPRESSION ZSTD)"
)
con.close()

for name in ["validation.csv", "backtest_timeline.csv", "backtest_summary.csv", "onset.csv"]:
    shutil.copy(Path("data/processed") / name, OUT / name)

for f in sorted(OUT.iterdir()):
    print(f"{f.name}: {f.stat().st_size / 1e6:.1f} MB")
