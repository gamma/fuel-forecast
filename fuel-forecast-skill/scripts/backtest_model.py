#!/usr/bin/env python3
"""Expanding-window historical backtest for the FuelForecast model."""
from __future__ import annotations

import argparse
import math
from datetime import datetime

from calibrate_bootstrap_model import build_examples, fit_horizon, rows_by_date
from common import data_dir, read_jsonl, save_json
from model import predict


def prediction_metrics(actual, predicted):
    if not actual:
        return {
            "predictions": 0,
            "mae_ct": None,
            "rmse_ct": None,
            "bias_ct": None,
            "direction_accuracy": None,
            "direction_samples": 0,
        }
    errors = [target - estimate for target, estimate in zip(actual, predicted)]
    direction_samples = [
        (target, estimate) for target, estimate in zip(actual, predicted)
        if abs(target) >= 0.5
    ]
    direction_hits = sum(
        1 for target, estimate in direction_samples
        if (target > 0) == (estimate > 0)
    )
    return {
        "predictions": len(actual),
        "mae_ct": sum(abs(error) for error in errors) / len(errors),
        "rmse_ct": math.sqrt(sum(error * error for error in errors) / len(errors)),
        "bias_ct": sum(errors) / len(errors),
        "direction_accuracy": (
            direction_hits / len(direction_samples) if direction_samples else None
        ),
        "direction_samples": len(direction_samples),
    }


def evaluate_checkpoint(fuel, market, checkpoint, evaluation_days=10,
                        horizons=(1, 2, 3, 4),
                        feature_mode="eur_market_asymmetric"):
    available_dates = sorted(set(fuel) & set(market))
    if checkpoint < 30 or checkpoint >= len(available_dates):
        raise ValueError(
            f"Checkpoint {checkpoint} must be between 30 and "
            f"{len(available_dates)-1}"
        )
    cutoff = available_dates[checkpoint - 1]
    evaluation_issue_dates = available_dates[
        checkpoint:min(len(available_dates), checkpoint + evaluation_days)
    ]
    evaluation_set = set(evaluation_issue_dates)
    horizon_results = {}
    all_actual = []
    all_predicted = []
    all_baseline = []

    for horizon in horizons:
        all_examples = build_examples(fuel, market, horizon, mode=feature_mode)
        training = [e for e in all_examples if e["target_date"] <= cutoff]
        evaluation = [e for e in all_examples if e["issue_date"] in evaluation_set]
        calibrated = fit_horizon(
            horizon,
            training,
            enforce_asymmetry=(feature_mode == "eur_market_asymmetric"),
        )
        actual = [e["target"] for e in evaluation]
        predicted = [predict(calibrated, e["x"]) for e in evaluation]
        baseline = [0.0] * len(evaluation)
        model_metrics = prediction_metrics(actual, predicted)
        baseline_metrics = prediction_metrics(actual, baseline)
        model_metrics["mae_gain_vs_unchanged_ct"] = (
            baseline_metrics["mae_ct"] - model_metrics["mae_ct"]
            if model_metrics["mae_ct"] is not None else None
        )
        horizon_results[str(horizon)] = {
            "training_samples": len(training),
            "training_last_target_date": max(e["target_date"] for e in training),
            "evaluation_first_issue_date": (
                evaluation[0]["issue_date"] if evaluation else None
            ),
            "evaluation_last_issue_date": (
                evaluation[-1]["issue_date"] if evaluation else None
            ),
            "calibration_method": calibrated["calibration"]["method"],
            "model": model_metrics,
            "unchanged_price_baseline": baseline_metrics,
        }
        all_actual.extend(actual)
        all_predicted.extend(predicted)
        all_baseline.extend(baseline)

    overall = prediction_metrics(all_actual, all_predicted)
    overall_baseline = prediction_metrics(all_actual, all_baseline)
    overall["mae_gain_vs_unchanged_ct"] = (
        overall_baseline["mae_ct"] - overall["mae_ct"]
        if overall["mae_ct"] is not None else None
    )
    return {
        "checkpoint_days": checkpoint,
        "feature_mode": feature_mode,
        "cutoff_date": cutoff,
        "evaluation_issue_dates": evaluation_issue_dates,
        "evaluation_mode": "weights frozen at cutoff; prior-day local features continue",
        "overall": overall,
        "unchanged_price_baseline": overall_baseline,
        "horizons": horizon_results,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--checkpoints", default="50,100,120,130,140",
        help="comma-separated counts of historical fuel days",
    )
    parser.add_argument(
        "--evaluation-days", type=int, default=10,
        help="maximum future fuel issue dates tested per checkpoint",
    )
    args = parser.parse_args()
    checkpoints = [int(value) for value in args.checkpoints.split(",") if value]

    target_dir = data_dir()
    fuel = rows_by_date(
        read_jsonl(target_dir / "bootstrap_noon.jsonl"),
        ("metrics", "cheap_reference"),
    )
    market = rows_by_date(read_jsonl(target_dir / "bootstrap_market.jsonl"))
    if not fuel or not market:
        raise SystemExit("Run both historical bootstrap downloaders first.")

    results = []
    for checkpoint in checkpoints:
        result = evaluate_checkpoint(
            fuel, market, checkpoint, evaluation_days=args.evaluation_days
        )
        results.append(result)
        overall = result["overall"]
        print(
            f"day {checkpoint} ({result['cutoff_date']}): "
            f"MAE {overall['mae_ct']:.2f} ct vs "
            f"{result['unchanged_price_baseline']['mae_ct']:.2f} ct unchanged, "
            f"gain {overall['mae_gain_vs_unchanged_ct']:+.2f} ct, "
            f"n={overall['predictions']}"
        )

    report = {
        "version": 1,
        "generated_at": datetime.now().astimezone().isoformat(),
        "target": "tankzeit noon day-to-day movement",
        "limitations": [
            "not the absolute Scriptable 11:50 target",
            "does not backtest GPT residual-news scores",
            "does not backtest the live-morning to 11:50 intraday offset",
            "Heating Oil futures are a middle-distillate proxy",
        ],
        "available_fuel_dates": len(fuel),
        "available_market_dates": len(market),
        "evaluation_days": args.evaluation_days,
        "checkpoints": results,
    }
    output = target_dir / "backtest_report.json"
    save_json(output, report)
    print(f"Saved {output}")


if __name__ == "__main__":
    main()
