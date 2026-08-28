import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "fuel-forecast-skill" / "scripts"))

from capture_guard import (assess_capture_time, assess_observation,
                           detect_capture_type)
from capture_observation import build_observation, replace_daily_observation
from quarantine_observation import quarantine_observation


def station(price, place="Oberkrämer", is_open=True):
    return {
        "id": str(price),
        "name": "Test",
        "place": place,
        "price": price,
        "isOpen": is_open,
    }


def test_capture_is_idempotent_per_day(tmp_path):
    cfg = {
        "fuel": "diesel",
        "region": {"preferred_places": ["Oberkrämer"]},
    }
    captured_at = datetime(2026, 8, 28, 11, 50, tzinfo=timezone.utc)
    first = build_observation(cfg, [station(1.70), station(1.72)], captured_at)
    updated = build_observation(cfg, [station(1.68), station(1.70)], captured_at)
    path = tmp_path / "observations.jsonl"

    replace_daily_observation(path, first)
    replace_daily_observation(path, updated)

    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert len(rows) == 1
    assert rows[0]["date"] == "2026-08-28"
    assert rows[0]["metrics"]["cheap_reference"] == 1.69


def test_capture_uses_five_cheapest_open_stations():
    cfg = {"fuel": "diesel", "region": {"preferred_places": []}}
    prices = [1.80, 1.70, 1.74, 1.72, 1.76, 1.78]
    observation = build_observation(
        cfg,
        [station(price) for price in prices] + [station(1.50, is_open=False)],
        datetime(2026, 8, 28, 11, 50, tzinfo=timezone.utc),
    )

    assert observation["metrics"]["count"] == 6
    assert observation["metrics"]["cheap_reference"] == 1.74


def guard_cfg():
    return {
        "fuel": "diesel",
        "region": {"target_time": "11:50", "preferred_places": []},
    }


def observation(reference=1.75, count=20):
    return {
        "date": "2026-08-28",
        "captured_at": "2026-08-28T11:50:00+00:00",
        "metrics": {"cheap_reference": reference, "count": count},
    }


def test_capture_rejects_outside_window_without_market_data():
    early = assess_capture_time(
        guard_cfg(), datetime(2026, 8, 28, 8, 53, tzinfo=timezone.utc)
    )
    late = assess_capture_time(
        guard_cfg(), datetime(2026, 8, 28, 12, 1, tzinfo=timezone.utc)
    )
    assert early["accepted"] is False
    assert late["accepted"] is False
    assert early["reasons"][0]["code"] == "outside_capture_window"


def test_auto_capture_selects_both_daily_windows():
    pre_noon = datetime(2026, 8, 28, 11, 50, tzinfo=timezone.utc)
    noon_reset = datetime(2026, 8, 28, 12, 20, tzinfo=timezone.utc)
    between = datetime(2026, 8, 28, 12, 5, tzinfo=timezone.utc)

    assert detect_capture_type(guard_cfg(), pre_noon) == "pre_noon"
    assert detect_capture_type(guard_cfg(), noon_reset) == "noon_reset"
    assert detect_capture_type(guard_cfg(), between) is None
    assert assess_capture_time(
        guard_cfg(), noon_reset, capture_type="auto"
    )["accepted"] is True


def test_capture_rejects_large_upward_jump_from_morning_anchor():
    captured_at = datetime(2026, 8, 28, 11, 50, tzinfo=timezone.utc)
    morning = {
        "date": "2026-08-28",
        "generated_at": "2026-08-28T10:06:00+00:00",
        "local": {"cheap_reference": 2.115},
    }
    result = assess_observation(
        guard_cfg(), observation(2.309), captured_at, [], morning
    )
    assert result["accepted"] is False
    assert result["anchor_delta_ct"] == 19.4
    assert "implausible_upward_jump" in [x["code"] for x in result["reasons"]]


def test_capture_accepts_small_change_in_window():
    captured_at = datetime(2026, 8, 28, 11, 50, tzinfo=timezone.utc)
    morning = {
        "date": "2026-08-28",
        "generated_at": "2026-08-28T10:06:00+00:00",
        "local": {"cheap_reference": 1.73},
    }
    result = assess_observation(
        guard_cfg(), observation(1.75), captured_at, [], morning
    )
    assert result["accepted"] is True


def test_noon_reset_accepts_regulatory_upward_jump():
    captured_at = datetime(2026, 8, 28, 12, 20, tzinfo=timezone.utc)
    result = assess_observation(
        guard_cfg(), observation(2.05), captured_at, [], {},
        capture_type="noon_reset",
    )
    assert result["accepted"] is True
    assert result["capture_type"] == "noon_reset"


def test_noon_reset_preserves_capture_closer_to_1220():
    captured_at = datetime(2026, 8, 28, 12, 27, tzinfo=timezone.utc)
    existing = [
        {
            "date": "2026-08-28",
            "captured_at": "2026-08-28T12:20:00+00:00",
            "metrics": {"cheap_reference": 2.05},
        }
    ]
    result = assess_observation(
        guard_cfg(), observation(2.04), captured_at, existing, {},
        capture_type="noon_reset",
    )
    assert result["accepted"] is False
    assert "existing_capture_closer_to_target" in [
        item["code"] for item in result["reasons"]
    ]


def test_capture_preserves_existing_value_closer_to_target():
    captured_at = datetime(2026, 8, 28, 11, 57, tzinfo=timezone.utc)
    existing = [
        {
            "date": "2026-08-28",
            "captured_at": "2026-08-28T11:50:00+00:00",
            "metrics": {"cheap_reference": 1.75},
        }
    ]
    result = assess_observation(
        guard_cfg(), observation(1.75), captured_at, existing, {}
    )
    assert result["accepted"] is False
    assert "existing_capture_closer_to_target" in [
        x["code"] for x in result["reasons"]
    ]


def test_quarantine_removes_bad_value_and_opens_recovery(tmp_path):
    bad = observation(2.309)
    replace_daily_observation(tmp_path / "observations.jsonl", bad)
    (tmp_path / "morning_context.json").write_text(
        json.dumps(
            {
                "date": "2026-08-28",
                "generated_at": "2026-08-28T10:06:00+00:00",
                "local": {"cheap_reference": 2.115},
            }
        )
    )

    audit = quarantine_observation(
        tmp_path, "2026-08-28", "post-noon capture"
    )

    assert audit["quarantined_observations"][0]["metrics"]["cheap_reference"] == 2.309
    assert (tmp_path / "observations.jsonl").read_text() == ""
    request = json.loads((tmp_path / "capture_recovery_request.json").read_text())
    assert request["status"] == "pending_verified_historical_lookup"
    assert request["anchors"][0]["reference"] == 2.115


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as directory:
        test_capture_is_idempotent_per_day(Path(directory))
    test_capture_uses_five_cheapest_open_stations()
    test_capture_rejects_outside_window_without_market_data()
    test_auto_capture_selects_both_daily_windows()
    test_capture_rejects_large_upward_jump_from_morning_anchor()
    test_capture_accepts_small_change_in_window()
    test_noon_reset_accepts_regulatory_upward_jump()
    test_noon_reset_preserves_capture_closer_to_1220()
    test_capture_preserves_existing_value_closer_to_target()
    with tempfile.TemporaryDirectory() as directory:
        test_quarantine_removes_bad_value_and_opens_recovery(Path(directory))
    print("OK")
