#!/usr/bin/env python3
from __future__ import annotations
import json, urllib.parse, urllib.request
from common import median, quantile

BASE = "https://creativecommons.tankerkoenig.de/json/list.php"

def fetch_live(cfg):
    reg = cfg["region"]
    c = reg["center"]
    params = {
        "lat": f'{c["lat"]:.5f}',
        "lng": f'{c["lng"]:.5f}',
        "rad": str(reg.get("radius_km", 25)),
        "sort": "price",
        "type": cfg.get("fuel", "diesel"),
        "apikey": cfg["tankerkoenig_api_key"],
    }
    url = BASE + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "FuelForecast/1.0 personal-research"})
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.load(r)
    if not data.get("ok"):
        raise RuntimeError("Tankerkönig API error: " + str(data.get("message", "unknown")))
    stations = []
    for s in data.get("stations", []):
        p = s.get("price")
        if p is None:
            continue
        stations.append({
            "id": s.get("id"),
            "name": s.get("name"),
            "brand": s.get("brand"),
            "street": s.get("street"),
            "houseNumber": s.get("houseNumber"),
            "postCode": s.get("postCode"),
            "place": s.get("place"),
            "lat": s.get("lat"),
            "lng": s.get("lng"),
            "dist": s.get("dist"),
            "price": float(p),
            "isOpen": bool(s.get("isOpen")),
        })
    return stations

def station_metrics(stations, preferred_places=None):
    open_stations = [s for s in stations if s.get("isOpen") and s.get("price") is not None]
    prices = [s["price"] for s in open_stations]
    sorted_s = sorted(open_stations, key=lambda x: x["price"])
    top5 = sorted_s[:5]
    metrics = {
        "count": len(open_stations),
        "best": min(prices) if prices else None,
        "cheap_reference": median([s["price"] for s in top5]) if top5 else None,
        "q25": quantile(prices, 0.25),
        "median": median(prices),
        "top5": top5,
        "places": {}
    }
    for place in preferred_places or []:
        needle = place.casefold()
        subset = [s for s in open_stations if needle in (s.get("place") or "").casefold()
                  or needle in (s.get("name") or "").casefold()]
        metrics["places"][place] = {
            "count": len(subset),
            "best": min((s["price"] for s in subset), default=None),
            "cheap_reference": median([s["price"] for s in sorted(subset, key=lambda x:x["price"])[:3]]) if subset else None,
            "stations": sorted(subset, key=lambda x:x["price"])[:5],
        }
    return metrics
