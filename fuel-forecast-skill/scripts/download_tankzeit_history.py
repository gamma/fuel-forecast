#!/usr/bin/env python3
"""
Bootstrap historical daily noon references from tankzeit.de derived MTS-K/Tankerkönig data.

Important:
- tankzeit's noon reference is NOT identical to our 11:50 target. A qualifying
  positive change between 12:00 and 12:15 can still become the noon reference.
- Therefore this script writes bootstrap_noon.jsonl, NOT observations.jsonl.
- The forecast model uses these rows primarily for day-to-day movement and
  regime/seasonality bootstrap. Scriptable 11:50 captures remain ground truth.

Sources attempted per station, in order:
1) GitHub raw tankzeit.de repository
2) Hugging Face dataset used/documented by tankzeit.de

No mass historical Tankerkönig realtime API polling is performed. The realtime
API is used once only to discover the currently relevant stations/UUIDs.
"""
from __future__ import annotations
import csv, io, json, urllib.parse, urllib.request, urllib.error
from datetime import datetime
from pathlib import Path
from common import data_dir, load_json, save_json, append_jsonl, read_jsonl, median, quantile
from tankerkoenig import fetch_live

UA = {"User-Agent": "FuelForecast/1.1 personal-research"}

GITHUB_BASES = [
    "https://raw.githubusercontent.com/volzinnovation/tankzeit.de/master",
    "https://raw.githubusercontent.com/volzinnovation/tankzeit.de/main",
]
HF_BASES = [
    "https://huggingface.co/datasets/loffenauer/fuel-prices-germany/resolve/main",
]

def uuid_path(uid: str) -> str:
    # tankzeit/HF splits standard UUID by dashes into nested path parts.
    return "/".join(uid.split("-"))

def candidate_urls(uid: str, fuel: str):
    nested = uuid_path(uid)
    flat = uid
    rels = [
        f"data2/{nested}/{fuel}/history.csv",
        f"data2/{flat}/{fuel}/history.csv",
    ]
    for base in GITHUB_BASES:
        for rel in rels:
            yield "github", f"{base}/{rel}"
    for base in HF_BASES:
        for rel in rels:
            yield "huggingface", f"{base}/{rel}?download=true"

def fetch_text(url: str, timeout=25) -> str:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8-sig", errors="replace")

def parse_history(text: str):
    rows = []
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return rows
    for r in reader:
        dt = (r.get("date") or "").strip()
        raw = (r.get("price") or "").strip().replace(",", ".")
        if not dt or not raw:
            continue
        try:
            p = float(raw)
        except ValueError:
            continue
        # Defensive normalization if a source ever stores integer milli-euros/cents.
        if p > 20:
            if p > 1000:
                p = p / 1000.0
            elif p > 100:
                p = p / 100.0
        if not (0.5 <= p <= 5.0):
            continue
        rows.append({
            "date": dt[:10],
            "price": p,
            "last_update": (r.get("last_update") or "").strip() or None,
        })
    rows.sort(key=lambda x: x["date"])
    return rows

def download_station(uid: str, fuel: str):
    errors = []
    for source, url in candidate_urls(uid, fuel):
        try:
            text = fetch_text(url)
            rows = parse_history(text)
            if rows:
                return rows, source, url, errors
            errors.append(f"{source}: empty/invalid")
        except urllib.error.HTTPError as e:
            errors.append(f"{source}: HTTP {e.code}")
        except Exception as e:
            errors.append(f"{source}: {type(e).__name__}: {e}")
    return [], None, None, errors

def day_metrics(day_prices, station_meta, preferred_places):
    entries = []
    for uid, p in day_prices.items():
        if p is None:
            continue
        s = station_meta.get(uid, {})
        entries.append({
            "id": uid,
            "name": s.get("name"),
            "brand": s.get("brand"),
            "place": s.get("place"),
            "postCode": s.get("postCode"),
            "price": p,
            "dist": s.get("dist"),
        })
    entries.sort(key=lambda x:x["price"])
    vals = [x["price"] for x in entries]
    out = {
        "count": len(vals),
        "best": min(vals) if vals else None,
        "cheap_reference": median(vals[:5]) if vals else None,
        "q25": quantile(vals, .25),
        "median": median(vals),
        "top5": entries[:5],
        "places": {},
    }
    for place in preferred_places:
        n = place.casefold()
        subset = [x for x in entries if n in (x.get("place") or "").casefold()
                  or n in (x.get("name") or "").casefold()]
        vv = [x["price"] for x in subset]
        out["places"][place] = {
            "count": len(vv),
            "best": min(vv) if vv else None,
            "cheap_reference": median(vv[:3]) if vv else None,
            "stations": subset[:5],
        }
    return out

def main():
    d = data_dir()
    cfg = load_json(d/"config.json")
    if not cfg:
        raise SystemExit(f"Missing {d/'config.json'}")
    if "PASTE_" in cfg.get("tankerkoenig_api_key",""):
        raise SystemExit("Set tankerkoenig_api_key in config.json first.")

    print("Discovering current OHV stations via one Tankerkönig list.php request...")
    live = fetch_live(cfg)
    if not live:
        raise SystemExit("No current stations discovered.")

    station_meta = {s["id"]: s for s in live if s.get("id")}
    fuel = cfg.get("fuel","diesel")
    cache_dir = d/"bootstrap_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    station_hist = {}
    manifest = {
        "generated_at": datetime.now().astimezone().isoformat(),
        "fuel": fuel,
        "stations_discovered": len(station_meta),
        "stations_downloaded": 0,
        "stations_failed": 0,
        "sources": {},
        "failures": [],
    }

    for i, (uid, meta) in enumerate(station_meta.items(), 1):
        cache = cache_dir/f"{uid}-{fuel}.json"
        rows = None
        source = None
        url = None
        if cache.exists():
            try:
                c = load_json(cache, {})
                rows = c.get("rows") or []
                source = c.get("source")
                url = c.get("url")
            except Exception:
                rows = None
        if not rows:
            rows, source, url, errors = download_station(uid, fuel)
            if rows:
                save_json(cache, {"source":source, "url":url, "rows":rows})
            else:
                manifest["stations_failed"] += 1
                manifest["failures"].append({
                    "id": uid, "name": meta.get("name"), "place": meta.get("place"),
                    "errors": errors[-6:],
                })
                print(f"[{i}/{len(station_meta)}] MISS {meta.get('place','')} {meta.get('name','')}")
                continue
        station_hist[uid] = rows
        manifest["stations_downloaded"] += 1
        manifest["sources"][source or "cache"] = manifest["sources"].get(source or "cache",0)+1
        print(f"[{i}/{len(station_meta)}] OK   {meta.get('place','')} {meta.get('name','')} ({len(rows)} days)")

    # Aggregate by date across all successfully downloaded stations.
    by_date = {}
    for uid, rows in station_hist.items():
        for r in rows:
            by_date.setdefault(r["date"], {})[uid] = r["price"]

    out_rows = []
    preferred = cfg["region"].get("preferred_places", [])
    for day in sorted(by_date):
        m = day_metrics(by_date[day], station_meta, preferred)
        if m["cheap_reference"] is None:
            continue
        out_rows.append({
            "version": 1,
            "date": day,
            "reference": "tankzeit noon",
            "source": "tankzeit.de derived MTS-K/Tankerkönig history",
            "target_semantics": "noon reference; qualifying increase 12:00-12:15 may be included",
            "fuel": fuel,
            "metrics": m,
        })

    # Rewrite deterministically; this file is derived/cacheable.
    target = d/"bootstrap_noon.jsonl"
    target.write_text(
        "".join(json.dumps(r, ensure_ascii=False, separators=(",",":"))+"\n" for r in out_rows),
        encoding="utf-8"
    )

    manifest["dates"] = len(out_rows)
    manifest["first_date"] = out_rows[0]["date"] if out_rows else None
    manifest["last_date"] = out_rows[-1]["date"] if out_rows else None
    manifest["output"] = str(target)
    save_json(d/"bootstrap_manifest.json", manifest)

    print("\nBootstrap finished.")
    print(f"Stations: {manifest['stations_downloaded']}/{manifest['stations_discovered']}")
    print(f"Dates:    {manifest['dates']} ({manifest['first_date']} .. {manifest['last_date']})")
    print(f"Output:   {target}")
    if manifest["stations_failed"]:
        print(f"Failed stations: {manifest['stations_failed']} — see bootstrap_manifest.json")

if __name__ == "__main__":
    main()
