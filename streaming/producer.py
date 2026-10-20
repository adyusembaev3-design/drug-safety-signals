import json, sys, time
import duckdb
from confluent_kafka import Producer

DB = "../data/faers.duckdb"
RATE = float(sys.argv[1]) if len(sys.argv) > 1 else 200   # reports per second

con = duckdb.connect(DB, read_only=True)
last_q = con.execute("SELECT MAX(quarter) FROM cases").fetchone()[0]
print(f"Loading reports from quarter {last_q} ...")

rows = con.execute("""
  WITH c AS (SELECT primaryid, fda_dt FROM cases WHERE quarter = ?),
  d AS (SELECT primaryid, LIST(DISTINCT UPPER(ingredient)) AS drugs
        FROM case_ps WHERE primaryid IN (SELECT primaryid FROM c) GROUP BY 1),
  r AS (SELECT primaryid, LIST(DISTINCT UPPER(pt)) AS events
        FROM case_reaction WHERE primaryid IN (SELECT primaryid FROM c) GROUP BY 1)
  SELECT c.primaryid, c.fda_dt, d.drugs, r.events
  FROM c JOIN d USING (primaryid) JOIN r USING (primaryid)
  ORDER BY c.fda_dt
""", [last_q]).fetchall()
con.close()
print(f"Streaming {len(rows):,} reports at {RATE:.0f}/sec (Ctrl+C to stop)")

p = Producer({"bootstrap.servers": "localhost:9092"})
try:
    for i, (pid, fda_dt, drugs, events) in enumerate(rows, 1):
        msg = {"primaryid": str(pid), "fda_dt": str(fda_dt),
               "drugs": [x for x in drugs if x], "events": [x for x in events if x]}
        p.produce("faers-reports", json.dumps(msg).encode())
        p.poll(0)
        if i % 10000 == 0:
            print(f"  sent {i:,} reports (fda_dt {fda_dt})")
        time.sleep(1 / RATE)
except KeyboardInterrupt:
    print("Stopped.")
p.flush()
