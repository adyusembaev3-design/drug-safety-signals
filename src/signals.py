"""Disproportionality statistics (PRR, ROR, IC) for every drug-event pair."""
from pathlib import Path

import duckdb

con = duckdb.connect("data/faers.duckdb")

con.execute("""
    CREATE OR REPLACE TABLE ps_u AS
    SELECT primaryid, ingredient FROM case_ps
    WHERE primaryid IN (SELECT DISTINCT primaryid FROM case_reaction)
""")

con.execute("""
    CREATE OR REPLACE TABLE signals AS
    WITH tot AS (
        SELECT count(DISTINCT primaryid)::DOUBLE AS n FROM ps_u
    ),
    dn AS (
        SELECT ingredient, count(DISTINCT primaryid)::DOUBLE AS n_d
        FROM ps_u GROUP BY 1
    ),
    en AS (
        SELECT pt, count(*)::DOUBLE AS n_e
        FROM case_reaction
        WHERE primaryid IN (SELECT primaryid FROM ps_u)
        GROUP BY 1
    ),
    pr AS (
        SELECT p.ingredient, r.pt, count(*)::DOUBLE AS a
        FROM ps_u p JOIN case_reaction r USING (primaryid)
        GROUP BY 1, 2
        HAVING count(*) >= 3
    ),
    cells AS (
        SELECT pr.ingredient, pr.pt, pr.a,
               GREATEST(dn.n_d - pr.a, 0) AS b,
               GREATEST(en.n_e - pr.a, 0) AS c,
               GREATEST(tot.n - dn.n_d - en.n_e + pr.a, 0) AS d,
               dn.n_d, en.n_e, tot.n
        FROM pr
        JOIN dn USING (ingredient)
        JOIN en USING (pt)
        CROSS JOIN tot
    ),
    m AS (
        SELECT *,
            ((a + 0.5) / (a + b + 1)) / ((c + 0.5) / (c + d + 1)) AS prr,
            sqrt(1 / (a + 0.5) - 1 / (a + b + 1) + 1 / (c + 0.5) - 1 / (c + d + 1)) AS se_prr,
            ((a + 0.5) * (d + 0.5)) / ((b + 0.5) * (c + 0.5)) AS ror,
            sqrt(1 / (a + 0.5) + 1 / (b + 0.5) + 1 / (c + 0.5) + 1 / (d + 0.5)) AS se_ror,
            n * power(a * d - b * c, 2) / ((a + b) * (c + d) * (a + c) * (b + d)) AS chi2,
            n_d * n_e / n AS expected
        FROM cells
    )
    SELECT ingredient, pt, a::INTEGER AS a, b::INTEGER AS b, c::INTEGER AS c,
           d::INTEGER AS d, n_d::INTEGER AS n_drug, n_e::INTEGER AS n_event,
           expected, prr, exp(ln(prr) - 1.96 * se_prr) AS prr_lo,
           ror, exp(ln(ror) - 1.96 * se_ror) AS ror_lo, chi2,
           log2((a + 0.5) / (expected + 0.5)) AS ic,
           log2((a + 0.5) / (expected + 0.5))
               - 3.3 * power(a + 0.5, -0.5) - 2 * power(a + 0.5, -1.5) AS ic025,
           (a >= 3 AND prr >= 2 AND chi2 >= 4) AS flag_evans
    FROM m
""")

con.execute("ALTER TABLE signals ADD COLUMN flag_strict BOOLEAN")
con.execute("UPDATE signals SET flag_strict = flag_evans AND ror_lo > 1 AND ic025 > 0")

Path("data/processed").mkdir(parents=True, exist_ok=True)
con.execute("COPY signals TO 'data/processed/signals.parquet' (FORMAT PARQUET)")

print("\n== overall ==")
con.sql("""
    SELECT count(*) AS pairs, sum(flag_evans::INT) AS evans_flagged,
           sum(flag_strict::INT) AS strict_flagged
    FROM signals
""").show()

for drug in ["RUXOLITINIB", "TOFACITINIB", "UPADACITINIB", "BARICITINIB"]:
    print(f"\n== {drug}: strongest strict signals (by IC lower bound) ==")
    con.sql(f"""
        SELECT pt, a AS cases, round(prr, 1) AS prr, round(ror_lo, 1) AS ror_lo,
               round(ic025, 2) AS ic025
        FROM signals
        WHERE ingredient = '{drug}' AND flag_strict AND a >= 20
        ORDER BY ic025 DESC LIMIT 12
    """).show(max_rows=15)

con.close()
