#!/usr/bin/env python3
"""One low-frequency 'should I refuel now?' check near the current device."""
from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import data_dir, load_json
from tankerkoenig import fetch_live


def current_location():
    raw = subprocess.check_output(
        ["apple-location", "current", "--accuracy", "near", "--compact", "-q"],
        text=True, timeout=25,
    )
    data = json.loads(raw)
    # CLI versions may use latitude/longitude or lat/lng.
    lat = data.get("latitude", data.get("lat"))
    lng = data.get("longitude", data.get("lng"))
    if lat is None or lng is None:
        raise RuntimeError("Gerätestandort enthält keine Koordinaten.")
    return float(lat), float(lng)


def haversine_km(a, b, c, d):
    from math import asin, cos, radians, sin, sqrt
    r = 6371.0
    dp, dl = radians(c-a), radians(d-b)
    x = sin(dp/2)**2 + cos(radians(a))*cos(radians(c))*sin(dl/2)**2
    return r * 2 * asin(sqrt(x))


def main():
    directory = data_dir()
    cfg = load_json(directory / "config.json")
    if not cfg:
        raise SystemExit("Konfiguration fehlt. Zuerst configure.py ausführen.")
    radius = float(cfg.get("widget", {}).get("radius_km", 5))
    lat, lng = current_location()
    # One list request; widen API radius only enough to filter device-local stations.
    query_cfg = json.loads(json.dumps(cfg))
    query_cfg["region"]["center"] = {"lat": lat, "lng": lng}
    query_cfg["region"]["radius_km"] = radius
    stations = [s for s in fetch_live(query_cfg)
                if s.get("isOpen") and s.get("price") is not None
                and haversine_km(lat, lng, float(s["lat"]), float(s["lng"])) <= radius]
    stations.sort(key=lambda s: s["price"])
    if not stations:
        raise SystemExit(f"Keine offene {cfg.get('fuel','diesel').upper()}-Tankstelle innerhalb von {radius:g} km gefunden.")
    best = stations[0]
    forecast = load_json(directory / "forecast.json", {}) or {}
    today = (forecast.get("forecast") or [{}])[0]
    expected = today.get("price")
    threshold = 2.0
    drop = (best["price"] - expected) * 100 if expected is not None else None
    from datetime import datetime
    hour = datetime.now().astimezone().hour
    # The learned same-day target is pre-noon. Never compare it to a post-reset
    # afternoon live price; it would manufacture a meaningless 20+ ct signal.
    if hour >= 12:
        advice = "JETZT TANKEN (WENN NÖTIG)"
        reason = "Nach 12 Uhr ist die 11:50-Prognose kein zulässiger Vergleich mehr; gezeigt wird deshalb nur der günstigste aktuelle Livepreis."
    elif drop is not None and drop >= threshold:
        advice = "WARTEN BIS 11:50"
        reason = f"Der Modellwert für heute liegt etwa {drop:.1f} ct/l unter dem günstigsten Livepreis."
    else:
        advice = "JETZT TANKEN"
        reason = "Kein ausreichend großer erwarteter Preisrückgang von mindestens 2 ct/l."
    print(f"{advice} — {cfg.get('fuel','diesel').upper()} innerhalb {radius:g} km")
    print(f"Günstigste offene Station: {best.get('brand') or best.get('name')} · {best.get('place')} · {best['price']:.3f} €/l · {best.get('dist','?')} km")
    if expected is not None:
        print(f"Modellwert 11:50 (regionale Referenz): {expected:.3f} €/l; Differenz {drop:+.1f} ct/l.")
    print(reason)
    print("Hinweis: Nur sinnvoll, wenn du heute tanken musst oder die Station ohne Extra-Umweg erreichst. Quelle: Tankerkönig/MTS-K.")

if __name__ == "__main__":
    main()
