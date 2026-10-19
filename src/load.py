"""Load raw FAERS quarterly files into DuckDB. Adds only quarters not yet loaded."""
from pathlib import Path

import duckdb

RAW = Path("data/raw")
DB = Path("data/faers.duckdb")
TABLES = {
    "demo": "raw_demo",
    "drug": "raw_drug",
    "reac": "raw_reac",
    "outc": "raw_outc",
    "ther": "raw_ther",
}


def main():
    con = duckdb.connect(str(DB))
    existing = {
        r[0] for r in con.execute("SELECT table_name FROM information_schema.tables").fetchall()
    }
    for prefix, table in TABLES.items():
        files = sorted(RAW.glob(f"*/{prefix}*.txt"))
        exists = table in existing
        have = set()
        if exists:
            have = {r[0] for r in con.execute(f"SELECT DISTINCT quarter FROM {table}").fetchall()}
        new = [f for f in files if f.parent.name not in have]
        if not new:
            print(f"{table}: nothing new to load")
            continue
        con.execute(
            f"""
            CREATE OR REPLACE TEMP TABLE _new AS
            SELECT *, regexp_extract(filename, '/(\\d{{4}}q\\d)/', 1) AS quarter
            FROM read_csv(
                {[str(f) for f in new]!r},
                delim='$', header=true, quote='', escape='',
                all_varchar=true, union_by_name=true, filename=true,
                ignore_errors=true, null_padding=true
            )
            """
        )
        if exists:
            keep = [r[0] for r in con.execute(f"DESCRIBE {table}").fetchall()]
            new_cols = {r[0] for r in con.execute("DESCRIBE _new").fetchall()}
            cols = ", ".join(c for c in keep if c in new_cols)
            con.execute(f"INSERT INTO {table} ({cols}) SELECT {cols} FROM _new")
        else:
            con.execute(f"CREATE TABLE {table} AS SELECT * FROM _new")
        n, q = con.execute(f"SELECT count(*), count(DISTINCT quarter) FROM {table}").fetchone()
        print(f"{table}: added {len(new)} files, now {n:,} rows across {q} quarters")
    con.close()


if __name__ == "__main__":
    main()
