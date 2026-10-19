"""Quarter-by-quarter replay: when would each signal first have been flagged?"""
from pathlib import Path

import duckdb
import pandas as pd

from src.definitions import GROUPS, REF, TARGETS, ror

con = duckdb.connect("data/faers.duckdb")

# A case is "known" from the first quarter in which any version of it appeared.
con.execute("""
    CREATE OR REPLACE TABLE case_q AS
    SELECT c.primaryid, f.first_q AS q
    FROM cases c
    JOIN (SELECT caseid, min(quarter) AS first_q FROM raw_demo GROUP BY caseid) f
      USING (caseid)
""")

for i, cond in enumerate(GROUPS.values()):
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE ev{i} AS
        SELECT DISTINCT primaryid FROM case_reaction WHERE {cond}
    """)

quarters = [r[0] for r in con.execute("SELECT DISTINCT q FROM case_q ORDER BY q").fetchall()]

timeline = []
for target in TARGETS:
    for i, name in enumerate(GROUPS):
        df = con.execute(f"""
            WITH cohort AS (
                SELECT p.primaryid, q.q,
                       CASE WHEN p.ingredient = '{target}' THEN 1 ELSE 0 END AS is_t
                FROM ps_u p JOIN case_q q USING (primaryid)
                WHERE p.ingredient = '{target}'
                   OR regexp_matches(p.ingredient, '^({REF})')
            )
            SELECT c.q,
                   coalesce(sum(is_t * (e.primaryid IS NOT NULL)::INT), 0) AS a,
                   coalesce(sum(is_t * (e.primaryid IS NULL)::INT), 0) AS b,
                   coalesce(sum((1 - is_t) * (e.primaryid IS NOT NULL)::INT), 0) AS c,
                   coalesce(sum((1 - is_t) * (e.primaryid IS NULL)::INT), 0) AS d
            FROM cohort c LEFT JOIN ev{i} e ON e.primaryid = c.primaryid
            GROUP BY c.q ORDER BY c.q
        """).df()
        cum = df.set_index("q").reindex(quarters, fill_value=0).astype(float).cumsum()
        for q, row in cum.iterrows():
            est, lo, hi = ror(row["a"], row["b"], row["c"], row["d"])
            timeline.append({
                "drug": target, "risk_group": name, "quarter": q,
                "cases": int(row["a"]), "ror": est, "ci_low": lo, "ci_high": hi,
                "flag": bool(row["a"] >= 3 and lo > 1),
            })

tl = pd.DataFrame(timeline)
Path("data/processed").mkdir(parents=True, exist_ok=True)
tl.to_csv("data/processed/backtest_timeline.csv", index=False)

summary = []
for (drug, risk), g in tl.groupby(["drug", "risk_group"], sort=False):
    qs, fl = g["quarter"].tolist(), g["flag"].tolist()
    first = next((q for q, f in zip(qs, fl) if f), None)
    sustained = next((qs[k] for k in range(len(qs)) if all(fl[k:])), None)
    last = g.iloc[-1]
    summary.append({
        "drug": drug, "risk_group": risk, "first_flagged": first,
        "sustained_from": sustained, "final_cases": int(last["cases"]),
        "final_ror": round(last["ror"], 2),
    })

sm = pd.DataFrame(summary)
sm.to_csv("data/processed/backtest_summary.csv", index=False)
pd.set_option("display.width", 200)
print(sm.to_string(index=False))
con.close()
