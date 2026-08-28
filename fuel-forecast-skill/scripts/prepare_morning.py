#!/usr/bin/env python3
from __future__ import annotations
from datetime import datetime
from pathlib import Path
import sys
from common import data_dir, load_json, save_json, append_jsonl
from tankerkoenig import fetch_live, station_metrics
from market import fetch_market

def main():
    d = data_dir()
    cfg = load_json(d / "config.json")
    if not cfg:
        raise SystemExit(f"Missing {d/'config.json'}")
    if "PASTE_" in cfg.get("tankerkoenig_api_key",""):
        raise SystemExit("Please set tankerkoenig_api_key in config.json")

    errors = []
    try:
        stations = fetch_live(cfg)
        local = station_metrics(stations, cfg["region"].get("preferred_places", []))
    except Exception as e:
        stations, local = [], {}
        errors.append("Tankerkönig: " + str(e))

    try:
        market = fetch_market(cfg)
        errors += market.get("errors", [])
    except Exception as e:
        market = {"needs_web_lookup": ["brent","distillate","eurusd"]}
        errors.append("Market: " + str(e))

    now = datetime.now().astimezone()
    ctx = {
        "version": 1,
        "date": now.date().isoformat(),
        "generated_at": now.isoformat(),
        "fuel": cfg.get("fuel","diesel"),
        "region": cfg["region"]["name"],
        "local": local,
        "market": market,
        "errors": errors,
        "instructions_for_gpt": {
            "lookback_hours": 48,
            "must_cross_check_market_direction": True,
            "write_file": str(d / "news_signal_draft.json"),
            "news_schema_version": 2,
            "require_exact_published_at": True,
        }
    }
    save_json(d / "morning_context.json", ctx)
    append_jsonl(d / "market_history.jsonl", {
        "date": ctx["date"], "generated_at": ctx["generated_at"], "market": market
    })
    print(str(d / "morning_context.json"))
    if errors:
        print("WARN:", " | ".join(errors), file=sys.stderr)

if __name__ == "__main__":
    main()
