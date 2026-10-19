"""Clean FAERS: latest case version, primary-suspect drugs, normalized ingredients."""
import duckdb

con = duckdb.connect("data/faers.duckdb")

SALTS = (
    "HYDROCHLORIDE|HCL|PHOSPHATE|SULFATE|SODIUM|POTASSIUM|CALCIUM|CITRATE|MALEATE|"
    "TARTRATE|MESYLATE|SUCCINATE|ACETATE|HYDROBROMIDE|BESYLATE|FUMARATE|DIHYDRATE|"
    "MONOHYDRATE|ANHYDROUS"
)

STEPS = {
    "cases": r"""
        CREATE OR REPLACE TABLE cases AS
        SELECT primaryid, caseid, caseversion, quarter, sex, age, age_cod,
               occr_country, event_dt, fda_dt
        FROM (
            SELECT primaryid, caseid,
                   TRY_CAST(caseversion AS INTEGER) AS caseversion,
                   quarter, sex, age, age_cod, occr_country, event_dt, fda_dt,
                   row_number() OVER (
                       PARTITION BY caseid
                       ORDER BY TRY_CAST(caseversion AS INTEGER) DESC NULLS LAST,
                                quarter DESC, primaryid DESC
                   ) AS rn
            FROM raw_demo
            WHERE caseid IS NOT NULL
        )
        WHERE rn = 1
    """,
    "case_ps": rf"""
        CREATE OR REPLACE TABLE case_ps AS
        SELECT DISTINCT primaryid, ingredient
        FROM (
            SELECT d.primaryid,
                   trim(regexp_replace(regexp_replace(
                       coalesce(nullif(trim(upper(d.prod_ai)), ''),
                                trim(upper(d.drugname))),
                       '\s+({SALTS})\b', '', 'g'), '\s+', ' ', 'g')) AS ingredient
            FROM raw_drug d
            JOIN cases c ON c.primaryid = d.primaryid
            WHERE d.role_cod = 'PS'
        )
        WHERE ingredient <> ''
    """,
    "case_reaction": r"""
        CREATE OR REPLACE TABLE case_reaction AS
        SELECT DISTINCT r.primaryid, upper(trim(r.pt)) AS pt
        FROM raw_reac r
        JOIN cases c ON c.primaryid = r.primaryid
        WHERE r.pt IS NOT NULL AND trim(r.pt) <> ''
    """,
}

REPORTS = {
    "table sizes": """
        SELECT (SELECT count(*) FROM cases) AS cases,
               (SELECT count(DISTINCT primaryid) FROM case_ps) AS cases_with_ps_drug,
               (SELECT count(*) FROM case_reaction) AS case_reaction_rows,
               (SELECT count(DISTINCT ingredient) FROM case_ps) AS distinct_ingredients
    """,
    "drug role codes (raw)": """
        SELECT role_cod, count(*) AS n FROM raw_drug GROUP BY 1 ORDER BY n DESC
    """,
    "top 15 primary-suspect ingredients": """
        SELECT ingredient, count(*) AS cases FROM case_ps
        GROUP BY 1 ORDER BY cases DESC LIMIT 15
    """,
    "JAK inhibitor name variants": """
        SELECT ingredient, count(*) AS cases FROM case_ps
        WHERE ingredient LIKE '%RUXOLITINIB%' OR ingredient LIKE '%TOFACITINIB%'
           OR ingredient LIKE '%BARICITINIB%' OR ingredient LIKE '%UPADACITINIB%'
        GROUP BY 1 ORDER BY cases DESC LIMIT 20
    """,
}

for name, sql in STEPS.items():
    print(f"building {name} ...", flush=True)
    con.execute(sql)

for title, sql in REPORTS.items():
    print(f"\n== {title} ==")
    con.sql(sql).show(max_rows=30)

con.close()
