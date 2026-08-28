#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime


DEFAULT_WINDOW_START = "11:40"
DEFAULT_WINDOW_END = "12:00"
DEFAULT_TARGET_TIME = "11:50"
DEFAULT_NOON_RESET_WINDOW_START = "12:15"
DEFAULT_NOON_RESET_WINDOW_END = "12:31"
DEFAULT_NOON_RESET_TARGET_TIME = "12:20"
DEFAULT_MAX_UPWARD_JUMP_CT = 6.0
DEFAULT_MAX_DOWNWARD_JUMP_CT = 12.0
DEFAULT_MINIMUM_OPEN_STATIONS = 5
CAPTURE_TYPES = ("pre_noon", "noon_reset")


def clock_minutes(value):
    hour, minute = str(value).split(":", 1)
    return int(hour) * 60 + int(minute)


def capture_policy(cfg):
    capture = cfg.get("capture", {})
    region = cfg.get("region", {})
    return {
        "window_start": capture.get("window_start", DEFAULT_WINDOW_START),
        "window_end": capture.get("window_end", DEFAULT_WINDOW_END),
        "target_time": region.get(
            "target_time", capture.get("target_time", DEFAULT_TARGET_TIME)
        ),
        "max_upward_jump_ct": float(
            capture.get("max_upward_jump_ct", DEFAULT_MAX_UPWARD_JUMP_CT)
        ),
        "max_downward_jump_ct": float(
            capture.get("max_downward_jump_ct", DEFAULT_MAX_DOWNWARD_JUMP_CT)
        ),
        "minimum_open_stations": int(
            capture.get("minimum_open_stations", DEFAULT_MINIMUM_OPEN_STATIONS)
        ),
        "noon_reset_window_start": capture.get(
            "noon_reset_window_start", DEFAULT_NOON_RESET_WINDOW_START
        ),
        "noon_reset_window_end": capture.get(
            "noon_reset_window_end", DEFAULT_NOON_RESET_WINDOW_END
        ),
        "noon_reset_target_time": capture.get(
            "noon_reset_target_time", DEFAULT_NOON_RESET_TARGET_TIME
        ),
    }


def local_minutes(value):
    return value.hour * 60 + value.minute + value.second / 60.0


def parse_timestamp(value, timezone):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone)
    return parsed.astimezone(timezone)


def _reason(code, message, **details):
    result = {"code": code, "message": message}
    result.update(details)
    return result


def capture_window(policy, capture_type):
    if capture_type == "noon_reset":
        return {
            "window_start": policy["noon_reset_window_start"],
            "window_end": policy["noon_reset_window_end"],
            "target_time": policy["noon_reset_target_time"],
            "minimum_open_stations": policy["minimum_open_stations"],
        }
    return {
        "window_start": policy["window_start"],
        "window_end": policy["window_end"],
        "target_time": policy["target_time"],
        "max_upward_jump_ct": policy["max_upward_jump_ct"],
        "max_downward_jump_ct": policy["max_downward_jump_ct"],
        "minimum_open_stations": policy["minimum_open_stations"],
    }


def detect_capture_type(cfg, captured_at):
    policy = capture_policy(cfg)
    minute = local_minutes(captured_at)
    for capture_type in CAPTURE_TYPES:
        active = capture_window(policy, capture_type)
        if (
            clock_minutes(active["window_start"])
            <= minute
            < clock_minutes(active["window_end"])
        ):
            return capture_type
    return None


def assess_capture_time(cfg, captured_at, existing_rows=None,
                        morning_context=None, capture_type="pre_noon"):
    full_policy = capture_policy(cfg)
    requested_type = capture_type
    if capture_type == "auto":
        capture_type = detect_capture_type(cfg, captured_at)
    if capture_type not in CAPTURE_TYPES:
        policy = capture_window(full_policy, "pre_noon")
        reasons = [
            _reason(
                "outside_capture_windows",
                "Capture time is outside both configured learning windows.",
                local_time=captured_at.strftime("%H:%M:%S"),
                pre_noon_window=(
                    f"{full_policy['window_start']}–{full_policy['window_end']}"
                ),
                noon_reset_window=(
                    f"{full_policy['noon_reset_window_start']}–"
                    f"{full_policy['noon_reset_window_end']}"
                ),
            )
        ]
        return {
            "accepted": False,
            "capture_type": None,
            "requested_capture_type": requested_type,
            "captured_at": captured_at.isoformat(),
            "policy": policy,
            "anchors": [],
            "reasons": reasons,
        }

    policy = capture_window(full_policy, capture_type)
    minute = local_minutes(captured_at)
    start = clock_minutes(policy["window_start"])
    end = clock_minutes(policy["window_end"])
    reasons = []
    if minute < start or minute >= end:
        reasons.append(
            _reason(
                "outside_capture_window",
                f"Capture time must be within {policy['window_start']}–{policy['window_end']} local time.",
                local_time=captured_at.strftime("%H:%M:%S"),
            )
        )
    anchors = []
    if capture_type == "pre_noon" and (existing_rows or morning_context):
        anchors = same_day_anchors(
            existing_rows or [], morning_context, captured_at
        )
    return {
        "accepted": not reasons,
        "capture_type": capture_type,
        "requested_capture_type": requested_type,
        "captured_at": captured_at.isoformat(),
        "policy": policy,
        "anchors": [
            {key: value for key, value in anchor.items() if key != "minute"}
            for anchor in anchors
        ],
        "reasons": reasons,
    }


def same_day_anchors(existing_rows, morning_context, captured_at,
                     existing_source="existing_observation"):
    day = captured_at.date().isoformat()
    timezone = captured_at.tzinfo
    anchors = []

    for row in existing_rows:
        if row.get("date") != day:
            continue
        reference = row.get("metrics", {}).get("cheap_reference")
        timestamp = parse_timestamp(row.get("captured_at"), timezone)
        if reference is None or timestamp is None or timestamp > captured_at:
            continue
        anchors.append(
            {
                "source": existing_source,
                "timestamp": timestamp.isoformat(),
                "reference": float(reference),
                "minute": local_minutes(timestamp),
            }
        )

    if morning_context and morning_context.get("date") == day:
        reference = morning_context.get("local", {}).get("cheap_reference")
        timestamp = parse_timestamp(morning_context.get("generated_at"), timezone)
        if reference is not None and timestamp is not None and timestamp <= captured_at:
            anchors.append(
                {
                    "source": "morning_context",
                    "timestamp": timestamp.isoformat(),
                    "reference": float(reference),
                    "minute": local_minutes(timestamp),
                }
            )

    anchors.sort(key=lambda item: item["timestamp"])
    return anchors


def assess_observation(cfg, observation, captured_at, existing_rows=None,
                       morning_context=None, capture_type="pre_noon"):
    result = assess_capture_time(
        cfg, captured_at, capture_type=capture_type
    )
    policy = result["policy"]
    reasons = result["reasons"]
    metrics = observation.get("metrics", {})
    reference = metrics.get("cheap_reference")
    count = int(metrics.get("count") or 0)

    if reference is None or not 0.5 <= float(reference) <= 5.0:
        reasons.append(
            _reason(
                "invalid_reference",
                "Regional cheap reference is missing or outside the plausible range.",
                reference=reference,
            )
        )
    if count < policy["minimum_open_stations"]:
        reasons.append(
            _reason(
                "too_few_stations",
                "Too few open stations for a robust regional reference.",
                count=count,
                minimum=policy["minimum_open_stations"],
            )
        )

    anchors = same_day_anchors(
        existing_rows or [],
        morning_context if capture_type == "pre_noon" else None,
        captured_at,
        existing_source=(
            "existing_observation"
            if capture_type == "pre_noon"
            else "existing_noon_reset"
        ),
    )
    result["anchors"] = [
        {key: value for key, value in anchor.items() if key != "minute"}
        for anchor in anchors
    ]

    target = clock_minutes(policy["target_time"])
    current_distance = abs(local_minutes(captured_at) - target)
    start = clock_minutes(policy["window_start"])
    end = clock_minutes(policy["window_end"])
    for anchor in anchors:
        expected_source = (
            "existing_observation"
            if capture_type == "pre_noon"
            else "existing_noon_reset"
        )
        if anchor["source"] != expected_source:
            continue
        if start <= anchor["minute"] < end:
            anchor_distance = abs(anchor["minute"] - target)
            if anchor_distance < current_distance:
                reasons.append(
                    _reason(
                        "existing_capture_closer_to_target",
                        "A stored capture is already closer to the configured target time.",
                        existing_timestamp=anchor["timestamp"],
                    )
                )
                break

    if capture_type == "pre_noon" and reference is not None and anchors:
        latest = anchors[-1]
        delta_ct = (float(reference) - latest["reference"]) * 100.0
        result["anchor_delta_ct"] = round(delta_ct, 1)
        if delta_ct > policy["max_upward_jump_ct"]:
            reasons.append(
                _reason(
                    "implausible_upward_jump",
                    "Price rose too far above the latest same-day pre-noon anchor.",
                    delta_ct=round(delta_ct, 1),
                    maximum_ct=policy["max_upward_jump_ct"],
                    anchor_source=latest["source"],
                    anchor_timestamp=latest["timestamp"],
                )
            )
        elif delta_ct < -policy["max_downward_jump_ct"]:
            reasons.append(
                _reason(
                    "implausible_downward_jump",
                    "Price fell too far below the latest same-day pre-noon anchor.",
                    delta_ct=round(delta_ct, 1),
                    maximum_ct=policy["max_downward_jump_ct"],
                    anchor_source=latest["source"],
                    anchor_timestamp=latest["timestamp"],
                )
            )

    result["accepted"] = not reasons
    return result
