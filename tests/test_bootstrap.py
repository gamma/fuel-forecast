import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]/"fuel-forecast-skill"/"scripts"))
from download_tankzeit_history import uuid_path, parse_history
from run_forecast import local_trends

assert uuid_path("b4ed695f-2cfc-4688-8ecf-268b10cdb93e") == "b4ed695f/2cfc/4688/8ecf/268b10cdb93e"
rows=parse_history("date,price,last_update\n2026-04-01,2.019,2026-04-01T12:01:00\n")
assert rows[0]["price"] == 2.019

boot={}
for i,p in enumerate([2.00,2.02,2.01,1.99]):
    d=f"2026-04-0{i+1}"
    boot[d]={"metrics":{"cheap_reference":p}}
one,three=local_trends({}, "2026-04-05", boot)
assert round(one,6) == -2.0
print("OK")
