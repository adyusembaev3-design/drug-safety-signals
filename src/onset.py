"""Time to onset: days from starting a JAK inhibitor to the reported event."""
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from scipy.stats import weibull_min

from src.definitions import GROUPS, TARGETS

con = duckdb.connect("data/faers.duckdb")
targets_sql = ", ".join(f"'{t}'" for t in TARGETS)

con.execute(f"""
    CREATE OR REPLACE TABLE onset AS
    WITH ps AS (
        SELECT d.primaryid, d.drug_seq, p.ingredient
        FROM ps_u p
        JOIN raw_drug d ON d.primaryid = p.primaryid AND d.role_cod = 'PS'
        WHERE p.ingredient IN ({targets_sql})
          AND upper(coalesce(nullif(trim(d.prod_ai), ''), d.drugname))
              LIKE p.ingredient || '%'
    ),
    tstart AS (
        SELECT primaryid, dsg_drug_seq AS drug_seq, min(start_dt) AS start_dt
        FROM raw_ther
        WHERE length(start_dt) = 8
        GROUP BY 1, 2
    )
    SELECT primaryid, ingredient, onset_days
    FROM (
        SELECT ps.primaryid, ps.ingredient,
               date_diff('day', try_strptime(s.start_dt, '%Y%m%d'),
                                try_strptime(c.event_dt, '%Y%m%d')) AS onset_days
        FROM ps
        JOIN tstart s ON s.primaryid = ps.primaryid AND s.drug_seq = ps.drug_seq
        JOIN cases c ON c.primaryid = ps.primaryid
        WHERE length(c.event_dt) = 8
    )
    WHERE onset_days BETWEEN 0 AND 3650
""")

print("\nreports with a usable onset time:")
con.sql("SELECT ingredient, count(*) AS reports FROM onset GROUP BY 1 ORDER BY 2 DESC").show()

for i, cond in enumerate(GROUPS.values()):
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE ev{i} AS
        SELECT DISTINCT primaryid FROM case_reaction WHERE {cond}
    """)


def describe(x):
    x = np.asarray(x, dtype=float)
    if len(x) < 20:
        return None
    shape, _, scale = weibull_min.fit(np.maximum(x, 1), floc=0)
    q25, med, q75 = np.percentile(x, [25, 50, 75])
    return {
        "n": len(x), "median_days": round(med), "q25_days": round(q25),
        "q75_days": round(q75), "weibull_shape": round(shape, 2),
        "weibull_scale_days": round(scale),
    }


rows = []
for target in TARGETS:
    sets = {"All reports": f"SELECT onset_days FROM onset WHERE ingredient = '{target}'"}
    for i, name in enumerate(GROUPS):
        sets[name] = f"""
            SELECT o.onset_days FROM onset o JOIN ev{i} e USING (primaryid)
            WHERE o.ingredient = '{target}'
        """
    for name, sql in sets.items():
        res = describe([r[0] for r in con.execute(sql).fetchall()])
        if res:
            rows.append({"drug": target, "risk_group": name, **res})

out = pd.DataFrame(rows)
Path("data/processed").mkdir(parents=True, exist_ok=True)
out.to_csv("data/processed/onset.csv", index=False)
pd.set_option("display.width", 200)
print(out.to_string(index=False))
con.close()
