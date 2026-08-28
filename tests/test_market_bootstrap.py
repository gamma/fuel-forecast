import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "fuel-forecast-skill" / "scripts"))

from download_market_history import (
    combine_cost_with_fx,
    dated_values,
    snapshot_before,
)
from market import converted_pct


def timestamp(day):
    return int(datetime.fromisoformat(day).replace(tzinfo=timezone.utc).timestamp())


def test_previous_date_alignment():
    rows = [
        ("2026-03-27", 80.0),
        ("2026-03-30", 82.0),
        ("2026-03-31", 84.0),
    ]
    # A same-day close must never enter that day's 11:50 fuel target.
    snap = snapshot_before(rows, "2026-03-31")
    assert snap["source_date"] == "2026-03-30"
    assert snap["latest"] == 82.0

    next_day = snapshot_before(rows, "2026-04-01")
    assert next_day["source_date"] == "2026-03-31"
    assert round(next_day["d1_pct"], 6) == round((84.0 / 82.0 - 1) * 100, 6)


def test_currency_conversion():
    costs = [("2026-03-30", 82.0), ("2026-03-31", 84.0)]
    fx = [("2026-03-27", 1.10), ("2026-03-31", 1.20)]
    converted = combine_cost_with_fx(costs, fx)
    assert converted == [
        ("2026-03-30", 82.0 / 1.10),
        ("2026-03-31", 84.0 / 1.20),
    ]
    assert round(converted_pct(10.0, 5.0), 8) == round((1.10 / 1.05 - 1) * 100, 8)


def test_timestamp_normalization():
    rows = dated_values([
        (timestamp("2026-03-30"), 82.0),
        (timestamp("2026-03-31"), 84.0),
    ])
    assert rows == [("2026-03-30", 82.0), ("2026-03-31", 84.0)]


if __name__ == "__main__":
    test_previous_date_alignment()
    test_currency_conversion()
    test_timestamp_normalization()
    print("OK")
