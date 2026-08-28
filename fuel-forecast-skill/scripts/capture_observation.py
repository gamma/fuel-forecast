#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from common import data_dir, load_json
from tankerkoenig import fetch_live, station_metrics


def build_observation(cfg, stations, captured_at):
    return {
        "version": 1,
        "date": captured_at.date().isoformat(),
        "captured_at": captured_at.isoformat(),
        "source": "Tankerkönig realtime API / MTS-K",
        "fuel": cfg.get("fuel", "diesel"),
        "metrics": station_metrics(
            stations, cfg["region"].get("preferred_places", [])
        ),
    }


def replace_daily_observation(path: Path, observation):
    rows = []
    if path.exists():
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if row.get("date") != observation["date"]:
                    rows.append(row)

    rows.append(observation)
    rows.sort(key=lambda row: row.get("date", ""))
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(
                json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
            )
    temporary.replace(path)


def main():
    directory = data_dir()
    cfg = load_json(directory / "config.json")
    if not cfg:
        raise SystemExit(f"Missing {directory / 'config.json'}")
    if "PASTE_" in cfg.get("tankerkoenig_api_key", ""):
        raise SystemExit("Please set tankerkoenig_api_key in config.json")

    captured_at = datetime.now().astimezone()
    stations = fetch_live(cfg)
    observation = build_observation(cfg, stations, captured_at)
    reference = observation["metrics"].get("cheap_reference")
    if reference is None:
        raise SystemExit("Tankerkönig returned no open stations with diesel prices.")

    replace_daily_observation(directory / "observations.jsonl", observation)
    print(
        f"FuelForecast {observation['date']}: {reference:.3f} €/l, "
        f"{observation['metrics']['count']} open stations"
    )


if __name__ == "__main__":
    main()
