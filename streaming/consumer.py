import json, re, time
from collections import Counter as C
import duckdb
from confluent_kafka import Consumer, Producer
from prometheus_client import start_http_server, Counter, Gauge

DB = "../data/faers.duckdb"
TOP_N = 10   # how many emerging signals to chart
JAK = ["DEURUXOLITINIB", "RUXOLITINIB", "TOFACITINIB", "BARICITINIB", "UPADACITINIB",
       "ABROCITINIB", "FILGOTINIB", "FEDRATINIB", "RITLECITINIB", "MOMELOTINIB", "PACRITINIB"]
CANON = "CASE " + " ".join(f"WHEN UPPER(ingredient) LIKE '%{j}%' THEN '{j}'" for j in JAK) + " END"

# Non-clinical MedDRA terms: product, dosing, administration and use issues
EXCLUDE = re.compile(
    r"PRODUCT|OFF LABEL|UNAPPROVED|DRUG INEFFECTIVE|MEDICATION ERROR|WRONG |INCORRECT |"
    r"DOSE |DOSING|UNDERDOSE|OVERDOSE|STORAGE|PRESCRIBED|INTENTIONAL|DEVICE|"
    r"THERAPY CESSATION|THERAPY INTERRUPTED|TREATMENT NONCOMPLIANCE|"
    r"INAPPROPRIATE SCHEDULE|NO ADVERSE EVENT")

def canon(name):
    for j in JAK:
        if j in name:
            return j
    return None

# ---- metrics ----
reports_total = Counter("reports_processed_total", "Reports processed")
jak_reports   = Counter("jak_reports_total", "Reports involving a JAK inhibitor")
signals_total = Counter("signals_flagged_total", "New signals flagged during stream")
prr_gauge     = Gauge("prr", "PRR of top emerging signals", ["drug", "event"])
cases_gauge   = Gauge("case_count", "Cases of top emerging signals", ["drug", "event"])
start_http_server(8000)

# ---- baseline from historical quarters ----
con = duckdb.connect(DB, read_only=True)
last_q = con.execute("SELECT MAX(quarter) FROM cases").fetchone()[0]
print(f"Building baseline from quarters before {last_q} ...")
BASE = """WITH base AS (
  SELECT primaryid FROM cases WHERE quarter < ?
  INTERSECT SELECT primaryid FROM case_ps
  INTERSECT SELECT primaryid FROM case_reaction)"""
JAKCTE = BASE + f""", jak AS (
  SELECT DISTINCT primaryid, {CANON} AS drug FROM case_ps
  WHERE primaryid IN (SELECT primaryid FROM base) AND {CANON} IS NOT NULL)"""

N = con.execute(BASE + " SELECT COUNT(*) FROM base", [last_q]).fetchone()[0]
event_n = C(dict(con.execute(BASE + """ SELECT UPPER(pt), COUNT(DISTINCT primaryid)
  FROM case_reaction WHERE primaryid IN (SELECT primaryid FROM base) GROUP BY 1""",
  [last_q]).fetchall()))
drug_n = C(dict(con.execute(JAKCTE + " SELECT drug, COUNT(*) FROM jak GROUP BY 1",
  [last_q]).fetchall()))
pair_n = C({(d, e): n for d, e, n in con.execute(JAKCTE + """
  SELECT j.drug, UPPER(r.pt), COUNT(DISTINCT j.primaryid)
  FROM jak j JOIN case_reaction r USING (primaryid) GROUP BY 1, 2""",
  [last_q]).fetchall()})
con.close()

def stats(d, e):
    """Return (PRR, Yates chi-square) for a drug-event 2x2 table."""
    a, ab = pair_n[(d, e)], drug_n[d]
    b = ab - a
    c = event_n[e] - a
    cd = N - ab
    dd = cd - c
    if a == 0 or ab == 0 or c <= 0 or cd <= 0:
        return None
    prr = (a / ab) / (c / cd)
    denom = ab * cd * (a + c) * (b + dd)
    chi2 = N * max(0, abs(a * dd - b * c) - N / 2) ** 2 / denom if denom else 0
    return prr, chi2

def is_signal(d, e):
    if EXCLUDE.search(e):
        return False
    s = stats(d, e)
    return s is not None and s[0] >= 2 and s[1] >= 4 and pair_n[(d, e)] >= 3

flagged = {k for k in pair_n if is_signal(*k)}
new_signals = set()
print(f"Baseline: {N:,} reports, {sum(drug_n.values()):,} JAK reports, "
      f"{len(flagged):,} existing signals (Evans criteria). Ready - start the producer.")

def update_gauges():
    prr_gauge.clear()
    cases_gauge.clear()
    ranked = sorted(new_signals, key=lambda k: -(stats(*k) or (0, 0))[1])[:TOP_N]
    for d, e in ranked:
        s = stats(d, e)
        if s:
            prr_gauge.labels(d, e).set(s[0])
            cases_gauge.labels(d, e).set(pair_n[(d, e)])

# ---- stream ----
c = Consumer({"bootstrap.servers": "localhost:9092",
              "group.id": f"signal-detector-{int(time.time())}",
              "auto.offset.reset": "earliest"})
c.subscribe(["faers-reports"])
out = Producer({"bootstrap.servers": "localhost:9092"})

while True:
    msg = c.poll(1.0)
    if msg is None or msg.error():
        continue
    rep = json.loads(msg.value())
    events = set(rep["events"])
    jaks = {j for j in (canon(x) for x in rep["drugs"]) if j}

    N += 1
    reports_total.inc()
    for e in events:
        event_n[e] += 1
    for d in jaks:
        drug_n[d] += 1
    if jaks:
        jak_reports.inc()

    for d in jaks:
        for e in events:
            pair_n[(d, e)] += 1
            if (d, e) not in flagged and is_signal(d, e):
                flagged.add((d, e))
                new_signals.add((d, e))
                signals_total.inc()
                prr, chi2 = stats(d, e)
                alert = {"drug": d, "event": e, "prr": round(prr, 2), "chi2": round(chi2, 1),
                         "cases": pair_n[(d, e)], "fda_dt": rep["fda_dt"]}
                print("NEW SIGNAL:", alert)
                out.produce("faers-signals", json.dumps(alert).encode())
                out.poll(0)

    if N % 200 == 0:
        update_gauges()
