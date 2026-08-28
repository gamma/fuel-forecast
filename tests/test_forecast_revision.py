import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "fuel-forecast-skill" / "scripts"))

from run_forecast import attach_forecast_revisions, previous_forecasts_by_target


def test_uses_latest_older_forecast_for_same_target_date():
    history = [
        {
            "date": "2026-08-25",
            "forecast": [{"date": "2026-08-29", "price": 1.700}],
        },
        {
            "date": "2026-08-26",
            "forecast": [{"date": "2026-08-29", "price": 1.720}],
        },
    ]

    previous = previous_forecasts_by_target(history, "2026-08-27")

    assert previous["2026-08-29"] == {
        "issue_date": "2026-08-26",
        "price": 1.720,
    }


def test_attaches_compact_revision_and_marks_new_dates():
    history = [
        {
            "date": "2026-08-27",
            "forecast": [{"date": "2026-08-29", "price": 1.720}],
        }
    ]
    forecasts = [
        {"date": "2026-08-29", "price": 1.735},
        {"date": "2026-09-01", "price": 1.710},
    ]

    attach_forecast_revisions(forecasts, history, "2026-08-28")

    assert forecasts[0]["revision_ct"] == 1.5
    assert forecasts[0]["revision_from_date"] == "2026-08-27"
    assert forecasts[1]["revision_ct"] is None
    assert forecasts[1]["revision_from_date"] is None


if __name__ == "__main__":
    test_uses_latest_older_forecast_for_same_target_date()
    test_attaches_compact_revision_and_marks_new_dates()
    print("OK")
