import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "fuel-forecast-skill" / "scripts"))

from capture_observation import build_observation, replace_daily_observation


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


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as directory:
        test_capture_is_idempotent_per_day(Path(directory))
    test_capture_uses_five_cheapest_open_stations()
    print("OK")
