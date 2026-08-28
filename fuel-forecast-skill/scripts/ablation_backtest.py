#!/usr/bin/env python3
"""Compare local, market, FX, and asymmetric FuelForecast variants."""
from __future__ import annotations

import argparse
import math
from datetime import datetime

from backtest_model import evaluate_checkpoint
from calibrate_bootstrap_model import rows_by_date
from common import data_dir, read_jsonl, save_json


VARIANTS = (
    ("local_only", "Local price dynamics + weekday"),
    ("usd_market_symmetric", "Local + Brent/distillate in USD, symmetric"),
    ("eur_market_symmetric", "Local + Brent/distillate converted to EUR, symmetric"),
    ("eur_market_asymmetric", "Local + EUR market + rockets-and-feathers"),
)


def aggregate_metrics(checkpoints, field):
    metrics = [checkpoint[field] for checkpoint in checkpoints]
    total = sum(metric["predictions"] for metric in metrics)
    direction_total = sum(metric["direction_samples"] for metric in metrics)
    if not total:
        return {}
    mae = sum(metric["mae_ct"] * metric["predictions"] for metric in metrics) / total
    rmse = math.sqrt(
        sum(metric["rmse_ct"] ** 2 * metric["predictions"] for metric in metrics)
        / total
    )
    bias = sum(metric["bias_ct"] * metric["predictions"] for metric in metrics) / total
    direction_hits = sum(
        (metric["direction_accuracy"] or 0.0) * metric["direction_samples"]
        for metric in metrics
    )
    return {
        "predictions": total,
        "mae_ct": mae,
        "rmse_ct": rmse,
        "bias_ct": bias,
        "direction_accuracy": (
            direction_hits / direction_total if direction_total else None
        ),
        "direction_samples": direction_total,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoints", default="50,100,120,130,140")
    parser.add_argument("--evaluation-days", type=int, default=10)
    args = parser.parse_args()
    checkpoint_values = [
        int(value) for value in args.checkpoints.split(",") if value
    ]

    target_dir = data_dir()
    fuel = rows_by_date(
        read_jsonl(target_dir / "bootstrap_noon.jsonl"),
        ("metrics", "cheap_reference"),
    )
    market = rows_by_date(read_jsonl(target_dir / "bootstrap_market.jsonl"))
    if not fuel or not market:
        raise SystemExit("Run both historical bootstrap downloaders first.")

    variants = []
    for mode, label in VARIANTS:
        checkpoints = [
            evaluate_checkpoint(
                fuel,
                market,
                checkpoint,
                evaluation_days=args.evaluation_days,
                feature_mode=mode,
            )
            for checkpoint in checkpoint_values
        ]
        overall = aggregate_metrics(checkpoints, "overall")
        baseline = aggregate_metrics(checkpoints, "unchanged_price_baseline")
        overall["mae_gain_vs_unchanged_ct"] = baseline["mae_ct"] - overall["mae_ct"]
        variants.append({
            "mode": mode,
            "label": label,
            "overall": overall,
            "unchanged_price_baseline": baseline,
            "checkpoints": checkpoints,
        })
        print(
            f"{mode}: MAE {overall['mae_ct']:.2f} ct, "
            f"gain {overall['mae_gain_vs_unchanged_ct']:+.2f} ct, "
            f"direction {overall['direction_accuracy']:.0%}, "
            f"n={overall['predictions']}"
        )

    best = min(variants, key=lambda item: item["overall"]["mae_ct"])
    report = {
        "version": 1,
        "generated_at": datetime.now().astimezone().isoformat(),
        "target": "tankzeit noon day-to-day movement",
        "checkpoints": checkpoint_values,
        "evaluation_days": args.evaluation_days,
        "best_variant_by_mae": best["mode"],
        "news_feature": {
            "historical_value": 0.0,
            "tested": False,
            "reason": (
                "No point-in-time residual-news archive; retrospective scoring "
                "would risk hindsight and publication-time leakage."
            ),
        },
        "variants": variants,
    }
    output = target_dir / "ablation_report.json"
    save_json(output, report)
    print(f"Best by MAE: {best['mode']}")
    print(f"Saved {output}")


if __name__ == "__main__":
    main()
