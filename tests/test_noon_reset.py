import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "fuel-forecast-skill" / "scripts"))

from noon_reset import (build_noon_shadow, estimate_next_pre_noon_offset,
                        evaluate_noon_shadows)
from run_forecast import local_trend_selection


def row(day, reference, capture_type):
    return {
        "date": day,
        "captured_at": f"{day}T12:20:00+02:00",
        "capture_type": capture_type,
        "metrics": {"cheap_reference": reference, "count": 20},
    }


def test_offset_pairs_do_not_require_same_day_pre_noon_capture():
    noon_rows = [row("2026-08-25", 1.80, "noon_reset")]
    observations = [row("2026-08-26", 1.74, "pre_noon")]

    model = estimate_next_pre_noon_offset(
        noon_rows, observations, before_date="2026-08-27"
    )

    assert model["samples"] == 1
    assert model["sample_median_ct"] == -6.0
    assert model["offset_ct"] == -4.25


def test_shadow_revision_is_separate_and_evaluable():
    observations = [row("2026-08-26", 1.74, "pre_noon")]
    historical_noon = [row("2026-08-25", 1.80, "noon_reset")]
    current = row("2026-08-26", 1.82, "noon_reset")
    current["pre_noon_reference"] = 1.74
    current["reset_jump_ct"] = 8.0
    forecast = {
        "date": "2026-08-26",
        "forecast": [{"date": "2026-08-27", "price": 1.75}],
    }

    shadow = build_noon_shadow(
        current, observations, historical_noon + [current], forecast
    )

    assert shadow["status"] == "shadow_only"
    assert shadow["production_effect"] == "none_until_validated"
    assert shadow["base_morning_price"] == 1.75
    assert shadow["shadow_correction_ct"] == 0.6

    target = row("2026-08-27", 1.77, "pre_noon")
    evaluations = evaluate_noon_shadows([shadow], observations + [target])
    assert evaluations[0]["base_error_ct"] == 2.0
    assert evaluations[0]["shadow_error_ct"] == 1.4


def test_noon_movement_is_fresh_fallback_without_becoming_truth():
    observations = {
        "2026-08-20": row("2026-08-20", 1.70, "pre_noon"),
        "2026-08-21": row("2026-08-21", 1.72, "pre_noon"),
    }
    noon = {
        "2026-08-25": row("2026-08-25", 1.80, "noon_reset"),
        "2026-08-26": row("2026-08-26", 1.77, "noon_reset"),
    }

    one, _, source = local_trend_selection(
        observations, "2026-08-27", noon_resets=noon
    )

    assert round(one, 1) == -3.0
    assert source == "noon_resets"


if __name__ == "__main__":
    test_offset_pairs_do_not_require_same_day_pre_noon_capture()
    test_shadow_revision_is_separate_and_evaluable()
    test_noon_movement_is_fresh_fallback_without_becoming_truth()
    print("OK")
