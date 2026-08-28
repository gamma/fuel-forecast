#!/usr/bin/env python3
from __future__ import annotations
import json, math, os
from pathlib import Path
from datetime import datetime, date, timedelta

DEFAULT_MOUNT_DIR = Path("/var/minis/mounts/FuelForecast")
DEFAULT_DATA_DIR = DEFAULT_MOUNT_DIR / "memory"
FALLBACK_DATA_DIR = Path("/var/minis/memory/fuel-forecast")

def data_dir() -> Path:
    env = os.environ.get("FUEL_FORECAST_DATA_DIR")
    if env:
        p = Path(env)
    elif DEFAULT_DATA_DIR.exists():
        p = DEFAULT_DATA_DIR
    else:
        p = FALLBACK_DATA_DIR
    p.mkdir(parents=True, exist_ok=True)
    return p

def load_json(path: Path, default=None):
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")
    tmp.replace(path)

def append_jsonl(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n")

def write_jsonl(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    tmp.replace(path)

def replace_jsonl_row(path: Path, obj, key="date"):
    value = obj.get(key)
    rows = [row for row in read_jsonl(path) if row.get(key) != value]
    rows.append(obj)
    rows.sort(key=lambda row: str(row.get(key, "")))
    write_jsonl(path, rows)

def read_jsonl(path: Path):
    if not path.exists():
        return []
    out = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out

def iso_today():
    return date.today().isoformat()

def parse_date(s):
    return date.fromisoformat(s)

def add_days(s, n):
    return (parse_date(s) + timedelta(days=n)).isoformat()

def pct_change(new, old):
    if new is None or old in (None, 0):
        return None
    return (new / old - 1.0) * 100.0

def median(vals):
    vals = sorted(v for v in vals if v is not None)
    if not vals:
        return None
    n = len(vals)
    m = n // 2
    return vals[m] if n % 2 else (vals[m-1] + vals[m]) / 2.0

def quantile(vals, q):
    vals = sorted(v for v in vals if v is not None)
    if not vals:
        return None
    if len(vals) == 1:
        return vals[0]
    pos = (len(vals)-1) * q
    lo, hi = int(math.floor(pos)), int(math.ceil(pos))
    if lo == hi:
        return vals[lo]
    w = pos - lo
    return vals[lo] * (1-w) + vals[hi] * w

def clamp(x, lo, hi):
    return max(lo, min(hi, x))

def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2-lat1)
    dl = math.radians(lon2-lon1)
    a = math.sin(dphi/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*r*math.asin(math.sqrt(a))
