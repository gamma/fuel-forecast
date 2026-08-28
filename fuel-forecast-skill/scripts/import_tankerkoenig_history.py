#!/usr/bin/env python3
"""
Optional bootstrap from an authorized Tankerkönig historical repository clone.
The current Tankerkönig historical repository requires separate verified access.
This script does NOT use the realtime API to mass-download history.
"""
from __future__ import annotations
import csv, argparse
from pathlib import Path
from datetime import date, timedelta, datetime, time
from common import data_dir, load_json, append_jsonl, haversine_km, median, quantile

def daterange(a,b):
    d=a
    while d<=b:
        yield d
        d += timedelta(days=1)

def latest_station_file(repo: Path, end: date):
    candidates = list((repo/"stations").glob("**/*-stations.csv"))
    if not candidates:
        raise SystemExit("No stations CSV found under repo/stations")
    return sorted(candidates)[-1]

def station_ids(repo, cfg, end):
    f = latest_station_file(repo,end)
    c=cfg["region"]["center"]; rad=float(cfg["region"].get("radius_km",25))
    out={}
    with f.open(newline="",encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            try:
                lat=float(r.get("latitude")); lon=float(r.get("longitude"))
            except Exception:
                continue
            if haversine_km(c["lat"],c["lng"],lat,lon)<=rad:
                uid=r.get("uuid")
                out[uid]=r
    return out

def metrics(prices, stations, preferred):
    vals=[p for p in prices.values() if p and p>0]
    top=sorted(vals)[:5]
    m={"count":len(vals),"best":min(vals) if vals else None,
       "cheap_reference":median(top),"q25":quantile(vals,.25),"median":median(vals),
       "places":{}}
    for place in preferred:
        ids=[u for u,s in stations.items() if place.casefold() in (s.get("city") or "").casefold()
             or place.casefold() in (s.get("name") or "").casefold()]
        vv=[prices.get(u) for u in ids if prices.get(u)]
        m["places"][place]={"count":len(vv),"best":min(vv) if vv else None,
                            "cheap_reference":median(sorted(vv)[:3]) if vv else None}
    return m

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--repo",required=True)
    ap.add_argument("--since",default="2026-04-01")
    ap.add_argument("--until",default=date.today().isoformat())
    ap.add_argument("--warmup-days",type=int,default=21)
    args=ap.parse_args()
    repo=Path(args.repo); d=data_dir(); cfg=load_json(d/"config.json")
    start=date.fromisoformat(args.since); end=date.fromisoformat(args.until)
    stations=station_ids(repo,cfg,end)
    current={}
    emitted=set(r.get("date") for r in __import__("common").read_jsonl(d/"observations.jsonl"))
    scan_start=start-timedelta(days=args.warmup_days)
    target=time(11,50)
    for day in daterange(scan_start,end):
        f=repo/"prices"/f"{day.year:04d}"/f"{day.month:02d}"/f"{day.isoformat()}-prices.csv"
        if not f.exists():
            continue
        events=[]
        with f.open(newline="",encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                uid=r.get("station_uuid")
                if uid not in stations:
                    continue
                try:
                    dt=datetime.fromisoformat(r["date"].replace("Z","+00:00"))
                    diesel=float(r["diesel"])
                except Exception:
                    continue
                events.append((dt,uid,diesel))
        events.sort()
        # Apply changes up to target time first, capture target, then apply remaining
        for dt,uid,p in events:
            local_t=dt.timetz().replace(tzinfo=None)
            if local_t<=target:
                current[uid]=p
        if day>=start and day.isoformat() not in emitted:
            m=metrics(current,stations,cfg["region"].get("preferred_places",[]))
            if m["cheap_reference"] is not None:
                append_jsonl(d/"observations.jsonl",{
                    "version":1,"date":day.isoformat(),"captured_at":f"{day.isoformat()}T11:50:00",
                    "source":"Tankerkönig historical CSV","fuel":"diesel","metrics":m
                })
        for dt,uid,p in events:
            local_t=dt.timetz().replace(tzinfo=None)
            if local_t>target:
                current[uid]=p
    print("Historical import finished.")

if __name__=="__main__":
    main()
