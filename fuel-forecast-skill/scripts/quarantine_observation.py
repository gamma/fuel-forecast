#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from pathlib import Path

from common import append_jsonl, data_dir, load_json, read_jsonl, save_json


def write_jsonl(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(
                json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
            )
    temporary.replace(path)


def quarantine_observation(directory: Path, target_date: str, reason: str):
    path = directory / "observations.jsonl"
    rows = read_jsonl(path)
    quarantined = [row for row in rows if row.get("date") == target_date]
    if not quarantined:
        raise ValueError(f"No observation found for {target_date}")

    kept = [row for row in rows if row.get("date") != target_date]
    write_jsonl(path, kept)
    now = datetime.now().astimezone()
    context = load_json(directory / "morning_context.json", {}) or {}
    anchors = []
    if context.get("date") == target_date and context.get(
        "local", {}
    ).get("cheap_reference") is not None:
        anchors.append(
            {
                "source": "morning_context_recovery_candidate_only",
                "timestamp": context.get("generated_at"),
                "reference": context["local"]["cheap_reference"],
            }
        )

    audit = {
        "version": 1,
        "status": "quarantined_existing_observation",
        "date": target_date,
        "quarantined_at": now.isoformat(),
        "reason": reason,
        "quarantined_observations": quarantined,
        "anchors": anchors,
    }
    append_jsonl(directory / "capture_rejections.jsonl", audit)
    request = {
        "version": 1,
        "status": "pending_verified_historical_lookup",
        "date": target_date,
        "target_time": "11:50",
        "created_at": now.isoformat(),
        "reason": reason,
        "anchors": anchors,
        "recovery_rules": [
            "Use only a stored target-window snapshot or verified event-level historical data.",
            "Do not use a current post-noon price or tankzeit noon as 11:50 ground truth.",
            "Leave the observation missing when no verified target-time value exists.",
        ],
    }
    save_json(directory / "capture_recovery_request.json", request)
    save_json(directory / "capture_status.json", audit)
    return audit


def main():
    parser = argparse.ArgumentParser(
        description="Quarantine a known-bad observation without inventing a replacement."
    )
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--reason", required=True)
    args = parser.parse_args()
    directory = data_dir()
    audit = quarantine_observation(directory, args.date, args.reason)
    print(
        f"Quarantined {len(audit['quarantined_observations'])} observation(s) "
        f"for {args.date}; verified historical recovery is pending."
    )


if __name__ == "__main__":
    main()
