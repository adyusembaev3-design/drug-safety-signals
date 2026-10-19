"""Validate: do JAK inhibitors show their labelled risks, vs similar drugs?"""
from pathlib import Path

import duckdb
import pandas as pd

from src.definitions import GROUPS, REF, TARGETS, ror

con = duckdb.connect("data/faers.duckdb")

for i, cond in enumerate(GROUPS.values()):
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE ev{i} AS
        SELECT DISTINCT primaryid FROM case_reaction WHERE {cond}
    """)

rows = []
for target in TARGETS:
    for background in ["comparators", "all other drugs"]:
        where = (
            f"p.ingredient = '{target}' OR regexp_matches(p.ingredient, '^({REF})')"
            if background == "comparators"
            else "TRUE"
        )
        for i, name in enumerate(GROUPS):
            a, b, c, d = con.execute(f"""
                WITH cohort AS (
                    SELECT p.primaryid,
                           CASE WHEN p.ingredient = '{target}' THEN 1 ELSE 0 END AS is_t
                    FROM ps_u p WHERE {where}
                )
                SELECT
                    coalesce(sum(is_t * (e.primaryid IS NOT NULL)::INT), 0),
                    coalesce(sum(is_t * (e.primaryid IS NULL)::INT), 0),
                    coalesce(sum((1 - is_t) * (e.primaryid IS NOT NULL)::INT), 0),
                    coalesce(sum((1 - is_t) * (e.primaryid IS NULL)::INT), 0)
                FROM cohort c LEFT JOIN ev{i} e ON e.primaryid = c.primaryid
            """).fetchone()
            est, lo, hi = ror(a, b, c, d)
            rows.append({
                "drug": target, "risk_group": name, "background": background,
                "cases": int(a), "drug_cases": int(a + b),
                "ror": round(est, 2), "ci_low": round(lo, 2), "ci_high": round(hi, 2),
                "signal": "YES" if lo > 1 else "no",
            })

out = pd.DataFrame(rows)
Path("data/processed").mkdir(parents=True, exist_ok=True)
out.to_csv("data/processed/validation.csv", index=False)
pd.set_option("display.width", 200)
print(out.to_string(index=False))
con.close()
