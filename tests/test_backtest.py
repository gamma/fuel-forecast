import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "fuel-forecast-skill" / "scripts"))

from backtest_model import evaluate_checkpoint, prediction_metrics


def synthetic_data(days=80):
    fuel = {}
    market = {}
    start = date(2026, 1, 1)
    price = 1.80
    for i in range(days):
        day = (start + timedelta(days=i)).isoformat()
        market_change = 2.0 if i % 6 < 3 else -1.0
        price += 0.003 if market_change > 0 else -0.001
        fuel[day] = {
            "date": day,
            "metrics": {"cheap_reference": price},
        }
        section = {"latest": 1.0, "d1_pct": market_change,
                   "d5_pct": market_change}
        market[day] = {
            "date": day,
            "brent_eur_per_barrel": dict(section),
            "distillate_eur_per_liter": dict(section),
            "eurusd_usd_per_eur": {"latest": 1.1, "d5_pct": 0.0},
        }
    return fuel, market


def test_checkpoint_has_no_training_lookahead():
    fuel, market = synthetic_data()
    result = evaluate_checkpoint(
        fuel, market, checkpoint=50, evaluation_days=10, horizons=(1, 2)
    )
    assert result["cutoff_date"] == sorted(fuel)[49]
    assert result["evaluation_issue_dates"][0] > result["cutoff_date"]
    for horizon in result["horizons"].values():
        assert horizon["training_last_target_date"] <= result["cutoff_date"]
        assert horizon["evaluation_first_issue_date"] > result["cutoff_date"]
        assert horizon["model"]["predictions"] > 0


def test_baseline_metrics():
    metrics = prediction_metrics([1.0, -3.0], [0.0, 0.0])
    assert metrics["mae_ct"] == 2.0
    assert metrics["bias_ct"] == -1.0


if __name__ == "__main__":
    test_checkpoint_has_no_training_lookahead()
    test_baseline_metrics()
    print("OK")
