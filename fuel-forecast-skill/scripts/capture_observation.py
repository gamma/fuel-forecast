#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from common import (append_jsonl, data_dir, load_json, read_jsonl, save_json)
from capture_guard import assess_capture_time, assess_observation
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


def record_rejection(directory, captured_at, assessment, observation=None):
    rejection = {
        "version": 1,
        "status": "rejected",
        "date": captured_at.date().isoformat(),
        "attempted_at": captured_at.isoformat(),
        "target_time": assessment["policy"]["target_time"],
        "reasons": assessment["reasons"],
        "anchors": assessment.get("anchors", []),
        "attempted_observation": observation,
    }
    append_jsonl(directory / "capture_rejections.jsonl", rejection)
    request = {
        "version": 1,
        "status": "pending_verified_historical_lookup",
        "date": rejection["date"],
        "target_time": rejection["target_time"],
        "created_at": captured_at.isoformat(),
        "reasons": rejection["reasons"],
        "anchors": rejection["anchors"],
        "recovery_rules": [
            "Do not write a current live price after the capture window.",
            "Use only event-level historical prices with publication timestamps at or before the local target time, or an already stored local target-time snapshot.",
            "Do not promote tankzeit noon data or an untimestamped web value to 11:50 ground truth.",
            "Leave the observation missing when no verified target-time value exists.",
        ],
    }
    save_json(directory / "capture_recovery_request.json", request)
    save_json(directory / "capture_status.json", rejection)


def record_acceptance(directory, observation, assessment):
    status = {
        "version": 1,
        "status": "accepted",
        "date": observation["date"],
        "captured_at": observation["captured_at"],
        "cheap_reference": observation["metrics"]["cheap_reference"],
        "policy": assessment["policy"],
    }
    save_json(directory / "capture_status.json", status)
    recovery = load_json(directory / "capture_recovery_request.json", {}) or {}
    if recovery.get("date") == observation["date"] and str(
        recovery.get("status", "")
    ).startswith("pending"):
        recovery["status"] = "resolved_by_valid_capture"
        recovery["resolved_at"] = observation["captured_at"]
        save_json(directory / "capture_recovery_request.json", recovery)


def main():
    directory = data_dir()
    cfg = load_json(directory / "config.json")
    if not cfg:
        raise SystemExit(f"Missing {directory / 'config.json'}")
    if "PASTE_" in cfg.get("tankerkoenig_api_key", ""):
        raise SystemExit("Please set tankerkoenig_api_key in config.json")

    captured_at = datetime.now().astimezone()
    existing_rows = read_jsonl(directory / "observations.jsonl")
    morning_context = load_json(directory / "morning_context.json", {}) or {}
    time_assessment = assess_capture_time(
        cfg, captured_at, existing_rows, morning_context
    )
    if not time_assessment["accepted"]:
        record_rejection(directory, captured_at, time_assessment)
        reasons = ", ".join(
            reason["code"] for reason in time_assessment["reasons"]
        )
        raise SystemExit(f"Capture rejected without a live API call: {reasons}")

    stations = fetch_live(cfg)
    observation = build_observation(cfg, stations, captured_at)
    reference = observation["metrics"].get("cheap_reference")
    if reference is None:
        raise SystemExit("Tankerkönig returned no open stations with diesel prices.")

    assessment = assess_observation(
        cfg, observation, captured_at, existing_rows, morning_context
    )
    if not assessment["accepted"]:
        record_rejection(directory, captured_at, assessment, observation)
        reasons = ", ".join(reason["code"] for reason in assessment["reasons"])
        raise SystemExit(f"Capture rejected; observations unchanged: {reasons}")

    replace_daily_observation(directory / "observations.jsonl", observation)
    record_acceptance(directory, observation, assessment)
    print(
        f"FuelForecast {observation['date']}: {reference:.3f} €/l, "
        f"{observation['metrics']['count']} open stations"
    )


if __name__ == "__main__":
    main()
