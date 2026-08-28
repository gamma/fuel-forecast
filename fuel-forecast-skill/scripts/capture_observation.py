#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from common import (append_jsonl, data_dir, load_json, read_jsonl,
                    replace_jsonl_row, save_json)
from capture_guard import assess_capture_time, assess_observation
from noon_reset import build_noon_shadow
from tankerkoenig import fetch_live, station_metrics


def build_observation(cfg, stations, captured_at, capture_type="pre_noon",
                      pre_noon_reference=None):
    observation = {
        "version": 1,
        "capture_type": capture_type,
        "date": captured_at.date().isoformat(),
        "captured_at": captured_at.isoformat(),
        "source": "Tankerkönig realtime API / MTS-K",
        "fuel": cfg.get("fuel", "diesel"),
        "metrics": station_metrics(
            stations, cfg["region"].get("preferred_places", [])
        ),
    }
    if capture_type == "noon_reset":
        reference = observation["metrics"].get("cheap_reference")
        observation.update(
            {
                "target_time": cfg.get("capture", {}).get(
                    "noon_reset_target_time", "12:20"
                ),
                "target_semantics": (
                    "post-12 reset proxy; later price reductions remain possible"
                ),
                "pre_noon_reference": pre_noon_reference,
                "reset_jump_ct": (
                    round((float(reference) - pre_noon_reference) * 100.0, 1)
                    if reference is not None and pre_noon_reference is not None
                    else None
                ),
            }
        )
    return observation


def replace_daily_observation(path: Path, observation):
    replace_jsonl_row(path, observation)


def record_rejection(directory, captured_at, assessment, observation=None):
    capture_type = assessment.get("capture_type")
    rejection = {
        "version": 1,
        "status": "rejected",
        "capture_type": capture_type,
        "date": captured_at.date().isoformat(),
        "attempted_at": captured_at.isoformat(),
        "target_time": assessment["policy"]["target_time"],
        "reasons": assessment["reasons"],
        "anchors": assessment.get("anchors", []),
        "attempted_observation": observation,
    }
    append_jsonl(directory / "capture_rejections.jsonl", rejection)
    if capture_type != "pre_noon":
        save_json(directory / "noon_reset_status.json", rejection)
        return
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
        "capture_type": observation["capture_type"],
        "date": observation["date"],
        "captured_at": observation["captured_at"],
        "cheap_reference": observation["metrics"]["cheap_reference"],
        "policy": assessment["policy"],
    }
    if observation["capture_type"] == "noon_reset":
        status["reset_jump_ct"] = observation.get("reset_jump_ct")
        save_json(directory / "noon_reset_status.json", status)
        return
    save_json(directory / "capture_status.json", status)
    recovery = load_json(directory / "capture_recovery_request.json", {}) or {}
    if recovery.get("date") == observation["date"] and str(
        recovery.get("status", "")
    ).startswith("pending"):
        recovery["status"] = "resolved_by_valid_capture"
        recovery["resolved_at"] = observation["captured_at"]
        save_json(directory / "capture_recovery_request.json", recovery)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Capture the pre-noon target or the post-12 reset."
    )
    parser.add_argument(
        "--mode",
        choices=("auto", "pre_noon", "noon_reset"),
        default="auto",
        help="auto selects the configured window from local time",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    directory = data_dir()
    cfg = load_json(directory / "config.json")
    if not cfg:
        raise SystemExit(f"Missing {directory / 'config.json'}")
    if "PASTE_" in cfg.get("tankerkoenig_api_key", ""):
        raise SystemExit("Please set tankerkoenig_api_key in config.json")

    timezone_name = cfg.get("region", {}).get("timezone", "Europe/Berlin")
    captured_at = datetime.now(ZoneInfo(timezone_name))
    existing_rows = read_jsonl(directory / "observations.jsonl")
    noon_rows = read_jsonl(directory / "noon_resets.jsonl")
    morning_context = load_json(directory / "morning_context.json", {}) or {}
    time_assessment = assess_capture_time(
        cfg, captured_at, existing_rows, morning_context,
        capture_type=args.mode,
    )
    if not time_assessment["accepted"]:
        record_rejection(directory, captured_at, time_assessment)
        reasons = ", ".join(
            reason["code"] for reason in time_assessment["reasons"]
        )
        raise SystemExit(f"Capture rejected without a live API call: {reasons}")

    capture_type = time_assessment["capture_type"]
    stations = fetch_live(cfg)
    pre_noon = next(
        (
            row for row in existing_rows
            if row.get("date") == captured_at.date().isoformat()
            and row.get("metrics", {}).get("cheap_reference") is not None
        ),
        None,
    )
    pre_noon_reference = (
        float(pre_noon["metrics"]["cheap_reference"])
        if pre_noon else None
    )
    observation = build_observation(
        cfg, stations, captured_at, capture_type=capture_type,
        pre_noon_reference=pre_noon_reference,
    )
    reference = observation["metrics"].get("cheap_reference")
    if reference is None:
        raise SystemExit("Tankerkönig returned no open stations with diesel prices.")

    assessment = assess_observation(
        cfg, observation, captured_at,
        existing_rows if capture_type == "pre_noon" else noon_rows,
        morning_context,
        capture_type=capture_type,
    )
    if not assessment["accepted"]:
        record_rejection(directory, captured_at, assessment, observation)
        reasons = ", ".join(reason["code"] for reason in assessment["reasons"])
        raise SystemExit(f"Capture rejected; observations unchanged: {reasons}")

    target_path = (
        directory / "observations.jsonl"
        if capture_type == "pre_noon"
        else directory / "noon_resets.jsonl"
    )
    replace_daily_observation(target_path, observation)
    record_acceptance(directory, observation, assessment)
    shadow = None
    if capture_type == "noon_reset":
        noon_rows = read_jsonl(directory / "noon_resets.jsonl")
        forecast = load_json(directory / "forecast.json", {}) or {}
        shadow = build_noon_shadow(
            observation, existing_rows, noon_rows, forecast
        )
        save_json(directory / "noon_shadow_forecast.json", shadow)
        replace_jsonl_row(
            directory / "noon_shadow_history.jsonl", shadow,
            key="issue_date",
        )
    print(
        f"FuelForecast {observation['date']} {capture_type}: "
        f"{reference:.3f} €/l, "
        f"{observation['metrics']['count']} open stations"
    )
    if shadow:
        correction = shadow.get("shadow_correction_ct")
        correction_text = (
            f"{correction:+.1f} ct"
            if correction is not None else "no same-day base forecast"
        )
        print(
            f"Shadow D+1 {shadow['target_date']}: "
            f"{shadow['shadow_revised_price']:.3f} €/l "
            f"({correction_text}, no production effect)"
        )


if __name__ == "__main__":
    main()
