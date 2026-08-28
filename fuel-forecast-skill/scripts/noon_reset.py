#!/usr/bin/env python3
from __future__ import annotations

from common import add_days, clamp, median


DEFAULT_NEXT_PRE_NOON_OFFSET_CT = -4.0
MAX_PAIR_OFFSET_DOWN_CT = -30.0
MAX_PAIR_OFFSET_UP_CT = 10.0


def rows_by_date(rows):
    return {
        row["date"]: row
        for row in rows
        if row.get("date")
        and row.get("metrics", {}).get("cheap_reference") is not None
    }


def noon_to_next_pre_noon_pairs(noon_rows, observation_rows, before_date=None):
    """Build leakage-safe noon(D) -> pre-noon(D+1) calibration pairs."""
    resets = rows_by_date(noon_rows)
    observations = rows_by_date(observation_rows)
    pairs = []
    for issue_date in sorted(resets):
        if before_date and issue_date >= before_date:
            continue
        target_date = add_days(issue_date, 1)
        if target_date not in observations:
            continue
        noon_reference = float(
            resets[issue_date]["metrics"]["cheap_reference"]
        )
        target_reference = float(
            observations[target_date]["metrics"]["cheap_reference"]
        )
        offset_ct = (target_reference - noon_reference) * 100.0
        if not MAX_PAIR_OFFSET_DOWN_CT <= offset_ct <= MAX_PAIR_OFFSET_UP_CT:
            continue
        pairs.append(
            {
                "issue_date": issue_date,
                "target_date": target_date,
                "noon_reference": noon_reference,
                "actual_pre_noon_reference": target_reference,
                "offset_ct": round(offset_ct, 3),
            }
        )
    return pairs


def estimate_next_pre_noon_offset(noon_rows, observation_rows,
                                  before_date=None):
    pairs = noon_to_next_pre_noon_pairs(
        noon_rows, observation_rows, before_date=before_date
    )[-30:]
    sample_offsets = [pair["offset_ct"] for pair in pairs]
    sample_median = median(sample_offsets)
    learned_weight = min(1.0, len(sample_offsets) / 8.0)
    estimate = DEFAULT_NEXT_PRE_NOON_OFFSET_CT
    if sample_median is not None:
        estimate = (
            (1.0 - learned_weight) * DEFAULT_NEXT_PRE_NOON_OFFSET_CT
            + learned_weight * sample_median
        )
    errors = (
        [abs(value - estimate) for value in sample_offsets]
        if sample_offsets else []
    )
    return {
        "version": 1,
        "method": "prior_blended_rolling_median",
        "offset_ct": round(estimate, 2),
        "prior_offset_ct": DEFAULT_NEXT_PRE_NOON_OFFSET_CT,
        "samples": len(sample_offsets),
        "sample_median_ct": (
            round(sample_median, 2) if sample_median is not None else None
        ),
        "mae_ct": round(sum(errors) / len(errors), 2) if errors else None,
        "training_pairs": pairs,
    }


def build_noon_shadow(noon_observation, observation_rows, noon_rows,
                      forecast):
    issue_date = noon_observation["date"]
    target_date = add_days(issue_date, 1)
    model = estimate_next_pre_noon_offset(
        noon_rows, observation_rows, before_date=issue_date
    )
    noon_reference = float(
        noon_observation["metrics"]["cheap_reference"]
    )
    noon_projection = noon_reference + model["offset_ct"] / 100.0

    base = None
    if forecast and forecast.get("date") == issue_date:
        base = next(
            (
                row for row in forecast.get("forecast", [])
                if row.get("date") == target_date and row.get("price") is not None
            ),
            None,
        )

    base_price = float(base["price"]) if base else None
    weight = min(0.65, 0.15 + 0.05 * model["samples"])
    correction_ct = None
    shadow_price = noon_projection
    if base_price is not None:
        correction_ct = clamp(
            (noon_projection - base_price) * 100.0 * weight, -8.0, 8.0
        )
        shadow_price = base_price + correction_ct / 100.0

    return {
        "version": 1,
        "status": "shadow_only",
        "issue_date": issue_date,
        "target_date": target_date,
        "generated_at": noon_observation["captured_at"],
        "source_capture": "noon_reset",
        "noon_reference": round(noon_reference, 3),
        "pre_noon_reference": noon_observation.get("pre_noon_reference"),
        "reset_jump_ct": noon_observation.get("reset_jump_ct"),
        "base_morning_price": (
            round(base_price, 3) if base_price is not None else None
        ),
        "noon_projection_price": round(noon_projection, 3),
        "shadow_revised_price": round(shadow_price, 3),
        "shadow_correction_ct": (
            round(correction_ct, 1) if correction_ct is not None else None
        ),
        "shadow_weight": round(weight, 2),
        "model": {
            key: value for key, value in model.items()
            if key != "training_pairs"
        },
        "production_effect": "none_until_validated",
    }


def evaluate_noon_shadows(shadow_rows, observation_rows):
    observations = rows_by_date(observation_rows)
    evaluations = []
    for shadow in shadow_rows:
        target_date = shadow.get("target_date")
        actual_row = observations.get(target_date)
        revised = shadow.get("shadow_revised_price")
        if actual_row is None or revised is None:
            continue
        actual = float(actual_row["metrics"]["cheap_reference"])
        base = shadow.get("base_morning_price")
        projection = shadow.get("noon_projection_price")
        evaluations.append(
            {
                "version": 1,
                "issue_date": shadow.get("issue_date"),
                "target_date": target_date,
                "actual_pre_noon_reference": round(actual, 3),
                "base_error_ct": (
                    round(abs(actual - float(base)) * 100.0, 2)
                    if base is not None else None
                ),
                "noon_projection_error_ct": (
                    round(abs(actual - float(projection)) * 100.0, 2)
                    if projection is not None else None
                ),
                "shadow_error_ct": round(
                    abs(actual - float(revised)) * 100.0, 2
                ),
            }
        )
    return evaluations


def evaluation_summary(evaluations):
    if not evaluations:
        return {
            "samples": 0,
            "base_mae_ct": None,
            "shadow_mae_ct": None,
            "shadow_wins": 0,
        }
    base_errors = [
        row["base_error_ct"] for row in evaluations
        if row.get("base_error_ct") is not None
    ]
    shadow_errors = [row["shadow_error_ct"] for row in evaluations]
    wins = sum(
        1 for row in evaluations
        if row.get("base_error_ct") is not None
        and row["shadow_error_ct"] < row["base_error_ct"]
    )
    return {
        "samples": len(evaluations),
        "base_mae_ct": (
            round(sum(base_errors) / len(base_errors), 2)
            if base_errors else None
        ),
        "shadow_mae_ct": round(
            sum(shadow_errors) / len(shadow_errors), 2
        ),
        "shadow_wins": wins,
    }
