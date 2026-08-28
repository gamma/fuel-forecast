import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "fuel-forecast-skill" / "scripts"))

from calibrate_bootstrap_model import build_examples, fit_horizon, historical_features
from model import FEATURE_NAMES, is_compatible


def fuel_row(day, price):
    return {"date": day, "metrics": {"cheap_reference": price}}


def market_row(day, change):
    section = {"latest": 1.0, "d1_pct": change, "d5_pct": change}
    return {
        "date": day,
        "brent_usd_per_barrel": dict(section),
        "distillate_usd_per_gallon": dict(section),
        "brent_eur_per_barrel": dict(section),
        "distillate_eur_per_liter": dict(section),
        "eurusd_usd_per_eur": {"latest": 1.1, "d5_pct": 0.0},
    }


def test_bootstrap_calibration():
    # Synthetic daily data is enough to exercise temporal splitting and schema.
    from datetime import date, timedelta
    start = date(2026, 1, 1)
    fuel = {}
    market = {}
    price = 1.80
    for i in range(70):
        day = (start + timedelta(days=i)).isoformat()
        change = 2.0 if i % 7 < 3 else -1.0
        price += (0.002 if change > 0 else -0.0005)
        fuel[day] = fuel_row(day, price)
        market[day] = market_row(day, change)
    examples = build_examples(fuel, market, 1)
    calibrated = fit_horizon(1, examples)
    assert is_compatible(calibrated)
    assert calibrated["bootstrap_samples"] == len(examples)
    assert len(calibrated["weights"]) == len(FEATURE_NAMES)
    assert calibrated["bootstrap_validation_samples"] > 0


def test_ablation_feature_modes():
    fuel = {
        "2026-01-01": fuel_row("2026-01-01", 1.80),
        "2026-01-02": fuel_row("2026-01-02", 1.81),
    }
    market = {"2026-01-02": market_row("2026-01-02", -5.0)}
    positions = {name: i for i, name in enumerate(FEATURE_NAMES)}
    local = historical_features("2026-01-02", fuel, market, "local_only")
    symmetric = historical_features(
        "2026-01-02", fuel, market, "usd_market_symmetric"
    )
    asymmetric = historical_features(
        "2026-01-02", fuel, market, "eur_market_asymmetric"
    )
    up = positions["brent_eur_1d_up"]
    down = positions["brent_eur_1d_down"]
    assert local[up] == local[down] == 0.0
    assert symmetric[up] == -1.0 and symmetric[down] == 0.0
    assert asymmetric[up] == 0.0 and asymmetric[down] == -1.0


if __name__ == "__main__":
    test_bootstrap_calibration()
    test_ablation_feature_modes()
    print("OK")
