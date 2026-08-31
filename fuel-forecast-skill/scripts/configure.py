#!/usr/bin/env python3
"""Create one local FuelForecast configuration without committing credentials."""
from __future__ import annotations
import argparse
import getpass
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parents[1] / "references" / "config.example.json"


def geocode(query: str):
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode({
        "q": query, "format": "jsonv2", "limit": 5, "countrycodes": "de"
    })
    req = urllib.request.Request(url, headers={"User-Agent": "FuelForecast setup/1.0 (personal use)"})
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.load(response)


def ask(label, default=None, required=True):
    suffix = f" [{default}]" if default else ""
    while True:
        value = input(f"{label}{suffix}: ").strip() or default
        if value or not required:
            return value
        print("Bitte einen Wert eingeben.")


def main():
    parser = argparse.ArgumentParser(description="Create local FuelForecast memory/config.json")
    parser.add_argument("--data-dir", type=Path, default=None,
                        help="Default: mounted FuelForecast/memory, else Minis local memory")
    parser.add_argument("--place", help="German town/address to search with OpenStreetMap")
    parser.add_argument("--lat", type=float)
    parser.add_argument("--lng", type=float)
    parser.add_argument("--name", help="Display name for the forecast region")
    parser.add_argument("--radius-km", type=float, default=25)
    parser.add_argument("--api-key", help="Tankerkönig key. Prefer interactive entry so it is not kept in shell history.")
    args = parser.parse_args()
    if (args.lat is None) != (args.lng is None):
        parser.error("--lat und --lng müssen zusammen angegeben werden")

    data_dir = args.data_dir or Path("/var/minis/mounts/FuelForecast/memory")
    if not data_dir.parent.exists() and args.data_dir is None:
        data_dir = Path("/var/minis/memory/fuel-forecast")
    cfg = json.loads(TEMPLATE.read_text(encoding="utf-8"))

    if args.lat is not None:
        lat, lng = args.lat, args.lng
        name = args.name or ask("Name der Region", "Meine Region")
    else:
        query = args.place or ask("Ort oder Adresse in Deutschland", required=True)
        results = geocode(query)
        if not results:
            raise SystemExit("Kein Ort gefunden. Erneut mit genauerer Adresse suchen oder --lat/--lng nutzen.")
        print("Treffer:")
        for i, result in enumerate(results, 1):
            print(f"  {i}. {result['display_name']} ({float(result['lat']):.5f}, {float(result['lon']):.5f})")
        choice = int(ask("Nummer", "1"))
        if not 1 <= choice <= len(results):
            raise SystemExit("Ungültige Auswahl")
        selected = results[choice - 1]
        lat, lng = float(selected["lat"]), float(selected["lon"])
        name = args.name or ask("Name der Region", query)

    key = args.api_key or getpass.getpass("Tankerkönig API-Key (wird nur lokal gespeichert): ").strip()
    if not key or key.startswith("PASTE_"):
        raise SystemExit("Kein gültiger Tankerkönig API-Key eingegeben.")
    cfg["region"]["name"] = name
    cfg["region"]["center"] = {"lat": round(lat, 5), "lng": round(lng, 5)}
    cfg["region"]["radius_km"] = args.radius_km
    cfg["region"]["preferred_places"] = [name]
    cfg["tankerkoenig_api_key"] = key
    data_dir.mkdir(parents=True, exist_ok=True)
    target = data_dir / "config.json"
    target.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Konfiguration geschrieben: {target}")
    print(f"Region: {name} · {lat:.5f}, {lng:.5f} · Radius {args.radius_km:g} km")


if __name__ == "__main__":
    main()
